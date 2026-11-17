
"""Módulo determinista para el cálculo y evaluación de acuerdos de nivel de servicio (SLA)."""

from datetime import datetime
from typing import Dict, NamedTuple

from src.models import Incident, SLAEvaluation, SLARule, SeverityLevel
from src.working_time_calculator import (
    calculate_working_minutes,
    to_bogota,
)


SLA_POLICY_TABLE: Dict[SeverityLevel, SLARule] = {
    "P0": SLARule(severity="P0", max_resolution_minutes=60, operates_24x7=True),
    "P1": SLARule(severity="P1", max_resolution_minutes=240, operates_24x7=True),
    "P2": SLARule(severity="P2", max_resolution_minutes=480, operates_24x7=False),
    "P3": SLARule(severity="P3", max_resolution_minutes=1440, operates_24x7=False),
}


def get_sla_rule_for_severity(severity: SeverityLevel) -> SLARule:
    """Obtiene la regla de SLA aplicable a una severidad validada contra la tabla."""
    if severity not in SLA_POLICY_TABLE:
        raise ValueError(f"Severidad no válida: {severity}")

    return SLA_POLICY_TABLE[severity]


def evaluate_sla_status(
    incident: Incident,
    reference_time: datetime,
) -> SLAEvaluation:
    """Evalúa el incumplimiento del SLA y la necesidad de escalamiento.

    P0/P1: contabilizan tiempo calendario 24x7.
    P2/P3: contabilizan únicamente tiempo hábil colombiano.

    Args:
        incident: Entidad del incidente a evaluar.
        reference_time: Marca de tiempo actual o de cierre contra la cual medir.

    Returns:
        SLAEvaluation con los minutos transcurridos, restantes y banderas de estado.
    """
    rule = get_sla_rule_for_severity(incident.severity)

    start_time = to_bogota(incident.created_at)
    end_time = to_bogota(incident.resolved_at or reference_time)

    if end_time < start_time:
        raise ValueError(
            "El tiempo de referencia no puede ser anterior a la creación."
        )

    if rule.operates_24x7:
        delta_seconds = (end_time - start_time).total_seconds()
        elapsed_minutes = int(delta_seconds // 60)
    else:
        elapsed_minutes = calculate_working_minutes(
            start_time,
            end_time,
        )

    remaining_minutes = rule.max_resolution_minutes - elapsed_minutes
    is_breached = elapsed_minutes > rule.max_resolution_minutes

    escalation_limit = int(
        rule.max_resolution_minutes * rule.escalation_threshold_ratio
    )

    requires_escalation = (
        incident.status != "RESOLVED"
        and not is_breached
        and elapsed_minutes >= escalation_limit
    )

    return SLAEvaluation(
        incident_id=incident.incident_id,
        severity=incident.severity,
        elapsed_minutes=elapsed_minutes,
        allowed_minutes=rule.max_resolution_minutes,
        remaining_minutes=remaining_minutes,
        is_breached=is_breached,
        requires_escalation=requires_escalation,
    )


class SLATestCase(NamedTuple):
    """Define un escenario de validación del cálculo SLA."""

    name: str
    severity: SeverityLevel
    created_at: datetime
    reference_time: datetime
    expected_minutes: int
    expected_breached: bool = False
    expected_escalation: bool = False


def _run_demo() -> None:
    """Ejecuta pruebas deterministas de los casos borde del cálculo SLA."""
    print("\n=== INCIDENTOPS | VALIDACIÓN DE CÁLCULO SLA ===")
    print("Zona horaria: America/Bogota")
    print("Horario hábil: Lunes-Viernes | 08:00-18:00\n")

    cases = [
        SLATestCase(
            name="P2: Cruce de fin de semana",
            severity="P2",
            created_at=datetime(2026, 11, 6, 17, 0),
            reference_time=datetime(2026, 11, 9, 9, 0),
            expected_minutes=120,
        ),
        SLATestCase(
            name="P2: Creación antes del horario laboral",
            severity="P2",
            created_at=datetime(2026, 11, 9, 6, 30),
            reference_time=datetime(2026, 11, 9, 9, 0),
            expected_minutes=60,
        ),
        SLATestCase(
            name="P2: Cruce del cierre de jornada",
            severity="P2",
            created_at=datetime(2026, 11, 9, 17, 0),
            reference_time=datetime(2026, 11, 10, 9, 0),
            expected_minutes=120,
        ),
        SLATestCase(
            name="P0: Cruce de fin de semana 24x7",
            severity="P0",
            created_at=datetime(2026, 11, 6, 17, 0),
            reference_time=datetime(2026, 11, 9, 9, 0),
            expected_minutes=3840,
            expected_breached=True,
        ),
        SLATestCase(
            name="P2: Festivo fijo nacional (Inmaculada Concepción)",
            severity="P2",
            created_at=datetime(2026, 12, 8, 9, 0),
            reference_time=datetime(2026, 12, 8, 10, 0),
            expected_minutes=0,
        ),
        SLATestCase(
            name="P2: Festivo trasladable (Reyes Magos)",
            severity="P2",
            created_at=datetime(2026, 1, 12, 9, 0),
            reference_time=datetime(2026, 1, 12, 10, 0),
            expected_minutes=0,
        ),
        SLATestCase(
            name="P2: Jueves y Viernes Santo",
            severity="P2",
            created_at=datetime(2026, 4, 2, 9, 0),
            reference_time=datetime(2026, 4, 3, 17, 0),
            expected_minutes=0,
        ),
        SLATestCase(
            name="P2: Escalamiento preventivo exactamente al 75%",
            severity="P2",
            created_at=datetime(2026, 11, 9, 8, 0),
            reference_time=datetime(2026, 11, 9, 14, 0),
            expected_minutes=360,
            expected_escalation=True,
        ),
        SLATestCase(
            name="P2: Incumplimiento al superar 480 minutos",
            severity="P2",
            created_at=datetime(2026, 11, 9, 8, 0),
            reference_time=datetime(2026, 11, 9, 16, 1),
            expected_minutes=481,
            expected_breached=True,
        ),
        SLATestCase(
            name="P3: Jornada completa de dos días y escalamiento",
            severity="P3",
            created_at=datetime(2026, 11, 9, 8, 0),
            reference_time=datetime(2026, 11, 10, 18, 0),
            expected_minutes=1200,
            expected_breached=False,
            expected_escalation=True,
        )
    ]

    passed = 0
    failed = 0

    for index, case in enumerate(cases, start=1):
        incident = Incident(
            incident_id=f"TEST-{index:03}",
            title=case.name,
            component="sla-test",
            severity=case.severity,
            status="OPEN",
            created_at=case.created_at,
        )

        result = evaluate_sla_status(
            incident,
            reference_time=case.reference_time,
        )

        valid = (
            result.elapsed_minutes == case.expected_minutes
            and result.is_breached == case.expected_breached
            and result.requires_escalation == case.expected_escalation
        )

        if valid:
            passed += 1
            status = "OK"
        else:
            failed += 1
            status = "ERROR"

        print(f"[{status}] {case.name}")
        print(
            f"       Esperado: {case.expected_minutes} min | "
            f"Obtenido: {result.elapsed_minutes} min"
        )

        if not valid:
            print(
                f"       Incumplido esperado/obtenido: "
                f"{case.expected_breached}/{result.is_breached}"
            )
            print(
                f"       Escalamiento esperado/obtenido: "
                f"{case.expected_escalation}/{result.requires_escalation}"
            )

    print("\n" + "=" * 55)
    print(f"RESULTADO: {passed}/{len(cases)} pruebas satisfactorias")
    print(f"Fallidas: {failed}")
    print("=" * 55)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _run_demo()
