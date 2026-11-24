"""Puertos secundarios declarados con `typing.Protocol` (Constitución Art. 2.4 y III).

Los adaptadores no heredan de estas clases: solo satisfacen su forma. `Protocol` no
valida en ejecución; la conformidad se verifica en `tests/test_spec_002_summary.py` y
`tests/test_spec_003_lifecycle_sla.py`, y las fronteras con Ruff y
`tests/test_arquitectura.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, Sequence

from src.domain.models import Incident


class IncidentIdConflictError(Exception):
    """El identificador ya existe en el almacén; lo lanza `add_incident` (spec 003 FR-004)."""

    def __init__(self, incident_id: str) -> None:
        super().__init__(f"Ya existe un incidente con el identificador {incident_id}.")
        self.incident_id = incident_id


class ClockPort(Protocol):
    """Suministra el instante de referencia; el núcleo nunca lee el reloj (Art. 1.3)."""

    def now(self) -> datetime:
        """Devuelve el instante actual según la implementación inyectada."""
        ...


class IncidentIdGeneratorPort(Protocol):
    """Suministra identificadores nuevos; el núcleo no genera aleatoriedad (Art. 1.3).

    Justificación: spec 003, research §R7 (Constitución 3.0.0, Principio 3.2).
    """

    def new_id(self) -> str:
        """Devuelve un identificador `INC-` seguido de 8 dígitos hexadecimales en mayúsculas."""
        ...


class IncidentRepositoryPort(Protocol):
    """Almacén de incidentes expresado en entidades de dominio (Art. III.2–III.3).

    No expone SQL, filas, tablas ni DSN. Los instantes se devuelven normalizados a hora
    de Bogotá. Justificación de cada método: ADR-006 y spec 003 (research §R4).
    """

    def save_incident(self, incident: Incident) -> None:
        """Inserta o reemplaza el incidente por `incident_id`.

        Raises:
            ValueError: si la severidad no tiene política SLA.
        """
        ...

    def add_incident(self, incident: Incident) -> None:
        """Inserta el incidente sin reemplazar uno existente (spec 003 FR-004).

        Raises:
            IncidentIdConflictError: si ya existe ese `incident_id`; el existente no cambia.
            ValueError: si la severidad no tiene política SLA.
        """
        ...

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Devuelve el incidente con ese identificador, o `None` si no existe."""
        ...

    def find_open_duplicates(self, duplicate_group_key: str, exclude_incident_id: str) -> Sequence[Incident]:
        """Activos con esa clave de grupo y otro identificador, por `(created_at, incident_id)`.

        La clave la calcula el dominio (Art. 1.11); el puerto solo compara igualdad. Quien
        llama nunca pasa una clave vacía ni nula.
        """
        ...

    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]:
        """Incidentes activos (estado distinto de `RESOLVED`), del componente si se indica.

        El componente se compara tal cual (quien llama ya lo normalizó). Sin orden
        garantizado: ordenar es responsabilidad del caso de uso.
        """
        ...

    def check_health(self) -> bool:
        """`True` si el almacén responde. Nunca lanza."""
        ...
