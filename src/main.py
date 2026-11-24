"""Raíz de composición de IncidentOps (Constitución Art. 2.1, 2.8 y III.5).

Único módulo que conoce implementaciones concretas (relojes y repositorios), el único que
lee `DATABASE_URL` y el único que las inyecta en el caso de uso compartido. Los
adaptadores primarios reciben `IncidentService` ya construido.

    uv run uvicorn src.main:app --host 127.0.0.1 --port 8080
    uv run python -X utf8 -m src.adapters.inbound.cli triage --raw-text "..."
    uv run python -X utf8 -m src.adapters.inbound.cli summary --format json

`app` se construye bajo demanda (`__getattr__` de módulo, PEP 562): importar este módulo
desde el CLI no crea el servicio HTTP ni importa FastAPI. `uvicorn src.main:app` resuelve
`app` con `getattr` y sigue funcionando.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from src.adapters.inbound.cli import create_cli
from src.adapters.outbound.clock import FixedClock, SystemClock
from src.adapters.outbound.demo_incidents import seed_demo_incidents
from src.adapters.outbound.factory import (
    DEFAULT_DATABASE_URL,
    create_incident_repository,
    is_in_memory_url,
)
from src.adapters.outbound.id_generator import RandomHexIdGenerator
from src.application.ports import IncidentIdGeneratorPort, IncidentRepositoryPort
from src.application.services import IncidentService


def build_repository(database_url: Optional[str] = None) -> IncidentRepositoryPort:
    """Selecciona el repositorio por `DATABASE_URL` (por defecto, demo en memoria).

    Raises:
        ValueError: si la URL no es soportada.
        RuntimeError: si el almacén no responde (`check_health`).
    """
    url = database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    repository = create_incident_repository(url)
    if not repository.check_health():
        raise RuntimeError("El almacén de incidentes no responde.")
    if is_in_memory_url(url):
        # Demo de H002 (spec 002, D1): sin persistencia de incidentes hasta H003.
        seed_demo_incidents(repository)
    return repository


def build_service(
    now: Optional[datetime] = None,
    repository: Optional[IncidentRepositoryPort] = None,
    id_generator: Optional[IncidentIdGeneratorPort] = None,
) -> IncidentService:
    """Construye el caso de uso.

    `now` fija el reloj, `repository` sustituye a `DATABASE_URL` e `id_generator` al
    generador aleatorio de identificadores (spec 003 research §R7).
    """
    clock = FixedClock(now) if now is not None else SystemClock()
    return IncidentService(
        clock,
        repository if repository is not None else build_repository(),
        id_generator if id_generator is not None else RandomHexIdGenerator(),
    )


cli = create_cli(build_service)


def __getattr__(name: str) -> Any:
    if name == "app":
        from src.adapters.inbound.api.app import create_app

        application = create_app(build_service())
        globals()["app"] = application  # Se construye una sola vez.
        return application
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    import uvicorn

    # Solo loopback por defecto: el servicio no tiene autenticación (spec 001 §6.4).
    uvicorn.run(__getattr__("app"), host="127.0.0.1", port=8080)
