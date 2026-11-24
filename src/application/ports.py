"""Puertos secundarios declarados con `typing.Protocol` (Constitución Art. 2.4 y III).

Los adaptadores no heredan de estas clases: solo satisfacen su forma. `Protocol` no
valida en ejecución; la conformidad se verifica en `tests/test_spec_002_summary.py`
y las fronteras con Ruff y `tests/test_arquitectura.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, Sequence

from src.domain.models import Incident


class ClockPort(Protocol):
    """Suministra el instante de referencia; el núcleo nunca lee el reloj (Art. 1.3)."""

    def now(self) -> datetime:
        """Devuelve el instante actual según la implementación inyectada."""
        ...


class IncidentRepositoryPort(Protocol):
    """Almacén de incidentes expresado en entidades de dominio (Art. III.2–III.3).

    No expone SQL, filas, tablas ni DSN. Los instantes se devuelven normalizados a hora
    de Bogotá. La justificación de cada método está en ADR-006.
    """

    def save_incident(self, incident: Incident) -> None:
        """Inserta o reemplaza el incidente por `incident_id`.

        Raises:
            ValueError: si la severidad no tiene política SLA.
        """
        ...

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Devuelve el incidente con ese identificador, o `None` si no existe."""
        ...

    def find_open_duplicates(
        self, component: str, created_from: datetime, created_to: datetime
    ) -> Sequence[Incident]:
        """Activos del componente creados en `[created_from, created_to]`, por `created_at`.

        La ventana la calcula quien llama: la regla de duplicados es del dominio
        (Art. 1.11); el puerto solo transporta.
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
