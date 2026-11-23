"""Raíz de composición de IncidentOps (Constitución Art. 2.1 y 2.8).

Único módulo que conoce implementaciones concretas (relojes) y las inyecta en el caso de
uso compartido. Los adaptadores primarios reciben `IncidentService` ya construido.

    uv run uvicorn src.main:app --host 127.0.0.1 --port 8080
    uv run python -X utf8 -m src.adapters.inbound.cli triage --raw-text "..."
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import create_cli
from src.adapters.outbound.clock import FixedClock, SystemClock
from src.application.services import IncidentService


def build_service(now: Optional[datetime] = None) -> IncidentService:
    """Construye el caso de uso; `now` fija el reloj para reproducir resultados."""
    clock = FixedClock(now) if now is not None else SystemClock()
    return IncidentService(clock)


app = create_app(build_service())
cli = create_cli(build_service)


if __name__ == "__main__":
    import uvicorn

    # Solo loopback por defecto: el servicio no tiene autenticación (spec 001 §6.4).
    uvicorn.run(app, host="127.0.0.1", port=8080)
