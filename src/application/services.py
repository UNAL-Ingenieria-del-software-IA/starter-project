"""Casos de uso compartidos: triaje (H001) y resumen de incidentes activos (H002).

`IncidentService` es el único punto por el que REST y CLI clasifican reportes y consultan
el resumen. `to_contract` (spec 001 §5.2) y `summary_to_contract` (spec 002) son las únicas
proyecciones al contrato público, de modo que la paridad entre canales se obtiene por
construcción (Art. 2.7). Minutos, incumplimiento y escalamiento salen solo de
`evaluate_sla_status` (spec 002 FR-005).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.application.ports import ClockPort, IncidentRepositoryPort
from src.domain.models import (
    ACTIVE_STATUSES,
    SEVERITY_ORDER,
    IncidentReport,
    IncidentStatus,
    SeverityLevel,
    TriageResult,
)
from src.domain.sla_calculator import evaluate_sla_status
from src.domain.triage_rules import classify_incident_batch
from src.domain.working_time_calculator import to_bogota


class ValidationError(Exception):
    """Entrada interpretable pero inaceptable para el caso de uso (spec 001 D11)."""

    def __init__(self, code: str, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


@dataclass(frozen=True)
class ReportInput:
    """Reporte crudo recibido por cualquier canal, ya traducido por su adaptador."""

    raw_text: str
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class ActiveIncidentView:
    """Una fila del detalle del resumen: datos del incidente más su evaluación SLA."""

    incident_id: str
    title: str
    component: str
    severity: SeverityLevel
    status: IncidentStatus
    elapsed_minutes: int
    is_breached: bool
    requires_escalation: bool


@dataclass(frozen=True)
class ActiveIncidentsSummary:
    """Resumen de activos a un instante (spec 002). Los totales se derivan del detalle (FR-010)."""

    reference_time: datetime
    component_filter: Optional[str]
    incidents: Tuple[ActiveIncidentView, ...]

    @property
    def total_active(self) -> int:
        return len(self.incidents)

    @property
    def breached_count(self) -> int:
        return sum(1 for view in self.incidents if view.is_breached)


def parse_reference_time(value: Optional[str]) -> Optional[datetime]:
    """Analiza el instante de referencia de cualquier canal con una sola regla (FR-008).

    Admite `datetime.fromisoformat` y un sufijo `Z` (CPython 3.10 no lo acepta). Sin zona =
    hora de Bogotá, lo resuelve el servicio.

    Raises:
        ValidationError: `invalid_timestamp` si la cadena no es ISO-8601.
    """
    if value is None:
        return None
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise ValidationError(
            "invalid_timestamp", f"'{value}' no es una fecha ISO-8601 válida.", "reference_time"
        ) from None


class IncidentService:
    """Casos de uso compartidos por todos los canales.

    El triaje (H001) no usa el repositorio; el resumen de activos (H002) solo lo lee.
    """

    def __init__(self, clock: ClockPort, repository: IncidentRepositoryPort) -> None:
        self._clock = clock
        self._repository = repository

    def triage_incident(self, reports: Sequence[ReportInput]) -> List[TriageResult]:
        """Valida y clasifica un lote de 1..N reportes, correlacionándolos entre sí.

        Raises:
            ValidationError: si el lote está vacío o algún `raw_text` está vacío o
                contiene solo espacios. En ese caso el motor no se ejecuta.
        """
        if not reports:
            raise ValidationError("invalid_payload", "El lote debe contener al menos un reporte.", "reports")

        for index, report in enumerate(reports):
            if not report.raw_text.strip():
                raise ValidationError(
                    "invalid_payload",
                    "El texto del reporte no puede estar vacío ni contener solo espacios.",
                    f"reports[{index}].raw_text",
                )

        reference_time = self._clock.now()
        domain_reports = [
            IncidentReport(
                # Rótulo posicional: el contrato de H001 no tiene identidad (spec 001 D4, §1.1).
                incident_id=f"R{index}",
                raw_text=report.raw_text,
                # Naive = hora de Bogotá (Art. 1.7); normalizar evita mezclar naive y aware.
                created_at=to_bogota(report.created_at or reference_time),
            )
            for index, report in enumerate(reports, start=1)
        ]
        return classify_incident_batch(domain_reports)

    def get_active_incidents_summary(
        self,
        component_filter: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> ActiveIncidentsSummary:
        """Resume los incidentes activos a un instante, opcionalmente de un componente.

        Solo lee el repositorio (FR-015). El instante es `reference_time` o el reloj
        inyectado, en hora de Bogotá y truncado a segundos: el mismo que se evalúa y se
        declara (FR-008). Los creados después del instante no cuentan (FR-009).
        """
        instant = to_bogota(reference_time or self._clock.now()).replace(microsecond=0)

        views: List[ActiveIncidentView] = []
        for incident in self._repository.list_active_incidents(component_filter):
            if incident.status not in ACTIVE_STATUSES or to_bogota(incident.created_at) > instant:
                continue
            evaluation = evaluate_sla_status(incident, instant)
            views.append(
                ActiveIncidentView(
                    incident_id=incident.incident_id,
                    title=incident.title,
                    component=incident.component,
                    severity=incident.severity,
                    status=incident.status,
                    elapsed_minutes=evaluation.elapsed_minutes,
                    is_breached=evaluation.is_breached,
                    requires_escalation=evaluation.requires_escalation,
                )
            )

        # FR-011: severidad más crítica primero, luego mayor tiempo, luego identificador.
        views.sort(key=lambda view: (SEVERITY_ORDER.index(view.severity), -view.elapsed_minutes, view.incident_id))
        return ActiveIncidentsSummary(
            reference_time=instant,
            component_filter=component_filter,
            incidents=tuple(views),
        )


def to_contract(result: TriageResult) -> Dict[str, Any]:
    """Proyecta un resultado de dominio a los campos públicos de la spec 001 §5.2.

    No publica `incident_id`, `rationale` ni `consistency_ratio`.
    """
    return {
        "severity": result.severity,
        "component": result.component,
        "recommended_team": result.recommended_team,
        "action": result.action,
        "duplicate_type": result.duplicate_type,
        "duplicate_group_key": result.duplicate_group_key,
        "merge": result.merge,
        "analysis": list(result.analysis),
    }


def summary_to_contract(summary: ActiveIncidentsSummary) -> Dict[str, Any]:
    """Proyecta el resumen al cuerpo JSON de la spec 002 (mismo valor por HTTP y CLI).

    `reference_time` se emite ya como cadena ISO con desfase: ningún canal re-serializa
    un `datetime` (research §R9).
    """
    return {
        "reference_time": summary.reference_time.isoformat(),
        "component_filter": summary.component_filter,
        "total_active": summary.total_active,
        "breached_count": summary.breached_count,
        "incidents": [
            {
                "incident_id": view.incident_id,
                "title": view.title,
                "component": view.component,
                "severity": view.severity,
                "status": view.status,
                "elapsed_minutes": view.elapsed_minutes,
                "is_breached": view.is_breached,
                "requires_escalation": view.requires_escalation,
            }
            for view in summary.incidents
        ],
    }
