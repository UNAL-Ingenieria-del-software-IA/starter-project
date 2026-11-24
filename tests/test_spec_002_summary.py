"""Aceptación de la spec 002 — Resumen de incidentes activos (H002).

Bloques:
1. Conformidad de `IncidentRepositoryPort` (forma y comportamiento) sobre
   `SQLiteIncidentRepository`, `NullIncidentRepository` y el doble en memoria.
2. Escenarios BDD E1–E12 sobre `IncidentService` con el doble en memoria (Art. III.6):
   cada `Given` declara sus propios incidentes y no depende del conjunto de demostración.
3. Canales HTTP y CLI sobre el mismo servicio, incluida la paridad (E10).
"""

from __future__ import annotations

import inspect
import logging
import typing
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

from src.adapters.inbound.api.app import create_app
from src.adapters.outbound.clock import FixedClock
from src.adapters.outbound.null_repository import NullIncidentRepository
from src.adapters.outbound.sqlite_repository import (
    SELECT_ACTIVE_BY_COMPONENT_SQL,
    SELECT_ACTIVE_SQL,
    SQLiteIncidentRepository,
)
from src.application.ports import IncidentRepositoryPort
from src.application.services import IncidentService
from src.domain.models import ACTIVE_STATUSES, Incident
from src.domain.sla_calculator import SLA_POLICY_TABLE, evaluate_sla_status
from src.domain.working_time_calculator import BOGOTA_TZ
from tests.doubles import InMemoryIncidentRepository

SUMMARY_PATH = "/api/v1/incidents/summary"
ITEM_FIELDS = {
    "incident_id",
    "title",
    "component",
    "severity",
    "status",
    "elapsed_minutes",
    "is_breached",
    "requires_escalation",
}
SUMMARY_FIELDS = {"reference_time", "component_filter", "total_active", "breached_count", "incidents"}

# Martes 2026-11-24, 09:00 en Bogotá: instante de referencia común de los escenarios.
REF = datetime(2026, 11, 24, 9, 0, tzinfo=BOGOTA_TZ)


def make_incident(
    incident_id: str,
    *,
    severity: str = "P1",
    status: str = "OPEN",
    component: str = "payment-gateway",
    created_at: datetime = REF - timedelta(minutes=10),
    title: str = "Incidente de prueba",
    resolved_at: typing.Optional[datetime] = None,
) -> Incident:
    if status == "RESOLVED" and resolved_at is None:
        resolved_at = created_at + timedelta(minutes=5)
    return Incident(
        incident_id=incident_id,
        title=title,
        component=component,
        severity=severity,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        created_at=created_at,
        resolved_at=resolved_at,
    )


def _by_id(incidents) -> List[Incident]:
    return sorted(incidents, key=lambda item: item.incident_id)


# ---------------------------------------------------------------------------
# 1. Conformidad de IncidentRepositoryPort
# ---------------------------------------------------------------------------

PORT_METHODS = sorted(
    name
    for name, value in vars(IncidentRepositoryPort).items()
    if callable(value) and not name.startswith("_")
)

IMPLEMENTATIONS = [SQLiteIncidentRepository, NullIncidentRepository, InMemoryIncidentRepository]

REPOSITORY_FACTORIES: typing.Dict[str, Callable[[], IncidentRepositoryPort]] = {
    "memoria": InMemoryIncidentRepository,
    "sqlite": lambda: SQLiteIncidentRepository(":memory:"),
}


@pytest.fixture(params=sorted(REPOSITORY_FACTORIES))
def repo(request) -> IncidentRepositoryPort:
    return REPOSITORY_FACTORIES[request.param]()


def test_el_puerto_declara_los_cinco_metodos_del_hito():
    assert PORT_METHODS == [
        "check_health",
        "find_open_duplicates",
        "get_incident",
        "list_active_incidents",
        "save_incident",
    ]


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda cls: cls.__name__)
@pytest.mark.parametrize("method", PORT_METHODS)
def test_forma_de_cada_implementacion_coincide_con_el_puerto(implementation, method):
    """
    Given el puerto IncidentRepositoryPort y una implementación concreta
    When  se comparan las firmas de cada método público
    Then  coinciden nombres, clases, valores por defecto y tipos resueltos
    """
    expected = getattr(IncidentRepositoryPort, method)
    actual = getattr(implementation, method, None)
    assert callable(actual), f"{implementation.__name__} no implementa {method}"

    def shape(func):
        signature = inspect.signature(func)
        return [(p.name, p.kind, p.default) for p in signature.parameters.values()]

    assert shape(actual) == shape(expected)
    assert typing.get_type_hints(actual) == typing.get_type_hints(expected)


def test_guardar_y_recuperar_normaliza_a_bogota(repo):
    """
    Given un incidente con creación sin zona horaria
    When  se guarda y se recupera por identificador
    Then  vuelve con la creación interpretada como hora de Bogotá (Art. 1.7)
    """
    repo.save_incident(make_incident("INC-1", created_at=datetime(2026, 11, 24, 8, 0)))
    stored = repo.get_incident("INC-1")
    assert stored is not None
    assert stored.created_at == datetime(2026, 11, 24, 8, 0, tzinfo=BOGOTA_TZ)
    assert stored.created_at.utcoffset() == timedelta(hours=-5)


def test_guardar_reemplaza_por_identificador(repo):
    repo.save_incident(make_incident("INC-1", title="Antes"))
    repo.save_incident(make_incident("INC-1", title="Después", status="IN_PROGRESS"))
    stored = repo.get_incident("INC-1")
    assert stored is not None and stored.title == "Después" and stored.status == "IN_PROGRESS"
    assert [item.incident_id for item in repo.list_active_incidents()] == ["INC-1"]


def test_identificador_inexistente_devuelve_none(repo):
    assert repo.get_incident("NO-EXISTE") is None


def test_severidad_sin_politica_se_rechaza(repo):
    with pytest.raises(ValueError):
        repo.save_incident(make_incident("INC-X", severity="P9"))


def test_activos_coinciden_exactamente_con_la_definicion_del_dominio(repo):
    """
    Given un incidente en cada uno de los cuatro estados válidos
    When  se listan los activos
    Then  el predicado del almacén coincide con ACTIVE_STATUSES del dominio (ADR-005)
    """
    for index, status in enumerate(["OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED", "RESOLVED"]):
        repo.save_incident(make_incident(f"INC-{index}", status=status))
    assert {item.status for item in repo.list_active_incidents()} == set(ACTIVE_STATUSES)
    assert len(repo.list_active_incidents()) == len(ACTIVE_STATUSES)


def test_activos_filtrados_por_componente(repo):
    repo.save_incident(make_incident("INC-1", component="payment-gateway"))
    repo.save_incident(make_incident("INC-2", component="auth-identity"))
    repo.save_incident(make_incident("INC-3", component="payment-gateway", status="RESOLVED"))
    assert [item.incident_id for item in repo.list_active_incidents("payment-gateway")] == ["INC-1"]
    assert repo.list_active_incidents("reporting-api") == []


def test_duplicados_abiertos_en_ventana_inclusiva_y_ordenados(repo):
    """
    Given activos y resueltos de un componente con distintas creaciones
    When  se buscan equivalentes abiertos en una ventana
    Then  solo vuelven los activos del componente dentro de la ventana, por creación
    """
    base = REF - timedelta(minutes=30)
    repo.save_incident(make_incident("INC-B", created_at=base + timedelta(minutes=30)))
    repo.save_incident(make_incident("INC-A", created_at=base))
    repo.save_incident(make_incident("INC-C", created_at=base + timedelta(minutes=31)))
    repo.save_incident(make_incident("INC-D", created_at=base + timedelta(minutes=5), status="RESOLVED"))
    repo.save_incident(make_incident("INC-E", created_at=base + timedelta(minutes=5), component="auth-identity"))
    found = repo.find_open_duplicates("payment-gateway", base, base + timedelta(minutes=30))
    assert [item.incident_id for item in found] == ["INC-A", "INC-B"]


def test_el_almacen_responde(repo):
    assert repo.check_health() is True


def test_sqlite_y_doble_devuelven_lo_mismo_para_los_mismos_datos():
    """
    Given el mismo conjunto de incidentes en el doble y en SQLite
    When  se consultan activos, por componente y por identificador
    Then  ambos devuelven entidades idénticas
    """
    incidents = [
        make_incident("INC-1", severity="P0", created_at=datetime(2026, 11, 24, 7, 30)),
        make_incident("INC-2", severity="P2", status="IN_PROGRESS", component="auth-identity"),
        make_incident("INC-3", severity="P3", status="ESCALATION_REQUIRED"),
        make_incident("INC-4", severity="P1", status="RESOLVED"),
    ]
    memory, sqlite = InMemoryIncidentRepository(), SQLiteIncidentRepository(":memory:")
    for incident in incidents:
        memory.save_incident(incident)
        sqlite.save_incident(incident)
    assert _by_id(memory.list_active_incidents()) == _by_id(sqlite.list_active_incidents())
    assert _by_id(memory.list_active_incidents("auth-identity")) == _by_id(sqlite.list_active_incidents("auth-identity"))
    for incident in incidents:
        assert memory.get_incident(incident.incident_id) == sqlite.get_incident(incident.incident_id)


def test_sla_policies_es_espejo_de_la_politica_del_dominio():
    """
    Given un almacén SQLite recién creado
    When  se lee la tabla sla_policies
    Then  coincide fila a fila con SLA_POLICY_TABLE (la tabla no es fuente de verdad)
    """
    repository = SQLiteIncidentRepository(":memory:")
    rows = repository._connection.execute(
        "SELECT severity, max_resolution_minutes, operates_24x7 FROM sla_policies ORDER BY severity"
    ).fetchall()
    expected = [
        (rule.severity, rule.max_resolution_minutes, int(rule.operates_24x7))
        for _, rule in sorted(SLA_POLICY_TABLE.items())
    ]
    assert rows == expected


@pytest.mark.parametrize(
    "sql, params",
    [(SELECT_ACTIVE_SQL, ()), (SELECT_ACTIVE_BY_COMPONENT_SQL, ("payment-gateway",))],
    ids=["global", "por-componente"],
)
def test_la_consulta_de_activos_usa_el_indice_parcial(sql, params):
    """
    Given un almacén SQLite con activos y resueltos
    When  se inspecciona el plan de la consulta de activos
    Then  usa idx_incidents_active_component (ADR-005) y el JOIN con sla_policies
    """
    repository = SQLiteIncidentRepository(":memory:")
    for index in range(50):
        status = "RESOLVED" if index % 3 == 0 else "OPEN"
        component = "payment-gateway" if index % 2 else "auth-identity"
        repository.save_incident(make_incident(f"INC-{index:03d}", status=status, component=component))
    plan = " | ".join(row[-1] for row in repository._connection.execute("EXPLAIN QUERY PLAN " + sql, params))
    assert "idx_incidents_active_component" in plan
    assert "sla_policies" in plan


def test_repositorio_nulo_no_tiene_efectos():
    repository = NullIncidentRepository()
    repository.save_incident(make_incident("INC-1"))
    assert repository.get_incident("INC-1") is None
    assert list(repository.list_active_incidents()) == []
    assert list(repository.find_open_duplicates("payment-gateway", REF, REF)) == []
    assert repository.check_health() is True


# ---------------------------------------------------------------------------
# 2. Historia 1 — Ver el estado operativo en una sola consulta (US1)
# ---------------------------------------------------------------------------


def summary_service(
    *incidents: Incident,
    now: datetime = REF,
    repository: Optional[IncidentRepositoryPort] = None,
) -> Tuple[IncidentService, IncidentRepositoryPort]:
    """Servicio con reloj fijo y un almacén sembrado con los incidentes del `Given`."""
    store = repository if repository is not None else InMemoryIncidentRepository()
    for incident in incidents:
        store.save_incident(incident)
    return IncidentService(FixedClock(now), store), store


def test_e1_resumen_global_excluye_resueltos():
    """
    E1 — Resumen global excluyendo RESOLVED
    Given tres incidentes activos de severidades y componentes distintos, uno de ellos
          con su SLA ya incumplido, y un incidente resuelto
    When  la persona de guardia consulta el resumen general en un instante fijo
    Then  el total activo es 3 y el total incumplido es 1
    And   el detalle muestra los tres activos con todos sus campos, sin el resuelto
    And   los totales coinciden con el detalle
    """
    service, _ = summary_service(
        make_incident("INC-A", severity="P0", component="payment-gateway", created_at=REF - timedelta(minutes=90)),
        make_incident(
            "INC-B", severity="P1", component="auth-identity", status="IN_PROGRESS", created_at=REF - timedelta(minutes=30)
        ),
        make_incident("INC-C", severity="P3", component="database-cluster", created_at=REF - timedelta(minutes=60)),
        make_incident("INC-R", severity="P0", component="payment-gateway", status="RESOLVED"),
    )

    summary = service.get_active_incidents_summary()

    assert summary.reference_time == REF
    assert summary.component_filter is None
    assert summary.total_active == 3
    assert summary.breached_count == 1
    assert {view.incident_id for view in summary.incidents} == {"INC-A", "INC-B", "INC-C"}
    assert summary.total_active == len(summary.incidents)
    assert summary.breached_count == sum(view.is_breached for view in summary.incidents)
    assert [view.incident_id for view in summary.incidents if view.is_breached] == ["INC-A"]


def test_e1_por_la_web_devuelve_el_contrato_completo():
    """
    E1 (canal HTTP)
    Given activos y un resuelto en el almacén
    When  se consulta por la web sin parámetros
    Then  la respuesta es exitosa, con los campos del contrato y totales consistentes
    """
    service, _ = summary_service(
        make_incident("INC-A", severity="P0", created_at=REF - timedelta(minutes=90)),
        make_incident("INC-B", severity="P1", component="auth-identity", status="IN_PROGRESS"),
        make_incident("INC-R", severity="P0", status="RESOLVED"),
    )

    response = TestClient(create_app(service)).get(SUMMARY_PATH)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == SUMMARY_FIELDS
    assert body["reference_time"] == "2026-11-24T09:00:00-05:00"
    assert body["component_filter"] is None
    assert body["total_active"] == len(body["incidents"]) == 2
    assert body["breached_count"] == sum(item["is_breached"] for item in body["incidents"]) == 1
    assert all(set(item) == ITEM_FIELDS for item in body["incidents"])
    assert "INC-R" not in {item["incident_id"] for item in body["incidents"]}


def test_metodo_distinto_de_get_responde_405():
    service, _ = summary_service()
    response = TestClient(create_app(service)).post(SUMMARY_PATH)
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_e4_solo_resolved_queda_fuera():
    """
    E4 — Solo RESOLVED queda fuera del resumen
    Given un almacén con incidentes OPEN, IN_PROGRESS, ESCALATION_REQUIRED y RESOLVED
    When  se consulta el resumen sin filtro
    Then  el detalle contiene OPEN, IN_PROGRESS y ESCALATION_REQUIRED
    And   el RESOLVED no cuenta en ninguna cifra
    """
    service, _ = summary_service(
        make_incident("INC-1", status="OPEN"),
        make_incident("INC-2", status="IN_PROGRESS"),
        make_incident("INC-3", status="ESCALATION_REQUIRED"),
        make_incident("INC-4", status="RESOLVED", created_at=REF - timedelta(minutes=500)),
    )

    summary = service.get_active_incidents_summary()

    assert {view.status for view in summary.incidents} == {"OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED"}
    assert summary.total_active == 3
    assert summary.breached_count == 0


def test_e7_minutos_segun_la_politica_de_la_severidad():
    """
    E7 — Los minutos transcurridos respetan la política de la severidad
    Given un incidente P0 y un P2 activos, ambos creados el mismo sábado
    When  se consulta el resumen en el mismo instante de referencia
    Then  el P0 acumula tiempo calendario y el P2 solo minutos hábiles
    And   ambos coinciden con la evaluación canónica de SLA
    """
    saturday = datetime(2026, 11, 21, 10, 0, tzinfo=BOGOTA_TZ)
    p0 = make_incident("INC-P0", severity="P0", created_at=saturday)
    p2 = make_incident("INC-P2", severity="P2", created_at=saturday)
    service, _ = summary_service(p0, p2)

    views = {view.incident_id: view for view in service.get_active_incidents_summary().incidents}

    assert views["INC-P0"].elapsed_minutes == 71 * 60  # sábado 10:00 → martes 09:00, 24x7.
    assert views["INC-P2"].elapsed_minutes == 600 + 60  # lunes completo + martes 08:00–09:00.
    for incident in (p0, p2):
        canonical = evaluate_sla_status(incident, REF)
        view = views[incident.incident_id]
        assert (view.elapsed_minutes, view.is_breached, view.requires_escalation) == (
            canonical.elapsed_minutes,
            canonical.is_breached,
            canonical.requires_escalation,
        )


def test_e8_incumplimiento_y_escalamiento_son_excluyentes():
    """
    E8 — Incumplimiento y escalamiento son excluyentes
    Given un activo que superó el umbral de escalamiento sin superar su límite
          y otro que ya superó el límite
    When  se consulta el resumen
    Then  el primero requiere escalamiento y no está incumplido
    And   el segundo está incumplido y no requiere escalamiento
    """
    service, _ = summary_service(
        make_incident("INC-UMBRAL", severity="P1", created_at=REF - timedelta(minutes=200)),
        make_incident("INC-LIMITE", severity="P1", created_at=REF - timedelta(minutes=241)),
    )

    views = {view.incident_id: view for view in service.get_active_incidents_summary().incidents}

    assert (views["INC-UMBRAL"].requires_escalation, views["INC-UMBRAL"].is_breached) == (True, False)
    assert (views["INC-LIMITE"].requires_escalation, views["INC-LIMITE"].is_breached) == (False, True)


def test_e9_orden_determinista_del_detalle():
    """
    E9 — Orden determinista del detalle
    Given activos de varias severidades y distintos tiempos transcurridos
    When  se consulta el resumen
    Then  va de la severidad más crítica a la menos crítica
    And   a igual severidad, primero el mayor tiempo transcurrido
    And   a igual severidad y tiempo, por identificador ascendente
    """
    service, _ = summary_service(
        make_incident("INC-9", severity="P3", created_at=REF - timedelta(minutes=30)),
        make_incident("INC-5", severity="P1", created_at=REF - timedelta(minutes=10)),
        make_incident("INC-2", severity="P0", created_at=REF - timedelta(minutes=5)),
        make_incident("INC-1", severity="P0", created_at=REF - timedelta(minutes=50)),
        make_incident("INC-7", severity="P2", created_at=REF - timedelta(minutes=20)),
        make_incident("INC-6", severity="P2", created_at=REF - timedelta(minutes=20)),
    )

    order = [view.incident_id for view in service.get_active_incidents_summary().incidents]

    assert order == ["INC-1", "INC-2", "INC-5", "INC-6", "INC-7", "INC-9"]


@pytest.mark.parametrize("store", sorted(REPOSITORY_FACTORIES))
def test_e12_la_consulta_no_modifica_los_datos(store, caplog):
    """
    E12 — La consulta no modifica los datos (SC-005)
    Given un almacén con incidentes activos y resueltos
    When  se consulta el resumen mil veces y otra vez por la web
    Then  ningún incidente se crea, modifica ni elimina
    And   ninguna traza registra títulos
    """
    incidents = [
        make_incident("INC-1", severity="P0", title="Título secreto de pagos"),
        make_incident("INC-2", severity="P2", status="IN_PROGRESS", title="Otro título sensible"),
        make_incident("INC-3", severity="P1", status="RESOLVED", title="Resuelto con título"),
    ]
    service, repository = summary_service(*incidents, repository=REPOSITORY_FACTORIES[store]())
    before = [repository.get_incident(item.incident_id) for item in incidents]
    active_before = _by_id(repository.list_active_incidents())

    for _ in range(1000):
        service.get_active_incidents_summary()
    caplog.set_level(logging.INFO, logger="src.adapters.inbound.api.app")
    response = TestClient(create_app(service)).get(SUMMARY_PATH)

    assert response.status_code == 200
    assert [repository.get_incident(item.incident_id) for item in incidents] == before
    assert _by_id(repository.list_active_incidents()) == active_before
    assert any("total_active=2" in record.getMessage() for record in caplog.records)
    for incident in incidents:
        assert incident.title not in caplog.text


# ---------------------------------------------------------------------------
# 3. Historia 2 — Enfocarse en un componente (US2)
# ---------------------------------------------------------------------------


def two_component_store() -> Tuple[Incident, ...]:
    return (
        make_incident("INC-P1", severity="P0", component="payment-gateway", created_at=REF - timedelta(minutes=90)),
        make_incident("INC-P2", severity="P2", component="payment-gateway", status="IN_PROGRESS"),
        make_incident("INC-P3", severity="P1", component="payment-gateway", status="RESOLVED"),
        make_incident("INC-A1", severity="P0", component="auth-identity", created_at=REF - timedelta(minutes=120)),
        make_incident("INC-A2", severity="P3", component="auth-identity", status="ESCALATION_REQUIRED"),
    )


def test_e2_filtro_por_componente():
    """
    E2 — Filtro por componente
    Given incidentes activos en payment-gateway y auth-identity
    When  la persona responsable consulta el resumen filtrando por payment-gateway
    Then  obtiene una respuesta exitosa
    And   el detalle muestra solo incidentes de payment-gateway
    And   los totales describen únicamente ese componente
    And   el resumen indica payment-gateway como componente filtrado
    """
    service, _ = summary_service(*two_component_store())

    summary = service.get_active_incidents_summary("payment-gateway")
    body = TestClient(create_app(service)).get(SUMMARY_PATH, params={"component": "payment-gateway"}).json()

    assert [view.incident_id for view in summary.incidents] == ["INC-P1", "INC-P2"]
    assert (summary.total_active, summary.breached_count) == (2, 1)
    assert summary.component_filter == "payment-gateway"
    assert body["component_filter"] == "payment-gateway"
    assert {item["component"] for item in body["incidents"]} == {"payment-gateway"}
    assert (body["total_active"], body["breached_count"]) == (2, 1)


@pytest.mark.parametrize(
    "incidents, component",
    [
        pytest.param(
            (make_incident("INC-R1", status="RESOLVED"), make_incident("INC-R2", status="RESOLVED")),
            None,
            id="E3.1-sin-activos",
        ),
        pytest.param(two_component_store(), "reporting-api", id="E3.2-sin-coincidencias"),
    ],
)
def test_e3_caso_vacio_es_exitoso(incidents, component):
    """
    E3 — Caso vacío: sin incidentes activos o sin coincidencias
    Given <situación del almacén>
    When  se consulta el resumen <consulta>
    Then  obtiene una respuesta exitosa y no un aviso de recurso inexistente
    And   el total activo es 0, el total incumplido es 0 y el detalle está vacío
    """
    service, _ = summary_service(*incidents)
    params = {"component": component} if component is not None else {}

    response = TestClient(create_app(service)).get(SUMMARY_PATH, params=params)

    assert response.status_code == 200
    body = response.json()
    assert (body["total_active"], body["breached_count"], body["incidents"]) == (0, 0, [])
    assert body["component_filter"] == component


def test_filtro_con_mayusculas_y_espacios_se_normaliza():
    """
    Caso borde — Filtro con mayúsculas o espacios circundantes
    Given activos en payment-gateway
    When  se filtra por " Payment-Gateway "
    Then  coincide con el componente canónico y lo declara normalizado
    """
    service, _ = summary_service(*two_component_store())

    summary = service.get_active_incidents_summary(" Payment-Gateway ")

    assert summary.component_filter == "payment-gateway"
    assert [view.incident_id for view in summary.incidents] == ["INC-P1", "INC-P2"]


def test_sc004_el_filtro_no_altera_las_cifras_de_otros_componentes():
    """
    SC-004 — Filtrar no altera las cifras del resto
    Given activos en dos componentes
    When  se consulta el global y cada componente por separado
    Then  la unión de los filtrados reproduce el global, valor a valor
    """
    service, _ = summary_service(*two_component_store())

    global_summary = service.get_active_incidents_summary()
    filtered = [service.get_active_incidents_summary(name) for name in ("payment-gateway", "auth-identity")]

    assert sum(item.total_active for item in filtered) == global_summary.total_active
    assert sum(item.breached_count for item in filtered) == global_summary.breached_count
    union = [view for item in filtered for view in item.incidents]
    assert _by_id(union) == _by_id(global_summary.incidents)


@pytest.mark.parametrize("component", ["", "   "])
def test_filtro_vacio_se_rechaza_con_422(component):
    """
    E11a (filtro) — Un filtro vacío o solo espacios es contenido inaceptable
    Given una consulta con filtro vacío
    When  se envía por la web
    Then  responde 422 invalid_payload sobre el campo component, sin resumen
    """
    service, _ = summary_service(*two_component_store())

    response = TestClient(create_app(service)).get(SUMMARY_PATH, params={"component": component})

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "invalid_payload",
        "message": "El filtro de componente no puede estar vacío ni contener solo espacios.",
        "field": "component",
    }
