"""Repositorio nulo para operaciones sin efectos (Constitución Art. III.4).

Satisface `IncidentRepositoryPort` sin almacenar nada: el triaje de H001 y sus pruebas
lo usan para que el servicio no necesite condicionales por canal ni una base de datos.
"""

from __future__ import annotations

from typing import Optional, Sequence

from src.domain.models import Incident


class NullIncidentRepository:
    """No guarda, no encuentra y siempre responde."""

    def save_incident(self, incident: Incident) -> None:
        return None

    def add_incident(self, incident: Incident) -> None:
        return None

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        return None

    def find_open_duplicates(self, duplicate_group_key: str, exclude_incident_id: str) -> Sequence[Incident]:
        return ()

    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]:
        return ()

    def check_health(self) -> bool:
        return True
