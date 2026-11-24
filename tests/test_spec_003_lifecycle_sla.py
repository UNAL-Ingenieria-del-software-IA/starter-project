"""Aceptación de la spec 003 — Ciclo de vida de incidentes y auditoría de SLA (H003).

Bloques:
1. Conformidad del puerto v3 (contracts/incident-repository-port.md): forma, batería
   compartida entre `SQLiteIncidentRepository` y el doble en memoria, migración aditiva de
   archivos de H002 e índice `idx_incidents_dup_key`.
2. Historia 1 — Crear un incidente (⭐E1, E3, E4, E15a, E15b, E17–E21).
3. Historia 2 — Aviso de duplicado abierto (⭐E5, E6, E8, E22, E23).
4. Historia 3 — Auditoría de SLA (E2, E9, E10, ⭐E11, ⭐E12, ⭐E13, ⭐E14, E16).
5. SC-006 — rendimiento por canal con 10 000 abiertos.

Cada escenario usa su propio almacén SQLite en `tmp_path` (o el doble en memoria cuando
el escenario lo pide) y un reloj fijo.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
import sqlite3
import threading
import time
import typing
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import create_cli
from src.adapters.outbound.demo_incidents import seed_demo_incidents
from src.adapters.outbound.id_generator import RandomHexIdGenerator
from src.adapters.outbound.null_repository import NullIncidentRepository
from src.adapters.outbound.sqlite_repository import SELECT_OPEN_DUPLICATES_SQL, SQLiteIncidentRepository
from src.application.ports import IncidentIdConflictError, IncidentIdGeneratorPort, IncidentRepositoryPort
from src.application.services import CreateIncidentInput, IncidentService
from src.domain.models import Incident, IncidentReport
from src.domain.triage_rules import classify_incident
from src.domain.working_time_calculator import BOGOTA_TZ
from src.main import build_service
from tests.doubles import FailingOnAddRepository, InMemoryIncidentRepository, SequenceIdGenerator

INCIDENTS_PATH = "/api/v1/incidents"
SUMMARY_PATH = "/api/v1/incidents/summary"
APP_LOGGER = "src.adapters.inbound.api.app"


def sla_path(incident_id: str) -> str:
    return f"{INCIDENTS_PATH}/{incident_id}/sla"


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """Instante de noviembre de 2026 en hora de Bogotá."""
    return datetime(2026, 11, day, hour, minute, tzinfo=BOGOTA_TZ)


# Martes 2026-11-24 en Bogotá: instantes comunes de los escenarios.
NOW_0910 = at(24, 9, 10)
REF = at(24, 9, 0)

CAIDA_PAGOS_TITULO = "Caída de la pasarela de pagos"
CAIDA_PAGOS = "La pasarela de pagos está caída, ningún cliente puede pagar"
CAIDA_PAGOS_URGENTE = "URGENTE: la pasarela de pagos está caída, ningún cliente puede pagar; lo necesitamos para hoy"
CAIDA_PAGOS_RECURRENTE = "Otra vez se cayó la pasarela de pagos"
CAIDA_AUTH = "El login está caído para todos los usuarios"
BOTON_DESALINEADO = "El botón de exportar está desalineado"
OTRO_BOTON_DESALINEADO = "El botón de guardar está desalineado en la interfaz"
SIN_CLASIFICAR = "Algo raro pasa con el sistema"
OTRO_SIN_CLASIFICAR = "Alguien comenta que algo no se ve bien"

GENERATED_ID = re.compile(r"^INC-[0-9A-F]{8}$")


# ---------------------------------------------------------------------------
# Utilidades de las pruebas
# ---------------------------------------------------------------------------


def seeded(
    incident_id: str,
    text: str,
    created_at: datetime,
    *,
    status: str = "OPEN",
    resolved_at: Optional[datetime] = None,
    severity: Optional[str] = None,
) -> Incident:
    """Incidente previo con componente, equipo y clave derivados del triaje del dominio."""
    triage = classify_incident(IncidentReport(incident_id, text, created_at))
    return Incident(
        incident_id=incident_id,
        title=text,
        component=triage.component,
        severity=severity or triage.severity,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        created_at=created_at,
        resolved_at=resolved_at,
        recommended_team=triage.recommended_team,
        duplicate_group_key=triage.duplicate_group_key,
    )


@pytest.fixture
def stores(tmp_path) -> typing.Iterator[Callable[..., SQLiteIncidentRepository]]:
    """Fábrica de almacenes SQLite desechables en `tmp_path`; los cierra al terminar."""
    opened: List[SQLiteIncidentRepository] = []
    counter = iter(range(1_000))

    def make(*incidents: Incident, name: Optional[str] = None) -> SQLiteIncidentRepository:
        path = tmp_path / (name or f"incidents-{next(counter)}.db")
        repository = SQLiteIncidentRepository(str(path))
        opened.append(repository)
        for incident in incidents:
            repository.save_incident(incident)
        return repository

    yield make
    for repository in opened:
        repository.close()  # En Windows, un archivo abierto impide limpiar tmp_path.


def channels(service: IncidentService):
    """Canal HTTP y CLI sobre el mismo servicio (en proceso, sin red ni subprocess)."""
    return TestClient(create_app(service)), create_cli(lambda now: service), CliRunner()


def create_args(payload: Dict[str, str]) -> List[str]:
    """Traduce un cuerpo de creación a las opciones equivalentes de `create`."""
    args = ["create"]
    for field, value in payload.items():
        args += [f"--{field.replace('_', '-')}", value]
    return args + ["--format", "json"]


def snapshot(repository: IncidentRepositoryPort, *incident_ids: str) -> List[Optional[Incident]]:
    return [repository.get_incident(incident_id) for incident_id in incident_ids]


# ---------------------------------------------------------------------------
# 1. Conformidad del puerto v3
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "implementation",
    [SQLiteIncidentRepository, NullIncidentRepository, InMemoryIncidentRepository],
    ids=lambda cls: cls.__name__,
)
@pytest.mark.parametrize("method", ["add_incident", "find_open_duplicates"])
def test_forma_de_los_metodos_nuevos_del_puerto(implementation, method):
    """
    Given el puerto enmendado por spec 003 y una implementación concreta
    When  se comparan las firmas de add_incident y find_open_duplicates
    Then  coinciden nombres, clases, valores por defecto y tipos resueltos
    """
    expected = getattr(IncidentRepositoryPort, method)
    actual = getattr(implementation, method, None)
    assert callable(actual), f"{implementation.__name__} no implementa {method}"

    def shape(func):
        return [(p.name, p.kind, p.default) for p in inspect.signature(func).parameters.values()]

    assert shape(actual) == shape(expected)
    assert typing.get_type_hints(actual) == typing.get_type_hints(expected)


@pytest.mark.parametrize("generator", [RandomHexIdGenerator, SequenceIdGenerator], ids=lambda cls: cls.__name__)
def test_forma_del_generador_de_identificadores(generator):
    expected = inspect.signature(IncidentIdGeneratorPort.new_id)
    actual = inspect.signature(generator.new_id)
    assert list(actual.parameters) == list(expected.parameters)


def test_el_generador_aleatorio_produce_la_forma_publica():
    ids = {RandomHexIdGenerator().new_id() for _ in range(50)}
    assert all(GENERATED_ID.fullmatch(item) for item in ids)
    assert len(ids) == 50


@pytest.fixture(params=["memoria", "sqlite"])
def repo(request, stores) -> IncidentRepositoryPort:
    return InMemoryIncidentRepository() if request.param == "memoria" else stores()


def test_insertar_un_identificador_existente_es_conflicto_sin_tocar_el_original(repo):
    original = seeded("INC-A", CAIDA_PAGOS, REF)
    repo.add_incident(original)
    with pytest.raises(IncidentIdConflictError) as raised:
        repo.add_incident(seeded("INC-A", CAIDA_AUTH, REF + timedelta(hours=1)))
    assert raised.value.incident_id == "INC-A"
    assert repo.get_incident("INC-A") == original


def test_insertar_con_severidad_sin_politica_se_rechaza(repo):
    with pytest.raises(ValueError):
        repo.add_incident(seeded("INC-X", CAIDA_PAGOS, REF, severity="P9"))


def test_duplicados_abiertos_filtran_por_clave_estado_y_excluido(repo):
    """
    Given abiertos en los tres estados activos, un resuelto, otra clave y uno sin clave
    When  se buscan los abiertos de la clave de pagos excluyendo uno
    Then  vuelven solo los activos de esa clave, sin el excluido, por creación e identificador
    """
    for incident in (
        seeded("INC-B", CAIDA_PAGOS, REF + timedelta(days=3)),
        seeded("INC-A", CAIDA_PAGOS, REF, status="IN_PROGRESS"),
        seeded("INC-A2", CAIDA_PAGOS, REF, status="ESCALATION_REQUIRED"),
        seeded("INC-C", CAIDA_PAGOS, REF + timedelta(minutes=5)),
        seeded("INC-D", CAIDA_PAGOS, REF, status="RESOLVED", resolved_at=REF + timedelta(hours=1)),
        seeded("INC-E", CAIDA_AUTH, REF),
        seeded("INC-F", BOTON_DESALINEADO, REF),
    ):
        repo.save_incident(incident)
    found = repo.find_open_duplicates("payment-availability", "INC-C")
    assert [item.incident_id for item in found] == ["INC-A", "INC-A2", "INC-B"]
    assert all(item.duplicate_group_key == "payment-availability" for item in found)


def test_ida_y_vuelta_de_los_nueve_campos(repo):
    incident = seeded(
        "INC-R", CAIDA_PAGOS, datetime(2026, 11, 24, 8, 0), status="RESOLVED", resolved_at=datetime(2026, 11, 24, 8, 45)
    )
    repo.add_incident(incident)
    stored = repo.get_incident("INC-R")
    assert stored is not None
    assert stored.created_at == at(24, 8) and stored.resolved_at == at(24, 8, 45)
    assert (stored.recommended_team, stored.duplicate_group_key) == ("Backend-Core", "payment-availability")
    assert stored == Incident(
        "INC-R",
        CAIDA_PAGOS,
        incident.component,
        incident.severity,
        "RESOLVED",
        at(24, 8),
        resolved_at=at(24, 8, 45),
        recommended_team="Backend-Core",
        duplicate_group_key="payment-availability",
    )


def test_un_archivo_de_h002_se_migra_sin_perder_filas(tmp_path):
    """
    Given un archivo SQLite creado con el esquema de H002 (siete columnas) y una fila
    When  se abre con el adaptador de H003, dos veces
    Then  gana las columnas nuevas, conserva la fila y acepta incidentes con clave
    """
    path = tmp_path / "h002.db"
    connection = sqlite3.connect(str(path))
    with connection:
        connection.execute(
            "CREATE TABLE sla_policies (severity TEXT PRIMARY KEY, max_resolution_minutes INTEGER NOT NULL, "
            "operates_24x7 INTEGER NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE incidents (incident_id TEXT PRIMARY KEY, title TEXT NOT NULL, component TEXT NOT NULL, "
            "severity TEXT NOT NULL REFERENCES sla_policies (severity), status TEXT NOT NULL, "
            "created_at TEXT NOT NULL, resolved_at TEXT)"
        )
        connection.execute(
            "INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("INC-H002", "Heredado", "payment-gateway", "P1", "OPEN", at(24, 8).isoformat(timespec="microseconds"), None),
        )
    connection.close()

    for _ in range(2):  # La migración es idempotente.
        repository = SQLiteIncidentRepository(str(path))
        try:
            columns = {row[1] for row in repository._connection.execute("PRAGMA table_info(incidents)")}
            assert {"recommended_team", "duplicate_group_key"} <= columns
            legacy = repository.get_incident("INC-H002")
            assert legacy is not None and legacy.title == "Heredado"
            assert (legacy.recommended_team, legacy.duplicate_group_key) == (None, None)
            if repository.get_incident("INC-NUEVO") is None:
                repository.add_incident(seeded("INC-NUEVO", CAIDA_PAGOS, REF))
            assert [i.incident_id for i in repository.find_open_duplicates("payment-availability", "-")] == ["INC-NUEVO"]
        finally:
            repository.close()


def test_la_busqueda_de_duplicados_usa_su_indice_parcial(stores):
    repository = stores(*(seeded(f"INC-{n:03d}", CAIDA_PAGOS if n % 2 else CAIDA_AUTH, REF) for n in range(50)))
    plan = " | ".join(
        row[-1]
        for row in repository._connection.execute(
            "EXPLAIN QUERY PLAN " + SELECT_OPEN_DUPLICATES_SQL, ("payment-availability", "INC-000")
        )
    )
    assert "idx_incidents_dup_key" in plan
    assert "sla_policies" in plan


# ---------------------------------------------------------------------------
# 2. Historia 1 — Crear un incidente cuando llega
# ---------------------------------------------------------------------------


def test_bdd_e1_registro_inicial_sin_duplicados(stores):
    """
    E1 — Registro inicial sin duplicados previos
    Given que no hay ningún incidente abierto de la pasarela de pagos
    And   el reloj marca las 09:10 del 24 de noviembre de 2026
    When  la persona de guardia registra por la web un incidente titulado "Caída de la
          pasarela de pagos" con el texto "La pasarela de pagos está caída, ningún cliente
          puede pagar", sin identificador, sin estado y sin instante de creación
    Then  el registro es exitoso (201 Created)
    And   el incidente recibe un identificador generado: INC- seguido de 8 dígitos hexadecimales
    And   queda abierto y creado a las 09:10 hora de Bogotá (status = OPEN)
    And   trae la clasificación completa que el triaje canónico asigna a ese texto,
          incluida su clave de grupo de duplicados
    And   el sistema confirma que no duplica ningún incidente abierto
          (is_duplicate = false, duplicate_of = [])
    """
    repository = stores()
    client, _, _ = channels(build_service(NOW_0910, repository))

    response = client.post(INCIDENTS_PATH, json={"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS})

    assert response.status_code == 201
    body = response.json()
    assert GENERATED_ID.fullmatch(body["incident_id"])
    assert body["status"] == "OPEN"
    assert body["created_at"] == "2026-11-24T09:10:00-05:00"
    assert body["resolved_at"] is None
    canonical = classify_incident(IncidentReport("R1", CAIDA_PAGOS, NOW_0910))
    assert (body["severity"], body["component"], body["recommended_team"], body["action"]) == (
        canonical.severity,
        canonical.component,
        canonical.recommended_team,
        canonical.action,
    )
    assert body["duplicate_group_key"] == canonical.duplicate_group_key == "payment-availability"
    assert body["is_duplicate"] is False
    assert body["duplicate_of"] == []
    assert repository.get_incident(body["incident_id"]) is not None


def test_bdd_e3_la_urgencia_no_cambia_la_severidad(stores):
    """
    E3 — La urgencia declarada no cambia la severidad
    Given dos reportes con el mismo texto de impacto, uno de ellos con las palabras
          "URGENTE" y "para hoy"
    When  se crean ambos incidentes
    Then  los dos reciben la misma severidad (Art. 1.4)
    """
    client, _, _ = channels(build_service(NOW_0910, stores()))

    plain = client.post(INCIDENTS_PATH, json={"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS})
    urgent = client.post(INCIDENTS_PATH, json={"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS_URGENTE})

    assert plain.status_code == urgent.status_code == 201
    assert plain.json()["severity"] == urgent.json()["severity"]


def test_bdd_e4_el_creado_aparece_en_el_resumen_de_activos(stores):
    """
    E4 — Un incidente creado aparece en el resumen de activos
    Given un incidente abierto recién creado
    When  se consulta el resumen de incidentes activos de H002 en un instante posterior
          a su creación
    Then  el incidente aparece en el detalle y cuenta en el total activo
    """
    client, _, _ = channels(build_service(NOW_0910, stores()))
    created = client.post(INCIDENTS_PATH, json={"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS}).json()

    summary = client.get(SUMMARY_PATH, params={"reference_time": "2026-11-24T09:30:00"})

    assert summary.status_code == 200
    body = summary.json()
    assert body["total_active"] == 1
    assert [item["incident_id"] for item in body["incidents"]] == [created["incident_id"]]


def test_bdd_e19_se_respeta_el_identificador_del_cliente(stores):
    """
    E19 — El identificador enviado por el cliente se respeta
    Given que no existe el incidente INC-CLIENTE-01
    When  se crea un incidente con identificador INC-CLIENTE-01
    Then  la creación es exitosa y el incidente queda guardado con ese identificador
    """
    repository = stores()
    client, _, _ = channels(build_service(NOW_0910, repository))

    response = client.post(
        INCIDENTS_PATH, json={"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS, "incident_id": "INC-CLIENTE-01"}
    )

    assert response.status_code == 201
    assert response.json()["incident_id"] == "INC-CLIENTE-01"
    stored = repository.get_incident("INC-CLIENTE-01")
    assert stored is not None and stored.title == CAIDA_PAGOS_TITULO


def test_bdd_e20_identificador_repetido_se_rechaza_sin_tocar_el_existente(stores):
    """
    E20 — Un identificador repetido se rechaza sin tocar el existente
    Given el incidente existente INC-2001
    When  se crea otro incidente con identificador INC-2001
    Then  HTTP responde 409 con código incident_id_conflict y el CLI termina con código de salida 1
    And   INC-2001 conserva todos sus datos
    """
    repository = stores()
    seed_demo_incidents(repository)
    before = repository.get_incident("INC-2001")
    client, cli_app, runner = channels(build_service(REF, repository))
    payload = {"title": "Otro título", "raw_text": CAIDA_AUTH, "incident_id": "INC-2001"}

    http = client.post(INCIDENTS_PATH, json=payload)
    cli = runner.invoke(cli_app, create_args(payload))

    assert http.status_code == 409
    assert http.json()["error"]["code"] == "incident_id_conflict"
    assert http.json()["error"]["field"] == "incident_id"
    assert cli.exit_code == 1
    assert "[incident_id_conflict]" in cli.stderr and cli.stdout == ""
    assert repository.get_incident("INC-2001") == before


E21_CASES = [
    pytest.param("IN_PROGRESS", None, "IN_PROGRESS", id="E21.1-en-curso"),
    pytest.param("ESCALATION_REQUIRED", None, "ESCALATION_REQUIRED", id="E21.2-escalado"),
    pytest.param("RESOLVED", "2026-11-24T08:30:00", "RESOLVED", id="E21.3-resuelto-completo"),
    pytest.param("RESOLVED", None, None, id="E21.4-resuelto-incompleto"),
    pytest.param("OPEN", "2026-11-24T08:30:00", None, id="E21.5-resolucion-en-abierto"),
    pytest.param("RESOLVED", "2026-11-24T07:30:00", None, id="E21.6-resolucion-previa"),
    pytest.param("CLOSED", None, None, id="E21.7-estado-inexistente"),
]


@pytest.mark.parametrize("status, resolved_at, expected_status", E21_CASES)
def test_bdd_e21_el_estado_inicial_puede_informarse(stores, status, resolved_at, expected_status):
    """
    E21 — El estado inicial puede informarse
    Given una creación con estado <estado> y <resolución>
    When  se envía
    Then  el resultado es <resultado>
    """
    payload = {"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS, "created_at": "2026-11-24T08:00:00", "status": status}
    if resolved_at is not None:
        payload["resolved_at"] = resolved_at
    http_store, cli_store = stores(), stores()
    client, _, _ = channels(build_service(REF, http_store))
    _, cli_app, runner = channels(build_service(REF, cli_store))

    http = client.post(INCIDENTS_PATH, json=payload)
    cli = runner.invoke(cli_app, create_args(payload))

    if expected_status is not None:
        assert http.status_code == 201 and cli.exit_code == 0
        for body in (http.json(), json.loads(cli.stdout)):
            assert body["status"] == expected_status
            expected_resolution = None if resolved_at is None else resolved_at + "-05:00"
            assert body["resolved_at"] == expected_resolution
    else:
        assert http.status_code == 422
        assert http.json()["error"]["code"] == "invalid_payload"
        assert cli.exit_code == 1 and cli.stdout == ""
        assert "[invalid_payload]" in cli.stderr
        assert list(http_store.list_active_incidents()) == list(cli_store.list_active_incidents()) == []


E15A_CASES = [
    pytest.param({"title": "   "}, "invalid_payload", id="E15a.1-titulo-vacio"),
    pytest.param({"raw_text": "   "}, "invalid_payload", id="E15a.2-texto-vacio"),
    pytest.param({"raw_text": "x" * 5_001}, "invalid_payload", id="E15a.3-texto-largo"),
    pytest.param({"title": "x" * 201}, "invalid_payload", id="E15a.4-titulo-largo"),
    pytest.param({"incident_id": "incidente-7"}, "invalid_payload", id="E15a.5-identificador-mal-formado"),
    pytest.param({"created_at": "ayer"}, "invalid_timestamp", id="E15a.6-instante-ilegible"),
]


@pytest.mark.parametrize("defect, code", E15A_CASES)
def test_bdd_e15a_contenido_inaceptable_no_guarda_nada(stores, defect, code):
    """
    E15a — Una creación con contenido inaceptable no guarda nada
    Given una creación con <defecto>
    When  se envía por la web y por la terminal
    Then  ambos canales la rechazan sin guardar nada
    And   HTTP responde 422 con código <código> y el CLI termina con código de salida 1
    """
    payload = {"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS, **defect}
    repository = stores()
    client, cli_app, runner = channels(build_service(REF, repository))

    http = client.post(INCIDENTS_PATH, json=payload)
    cli = runner.invoke(cli_app, create_args(payload))

    assert http.status_code == 422
    assert http.json()["error"]["code"] == code
    assert cli.exit_code == 1 and cli.stdout == ""
    assert f"[{code}]" in cli.stderr
    assert list(repository.list_active_incidents()) == []


E15B_CASES = [pytest.param("priority", "invalid_payload", id="E15b.1-desconocido")] + [
    pytest.param(field, "reserved_field", id=f"E15b.2-reservado-{field}")
    for field in ("severity", "component", "recommended_team", "action", "duplicate_group_key")
]


@pytest.mark.parametrize("field, http_code", E15B_CASES)
def test_bdd_e15b_fuera_de_contrato_no_guarda_nada(stores, field, http_code):
    """
    E15b — Una creación que no respeta el contrato no guarda nada
    Given una creación que incluye <campo>
    When  se envía por la web y por la terminal
    Then  ambos canales la rechazan sin guardar nada
    And   HTTP responde 400 y el CLI termina con código de salida 2
    """
    repository = stores()
    client, cli_app, runner = channels(build_service(REF, repository))
    payload = {"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS, field: "P0"}

    http = client.post(INCIDENTS_PATH, json=payload)
    cli = runner.invoke(cli_app, create_args(payload))

    assert http.status_code == 400
    assert http.json()["error"]["code"] == http_code
    assert cli.exit_code == 2 and cli.stdout == ""
    assert list(repository.list_active_incidents()) == []


def test_bdd_e17_fallo_del_almacen_al_crear():
    """
    E17 — Fallo del almacén al crear
    Given un almacén que falla al guardar
    When  se crea un incidente
    Then  HTTP responde 500 con código internal_error y el CLI termina con código de salida 4
    And   no se devuelve identificador ni queda un registro parcial
    """
    repository = FailingOnAddRepository()
    service = build_service(REF, repository)
    client = TestClient(create_app(service), raise_server_exceptions=False)
    cli_app, runner = create_cli(lambda now: service), CliRunner()
    payload = {"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS}

    http = client.post(INCIDENTS_PATH, json=payload)
    cli = runner.invoke(cli_app, create_args(payload))

    assert http.status_code == 500
    assert http.json() == {"error": {"code": "internal_error", "message": "Error interno al procesar la petición."}}
    assert cli.exit_code == 4 and cli.stdout == ""
    assert cli.stderr.strip() == "error [internal_error]: RuntimeError"
    assert list(repository.list_active_incidents()) == []


def test_bdd_e18_la_creacion_no_expone_el_contenido_en_las_trazas(stores, caplog):
    """
    E18 — La creación no expone el contenido del reporte en las trazas
    Given un incidente con un texto y un título identificables
    When  se crea
    Then  la creación es exitosa
    And   ninguna traza incluye el texto ni el título; solo el identificador, si es
          duplicado, el número de duplicados, la duración y el código de resultado
    """
    title = "Título-secreto-7Q2"
    raw_text = "La pasarela de pagos está caída; marcador-confidencial-9Z4"
    client, _, _ = channels(build_service(NOW_0910, stores()))

    with caplog.at_level(logging.DEBUG):
        response = client.post(INCIDENTS_PATH, json={"title": title, "raw_text": raw_text})

    assert response.status_code == 201
    assert title not in caplog.text and "marcador-confidencial-9Z4" not in caplog.text
    app_lines = [record.getMessage() for record in caplog.records if record.name == APP_LOGGER]
    assert len(app_lines) == 1
    line = app_lines[0]
    assert response.json()["incident_id"] in line
    assert "is_duplicate=False" in line and "duplicados=0" in line
    assert "duracion_ms=" in line and "codigo=201" in line


# ---------------------------------------------------------------------------
# 3. Historia 2 — Enterarse de que ya existe un duplicado abierto
# ---------------------------------------------------------------------------


def test_bdd_e5_duplicado_abierto_ignora_resueltos(stores):
    """
    E5 — Detección de duplicado abierto, ignorando los resueltos
    Given un incidente abierto por caída de la pasarela de pagos, INC-0000A001
    And   un incidente ya resuelto por una caída anterior de la pasarela de pagos, INC-0000A002
    When  la persona de guardia registra un incidente nuevo por otra caída de la pasarela de pagos
    Then  el registro es exitoso (201 Created) con un identificador nuevo
    And   el sistema avisa que el incidente nuevo duplica uno abierto (is_duplicate = true)
    And   el aviso señala solo al incidente abierto (duplicate_of = ["INC-0000A001"])
    And   el incidente resuelto INC-0000A002 no aparece en el aviso, aunque trate del mismo problema
    And   ninguno de los dos incidentes previos cambia de estado ni de datos
    """
    repository = stores(
        seeded("INC-0000A001", CAIDA_PAGOS, at(24, 8)),
        seeded("INC-0000A002", CAIDA_PAGOS, at(20, 10), status="RESOLVED", resolved_at=at(20, 12)),
    )
    before = snapshot(repository, "INC-0000A001", "INC-0000A002")
    client, _, _ = channels(build_service(NOW_0910, repository))

    response = client.post(INCIDENTS_PATH, json={"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS})

    assert response.status_code == 201
    body = response.json()
    assert body["incident_id"] not in {"INC-0000A001", "INC-0000A002"}
    assert body["is_duplicate"] is True
    assert body["duplicate_of"] == ["INC-0000A001"]
    assert "INC-0000A002" not in body["duplicate_of"]
    assert snapshot(repository, "INC-0000A001", "INC-0000A002") == before


E6_CASES = [
    pytest.param(CAIDA_AUTH, "OPEN", CAIDA_PAGOS, id="E6.1-otra-clave"),
    pytest.param(CAIDA_PAGOS, "RESOLVED", CAIDA_PAGOS, id="E6.2-coincidente-resuelto"),
    pytest.param(BOTON_DESALINEADO, "OPEN", OTRO_BOTON_DESALINEADO, id="E6.3-sin-clave"),
    pytest.param(SIN_CLASIFICAR, "OPEN", OTRO_SIN_CLASIFICAR, id="E6.4-sin-clasificar"),
]


@pytest.mark.parametrize("existing_text, existing_status, new_text", E6_CASES)
def test_bdd_e6_sin_aviso_cuando_no_hay_abierto_con_la_misma_clave(stores, existing_text, existing_status, new_text):
    """
    E6 — Sin aviso cuando no hay un abierto con la misma clave
    Given <situación del almacén>
    When  se crea <incidente>
    Then  la creación es exitosa y el incidente no es duplicado de ningún abierto
    """
    resolved_at = at(24, 8, 30) if existing_status == "RESOLVED" else None
    existing = seeded("INC-0000E001", existing_text, at(24, 8), status=existing_status, resolved_at=resolved_at)
    client, _, _ = channels(build_service(NOW_0910, stores(existing)))

    response = client.post(INCIDENTS_PATH, json={"title": new_text, "raw_text": new_text})

    assert response.status_code == 201
    body = response.json()
    assert body["is_duplicate"] is False
    assert body["duplicate_of"] == []
    if existing_text in (BOTON_DESALINEADO, SIN_CLASIFICAR):
        # Los ejemplos sin clave lo son porque el triaje no asigna ninguna.
        assert body["duplicate_group_key"] is None and existing.duplicate_group_key is None
    if existing_text == SIN_CLASIFICAR:
        assert body["component"] == existing.component == "unclassified"


def test_bdd_e8_creaciones_simultaneas_del_mismo_problema(stores):
    """
    E8 — Creaciones simultáneas del mismo problema
    Given que no hay incidentes abiertos de la pasarela de pagos
    When  se crean al mismo tiempo dos incidentes por caída de la pasarela de pagos
    Then  ambos quedan guardados con identificadores distintos
    And   al menos uno de los dos es duplicado del otro
    """
    repository = stores()
    service = build_service(NOW_0910, repository)
    barrier = threading.Barrier(2)
    results, errors = [], []

    def create() -> None:
        try:
            barrier.wait(timeout=5)
            results.append(service.create_incident(CreateIncidentInput(CAIDA_PAGOS_TITULO, CAIDA_PAGOS)))
        except Exception as exc:  # noqa: BLE001 — se reporta en la aserción.
            errors.append(exc)

    workers = [threading.Thread(target=create) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert errors == [] and len(results) == 2
    first, second = results
    assert first.incident.incident_id != second.incident.incident_id
    assert all(repository.get_incident(item.incident.incident_id) is not None for item in results)
    assert (second.incident.incident_id in first.duplicate_of) or (first.incident.incident_id in second.duplicate_of)


def test_bdd_e22_ni_la_antiguedad_ni_la_recurrencia_impiden_el_aviso(stores):
    """
    E22 — Ni la antigüedad ni la recurrencia impiden el aviso
    Given un incidente abierto por caída de la pasarela de pagos creado tres días antes
    When  se crea un incidente con el texto "Otra vez se cayó la pasarela de pagos"
    Then  el incidente nuevo es duplicado del abierto, porque comparten clave de grupo
    """
    old = seeded("INC-0000C001", CAIDA_PAGOS, NOW_0910 - timedelta(days=3))
    client, _, _ = channels(build_service(NOW_0910, stores(old)))

    response = client.post(INCIDENTS_PATH, json={"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS_RECURRENTE})

    assert response.status_code == 201
    body = response.json()
    assert body["duplicate_group_key"] == old.duplicate_group_key
    assert body["is_duplicate"] is True
    assert body["duplicate_of"] == ["INC-0000C001"]


def test_bdd_e23_un_creado_ya_resuelto_no_genera_avisos_en_otros(stores):
    """
    E23 — Un incidente creado ya resuelto no genera avisos en otros
    Given un incidente por caída de la pasarela de pagos creado directamente en estado RESOLVED
    When  se crea después otro incidente por caída de la pasarela de pagos
    Then  el segundo no es duplicado del primero
    """
    client, _, _ = channels(build_service(NOW_0910, stores()))
    first = client.post(
        INCIDENTS_PATH,
        json={
            "title": CAIDA_PAGOS_TITULO,
            "raw_text": CAIDA_PAGOS,
            "created_at": "2026-11-24T08:00:00",
            "status": "RESOLVED",
            "resolved_at": "2026-11-24T08:30:00",
        },
    )
    assert first.status_code == 201

    second = client.post(INCIDENTS_PATH, json={"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS})

    assert second.status_code == 201
    assert second.json()["is_duplicate"] is False
    assert first.json()["incident_id"] not in second.json()["duplicate_of"]


# ---------------------------------------------------------------------------
# 4. Historia 3 — Auditar cómo va el SLA de un incidente
# ---------------------------------------------------------------------------


def test_bdd_e2_el_incidente_sobrevive_al_reinicio(tmp_path):
    """
    E2 — El incidente sobrevive al reinicio
    Given un incidente creado en un almacén persistente
    And   el servicio reiniciado sobre el mismo almacén
    When  se audita el SLA de ese incidente por su identificador
    Then  la consulta es exitosa
    And   el título, el componente, la severidad, el estado y el instante de creación son
          los mismos que devolvió la creación
    """
    path = str(tmp_path / "persistente.db")
    first = SQLiteIncidentRepository(path)
    try:
        client, _, _ = channels(build_service(NOW_0910, first))
        created = client.post(INCIDENTS_PATH, json={"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS}).json()
    finally:
        first.close()

    restarted = SQLiteIncidentRepository(path)
    try:
        client, _, _ = channels(build_service(NOW_0910 + timedelta(minutes=20), restarted))
        response = client.get(sla_path(created["incident_id"]))
    finally:
        restarted.close()

    assert response.status_code == 200
    audit = response.json()
    for field in ("incident_id", "title", "component", "severity", "status", "created_at"):
        assert audit[field] == created[field], field


def test_bdd_e9_sla_de_un_incidente_activo(stores):
    """
    E9 — SLA de un incidente activo
    Given un incidente abierto de severidad P0 creado a las 09:00 del 24 de noviembre de 2026
    When  la persona de guardia audita su SLA por la web con instante de referencia 09:50
    Then  obtiene una consulta exitosa
    And   muestra 50 minutos transcurridos, 60 permitidos y 10 restantes
    And   el incidente requiere escalamiento y no está incumplido
    """
    client, _, _ = channels(build_service(REF, stores(seeded("INC-0000D009", CAIDA_PAGOS, at(24, 9), severity="P0"))))

    response = client.get(sla_path("INC-0000D009"), params={"reference_time": "2026-11-24T09:50:00"})

    assert response.status_code == 200
    body = response.json()
    assert (body["elapsed_minutes"], body["allowed_minutes"], body["remaining_minutes"]) == (50, 60, 10)
    assert body["requires_escalation"] is True
    assert body["is_breached"] is False
    assert body["resolved_at_reference"] is False


E10_CASES = [
    pytest.param("2026-11-24T11:30:00", 210, False, True, False, id="E10.1-antes-del-cierre"),
    pytest.param("2026-11-24T14:00:00", 300, True, False, True, id="E10.2-despues-del-cierre"),
]


@pytest.mark.parametrize("reference, elapsed, breached, escalation, resolved", E10_CASES)
def test_bdd_e10_reconstruccion_del_sla_a_un_instante_pasado(stores, reference, elapsed, breached, escalation, resolved):
    """
    E10 — Reconstrucción del SLA a un instante pasado, con cierre fuera de plazo
    Given un incidente P1 creado a las 08:00 del 24 de noviembre de 2026 y resuelto
          a las 13:00 del mismo día
    When  la persona auditora consulta su SLA con instante de referencia <instante>
    Then  obtiene una consulta exitosa con <transcurridos> minutos transcurridos
    And   el incumplimiento es <incumplido>, el escalamiento es <escalamiento> y el incidente <resuelto>
    """
    incident = seeded(
        "INC-0000D010", CAIDA_PAGOS, at(24, 8), status="RESOLVED", resolved_at=at(24, 13), severity="P1"
    )
    client, _, _ = channels(build_service(REF, stores(incident)))

    response = client.get(sla_path("INC-0000D010"), params={"reference_time": reference})

    assert response.status_code == 200
    body = response.json()
    assert body["elapsed_minutes"] == elapsed
    assert body["is_breached"] is breached
    assert body["requires_escalation"] is escalation
    assert body["resolved_at_reference"] is resolved
    assert body["status"] == "RESOLVED"


E11_CASES = [
    pytest.param(
        "create",
        lambda client: client.post(
            INCIDENTS_PATH, json={"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS, "incident_id": "INC-CLIENTE-02"}
        ),
        create_args({"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS, "incident_id": "INC-CLIENTE-02"}),
        201,
        id="E11.1-registrar",
    ),
    pytest.param(
        "sla",
        lambda client: client.get(sla_path("INC-0000B001"), params={"reference_time": "2026-11-24T09:30:00"}),
        ["sla", "INC-0000B001", "--reference-time", "2026-11-24T09:30:00", "--format", "json"],
        200,
        id="E11.2-auditar",
    ),
]


@pytest.mark.parametrize("operation, http_call, cli_args, http_status", E11_CASES)
def test_bdd_e11_paridad_cli_create_y_sla(stores, operation, http_call, cli_args, http_status):
    """
    E11 — Operación equivalente por terminal con create y sla
    Given dos almacenes equivalentes, con un incidente abierto por caída de la pasarela de
          pagos, y el mismo reloj
    When  el operador realiza <operación> por la web sobre un almacén y por la terminal
          sobre el otro, en formato estructurado
    Then  ambos canales responden con éxito (<éxito web> por la web, código de salida 0 por la terminal)
    And   ambos resultados coinciden campo a campo, incluido el aviso de duplicado
    """
    existing = seeded("INC-0000B001", CAIDA_PAGOS, at(24, 8))
    client, _, _ = channels(build_service(NOW_0910, stores(existing)))
    _, cli_app, runner = channels(build_service(NOW_0910, stores(existing)))

    http = http_call(client)
    cli = runner.invoke(cli_app, cli_args)

    assert http.status_code == http_status
    assert cli.exit_code == 0, cli.stderr
    assert cli.stderr == ""
    assert http.json() == json.loads(cli.stdout)
    if operation == "create":
        assert http.json()["is_duplicate"] is True
        assert http.json()["duplicate_of"] == ["INC-0000B001"]


def test_bdd_e12_sla_habil_determinista(stores):
    """
    E12 — Auditoría determinista de SLA en horario hábil
    Given un incidente P2 abierto registrado el viernes 6 de noviembre de 2026 a las 17:00 hora de Bogotá
    And   que el lunes 9 de noviembre de 2026 no es festivo en Colombia
    When  la persona auditora consulta su SLA con instante de referencia lunes 9 de
          noviembre de 2026 a las 09:00
    Then  la consulta es exitosa (200 OK)
    And   muestra 120 minutos hábiles transcurridos (elapsed_minutes = 120)
    And   de los 480 minutos permitidos quedan 360 (allowed_minutes = 480, remaining_minutes = 360)
    And   el incidente no está incumplido ni requiere escalamiento
          (is_breached = false, requires_escalation = false)
    """
    incident = seeded("INC-0000D012", CAIDA_PAGOS, at(6, 17), severity="P2")
    client, _, _ = channels(build_service(REF, stores(incident)))

    response = client.get(sla_path("INC-0000D012"), params={"reference_time": "2026-11-09T09:00:00"})

    assert response.status_code == 200
    body = response.json()
    assert body["elapsed_minutes"] == 120
    assert body["allowed_minutes"] == 480
    assert body["remaining_minutes"] == 360
    assert body["is_breached"] is False
    assert body["requires_escalation"] is False
    assert body["reference_time"] == "2026-11-09T09:00:00-05:00"


def test_bdd_e13_auditoria_incidente_inexistente(stores):
    """
    E13 — Auditoría de un incidente inexistente
    Given que no existe ningún incidente con el identificador INC-FFFFFFFF
    When  la persona auditora consulta el SLA de INC-FFFFFFFF por la web y por la terminal
    Then  ambos canales rechazan la consulta como incidente inexistente, sin devolver
          evaluación (404 Not Found con código incident_not_found; código de salida 1)
    And   la terminal explica el motivo por la salida de diagnóstico (stderr)
    """
    client, cli_app, runner = channels(build_service(REF, stores()))

    http = client.get(sla_path("INC-FFFFFFFF"))
    cli = runner.invoke(cli_app, ["sla", "INC-FFFFFFFF", "--format", "json"])

    assert http.status_code == 404
    assert http.json()["error"]["code"] == "incident_not_found"
    assert "elapsed_minutes" not in http.text
    assert cli.exit_code == 1
    assert cli.stdout == ""
    assert "[incident_not_found]" in cli.stderr and "INC-FFFFFFFF" in cli.stderr


def test_bdd_e14_auditoria_antes_de_la_creacion(stores):
    """
    E14 — Auditoría en un instante anterior a la creación
    Given un incidente registrado el 24 de noviembre de 2026 a las 09:00
    When  la persona auditora consulta su SLA con instante de referencia 08:59 del mismo
          día, por la web y por la terminal
    Then  ambos canales rechazan la consulta porque el incidente aún no existía en ese
          instante (422 Unprocessable Entity con código reference_before_creation; código de salida 1)
    And   no se devuelve ninguna evaluación de SLA
    """
    client, cli_app, runner = channels(build_service(REF, stores(seeded("INC-0000D014", CAIDA_PAGOS, at(24, 9)))))

    http = client.get(sla_path("INC-0000D014"), params={"reference_time": "2026-11-24T08:59:00"})
    cli = runner.invoke(
        cli_app, ["sla", "INC-0000D014", "--reference-time", "2026-11-24T08:59:00", "--format", "json"]
    )

    assert http.status_code == 422
    assert http.json()["error"]["code"] == "reference_before_creation"
    assert http.json()["error"]["field"] == "reference_time"
    assert "elapsed_minutes" not in http.text
    assert cli.exit_code == 1 and cli.stdout == ""
    assert "[reference_before_creation]" in cli.stderr


def test_bdd_e16_la_auditoria_no_modifica_datos_ni_expone_contenido(stores, caplog):
    """
    E16 — La auditoría de SLA no modifica datos ni expone contenido
    Given un almacén con incidentes abiertos y resueltos
    When  se audita el SLA de cada incidente repetidamente
    Then  no se crea, modifica ni elimina ningún incidente
    And   ninguna traza de la auditoría registra títulos
    """
    incidents = [
        seeded("INC-0000D161", CAIDA_PAGOS + " (abierto-título-único-1)", at(24, 8)),
        seeded("INC-0000D162", CAIDA_AUTH + " (escalado-título-único-2)", at(24, 7), status="ESCALATION_REQUIRED"),
        seeded(
            "INC-0000D163",
            BOTON_DESALINEADO + " (resuelto-título-único-3)",
            at(23, 10),
            status="RESOLVED",
            resolved_at=at(23, 11),
        ),
    ]
    repository = stores(*incidents)
    ids = [incident.incident_id for incident in incidents]
    before = snapshot(repository, *ids)
    active_before = sorted(item.incident_id for item in repository.list_active_incidents())
    client, cli_app, runner = channels(build_service(REF, repository))

    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            for incident_id in ids:
                assert client.get(sla_path(incident_id)).status_code == 200
                assert runner.invoke(cli_app, ["sla", incident_id, "--format", "json"]).exit_code == 0

    assert snapshot(repository, *ids) == before
    assert sorted(item.incident_id for item in repository.list_active_incidents()) == active_before
    for incident in incidents:
        assert incident.title not in caplog.text
    assert "título-único" not in caplog.text


# ---------------------------------------------------------------------------
# 5. SC-006 — Rendimiento por canal con 10 000 abiertos
# ---------------------------------------------------------------------------


def test_sc006_crear_y_auditar_con_diez_mil_abiertos_en_menos_de_un_segundo(stores):
    """
    SC-006 — Con 10 000 incidentes abiertos, crear (con búsqueda de duplicados) y auditar
    el SLA tardan menos de 1 s por canal (medida en proceso, sin el arranque del intérprete)
    """
    repository = stores()
    # Solo acelera la siembra de la prueba: sin fsync por cada una de las 10 000 escrituras.
    repository._connection.execute("PRAGMA synchronous = OFF")
    texts = (CAIDA_PAGOS, CAIDA_AUTH, BOTON_DESALINEADO, SIN_CLASIFICAR)
    templates = [seeded("INC-T", text, REF) for text in texts]
    for index in range(10_000):
        template = templates[index % len(templates)]
        repository.save_incident(
            Incident(
                incident_id=f"INC-{index:05d}",
                title=template.title,
                component=template.component,
                severity=("P0", "P1", "P2", "P3")[index % 4],  # type: ignore[arg-type]
                status="OPEN" if index % 2 else "IN_PROGRESS",
                created_at=REF - timedelta(minutes=index + 1),
                recommended_team=template.recommended_team,
                duplicate_group_key=template.duplicate_group_key,
            )
        )
    client, cli_app, runner = channels(
        build_service(REF, repository, SequenceIdGenerator(["INC-SC6-HTTP", "INC-SC6-CLI"]))
    )
    payload = {"title": CAIDA_PAGOS_TITULO, "raw_text": CAIDA_PAGOS}

    timings = {}
    started = time.perf_counter()
    http_create = client.post(INCIDENTS_PATH, json=payload)
    timings["http create"] = time.perf_counter() - started
    started = time.perf_counter()
    cli_create = runner.invoke(cli_app, create_args(payload))
    timings["cli create"] = time.perf_counter() - started
    started = time.perf_counter()
    http_sla = client.get(sla_path("INC-00001"))
    timings["http sla"] = time.perf_counter() - started
    started = time.perf_counter()
    cli_sla = runner.invoke(cli_app, ["sla", "INC-00001", "--format", "json"])
    timings["cli sla"] = time.perf_counter() - started

    assert http_create.status_code == 201 and http_create.json()["is_duplicate"] is True
    assert len(http_create.json()["duplicate_of"]) == 2_500
    assert cli_create.exit_code == 0 and json.loads(cli_create.stdout)["is_duplicate"] is True
    assert http_sla.status_code == 200 and cli_sla.exit_code == 0
    for name, seconds in timings.items():
        assert seconds < 1.0, f"{name} tardó {seconds:.3f} s"
