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
import typing
from datetime import datetime, timedelta
from typing import Callable, List

import pytest

from src.adapters.outbound.null_repository import NullIncidentRepository
from src.adapters.outbound.sqlite_repository import (
    SELECT_ACTIVE_BY_COMPONENT_SQL,
    SELECT_ACTIVE_SQL,
    SQLiteIncidentRepository,
)
from src.application.ports import IncidentRepositoryPort
from src.domain.models import ACTIVE_STATUSES, Incident
from src.domain.sla_calculator import SLA_POLICY_TABLE
from src.domain.working_time_calculator import BOGOTA_TZ
from tests.doubles import InMemoryIncidentRepository

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
