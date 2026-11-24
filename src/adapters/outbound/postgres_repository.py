"""Adaptador PostgreSQL de `IncidentRepositoryPort` (ADR-004; Constitución 2.6, 3.3 y T3; spec 004).

- Solo `psycopg[binary]`, sin ORM ni capa de abstracción SQL. Todas las sentencias son
  constantes con marcadores `%s`; nunca se concatena SQL.
- Esquema espejo del de SQLite: mismas columnas, `TEXT COLLATE "C"` en todo texto (orden
  por bytes, equivalente a `BINARY` en SQLite) e instantes ISO 8601 como texto con el
  formato de `row_mapping.py`. Ninguna regla temporal ni de SLA se calcula en SQL.
- Índices parciales idénticos a los de SQLite: `idx_incidents_active_component` (ADR-001
  con el predicado de ADR-005) e `idx_incidents_dup_key` (spec 003).
- Conexión principal perezosa (el constructor no abre red, research §R1), en `autocommit`,
  con `dict_row` y límites de 2 s, protegida por un candado. Se descarta ante un fallo de
  conexión y la siguiente operación vuelve a conectar.
- Inicialización única por proceso en una transacción con candado consultivo: DDL,
  *upsert* de `sla_policies` y siembra «si está vacía» (research §R4–R5).
- `check_health()` sondea por una conexión efímera acotada (research §R2) y nunca lanza.
- Ningún tipo ni mensaje de `psycopg` sale del adaptador (Constitución 3.3, contrato C11):
  la URL nunca aparece en mensajes ni registros.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence

import psycopg
from psycopg import errors
from psycopg.rows import dict_row

from src.adapters.outbound.row_mapping import (
    INCIDENT_COLUMNS,
    active_incident,
    full_incident,
    incident_params,
)
from src.application.ports import IncidentIdConflictError, StoreUnavailableError
from src.domain.models import Incident
from src.domain.sla_calculator import SLA_POLICY_TABLE, get_sla_rule_for_severity

# Límites de red y de consulta (research §R1–R2, RNF-002): una base caída o una red colgada
# no bloquean más de unos segundos ni la sonda ni una operación de negocio.
_CONNECT_OPTIONS: Dict[str, Any] = {
    "connect_timeout": 2,
    "tcp_user_timeout": 2000,
    "options": "-c statement_timeout=2000",
}

# Clave entera constante del candado consultivo de inicialización (research §R4).
_INIT_LOCK_KEY = 4_004_2026

_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS sla_policies (
        severity TEXT COLLATE "C" PRIMARY KEY,
        max_resolution_minutes INTEGER NOT NULL,
        operates_24x7 INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS incidents (
        incident_id TEXT COLLATE "C" NOT NULL,
        title TEXT COLLATE "C" NOT NULL,
        component TEXT COLLATE "C" NOT NULL,
        severity TEXT COLLATE "C" NOT NULL REFERENCES sla_policies (severity),
        status TEXT COLLATE "C" NOT NULL,
        created_at TEXT COLLATE "C" NOT NULL,
        resolved_at TEXT COLLATE "C",
        recommended_team TEXT COLLATE "C",
        duplicate_group_key TEXT COLLATE "C",
        CONSTRAINT incidents_pkey PRIMARY KEY (incident_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_incidents_active_component
    ON incidents (component, status, severity, created_at, incident_id, title)
    WHERE status <> 'RESOLVED'
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_incidents_dup_key
    ON incidents (duplicate_group_key, status)
    WHERE status <> 'RESOLVED' AND duplicate_group_key IS NOT NULL
    """,
)

_INIT_LOCK_SQL = "SELECT pg_advisory_xact_lock(%s)"

_UPSERT_POLICY_SQL = """
    INSERT INTO sla_policies (severity, max_resolution_minutes, operates_24x7)
    VALUES (%s, %s, %s)
    ON CONFLICT (severity) DO UPDATE SET
        max_resolution_minutes = EXCLUDED.max_resolution_minutes,
        operates_24x7 = EXCLUDED.operates_24x7
"""

_HAS_INCIDENTS_SQL = "SELECT EXISTS (SELECT 1 FROM incidents) AS has_incidents"

_UPSERT_INCIDENT_SQL = """
    INSERT INTO incidents (
        incident_id, title, component, severity, status, created_at, resolved_at,
        recommended_team, duplicate_group_key
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (incident_id) DO UPDATE SET
        title = EXCLUDED.title,
        component = EXCLUDED.component,
        severity = EXCLUDED.severity,
        status = EXCLUDED.status,
        created_at = EXCLUDED.created_at,
        resolved_at = EXCLUDED.resolved_at,
        recommended_team = EXCLUDED.recommended_team,
        duplicate_group_key = EXCLUDED.duplicate_group_key
"""

# Sin ON CONFLICT: la clave primaria `incidents_pkey` resuelve el conflicto de forma atómica.
_INSERT_INCIDENT_SQL = """
    INSERT INTO incidents (
        incident_id, title, component, severity, status, created_at, resolved_at,
        recommended_team, duplicate_group_key
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# Siembra idempotente aun sin el candado consultivo (caso borde de la spec).
_SEED_INCIDENT_SQL = """
    INSERT INTO incidents (
        incident_id, title, component, severity, status, created_at, resolved_at,
        recommended_team, duplicate_group_key
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (incident_id) DO NOTHING
"""

_SELECT_BY_ID_SQL = """
    SELECT incident_id, title, component, severity, status, created_at, resolved_at,
           recommended_team, duplicate_group_key
    FROM incidents
    WHERE incident_id = %s
"""

# Mismas consultas que en SQLite: predicado literal del índice parcial e INNER JOIN.
SELECT_ACTIVE_SQL = """
    SELECT i.incident_id, i.title, i.component, i.severity, i.status, i.created_at
    FROM incidents AS i
    INNER JOIN sla_policies AS p ON p.severity = i.severity
    WHERE i.status <> 'RESOLVED'
"""

SELECT_ACTIVE_BY_COMPONENT_SQL = """
    SELECT i.incident_id, i.title, i.component, i.severity, i.status, i.created_at
    FROM incidents AS i
    INNER JOIN sla_policies AS p ON p.severity = i.severity
    WHERE i.status <> 'RESOLVED' AND i.component = %s
"""

SELECT_OPEN_DUPLICATES_SQL = """
    SELECT i.incident_id, i.title, i.component, i.severity, i.status, i.created_at, i.resolved_at,
           i.recommended_team, i.duplicate_group_key
    FROM incidents AS i
    INNER JOIN sla_policies AS p ON p.severity = i.severity
    WHERE i.status <> 'RESOLVED' AND i.duplicate_group_key IS NOT NULL
      AND i.duplicate_group_key = %s AND i.incident_id <> %s
    ORDER BY i.created_at, i.incident_id
"""

_VACUUM_SQL = "VACUUM ANALYZE incidents"

_ACTIVE_COLUMNS = INCIDENT_COLUMNS[:6]
_INTEGRITY_MESSAGE = "El incidente viola la integridad del almacén."
_REJECTED_MESSAGE = "El almacén de incidentes rechazó la operación."


def _active_from_row(row: Dict[str, Any]) -> Incident:
    return active_incident(*(row[column] for column in _ACTIVE_COLUMNS))


def _full_from_row(row: Dict[str, Any]) -> Incident:
    return full_incident(*(row[column] for column in INCIDENT_COLUMNS))


class PostgresIncidentRepository:
    """Implementación de `IncidentRepositoryPort` sobre `psycopg` (ADR-004)."""

    def __init__(self, database_url: str, *, seed_if_empty: Sequence[Incident] = ()) -> None:
        # Perezoso: no abre red; la URL ya llega validada por la fábrica (research §R7).
        self._url = database_url
        self._seed = tuple(seed_if_empty)
        self._lock = threading.Lock()
        self._connection: Optional[psycopg.Connection] = None
        self._initialized = False

    def __repr__(self) -> str:
        # Nunca se muestra la URL: lleva credenciales (Constitución 3.5).
        return "PostgresIncidentRepository(<postgresql>)"

    # -- Conexión -------------------------------------------------------------

    def _connect(self, **extra: Any) -> psycopg.Connection:
        return psycopg.connect(self._url, autocommit=True, **_CONNECT_OPTIONS, **extra)

    def _main_connection(self) -> psycopg.Connection:
        """Conexión principal; se abre en la primera operación (llamar con el candado)."""
        if self._connection is None or self._connection.closed or self._connection.broken:
            self._discard()
            self._connection = self._connect(row_factory=dict_row)
        return self._connection

    def _discard(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 — cerrar una conexión rota no debe enmascarar el fallo.
                pass

    @contextmanager
    def _session(self) -> Iterator[psycopg.Connection]:
        """Conexión principal inicializada, bajo el candado y con errores traducidos.

        `OperationalError`, `InterfaceError` o una conexión rota descartan la conexión y se
        convierten en `StoreUnavailableError` sin causa encadenada; cualquier otro error del
        driver se convierte en `RuntimeError` genérico. Ningún tipo de `psycopg` sale del
        adaptador (Constitución 3.3, research §R6).
        """
        with self._lock:
            try:
                connection = self._main_connection()
                if not self._initialized:
                    self._initialize(connection)
                yield connection
            except (psycopg.OperationalError, psycopg.InterfaceError):
                self._discard()
                raise StoreUnavailableError() from None
            except psycopg.Error:
                if self._connection is not None and self._connection.broken:
                    self._discard()
                    raise StoreUnavailableError() from None
                raise RuntimeError(_REJECTED_MESSAGE) from None

    def _initialize(self, connection: psycopg.Connection) -> None:
        """Esquema, políticas y siembra en una transacción serializada entre procesos."""
        with connection.transaction():
            connection.execute(_INIT_LOCK_SQL, (_INIT_LOCK_KEY,))
            for statement in _SCHEMA_SQL:
                connection.execute(statement)
            with connection.cursor() as cursor:
                cursor.executemany(
                    _UPSERT_POLICY_SQL,
                    [
                        (rule.severity, rule.max_resolution_minutes, 1 if rule.operates_24x7 else 0)
                        for rule in SLA_POLICY_TABLE.values()
                    ],
                )
                if self._seed and not connection.execute(_HAS_INCIDENTS_SQL).fetchone()["has_incidents"]:
                    cursor.executemany(_SEED_INCIDENT_SQL, [incident_params(incident) for incident in self._seed])
        self._initialized = True

    # -- Fuera del puerto -----------------------------------------------------

    def close(self) -> None:
        """Cierra la conexión principal (fuera del puerto, como en SQLite)."""
        with self._lock:
            self._discard()

    def vacuum_analyze(self) -> None:
        """`VACUUM ANALYZE incidents` (fuera del puerto): estadísticas y mapa de visibilidad
        al día antes de medir (research §R13)."""
        with self._session() as connection:
            connection.execute(_VACUUM_SQL)

    # -- Puerto ---------------------------------------------------------------

    def save_incident(self, incident: Incident) -> None:
        get_sla_rule_for_severity(incident.severity)  # ValueError si la severidad no tiene política.
        with self._session() as connection:
            try:
                connection.execute(_UPSERT_INCIDENT_SQL, incident_params(incident))
            except psycopg.IntegrityError:
                raise ValueError(_INTEGRITY_MESSAGE) from None

    def add_incident(self, incident: Incident) -> None:
        get_sla_rule_for_severity(incident.severity)  # ValueError si la severidad no tiene política.
        with self._session() as connection:
            try:
                connection.execute(_INSERT_INCIDENT_SQL, incident_params(incident))
            except errors.UniqueViolation as exc:
                if exc.diag.constraint_name == "incidents_pkey":
                    raise IncidentIdConflictError(incident.incident_id) from None
                raise ValueError(_INTEGRITY_MESSAGE) from None
            except psycopg.IntegrityError:
                raise ValueError(_INTEGRITY_MESSAGE) from None

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        with self._session() as connection:
            row = connection.execute(_SELECT_BY_ID_SQL, (incident_id,)).fetchone()
        return _full_from_row(row) if row is not None else None

    def find_open_duplicates(self, duplicate_group_key: str, exclude_incident_id: str) -> Sequence[Incident]:
        with self._session() as connection:
            rows = connection.execute(SELECT_OPEN_DUPLICATES_SQL, (duplicate_group_key, exclude_incident_id)).fetchall()
        return [_full_from_row(row) for row in rows]

    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]:
        if component is None:
            return self._read_active(SELECT_ACTIVE_SQL, ())
        return self._read_active(SELECT_ACTIVE_BY_COMPONENT_SQL, (component,))

    def check_health(self) -> bool:
        """Sonda acotada en el tiempo por una conexión efímera; nunca lanza (research §R2).

        `True` solo si `SELECT 1` responde y el almacén está inicializado: «sano» significa
        «listo para atender» (E17).
        """
        try:
            with self._connect() as probe:
                if probe.execute("SELECT 1").fetchone() != (1,):
                    return False
            if not self._initialized:
                with self._session():
                    pass
            return True
        except Exception:  # noqa: BLE001 — contrato del puerto: la sonda nunca lanza.
            return False

    def _read_active(self, sql: str, params: tuple) -> List[Incident]:
        # Streaming (ADR-001, Constitución 2.6): el servidor envía las filas de una en una y
        # se mapean sin `fetchall()`. Se recorre dentro del candado y se devuelve una lista
        # ya construida, igual que en SQLite.
        with self._session() as connection:
            with connection.cursor() as cursor:
                return [_active_from_row(row) for row in cursor.stream(sql, params)]
