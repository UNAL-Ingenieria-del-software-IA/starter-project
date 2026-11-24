"""Dobles de los puertos secundarios para las pruebas (Constitución Art. III.6).

`InMemoryIncidentRepository` permite verificar las reglas de los casos de uso sin abrir
SQLite. Su semántica es la de los contratos de spec 002 y spec 003
(`specs/003-incident-lifecycle-sla/contracts/incident-repository-port.md`), y las
baterías de conformidad la comparan con `SQLiteIncidentRepository`.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Sequence

from src.application.ports import IncidentIdConflictError
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
        self._lock = threading.Lock()
        for incident in incidents:
            self.save_incident(incident)

    def save_incident(self, incident: Incident) -> None:
        get_sla_rule_for_severity(incident.severity)  # ValueError si no hay política.
        with self._lock:
            self._items[incident.incident_id] = _normalized(incident)

    def add_incident(self, incident: Incident) -> None:
        get_sla_rule_for_severity(incident.severity)  # ValueError si no hay política.
        with self._lock:
            if incident.incident_id in self._items:
                raise IncidentIdConflictError(incident.incident_id)
            self._items[incident.incident_id] = _normalized(incident)

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        stored = self._items.get(incident_id)
        return replace(stored) if stored is not None else None

    def find_open_duplicates(self, duplicate_group_key: str, exclude_incident_id: str) -> Sequence[Incident]:
        matches = [
            replace(item)
            for item in self._items.values()
            if item.status in ACTIVE_STATUSES
            and item.duplicate_group_key == duplicate_group_key
            and item.incident_id != exclude_incident_id
        ]
        return sorted(matches, key=lambda item: (item.created_at, item.incident_id))

    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]:
        # Igual que la consulta cubriente de SQLite: el resumen no usa los campos de H003.
        return [
            replace(item, recommended_team=None, duplicate_group_key=None)
            for item in self._items.values()
            if item.status in ACTIVE_STATUSES and (component is None or item.component == component)
        ]

    def check_health(self) -> bool:
        return True


class FailingIncidentRepository(InMemoryIncidentRepository):
    """Doble que simula un fallo inesperado del almacén al leer activos (spec 002 FR-012/FR-013)."""

    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]:
        raise RuntimeError("fallo simulado del almacén")


class FailingOnAddRepository(InMemoryIncidentRepository):
    """Doble que simula un fallo inesperado del almacén al crear (spec 003 E17)."""

    def add_incident(self, incident: Incident) -> None:
        raise RuntimeError("fallo simulado del almacén")


class SequenceIdGenerator:
    """Generador de identificadores con una secuencia fija, para pruebas deterministas."""

    def __init__(self, ids: Iterable[str]) -> None:
        self._ids: List[str] = list(ids)
        self._lock = threading.Lock()

    def new_id(self) -> str:
        with self._lock:
            if not self._ids:
                raise RuntimeError("SequenceIdGenerator agotado")
            return self._ids.pop(0)
