"""Puente de compatibilidad y regresión SLA.

La política y `evaluate_sla_status` viven en `src.domain.sla_calculator` (ADR-003).
Este módulo conserva el arnés `_run_demo()` (12 aserciones) que se ejecuta con
`uv run python -X utf8 -m src.sla_calculator`; imprimir no está permitido en el dominio.
Los casos E10.1 y E10.2 (spec 003) cubren la reconstrucción del SLA en un instante
anterior y posterior a la resolución (Art. 1.12).
"""

from datetime import datetime
from typing import NamedTuple, Optional

from src.domain.models import Incident, SeverityLevel
from src.domain.sla_calculator import (  # noqa: F401
    SLA_POLICY_TABLE,
    evaluate_sla_status,
    get_sla_rule_for_severity,
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
    resolved_at: Optional[datetime] = None


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
        ),
        SLATestCase(
            name="P1 resuelto fuera de plazo: auditoría antes del cierre (E10.1)",
            severity="P1",
            created_at=datetime(2026, 11, 24, 8, 0),
            reference_time=datetime(2026, 11, 24, 11, 30),
            expected_minutes=210,
            expected_breached=False,
            expected_escalation=True,
            resolved_at=datetime(2026, 11, 24, 13, 0),
        ),
        SLATestCase(
            name="P1 resuelto fuera de plazo: auditoría después del cierre (E10.2)",
            severity="P1",
            created_at=datetime(2026, 11, 24, 8, 0),
            reference_time=datetime(2026, 11, 24, 14, 0),
            expected_minutes=300,
            expected_breached=True,
            expected_escalation=False,
            resolved_at=datetime(2026, 11, 24, 13, 0),
        ),
    ]

    passed = 0
    failed = 0

    for index, case in enumerate(cases, start=1):
        incident = Incident(
            incident_id=f"TEST-{index:03}",
            title=case.name,
            component="sla-test",
            severity=case.severity,
            status="RESOLVED" if case.resolved_at is not None else "OPEN",
            created_at=case.created_at,
            resolved_at=case.resolved_at,
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
