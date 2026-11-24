"""Aceptación de la spec 004 — Persistencia PostgreSQL y runtime en contenedores (H004).

Bloques (research §R12):
1. US1 — sonda: `GET /health` y el subcomando `health` (E1–E6), sin red ni contenedores.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

import pytest
import typer
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import create_cli
from src.application.ports import StoreUnavailableError
from src.application.services import IncidentService
from src.main import build_service
from tests.doubles import InMemoryIncidentRepository, ToggleHealthRepository

APP_LOGGER = "src.adapters.inbound.api.app"
HEALTH_OK = {"status": "ok", "database": "connected"}
HEALTH_KO = {"status": "error", "database": "unavailable"}
UNAVAILABLE_DIAGNOSTIC = "error [database_unavailable]: el almacén de incidentes no responde."


@pytest.fixture(autouse=True)
def _sin_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cada prueba parte del almacén por defecto salvo que fije `DATABASE_URL`."""
    monkeypatch.delenv("DATABASE_URL", raising=False)


def _cli_sobre(repository) -> typer.Typer:
    return create_cli(lambda now: build_service(now, repository=repository))


class _HealthQueLanza(InMemoryIncidentRepository):
    """Adaptador que incumple «nunca lanza» en `check_health()` (FR-004)."""

    def check_health(self) -> bool:
        raise RuntimeError("fallo simulado de la sonda")


# ---------------------------------------------------------------------------
# US1 — sonda
# ---------------------------------------------------------------------------


def test_bdd_e1_health_200():
    """
    Given el servicio con el almacén configurado disponible
    When  se consulta GET /health dos veces
    Then  responde 200 con {"status": "ok", "database": "connected"} y cada petición
          consulta el almacén (sin caché, FR-001)
    """
    repository = ToggleHealthRepository(available=True)
    client = TestClient(create_app(build_service(repository=repository)))

    first = client.get("/health")
    second = client.get("/health")

    assert first.status_code == 200
    assert first.json() == HEALTH_OK
    assert second.json() == HEALTH_OK
    assert repository.health_calls == 2


def test_bdd_e1_health_200_con_el_almacen_por_defecto():
    """
    Given el servicio sin DATABASE_URL (SQLite en memoria)
    When  se consulta GET /health
    Then  responde 200 connected
    """
    client = TestClient(create_app(build_service(require_health=False)))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == HEALTH_OK


def test_bdd_e2_cli_health_ok():
    """
    Given la CLI con el almacén por defecto
    When  se ejecuta `health --format json` y `health --format table`
    Then  sale con 0, imprime el mismo JSON que GET /health y stderr queda vacío
    """
    runner = CliRunner()
    cli = create_cli(build_service)

    as_json = runner.invoke(cli, ["health", "--format", "json"])
    as_table = runner.invoke(cli, ["health"])

    assert as_json.exit_code == 0, as_json.output
    assert json.loads(as_json.stdout) == HEALTH_OK
    assert as_json.stderr == ""
    assert as_table.exit_code == 0
    lines = as_table.stdout.strip().splitlines()
    assert lines[0].split() == ["estado", "ok"]
    assert lines[1].split() == ["base", "de", "datos", "connected"]


def test_bdd_e3_health_503_con_doble():
    """
    Given un almacén cuya sonda devuelve False
    When  se consulta GET /health
    Then  responde 503 con {"status": "error", "database": "unavailable"}
    """
    client = TestClient(create_app(build_service(repository=ToggleHealthRepository(available=False))))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == HEALTH_KO


def test_bdd_e4_cli_health_unavailable_con_doble():
    """
    Given una composición que no puede construir el servicio porque el almacén no responde
    When  se ejecuta `health --format json`
    Then  sale con 4, el cuerpo unavailable va a stdout y el diagnóstico a stderr
    """

    def factory(now: Optional[datetime]) -> IncidentService:
        raise StoreUnavailableError()

    result = CliRunner().invoke(create_cli(factory), ["health", "--format", "json"])

    assert result.exit_code == 4
    assert json.loads(result.stdout) == HEALTH_KO
    assert result.stderr.strip() == UNAVAILABLE_DIAGNOSTIC


def test_bdd_e4_cli_health_unavailable_al_consultar():
    """
    Given un servicio construido cuyo almacén deja de responder
    When  se ejecuta `health` en tabla
    Then  sale con 4, la tabla dice error/unavailable y stderr lleva el diagnóstico
    """
    result = CliRunner().invoke(_cli_sobre(ToggleHealthRepository(available=False)), ["health"])
    assert result.exit_code == 4
    lines = result.stdout.strip().splitlines()
    assert lines[0].split() == ["estado", "error"]
    assert lines[1].split() == ["base", "de", "datos", "unavailable"]
    assert result.stderr.strip() == UNAVAILABLE_DIAGNOSTIC


def test_bdd_e5_recuperacion_sin_reinicio():
    """
    Given el mismo proceso HTTP con un almacén que cae y vuelve
    When  se consulta GET /health antes y después de la recuperación
    Then  responde 503 y luego 200, sin reiniciar la aplicación
    """
    repository = ToggleHealthRepository(available=False)
    client = TestClient(create_app(build_service(repository=repository)))

    assert client.get("/health").status_code == 503
    repository.available = True
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == HEALTH_OK


def test_bdd_e6_liveness_sin_cambios():
    """
    Given un almacén que no responde
    When  se consulta GET /v1/health
    Then  sigue respondiendo 200 {"status": "ok"} sin consultar el almacén (FR-005)
    """
    repository = ToggleHealthRepository(available=False)
    client = TestClient(create_app(build_service(repository=repository)))
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert repository.health_calls == 0


def test_health_metodo_no_permitido():
    """
    Given el servicio en marcha
    When  se envía POST /health
    Then  responde 405 con el sobre común method_not_allowed
    """
    client = TestClient(create_app(build_service(repository=ToggleHealthRepository())))
    response = client.post("/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_rnf006_registro_solo_cambios_de_estado(caplog: pytest.LogCaptureFixture):
    """
    Given la secuencia de sondas ok, ok, ko, ko, ok
    When  se consulta GET /health cinco veces
    Then  se registran exactamente 4 líneas (primera, ko, ko, recuperación), sin la URL
    """
    repository = ToggleHealthRepository(available=True)
    client = TestClient(create_app(build_service(repository=repository)))

    with caplog.at_level(logging.INFO, logger=APP_LOGGER):
        for available in (True, True, False, False, True):
            repository.available = available
            client.get("/health")

    lines = [r for r in caplog.records if r.name == APP_LOGGER and "Sonda" in r.getMessage()]
    assert [r.levelno for r in lines] == [logging.INFO, logging.WARNING, logging.WARNING, logging.INFO]
    for record in lines:
        message = record.getMessage()
        assert "sqlite" not in message and "postgresql" not in message
        assert "duracion_ms=" in message and "codigo=" in message


def test_fr004_check_health_que_lanza_es_unavailable():
    """
    Given un adaptador cuya sonda lanza una excepción
    When  se consulta GET /health
    Then  responde 503 unavailable, nunca 500
    """
    client = TestClient(create_app(build_service(repository=_HealthQueLanza())))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == HEALTH_KO
