"""Caso de uso compartido de triaje (H001).

`IncidentService` es el único punto por el que REST y CLI clasifican reportes: valida la
entrada, completa `created_at` con el reloj inyectado y delega en el pipeline del dominio.
`to_contract` es la única proyección del resultado al contrato público de la spec 001 §5.2,
de modo que la paridad entre canales se obtiene por construcción (Art. 2.7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.application.ports import ClockPort
from src.domain.models import IncidentReport, TriageResult
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


class IncidentService:
    """Orquesta el triaje de un lote sin efectos secundarios."""

    def __init__(self, clock: ClockPort) -> None:
        self._clock = clock

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
