"""Dobles de `IncidentRepositoryPort` para las pruebas (Constitución Art. III.6).

`InMemoryIncidentRepository` permite verificar las reglas del resumen sin abrir SQLite.
Su semántica es la del contrato `specs/002-active-incident-summary/contracts/incident-repository-port.md`
y la batería de conformidad la compara con `SQLiteIncidentRepository`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Dict, Iterable, Optional, Sequence

from src.domain.models import ACTIVE_STATUSES, Incident
from src.domain.sla_calculator import get_sla_rule_for_severity
from src.domain.working_time_calculator import to_bogota


def _normalized(incident: Incident) -> Incident:
    return replace(
        incident,
        created_at=to_bogota(incident.created_at),
        resolved_at=to_bogota(incident.resolved_at) if incident.resolved_at is not None else None,
    )


class InMemoryIncidentRepository:
    """Almacén en memoria con la misma semántica observable que el adaptador SQLite."""

    def __init__(self, incidents: Iterable[Incident] = ()) -> None:
        self._items: Dict[str, Incident] = {}
        for incident in incidents:
            self.save_incident(incident)

    def save_incident(self, incident: Incident) -> None:
        get_sla_rule_for_severity(incident.severity)  # ValueError si no hay política.
        self._items[incident.incident_id] = _normalized(incident)

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        stored = self._items.get(incident_id)
        return replace(stored) if stored is not None else None

    def find_open_duplicates(
        self, component: str, created_from: datetime, created_to: datetime
    ) -> Sequence[Incident]:
        start, end = to_bogota(created_from), to_bogota(created_to)
        matches = [
            replace(item)
            for item in self._items.values()
            if item.status in ACTIVE_STATUSES and item.component == component and start <= item.created_at <= end
        ]
        return sorted(matches, key=lambda item: (item.created_at, item.incident_id))

    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]:
        return [
            replace(item)
            for item in self._items.values()
            if item.status in ACTIVE_STATUSES and (component is None or item.component == component)
        ]

    def check_health(self) -> bool:
        return True


class FailingIncidentRepository(InMemoryIncidentRepository):
    """Doble que simula un fallo inesperado del almacén al leer activos (FR-012/FR-013)."""

    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]:
        raise RuntimeError("fallo simulado del almacén")
