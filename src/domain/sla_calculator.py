"""Módulo determinista para el cálculo y evaluación de acuerdos de nivel de servicio (SLA)."""

from datetime import datetime
from typing import Dict

from src.domain.models import Incident, SLAEvaluation, SLARule, SeverityLevel
from src.domain.working_time_calculator import (
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
    """Evalúa el incumplimiento del SLA y la necesidad de escalamiento en un instante.

    P0/P1: contabilizan tiempo calendario 24x7.
    P2/P3: contabilizan únicamente tiempo hábil colombiano.

    Las tres marcas (creación, resolución y referencia) se normalizan a hora de Bogotá
    (Art. 1.7: naive = Bogotá), así que se pueden mezclar valores naive y aware. La
    evaluación se reconstruye en `reference_time` (spec 003 FR-015): el incidente cuenta
    como resuelto solo si su resolución ocurrió en ese instante o antes, el tiempo se mide
    hasta el primero de ambos instantes y el escalamiento depende de ese estado, no de
    `status` (Art. 1.8, Constitución 3.0.0).

    Args:
        incident: Entidad del incidente a evaluar.
        reference_time: Instante en el que se evalúa el SLA.

    Returns:
        SLAEvaluation con los minutos transcurridos, restantes y banderas de estado.

    Raises:
        ValueError: si `reference_time` es anterior a la creación.
    """
    rule = get_sla_rule_for_severity(incident.severity)

    start_time = to_bogota(incident.created_at)
    reference = to_bogota(reference_time)
    resolved_at = to_bogota(incident.resolved_at) if incident.resolved_at is not None else None

    if reference < start_time:
        raise ValueError(
            "El tiempo de referencia no puede ser anterior a la creación."
        )

    resolved_at_reference = resolved_at is not None and resolved_at <= reference
    end_time = resolved_at if resolved_at_reference else reference
    if end_time < start_time:
        raise ValueError("La resolución no puede ser anterior a la creación.")

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
        not resolved_at_reference
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
        resolved_at_reference=resolved_at_reference,
    )
