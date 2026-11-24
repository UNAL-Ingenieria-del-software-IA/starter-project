"""Aceptación de la spec 004 — Persistencia PostgreSQL y runtime en contenedores (H004).

Bloques (research §R12):
1. US1 — sonda: `GET /health` y el subcomando `health` (E1–E6), sin red ni contenedores.
2. US2 — selección de motor, rápidas: E4 por el camino real, E7, E8, E10, E17, conformidad
   estructural, URL mal formada, C9 y C11 contra un puerto muerto (sin base).
3. US2 — PostgreSQL (`@pytest.mark.postgres`): conformidad C1–C8 parametrizada sobre ambos
   motores, C10, E9 y E11. Necesitan `INCIDENTOPS_TEST_POSTGRES_URL` (servicio `db-test`);
   sin ella se omiten de forma visible.
4. US3 — estructura Docker, rápidas: `Dockerfile`, `.dockerignore` y `docker-compose.yml`
   por aserciones de texto (sin `pyyaml`).
5. US3 — contenedores (`@pytest.mark.docker`): `docker compose config` y E12–E17, cada uno
   en un proyecto aislado `incidentops-t<uuid8>` que se elimina con `down -v`. Sin Docker
   se omiten de forma visible.

Ninguna salida, cuerpo ni registro puede contener `DATABASE_URL` ni sus partes (RNF-003).
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
import socket
import subprocess
import time
import typing
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest
import typer
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import create_cli
from src.adapters.outbound.clock import FixedClock
from src.adapters.outbound.demo_incidents import classified_demo_incidents
from src.adapters.outbound.factory import create_repository
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.ports import IncidentIdConflictError, IncidentRepositoryPort, StoreUnavailableError
from src.application.services import (
    CreateIncidentInput,
    IncidentService,
    creation_to_contract,
    sla_audit_to_contract,
    summary_to_contract,
)
from src.domain.models import Incident
from src.domain.working_time_calculator import BOGOTA_TZ
from src.main import build_service
from tests.doubles import InMemoryIncidentRepository, SequenceIdGenerator, ToggleHealthRepository

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


# ---------------------------------------------------------------------------
# US2 — selección de motor (rápidas: sin base ni contenedores)
# ---------------------------------------------------------------------------

DEAD_PG_URL = "postgresql://u:secreto@127.0.0.1:1/db"
PORT_METHODS = (
    "save_incident",
    "add_incident",
    "get_incident",
    "find_open_duplicates",
    "list_active_incidents",
    "check_health",
)
REFERENCE = "2026-11-24T09:00:00"
DEMO_ACTIVE_IDS = {"INC-2001", "INC-2002", "INC-2003", "INC-2004", "INC-2005", "INC-2007"}


def _sin_fugas(*texts: str) -> None:
    for text in texts:
        assert "secreto" not in text
        assert "u:" not in text and "127.0.0.1:1" not in text
        assert DEAD_PG_URL not in text


@pytest.mark.parametrize("ausencia", ["sin_variable", "vacia"])
def test_bdd_e7_sin_database_url_usa_memoria(monkeypatch: pytest.MonkeyPatch, ausencia: str):
    """
    Given DATABASE_URL ausente o vacía
    When  se ejecutan `summary` y `health` por la CLI
    Then  se usa SQLite en memoria con los incidentes de demostración y la sonda dice connected
    """
    if ausencia == "vacia":
        monkeypatch.setenv("DATABASE_URL", "")
    runner = CliRunner()
    cli = create_cli(build_service)

    summary = runner.invoke(cli, ["summary", "--reference-time", REFERENCE, "--format", "json"])
    health = runner.invoke(cli, ["health", "--format", "json"])

    assert summary.exit_code == 0, summary.output
    assert {item["incident_id"] for item in json.loads(summary.stdout)["incidents"]} == DEMO_ACTIVE_IDS
    assert health.exit_code == 0
    assert json.loads(health.stdout) == HEALTH_OK


def test_bdd_e8_sqlite_archivo(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """
    Given DATABASE_URL=sqlite:///<archivo>
    When  se crea un incidente y se audita su SLA en dos invocaciones
    Then  la segunda lo encuentra y el archivo no tiene datos de demostración
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'incidentes.db'}")
    runner = CliRunner()
    cli = create_cli(build_service)

    created = runner.invoke(
        cli,
        [
            "create", "--incident-id", "INC-E8", "--title", "Caída de pagos",
            "--raw-text", "La pasarela de pagos está caída, ningún cliente puede pagar",
            "--created-at", "2026-11-24T08:00:00", "--format", "json",
        ],
    )
    audit = runner.invoke(cli, ["sla", "INC-E8", "--reference-time", REFERENCE, "--format", "json"])
    summary = runner.invoke(cli, ["summary", "--reference-time", REFERENCE, "--format", "json"])

    assert created.exit_code == 0, created.output
    assert audit.exit_code == 0, audit.output
    assert json.loads(audit.stdout)["incident_id"] == "INC-E8"
    assert [item["incident_id"] for item in json.loads(summary.stdout)["incidents"]] == ["INC-E8"]


@pytest.mark.parametrize(
    ("url", "esquema"),
    [("mysql://u:secreto@h/db", "mysql"), ("postgres://u:secreto@h/db", "postgres"), ("texto", "desconocido")],
)
@pytest.mark.parametrize("subcomando", ["summary", "health"])
def test_bdd_e10_esquema_no_soportado(monkeypatch: pytest.MonkeyPatch, url: str, esquema: str, subcomando: str):
    """
    Given una DATABASE_URL con un esquema no admitido
    When  se ejecuta la CLI
    Then  sale con 4 y el mensaje nombra solo el esquema, sin credenciales
    """
    monkeypatch.setenv("DATABASE_URL", url)
    result = CliRunner().invoke(create_cli(build_service), [subcomando, "--format", "json"])

    assert result.exit_code == 4
    assert result.stdout == ""
    assert result.stderr.startswith(f"error [internal_error]: DATABASE_URL no soportada (esquema '{esquema}')")
    assert "secreto" not in result.stderr


@pytest.mark.parametrize("url", ["sqlite:///:memory:", DEAD_PG_URL], ids=["sqlite", "postgresql"])
@pytest.mark.parametrize("method", PORT_METHODS)
def test_create_repository_conformidad_estructural(url: str, method: str):
    """
    Given create_repository con una URL de cada motor
    When  se comparan los métodos con IncidentRepositoryPort
    Then  existen con la misma firma y construir el de PostgreSQL no abre red
    """
    started = time.perf_counter()
    repository = create_repository(url)
    assert time.perf_counter() - started < 0.5, "construir el adaptador no debe conectar"

    expected = getattr(IncidentRepositoryPort, method)
    actual = getattr(type(repository), method, None)
    assert callable(actual), f"{type(repository).__name__} no implementa {method}"

    def shape(func):
        return [(p.name, p.kind, p.default) for p in inspect.signature(func).parameters.values()]

    assert shape(actual) == shape(expected)
    assert typing.get_type_hints(actual) == typing.get_type_hints(expected)


def test_bdd_e4_camino_real_puerto_muerto(monkeypatch: pytest.MonkeyPatch):
    """
    Given DATABASE_URL hacia un PostgreSQL inalcanzable
    When  se ejecuta `health --format json`
    Then  sale con 4 y cuerpo unavailable en 3 s o menos, sin la URL ni sus partes
    """
    monkeypatch.setenv("DATABASE_URL", DEAD_PG_URL)
    started = time.perf_counter()
    result = CliRunner().invoke(create_cli(build_service), ["health", "--format", "json"])
    elapsed = time.perf_counter() - started

    assert result.exit_code == 4
    assert json.loads(result.stdout) == HEALTH_KO
    assert result.stderr.strip() == UNAVAILABLE_DIAGNOSTIC
    assert elapsed <= 3.0
    _sin_fugas(result.stdout, result.stderr)


def test_bdd_e17_arranque_degradado_rapido(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    """
    Given la API compuesta con require_health=False hacia un PostgreSQL inalcanzable
    When  se consultan GET /health y el resumen
    Then  la API arrancó; /health responde 503 y el resumen 500 internal_error, sin la URL
    """
    monkeypatch.setenv("DATABASE_URL", DEAD_PG_URL)
    with caplog.at_level(logging.INFO):
        client = TestClient(create_app(build_service(require_health=False)), raise_server_exceptions=False)
        health = client.get("/health")
        summary = client.get("/api/v1/incidents/summary")

    assert health.status_code == 503
    assert health.json() == HEALTH_KO
    assert summary.status_code == 500
    assert summary.json()["error"]["code"] == "internal_error"
    _sin_fugas(health.text, summary.text, caplog.text)


def test_url_postgres_mal_formada():
    """
    Given una URL postgresql:// que libpq no puede interpretar
    When  se construye el repositorio
    Then  falla con ValueError sin la URL ni la causa encadenada
    """
    with pytest.raises(ValueError) as info:
        create_repository("postgresql://u:secreto@h/db?badparam=1")
    assert str(info.value) == "DATABASE_URL de PostgreSQL mal formada (esquema 'postgresql')."
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_c9_check_health_con_el_almacen_caido():
    """
    Given el adaptador PostgreSQL hacia un puerto muerto
    When  se ejecuta check_health()
    Then  devuelve False en 3 s o menos, sin lanzar (contrato C9)
    """
    from src.adapters.outbound.postgres_repository import PostgresIncidentRepository

    started = time.perf_counter()
    assert PostgresIncidentRepository(DEAD_PG_URL).check_health() is False
    assert time.perf_counter() - started <= 3.0


def test_c11_error_del_driver_no_cruza_el_puerto():
    """
    Given el adaptador PostgreSQL hacia un puerto muerto
    When  se listan los incidentes activos
    Then  lanza StoreUnavailableError sin causa encadenada ni la URL, en 3 s o menos (C11)
    """
    import psycopg

    from src.adapters.outbound.postgres_repository import PostgresIncidentRepository

    repository = PostgresIncidentRepository(DEAD_PG_URL)
    started = time.perf_counter()
    with pytest.raises(StoreUnavailableError) as info:
        repository.list_active_incidents()
    assert time.perf_counter() - started <= 3.0
    assert not isinstance(info.value, psycopg.Error)
    assert info.value.__cause__ is None and info.value.__suppress_context__
    _sin_fugas(str(info.value))


# ---------------------------------------------------------------------------
# US2 — PostgreSQL (conformidad de comportamiento, E9, E11, siembra única)
# ---------------------------------------------------------------------------

PG_ENV = "INCIDENTOPS_TEST_POSTGRES_URL"
NOW = datetime(2026, 11, 24, 9, 10, tzinfo=BOGOTA_TZ)
REF_DT = datetime(2026, 11, 24, 9, 0, tzinfo=BOGOTA_TZ)
CAIDA_PAGOS = "La pasarela de pagos está caída, ningún cliente puede pagar"


def _pg_execute(url: str, sql: str):
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        cursor = conn.execute(sql)
        return cursor.fetchone() if cursor.description else None


def _pg_count(url: str) -> int:
    return _pg_execute(url, "SELECT count(*) FROM incidents")[0]


@pytest.fixture
def pg_url() -> str:
    """URL de la base de pruebas `db-test`; se omite de forma visible si no está configurada."""
    url = os.environ.get(PG_ENV)
    if not url:
        pytest.skip(f"{PG_ENV} no está definida: casos PostgreSQL omitidos (Constitución 3.6)")
    _pg_execute(url, "DROP TABLE IF EXISTS incidents, sla_policies")
    return url


@pytest.fixture(params=["sqlite", pytest.param("postgresql", marks=pytest.mark.postgres)])
def repositorio(request: pytest.FixtureRequest, tmp_path):
    """El mismo almacén vacío sobre cada motor (contracts/incident-repository-port.md)."""
    if request.param == "sqlite":
        repository = SQLiteIncidentRepository(str(tmp_path / "conformidad.db"))
    else:
        from src.adapters.outbound.postgres_repository import PostgresIncidentRepository

        repository = PostgresIncidentRepository(request.getfixturevalue("pg_url"))
    yield repository
    repository.close()


def _inc(
    incident_id: str,
    *,
    component: str = "payment-gateway",
    severity: str = "P1",
    status: str = "OPEN",
    created_at: datetime = REF_DT,
    resolved_at: Optional[datetime] = None,
    title: str = "Incidente de conformidad",
    team: Optional[str] = "Backend-Core",
    key: Optional[str] = None,
) -> Incident:
    return Incident(
        incident_id=incident_id,
        title=title,
        component=component,
        severity=severity,
        status=status,
        created_at=created_at,
        resolved_at=resolved_at,
        recommended_team=team,
        duplicate_group_key=key,
    )


def test_c1_save_incident_reemplaza(repositorio):
    repositorio.save_incident(_inc("INC-C1", title="primero"))
    repositorio.save_incident(_inc("INC-C1", title="segundo", status="IN_PROGRESS"))
    stored = repositorio.get_incident("INC-C1")
    assert stored.title == "segundo" and stored.status == "IN_PROGRESS"
    assert [i.incident_id for i in repositorio.list_active_incidents()] == ["INC-C1"]


def test_c2_add_incident_con_id_existente(repositorio):
    repositorio.add_incident(_inc("INC-C2", title="original"))
    with pytest.raises(IncidentIdConflictError):
        repositorio.add_incident(_inc("INC-C2", title="intruso"))
    assert repositorio.get_incident("INC-C2").title == "original"


@pytest.mark.parametrize("operation", ["save_incident", "add_incident"])
def test_c3_severidad_sin_politica(repositorio, operation: str):
    with pytest.raises(ValueError):
        getattr(repositorio, operation)(_inc("INC-C3", severity="P9"))
    assert repositorio.get_incident("INC-C3") is None


def test_c4_get_incident_inexistente(repositorio):
    assert repositorio.get_incident("INC-NADA") is None


def test_c5_ida_y_vuelta_de_instantes(repositorio):
    created = datetime(2026, 11, 24, 9, 0, 0, 123456, tzinfo=BOGOTA_TZ)
    resolved = datetime(2026, 11, 24, 10, 30, 0, 654321, tzinfo=BOGOTA_TZ)
    repositorio.save_incident(_inc("INC-C5", status="RESOLVED", created_at=created, resolved_at=resolved))
    stored = repositorio.get_incident("INC-C5")
    assert stored.created_at == created and stored.resolved_at == resolved
    assert stored.created_at.utcoffset() == created.utcoffset()


def test_c6_activos_por_estado_y_componente(repositorio):
    repositorio.save_incident(_inc("INC-A1", status="OPEN"))
    repositorio.save_incident(_inc("INC-A2", status="ESCALATION_REQUIRED", component="auth-identity"))
    repositorio.save_incident(
        _inc("INC-A3", status="RESOLVED", resolved_at=datetime(2026, 11, 24, 9, 30, tzinfo=BOGOTA_TZ))
    )
    assert {i.incident_id for i in repositorio.list_active_incidents()} == {"INC-A1", "INC-A2"}
    assert [i.incident_id for i in repositorio.list_active_incidents("auth-identity")] == ["INC-A2"]
    assert list(repositorio.list_active_incidents("Auth-Identity")) == []


def test_c7_duplicados_abiertos_en_orden_por_bytes(repositorio):
    key = "payment-availability"
    repositorio.save_incident(_inc("INC-abc1", key=key))
    repositorio.save_incident(_inc("INC-ABC1", key=key))
    repositorio.save_incident(_inc("INC-PREVIO", key=key, created_at=datetime(2026, 11, 24, 8, 0, tzinfo=BOGOTA_TZ)))
    repositorio.save_incident(
        _inc("INC-CERRADO", key=key, status="RESOLVED", resolved_at=datetime(2026, 11, 24, 9, 5, tzinfo=BOGOTA_TZ))
    )
    repositorio.save_incident(_inc("INC-NUEVO", key=key))
    repositorio.save_incident(_inc("INC-OTRA", key="auth-availability"))

    found = repositorio.find_open_duplicates(key, "INC-NUEVO")
    assert [i.incident_id for i in found] == ["INC-PREVIO", "INC-ABC1", "INC-abc1"]


def test_c8_check_health_disponible(repositorio):
    assert repositorio.check_health() is True


@pytest.mark.postgres
def test_c10_siembra_unica(pg_url: str):
    """
    Given una base PostgreSQL vacía
    When  dos adaptadores con semilla se inicializan en secuencia, o la base ya tiene datos
    Then  quedan los 8 de demostración una sola vez, y una base con datos no se siembra
    """
    from src.adapters.outbound.postgres_repository import PostgresIncidentRepository

    seed = classified_demo_incidents()
    for _ in range(2):
        repository = PostgresIncidentRepository(pg_url, seed_if_empty=seed)
        assert repository.check_health() is True
        repository.close()
    assert _pg_count(pg_url) == 8

    _pg_execute(pg_url, "DROP TABLE IF EXISTS incidents, sla_policies")
    previo = PostgresIncidentRepository(pg_url)
    previo.save_incident(_inc("INC-PREVIO"))
    previo.close()
    sembrado = PostgresIncidentRepository(pg_url, seed_if_empty=seed)
    assert sembrado.check_health() is True
    sembrado.close()
    assert _pg_count(pg_url) == 1


@pytest.mark.postgres
def test_bdd_e9_postgresql_persiste_entre_procesos(monkeypatch: pytest.MonkeyPatch, pg_url: str):
    """
    Given DATABASE_URL=postgresql://… hacia una base vacía
    When  se crea un incidente por HTTP con un servicio y se audita por la CLI con otro nuevo
    Then  la auditoría lo encuentra y la base tiene los 8 de demostración más el creado
    """
    monkeypatch.setenv("DATABASE_URL", pg_url)
    client = TestClient(create_app(build_service(NOW)))
    created = client.post(
        "/api/v1/incidents",
        json={"incident_id": "INC-E9", "title": "Caída de pagos", "raw_text": CAIDA_PAGOS},
    )
    assert created.status_code == 201, created.text
    assert created.json()["duplicate_of"] == ["INC-2001"]

    audit = CliRunner().invoke(
        create_cli(build_service), ["sla", "INC-E9", "--reference-time", "2026-11-24T10:00:00", "--format", "json"]
    )
    assert audit.exit_code == 0, audit.output
    assert json.loads(audit.stdout)["incident_id"] == "INC-E9"
    assert _pg_count(pg_url) == 9


@pytest.mark.postgres
def test_bdd_e11_paridad_byte_a_byte(pg_url: str):
    """
    Given el mismo conjunto de datos en SQLite y en PostgreSQL
    When  se piden resumen, auditoría de SLA y una creación con duplicado al mismo instante
    Then  los JSON son idénticos byte a byte
    """
    from src.adapters.outbound.postgres_repository import PostgresIncidentRepository

    def bodies(repository) -> list:
        for incident in classified_demo_incidents():
            repository.save_incident(incident)
        repository.save_incident(_inc("INC-ABC1", key="payment-availability"))
        repository.save_incident(_inc("INC-abc1", key="payment-availability"))
        service = IncidentService(FixedClock(NOW), repository, SequenceIdGenerator(["INC-0000BEEF"]))
        creation = service.create_incident(CreateIncidentInput(title="Caída de pagos", raw_text=CAIDA_PAGOS))
        return [
            json.dumps(summary_to_contract(service.get_active_incidents_summary(None, REF_DT)), ensure_ascii=False),
            json.dumps(
                summary_to_contract(service.get_active_incidents_summary("payment-gateway", REF_DT)),
                ensure_ascii=False,
            ),
            json.dumps(sla_audit_to_contract(service.evaluate_incident_sla("INC-2004", REF_DT)), ensure_ascii=False),
            json.dumps(sla_audit_to_contract(service.evaluate_incident_sla("INC-2006", REF_DT)), ensure_ascii=False),
            json.dumps(creation_to_contract(creation), ensure_ascii=False),
        ]

    sqlite_repository = SQLiteIncidentRepository(":memory:")
    pg_repository = PostgresIncidentRepository(pg_url)
    try:
        sqlite_bodies, pg_bodies = bodies(sqlite_repository), bodies(pg_repository)
    finally:
        sqlite_repository.close()
        pg_repository.close()
    assert '"duplicate_of": ["INC-2001", "INC-ABC1", "INC-abc1"]' in sqlite_bodies[-1]
    assert pg_bodies == sqlite_bodies


# ---------------------------------------------------------------------------
# US3 — estructura Docker (rápidas: aserciones de texto, sin pyyaml, research §R12)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCKERIGNORE_ENTRIES = (
    ".git", ".venv", "__pycache__", "*.pyc", ".pytest_cache", ".ruff_cache", ".env", ".env.*",
    "tests/", "specs/", "docs/", "data/", ".claude/", ".opencode/", ".specify/", "CONTEXT_LOG.md",
    "*.db", "*.sqlite", "*.sqlite3", "Dockerfile", "docker-compose.yml", ".dockerignore",
)


def _read(name: str) -> str:
    return (PROJECT_ROOT / name).read_text(encoding="utf-8")


def _service_block(compose: str, service: str) -> str:
    """Líneas del servicio `service` dentro de `services:` (indentación de dos espacios)."""
    lines = compose.splitlines()
    start = lines.index(f"  {service}:")
    block = []
    for line in lines[start + 1:]:
        if line and not line.startswith("   ") and not line.startswith("  #"):
            break
        block.append(line)
    return "\n".join(block)


def _directives(text: str) -> list:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


def test_dockerfile_estructura():
    dockerfile = _read("Dockerfile")
    directives = _directives(dockerfile)
    assert "FROM python:3.12-slim" in directives
    assert "ghcr.io/astral-sh/uv:0.13.8" in dockerfile
    assert "uv sync --frozen --no-dev --no-install-project" in dockerfile
    users = [line.split()[1] for line in directives if line.startswith("USER ")]
    assert users and users[-1] not in {"root", "0"}
    assert '"--host", "0.0.0.0"' in dockerfile
    assert "PYTHONUTF8=1" in dockerfile
    assert "DATABASE_URL=" not in dockerfile


def test_dockerignore_entradas_del_contrato():
    entries = set(_directives(_read(".dockerignore")))
    missing = [entry for entry in DOCKERIGNORE_ENTRIES if entry not in entries]
    assert not missing, missing


def test_compose_estructura():
    compose = _read("docker-compose.yml")
    db, api, db_test = (_service_block(compose, name) for name in ("db", "api", "db-test"))

    assert "image: postgres:16-alpine" in db and "image: postgres:16-alpine" in db_test
    assert "pg_isready" in db and "pg_isready" in db_test
    assert "--locale=C" in db and "--locale=C" in db_test
    assert "pgdata:/var/lib/postgresql/data" in db and "\nvolumes:\n  pgdata:" in compose
    assert "ports:" not in db, "la base del runtime no se publica en el host"
    assert "restart: unless-stopped" in db and "restart: unless-stopped" in api

    assert "condition: service_healthy" in api
    assert "/health" in api and "healthcheck:" in api
    assert "DATABASE_URL: postgresql://" in api and "@db:5432/" in api
    assert 'profiles: ["test"]' in db_test

    published = [line.strip() for line in compose.splitlines() if line.strip().startswith('- "') and ":" in line]
    port_lines = [line for line in published if line.count(":") >= 2 and "/" not in line.split(":")[-1]]
    assert port_lines and all(line.startswith('- "127.0.0.1:') for line in port_lines), port_lines

    # Sin contraseñas literales: solo `${POSTGRES_PASSWORD:-…}` (FR-018).
    for line in compose.splitlines():
        if "PASSWORD" in line and not line.strip().startswith("#"):
            assert "${POSTGRES_PASSWORD:-" in line, line


# ---------------------------------------------------------------------------
# US3 — contenedores (`@pytest.mark.docker`, proyectos aislados, RNF-011)
# ---------------------------------------------------------------------------

DEMO_SUMMARY_PATH = "/api/v1/incidents/summary?reference_time=2026-11-24T09:00:00"


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class ComposeProject:
    """Proyecto de composición aislado (`incidentops-t<uuid8>`) con su propio puerto."""

    def __init__(self) -> None:
        self.name = f"incidentops-t{uuid.uuid4().hex[:8]}"
        self.port = _free_port()
        self.env = {**os.environ, "API_HOST_PORT": str(self.port)}
        self.env.pop("DATABASE_URL", None)

    def compose(self, *args: str, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["docker", "compose", "-p", self.name, *args],
            cwd=PROJECT_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise AssertionError(f"docker compose {' '.join(args)} falló:\n{result.stdout}\n{result.stderr}")
        return result

    def container(self, service: str) -> str:
        return self.compose("ps", "-a", "-q", service).stdout.strip()

    def inspect(self, service: str, template: str) -> str:
        result = subprocess.run(
            ["docker", "inspect", "--format", template, self.container(service)],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def http(self, path: str, method: str = "GET", body: Optional[dict] = None) -> tuple:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8") or "null")

    def wait_for(self, predicate, timeout: float, interval: float = 1.0) -> float:
        """Espera a que `predicate()` sea verdadero; devuelve los segundos transcurridos."""
        started = time.monotonic()
        while True:
            try:
                if predicate():
                    return time.monotonic() - started
            except (OSError, urllib.error.URLError, ValueError):
                pass
            if time.monotonic() - started > timeout:
                raise AssertionError(f"condición no alcanzada en {timeout} s")
            time.sleep(interval)


@pytest.fixture
def compose_project():
    if not _docker_available():
        pytest.skip("Docker con Compose v2 no está disponible: casos de contenedores omitidos")
    project = ComposeProject()
    try:
        yield project
    finally:
        project.compose("down", "-v", "--rmi", "local", "--remove-orphans", check=False)


def _active_ids(project: ComposeProject) -> list:
    status, body = project.http(DEMO_SUMMARY_PATH)
    assert status == 200, body
    return sorted(item["incident_id"] for item in body["incidents"])


@pytest.mark.docker
def test_compose_config_valida(compose_project: ComposeProject):
    config = json.loads(compose_project.compose("--profile", "test", "config", "--format", "json").stdout)
    services = config["services"]
    assert set(services) == {"db", "api", "db-test"}
    assert services["db-test"]["profiles"] == ["test"]
    assert "ports" not in services["db"]
    assert services["api"]["depends_on"]["db"]["condition"] == "service_healthy"
    for name in ("api", "db-test"):
        assert all(port["host_ip"] == "127.0.0.1" for port in services[name]["ports"])
    assert "pgdata" in config["volumes"]


@pytest.mark.docker
def test_bdd_e12_entorno_nuevo(compose_project: ComposeProject):
    """
    Given un entorno sin contenedores ni volúmenes del proyecto
    When  se ejecuta `docker compose up -d --build --wait`
    Then  db queda sana antes de que arranque api, /health responde 200 y hay datos de demo
    """
    compose_project.compose("up", "-d", "--build", "--wait")

    assert compose_project.inspect("db", "{{.State.Health.Status}}") == "healthy"
    assert compose_project.inspect("api", "{{.State.Health.Status}}") == "healthy"
    assert compose_project.inspect("api", "{{.State.StartedAt}}") > compose_project.inspect("db", "{{.State.StartedAt}}")
    assert compose_project.http("/health") == (200, HEALTH_OK)
    assert _active_ids(compose_project) == sorted(DEMO_ACTIVE_IDS)


@pytest.mark.docker
def test_bdd_e13_persistencia_tras_reinicio(compose_project: ComposeProject):
    """
    Given el runtime en marcha con un incidente creado
    When  se detienen los servicios y se vuelven a levantar
    Then  el incidente sigue y los datos de demostración no se duplican
    """
    compose_project.compose("up", "-d", "--build", "--wait")
    status, body = compose_project.http(
        "/api/v1/incidents", "POST",
        {"incident_id": "INC-E13", "title": "Caída de pagos", "raw_text": CAIDA_PAGOS,
         "created_at": "2026-11-24T08:30:00"},
    )
    assert status == 201, body

    compose_project.compose("stop")
    compose_project.compose("up", "-d", "--wait")

    status, audit = compose_project.http("/api/v1/incidents/INC-E13/sla?reference_time=2026-11-24T09:00:00")
    assert status == 200 and audit["incident_id"] == "INC-E13"
    assert _active_ids(compose_project) == sorted(DEMO_ACTIVE_IDS | {"INC-E13"})


@pytest.mark.docker
def test_bdd_e14_caida_de_la_base(compose_project: ComposeProject):
    """
    Given el runtime sano
    When  se detiene db y después se vuelve a arrancar
    Then  /health pasa a 503 y api a «unhealthy» en ≤ 60 s, y vuelve a «healthy» en ≤ 60 s
          sin reiniciar la API
    """
    compose_project.compose("up", "-d", "--build", "--wait")
    started_at = compose_project.inspect("api", "{{.State.StartedAt}}")

    compose_project.compose("stop", "db")
    compose_project.wait_for(lambda: compose_project.http("/health") == (503, HEALTH_KO), timeout=15)
    compose_project.wait_for(lambda: compose_project.inspect("api", "{{.State.Health.Status}}") == "unhealthy", 60)

    compose_project.compose("start", "db")
    compose_project.wait_for(lambda: compose_project.inspect("api", "{{.State.Health.Status}}") == "healthy", 60)
    assert compose_project.http("/health") == (200, HEALTH_OK)
    assert compose_project.inspect("api", "{{.State.StartedAt}}") == started_at


@pytest.mark.docker
def test_bdd_e15_exposicion_minima(compose_project: ComposeProject):
    """
    Given el runtime en marcha
    When  se consultan los puertos publicados
    Then  api solo escucha en el loopback del host y db no está publicada
    """
    compose_project.compose("up", "-d", "--build", "--wait")
    api_port = compose_project.compose("port", "api", "8080").stdout.strip()
    assert api_port == f"127.0.0.1:{compose_project.port}"
    # Según la versión de Compose, un puerto sin publicar sale con error o imprime
    # `invalid IP:0` con código 0; en ningún caso es una dirección `<ip>:<puerto>` válida.
    db_port = compose_project.compose("port", "db", "5432", check=False)
    assert db_port.returncode != 0 or not re.fullmatch(r"[\d.:\[\]a-f]+:[1-9]\d*", db_port.stdout.strip())
    assert compose_project.inspect("db", "{{json .HostConfig.PortBindings}}") in {"{}", "null"}


@pytest.mark.docker
def test_bdd_e16_imagen_limpia(compose_project: ComposeProject):
    """
    Given la imagen construida
    When  se inspecciona el contenedor de api
    Then  no corre como root, no tiene dependencias de desarrollo ni archivos del host
    """
    compose_project.compose("up", "-d", "--build", "--wait")

    def run(*command: str) -> subprocess.CompletedProcess:
        return compose_project.compose("exec", "-T", "api", *command, check=False)

    assert run("id", "-u").stdout.strip() not in {"", "0"}
    assert run("python", "-c", "import pytest").returncode != 0
    listing = set(run("ls", "-A", "/app").stdout.split())
    assert listing >= {"src", ".venv", "pyproject.toml", "uv.lock"}
    assert not listing & {".git", "tests", ".env", ".claude", ".opencode", ".specify", "specs", "docs", "data"}
    # El venv es el de la imagen (Linux), no el del host (Windows usa Scripts/).
    assert "Scripts" not in run("ls", "/app/.venv").stdout.split()


@pytest.mark.docker
def test_bdd_e17_arranque_degradado(compose_project: ComposeProject):
    """
    Given la base detenida
    When  se arranca solo api y después la base
    Then  api arranca y responde 503; con la base sana responde 200 y la demo está una sola vez
    """
    compose_project.compose("up", "-d", "--build", "--no-deps", "api")
    compose_project.wait_for(lambda: compose_project.http("/health") == (503, HEALTH_KO), timeout=60)

    compose_project.compose("up", "-d", "--wait", "db")
    compose_project.wait_for(lambda: compose_project.http("/health") == (200, HEALTH_OK), timeout=60)
    assert _active_ids(compose_project) == sorted(DEMO_ACTIVE_IDS)
