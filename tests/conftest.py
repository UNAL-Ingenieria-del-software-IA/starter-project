"""Fixtures compartidas de la suite de aceptación de la spec 001.

Ambos canales se construyen con la misma fábrica de la raíz de composición y un reloj
fijo, de modo que la paridad REST/CLI se verifica en proceso, sin red ni puertos (D8).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pytest
import typer
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import create_cli
from src.adapters.outbound.null_repository import NullIncidentRepository
from src.application.services import IncidentService
from src.main import build_service

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample_incidents.json"

# Instante de referencia fijo (ClockPort) compartido por ambos canales.
FIXED_NOW = datetime(2026, 11, 5, 9, 0)


@pytest.fixture
def fixed_now() -> datetime:
    return FIXED_NOW


@pytest.fixture
def service() -> IncidentService:
    # El triaje no tiene efectos: repositorio nulo (Constitución Art. III.4).
    return build_service(FIXED_NOW, repository=NullIncidentRepository())


@pytest.fixture
def client(service: IncidentService) -> TestClient:
    return TestClient(create_app(service))


@pytest.fixture
def cli_app() -> typer.Typer:
    def factory(now: Optional[datetime]) -> IncidentService:
        return build_service(now or FIXED_NOW, repository=NullIncidentRepository())

    return create_cli(factory)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(scope="session")
def sample_texts() -> Dict[str, str]:
    """`raw_text` del fixture graduado, indexado por `id` (`INC-1001`…`INC-1010`)."""
    items = json.loads(SAMPLE_DATA_PATH.read_text(encoding="utf-8"))
    return {item["id"]: item["raw_text"] for item in items}
