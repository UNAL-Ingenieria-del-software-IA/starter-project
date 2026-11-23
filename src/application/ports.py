"""Puertos secundarios declarados con `typing.Protocol` (Constitución Art. 2.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ClockPort(Protocol):
    """Suministra el instante de referencia; el núcleo nunca lee el reloj (Art. 1.3)."""

    def now(self) -> datetime:
        """Devuelve el instante actual según la implementación inyectada."""
        ...
