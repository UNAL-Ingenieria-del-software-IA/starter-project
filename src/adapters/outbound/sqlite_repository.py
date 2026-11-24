"""Adaptador SQLite de `IncidentRepositoryPort` (Constitución Art. 2.6, T3; ADR-001, ADR-005, ADR-006).

- Solo `sqlite3` de la librería estándar, con marcadores `?` y sentencias constantes.
- Índice compuesto, parcial y cubriente `idx_incidents_active_component`, que empieza por
  `(component, status)` y usa el predicado de ADR-005 (`status <> 'RESOLVED'`). Las
  consultas repiten ese predicado literal para que SQLite pueda usar el índice parcial.
- `sla_policies` es un espejo de `SLA_POLICY_TABLE` y destino de la clave foránea de
  `incidents.severity`; el `INNER JOIN` garantiza que toda fila leída tenga política
  evaluable, pero ninguna columna de la tabla se usa para calcular (Art. 1.1).
- Una sola conexión (`check_same_thread=False`) protegida por un candado: con
  `:memory:` cada conexión es una base distinta y FastAPI atiende en un pool de hilos.
- El DDL y el mapeo fila ↔ entidad viven solo aquí.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from typing import List, Optional, Sequence

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
        resolved_at TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_incidents_active_component
    ON incidents (component, status, severity, created_at, incident_id, title)
    WHERE status <> 'RESOLVED'
    """,
)

_UPSERT_POLICY_SQL = """
    INSERT INTO sla_policies (severity, max_resolution_minutes, operates_24x7)
    VALUES (?, ?, ?)
    ON CONFLICT (severity) DO UPDATE SET
        max_resolution_minutes = excluded.max_resolution_minutes,
        operates_24x7 = excluded.operates_24x7
"""

_UPSERT_INCIDENT_SQL = """
    INSERT INTO incidents (incident_id, title, component, severity, status, created_at, resolved_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (incident_id) DO UPDATE SET
        title = excluded.title,
        component = excluded.component,
        severity = excluded.severity,
        status = excluded.status,
        created_at = excluded.created_at,
        resolved_at = excluded.resolved_at
"""

_SELECT_BY_ID_SQL = """
    SELECT incident_id, title, component, severity, status, created_at, resolved_at
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

_SELECT_OPEN_DUPLICATES_SQL = """
    SELECT i.incident_id, i.title, i.component, i.severity, i.status, i.created_at
    FROM incidents AS i
    INNER JOIN sla_policies AS p ON p.severity = i.severity
    WHERE i.status <> 'RESOLVED' AND i.component = ? AND i.created_at >= ? AND i.created_at <= ?
    ORDER BY i.created_at, i.incident_id
"""


def _to_text(value: datetime) -> str:
    """Instante en Bogotá con ancho fijo: la comparación de texto equivale a la temporal."""
    return to_bogota(value).isoformat(timespec="microseconds")


def _active_row_to_incident(row: Sequence) -> Incident:
    # Un incidente activo no tiene `resolved_at` (spec 002, consistencia del almacén); la
    # consulta cubriente no lo proyecta.
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
            self._connection.executemany(
                _UPSERT_POLICY_SQL,
                [
                    (rule.severity, rule.max_resolution_minutes, 1 if rule.operates_24x7 else 0)
                    for rule in SLA_POLICY_TABLE.values()
                ],
            )

    def save_incident(self, incident: Incident) -> None:
        get_sla_rule_for_severity(incident.severity)  # ValueError si la severidad no tiene política.
        params = (
            incident.incident_id,
            incident.title,
            incident.component,
            incident.severity,
            incident.status,
            _to_text(incident.created_at),
            _to_text(incident.resolved_at) if incident.resolved_at is not None else None,
        )
        with self._lock, self._connection:
            self._connection.execute(_UPSERT_INCIDENT_SQL, params)

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        with self._lock:
            row = self._connection.execute(_SELECT_BY_ID_SQL, (incident_id,)).fetchone()
        if row is None:
            return None
        incident_id, title, component, severity, status, created_at, resolved_at = row
        return Incident(
            incident_id=incident_id,
            title=title,
            component=component,
            severity=severity,
            status=status,
            created_at=datetime.fromisoformat(created_at),
            resolved_at=datetime.fromisoformat(resolved_at) if resolved_at is not None else None,
        )

    def find_open_duplicates(
        self, component: str, created_from: datetime, created_to: datetime
    ) -> Sequence[Incident]:
        params = (component, _to_text(created_from), _to_text(created_to))
        return self._read_active(_SELECT_OPEN_DUPLICATES_SQL, params)

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
