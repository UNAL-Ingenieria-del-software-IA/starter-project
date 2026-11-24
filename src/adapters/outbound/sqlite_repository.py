"""Adaptador SQLite de `IncidentRepositoryPort` (Constitución Art. 2.6, T3; ADR-001, ADR-005, ADR-006; spec 003).

- Solo `sqlite3` de la librería estándar, con marcadores `?` y sentencias constantes.
- Índice compuesto, parcial y cubriente `idx_incidents_active_component`, que empieza por
  `(component, status)` y usa el predicado de ADR-005 (`status <> 'RESOLVED'`). Las
  consultas repiten ese predicado literal para que SQLite pueda usar el índice parcial.
- Índice parcial `idx_incidents_dup_key` sobre `(duplicate_group_key, status)` para la
  búsqueda de duplicados abiertos de spec 003 (research §R8).
- `sla_policies` es un espejo de `SLA_POLICY_TABLE` y destino de la clave foránea de
  `incidents.severity`; el `INNER JOIN` garantiza que toda fila leída tenga política
  evaluable, pero ninguna columna de la tabla se usa para calcular (Art. 1.1).
- Una sola conexión (`check_same_thread=False`) protegida por un candado: con
  `:memory:` cada conexión es una base distinta y FastAPI atiende en un pool de hilos.
- Los archivos creados por H002 se migran al abrir: se añaden las columnas que falten
  (`ALTER TABLE … ADD COLUMN`), sin tocar las filas existentes.
- El DDL y el mapeo fila ↔ entidad viven solo aquí.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from typing import List, Optional, Sequence

from src.application.ports import IncidentIdConflictError
from src.domain.models import Incident
from src.domain.sla_calculator import SLA_POLICY_TABLE, get_sla_rule_for_severity
from src.domain.working_time_calculator import to_bogota

_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS sla_policies (
        severity TEXT PRIMARY KEY,
        max_resolution_minutes INTEGER NOT NULL,
        operates_24x7 INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS incidents (
        incident_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        component TEXT NOT NULL,
        severity TEXT NOT NULL REFERENCES sla_policies (severity),
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        recommended_team TEXT,
        duplicate_group_key TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_incidents_active_component
    ON incidents (component, status, severity, created_at, incident_id, title)
    WHERE status <> 'RESOLVED'
    """,
)

# Migración aditiva de archivos de H002: columna → sentencia constante (sin concatenar SQL).
_ADDITIVE_COLUMNS = (
    ("recommended_team", "ALTER TABLE incidents ADD COLUMN recommended_team TEXT"),
    ("duplicate_group_key", "ALTER TABLE incidents ADD COLUMN duplicate_group_key TEXT"),
)

# Se crea después de la migración: en un archivo de H002 la columna aún no existe.
_DUP_KEY_INDEX_SQL = """
    CREATE INDEX IF NOT EXISTS idx_incidents_dup_key
    ON incidents (duplicate_group_key, status)
    WHERE status <> 'RESOLVED' AND duplicate_group_key IS NOT NULL
"""

_UPSERT_POLICY_SQL = """
    INSERT INTO sla_policies (severity, max_resolution_minutes, operates_24x7)
    VALUES (?, ?, ?)
    ON CONFLICT (severity) DO UPDATE SET
        max_resolution_minutes = excluded.max_resolution_minutes,
        operates_24x7 = excluded.operates_24x7
"""

_UPSERT_INCIDENT_SQL = """
    INSERT INTO incidents (
        incident_id, title, component, severity, status, created_at, resolved_at,
        recommended_team, duplicate_group_key
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (incident_id) DO UPDATE SET
        title = excluded.title,
        component = excluded.component,
        severity = excluded.severity,
        status = excluded.status,
        created_at = excluded.created_at,
        resolved_at = excluded.resolved_at,
        recommended_team = excluded.recommended_team,
        duplicate_group_key = excluded.duplicate_group_key
"""

# Sin ON CONFLICT: la clave primaria resuelve el conflicto en un único INSERT atómico.
_INSERT_INCIDENT_SQL = """
    INSERT INTO incidents (
        incident_id, title, component, severity, status, created_at, resolved_at,
        recommended_team, duplicate_group_key
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_EXISTS_SQL = "SELECT 1 FROM incidents WHERE incident_id = ?"

_SELECT_BY_ID_SQL = """
    SELECT incident_id, title, component, severity, status, created_at, resolved_at,
           recommended_team, duplicate_group_key
    FROM incidents
    WHERE incident_id = ?
"""

# Las dos variantes de la consulta de activos son sentencias constantes (sin concatenar SQL).
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
    WHERE i.status <> 'RESOLVED' AND i.component = ?
"""

SELECT_OPEN_DUPLICATES_SQL = """
    SELECT i.incident_id, i.title, i.component, i.severity, i.status, i.created_at, i.resolved_at,
           i.recommended_team, i.duplicate_group_key
    FROM incidents AS i
    INNER JOIN sla_policies AS p ON p.severity = i.severity
    WHERE i.status <> 'RESOLVED' AND i.duplicate_group_key IS NOT NULL
      AND i.duplicate_group_key = ? AND i.incident_id <> ?
    ORDER BY i.created_at, i.incident_id
"""


def _to_text(value: datetime) -> str:
    """Instante en Bogotá con ancho fijo: la comparación de texto equivale a la temporal."""
    return to_bogota(value).isoformat(timespec="microseconds")


def _params(incident: Incident) -> tuple:
    return (
        incident.incident_id,
        incident.title,
        incident.component,
        incident.severity,
        incident.status,
        _to_text(incident.created_at),
        _to_text(incident.resolved_at) if incident.resolved_at is not None else None,
        incident.recommended_team,
        incident.duplicate_group_key,
    )


def _active_row_to_incident(row: Sequence) -> Incident:
    # Un incidente activo no tiene `resolved_at` (spec 002, consistencia del almacén); la
    # consulta cubriente no lo proyecta, ni tampoco los campos de H003 que el resumen no usa.
    incident_id, title, component, severity, status, created_at = row
    return Incident(
        incident_id=incident_id,
        title=title,
        component=component,
        severity=severity,
        status=status,
        created_at=datetime.fromisoformat(created_at),
        resolved_at=None,
    )


def _full_row_to_incident(row: Sequence) -> Incident:
    incident_id, title, component, severity, status, created_at, resolved_at, team, group_key = row
    return Incident(
        incident_id=incident_id,
        title=title,
        component=component,
        severity=severity,
        status=status,
        created_at=datetime.fromisoformat(created_at),
        resolved_at=datetime.fromisoformat(resolved_at) if resolved_at is not None else None,
        recommended_team=team,
        duplicate_group_key=group_key,
    )


class SQLiteIncidentRepository:
    """Implementación de `IncidentRepositoryPort` sobre `sqlite3`."""

    def __init__(self, database: str = ":memory:") -> None:
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(database, check_same_thread=False)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._connection:
            for statement in _SCHEMA_SQL:
                self._connection.execute(statement)
            existing = {row[1] for row in self._connection.execute("PRAGMA table_info(incidents)")}
            for column, statement in _ADDITIVE_COLUMNS:
                if column not in existing:
                    self._connection.execute(statement)
            self._connection.execute(_DUP_KEY_INDEX_SQL)
            self._connection.executemany(
                _UPSERT_POLICY_SQL,
                [
                    (rule.severity, rule.max_resolution_minutes, 1 if rule.operates_24x7 else 0)
                    for rule in SLA_POLICY_TABLE.values()
                ],
            )

    def close(self) -> None:
        """Cierra la conexión (fuera del puerto): en Windows libera el archivo."""
        with self._lock:
            self._connection.close()

    def save_incident(self, incident: Incident) -> None:
        get_sla_rule_for_severity(incident.severity)  # ValueError si la severidad no tiene política.
        with self._lock, self._connection:
            self._connection.execute(_UPSERT_INCIDENT_SQL, _params(incident))

    def add_incident(self, incident: Incident) -> None:
        get_sla_rule_for_severity(incident.severity)  # ValueError si la severidad no tiene política.
        with self._lock:
            try:
                with self._connection:
                    self._connection.execute(_INSERT_INCIDENT_SQL, _params(incident))
            except sqlite3.IntegrityError as exc:
                # Distingue la clave primaria de cualquier otra violación de integridad.
                if self._connection.execute(_EXISTS_SQL, (incident.incident_id,)).fetchone() is not None:
                    raise IncidentIdConflictError(incident.incident_id) from None
                raise ValueError(f"El incidente viola la integridad del almacén: {exc}") from None

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        with self._lock:
            row = self._connection.execute(_SELECT_BY_ID_SQL, (incident_id,)).fetchone()
        return _full_row_to_incident(row) if row is not None else None

    def find_open_duplicates(self, duplicate_group_key: str, exclude_incident_id: str) -> Sequence[Incident]:
        with self._lock:
            rows = self._connection.execute(
                SELECT_OPEN_DUPLICATES_SQL, (duplicate_group_key, exclude_incident_id)
            ).fetchall()
        return [_full_row_to_incident(row) for row in rows]

    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]:
        if component is None:
            return self._read_active(SELECT_ACTIVE_SQL, ())
        return self._read_active(SELECT_ACTIVE_BY_COMPONENT_SQL, (component,))

    def check_health(self) -> bool:
        try:
            with self._lock:
                return self._connection.execute("SELECT 1").fetchone() == (1,)
        except sqlite3.Error:
            return False

    def _read_active(self, sql: str, params: tuple) -> List[Incident]:
        # Se recorre el cursor dentro del candado (sin fetchall) y se devuelve una lista ya
        # construida, para que ningún iterador vivo retenga el candado fuera del adaptador.
        with self._lock:
            return [_active_row_to_incident(row) for row in self._connection.execute(sql, params)]
