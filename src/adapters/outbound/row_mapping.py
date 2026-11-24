"""Mapeo compartido fila ↔ entidad de los dos adaptadores de persistencia (ADR-004).

Única fuente del formato de instantes y del orden de parámetros, para que SQLite y
PostgreSQL guarden y devuelvan exactamente lo mismo (spec 004 FR-012, RNF-001):

- los instantes se guardan como texto ISO 8601 en hora de Bogotá, con microsegundos y
  desfase explícito (`2026-11-24T09:00:00.000000-05:00`). El ancho y el desfase son fijos,
  así que el orden del texto coincide con el cronológico (Constitución 2.6);
- `incident_params` devuelve los nueve valores en el orden de las columnas del DDL.

No conoce ningún driver: recibe y devuelve valores de Python.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from src.domain.models import Incident
from src.domain.working_time_calculator import to_bogota

# Orden de columnas de `incidents` en ambos motores (data-model.md §1).
INCIDENT_COLUMNS: Tuple[str, ...] = (
    "incident_id",
    "title",
    "component",
    "severity",
    "status",
    "created_at",
    "resolved_at",
    "recommended_team",
    "duplicate_group_key",
)


def instant_to_text(value: datetime) -> str:
    """Instante en Bogotá con ancho fijo: la comparación de texto equivale a la temporal."""
    return to_bogota(value).isoformat(timespec="microseconds")


def text_to_instant(value: Optional[str]) -> Optional[datetime]:
    """Inversa de `instant_to_text`; `None` se conserva."""
    return datetime.fromisoformat(value) if value is not None else None


def incident_params(incident: Incident) -> tuple:
    """Los nueve valores del incidente en el orden de `INCIDENT_COLUMNS`."""
    return (
        incident.incident_id,
        incident.title,
        incident.component,
        incident.severity,
        incident.status,
        instant_to_text(incident.created_at),
        instant_to_text(incident.resolved_at) if incident.resolved_at is not None else None,
        incident.recommended_team,
        incident.duplicate_group_key,
    )


def active_incident(incident_id: str, title: str, component: str, severity: str, status: str, created_at: str) -> Incident:
    """Incidente leído por la consulta cubriente de activos.

    Un activo no tiene `resolved_at` (spec 002); la consulta cubriente tampoco proyecta los
    campos de H003, que el resumen no usa.
    """
    return Incident(
        incident_id=incident_id,
        title=title,
        component=component,
        severity=severity,
        status=status,
        created_at=datetime.fromisoformat(created_at),
        resolved_at=None,
    )


def full_incident(
    incident_id: str,
    title: str,
    component: str,
    severity: str,
    status: str,
    created_at: str,
    resolved_at: Optional[str],
    recommended_team: Optional[str],
    duplicate_group_key: Optional[str],
) -> Incident:
    """Incidente completo, con las nueve columnas en el orden de `INCIDENT_COLUMNS`."""
    return Incident(
        incident_id=incident_id,
        title=title,
        component=component,
        severity=severity,
        status=status,
        created_at=datetime.fromisoformat(created_at),
        resolved_at=text_to_instant(resolved_at),
        recommended_team=recommended_team,
        duplicate_group_key=duplicate_group_key,
    )
