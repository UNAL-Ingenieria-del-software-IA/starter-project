"""Entidades de dominio y tipos de datos para IncidentOps."""

from dataclasses import dataclass
from datetime import datetime
from typing import FrozenSet, Literal, Optional, Tuple

SeverityLevel = Literal["P0", "P1", "P2", "P3"]
IncidentStatus = Literal["OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED", "RESOLVED"]

# Constitución Art. 1.10 (enmendado por ADR-005): activo es todo estado distinto de RESOLVED.
ACTIVE_STATUSES: FrozenSet[IncidentStatus] = frozenset({"OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED"})

# Orden de criticidad, de más a menos crítica (spec 002 FR-011).
SEVERITY_ORDER: Tuple[SeverityLevel, ...] = ("P0", "P1", "P2", "P3")

TeamName = Literal["Backend-Core", "Platform-SRE", "Data-DBA", "Security-IAM"]

DuplicateType = Literal[
    "none",               # Incidente independiente.
    "exact_duplicate",    # Mismo evento reportado varias veces (confirmado por ventana temporal).
    "recurrence",         # Mismo síntoma/componente, pero episodios distintos.
    "related_incidents",  # Posible causa raíz compartida; se investiga en conjunto.
]

TriageAction = Literal[
    "escalate_24x7",
    "contain_security_breach",
    "mitigate_capacity_risk",
    "restore_account",
    "investigate_shared_root_cause",
    "optimize_query_performance",
    "optimize_export_performance",
    "register_enhancement",
    "schedule_certificate_rotation",
    "manual_review",
]


@dataclass(frozen=True)
class SLARule:
    """Define el acuerdo de nivel de servicio (SLA) para un nivel de severidad."""

    severity: SeverityLevel
    max_resolution_minutes: int
    operates_24x7: bool
    escalation_threshold_ratio: float = 0.75


@dataclass
class Incident:
    """Representa un incidente registrado en la plataforma IncidentOps."""

    incident_id: str
    title: str
    component: str
    severity: SeverityLevel
    status: IncidentStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None


@dataclass(frozen=True)
class SLAEvaluation:
    """Resultado determinista de la evaluación de SLA de un incidente."""

    incident_id: str
    severity: SeverityLevel
    elapsed_minutes: int
    allowed_minutes: int
    remaining_minutes: int
    is_breached: bool
    requires_escalation: bool


@dataclass(frozen=True)
class IncidentReport:
    """Reporte crudo entrante, antes del triaje."""

    incident_id: str
    raw_text: str
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class TriageResult:
    """Resultado estructurado producido por el clasificador de triaje.

    Los campos nuevos tienen valores por defecto para mantener compatibilidad con
    los consumidores existentes que solo usan severity/component/rationale.
    """

    incident_id: str
    severity: SeverityLevel
    component: str
    rationale: str
    consistency_ratio: float = 1.0
    recommended_team: Optional[TeamName] = None
    duplicate_group_key: Optional[str] = None
    duplicate_type: DuplicateType = "none"
    merge: bool = False
    action: TriageAction = "manual_review"
    analysis: Tuple[str, ...] = ()

    def to_output_line(self) -> str:
        """Serializa en el formato `<output>` acordado."""
        return (
            f"severity={self.severity} | component={self.component} | "
            f"duplicate_group={self.duplicate_group_key or 'none'} | "
            f"duplicate_type={self.duplicate_type} | "
            f"merge={'true' if self.merge else 'false'} | action={self.action}"
        )