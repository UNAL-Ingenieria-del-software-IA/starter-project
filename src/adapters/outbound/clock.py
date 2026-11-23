"""Implementaciones concretas de `ClockPort`."""

from __future__ import annotations

from datetime import datetime

from src.domain.working_time_calculator import BOGOTA_TZ


class SystemClock:
    """Reloj del sistema expresado en hora de Bogotá (Constitución Art. 1.7)."""

    def now(self) -> datetime:
        return datetime.now(BOGOTA_TZ)


class FixedClock:
    """Reloj fijo para demos, reproducción (`--now`) y pruebas deterministas."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant
