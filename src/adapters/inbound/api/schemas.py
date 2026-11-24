"""DTO del canal HTTP (spec 001 §5 y §6.3; spec 002, contrato del resumen; spec 003, creación y SLA).

Solo describen la forma del contrato: los valores válidos de severidad, estado, equipo,
acción y tipo de duplicado se toman de los `Literal` del dominio, nunca se redefinen aquí
(Art. 1.1).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from src.domain.models import DuplicateType, IncidentStatus, SeverityLevel, TeamName, TriageAction


class ReportIn(BaseModel):
    """Reporte entrante. `incident_id` y cualquier campo desconocido se rechazan con 400."""

    model_config = ConfigDict(extra="forbid")

    raw_text: StrictStr
    created_at: Optional[datetime] = None


class TriageRequest(BaseModel):
    """Cuerpo de `POST /v1/triage`: un lote de 1..N reportes."""

    model_config = ConfigDict(extra="forbid")

    reports: List[ReportIn]


class TriageResultOut(BaseModel):
    """Campos públicos de un resultado (spec 001 §5.2)."""

    severity: SeverityLevel
    component: str
    recommended_team: TeamName
    action: TriageAction
    duplicate_type: DuplicateType
    duplicate_group_key: Optional[str]
    merge: bool
    analysis: List[str]


class TriageResponse(BaseModel):
    """Respuesta de `POST /v1/triage`; conserva orden y longitud del lote."""

    results: List[TriageResultOut]


class SummaryQueryParams(BaseModel):
    """Parámetros de `GET /api/v1/incidents/summary`. Uno desconocido se rechaza con 400.

    Ambos llegan como texto: el servicio normaliza el componente y `parse_reference_time`
    analiza el instante, igual que en el CLI (paridad de aceptación y rechazo).
    """

    model_config = ConfigDict(extra="forbid")

    component: Optional[StrictStr] = None
    reference_time: Optional[StrictStr] = None


class ActiveIncidentItem(BaseModel):
    """Una fila del detalle del resumen (spec 002, FR-004)."""

    incident_id: str
    title: str
    component: str
    severity: SeverityLevel
    status: IncidentStatus
    elapsed_minutes: int
    is_breached: bool
    requires_escalation: bool


class ActiveIncidentsSummaryResponse(BaseModel):
    """Respuesta del resumen; idéntica al `--format json` del CLI (FR-014)."""

    reference_time: str = Field(
        json_schema_extra={"format": "date-time"},
        description="Instante evaluado, ISO-8601 con desfase de Bogotá (-05:00).",
    )
    component_filter: Optional[str]
    total_active: int
    breached_count: int
    incidents: List[ActiveIncidentItem]


class CreateIncidentRequest(BaseModel):
    """Cuerpo de `POST /api/v1/incidents` (spec 003 FR-002).

    Todo llega como texto: longitudes, forma del identificador, estado e instantes los
    valida el servicio, igual que en el CLI (paridad de aceptación y rechazo). Un campo
    desconocido o reservado (lo asigna el triaje) se rechaza con 400.
    """

    model_config = ConfigDict(extra="forbid")

    title: StrictStr
    raw_text: StrictStr
    incident_id: Optional[StrictStr] = None
    created_at: Optional[StrictStr] = None
    status: Optional[StrictStr] = None
    resolved_at: Optional[StrictStr] = None


class IncidentCreatedResponse(BaseModel):
    """Respuesta `201` de la creación; idéntica al `create --format json` del CLI (FR-020)."""

    incident_id: str
    title: str
    status: IncidentStatus
    created_at: str = Field(json_schema_extra={"format": "date-time"})
    resolved_at: Optional[str] = Field(json_schema_extra={"format": "date-time"})
    severity: SeverityLevel
    component: str
    recommended_team: TeamName
    action: TriageAction
    duplicate_group_key: Optional[str]
    analysis: List[str]
    is_duplicate: bool
    duplicate_of: List[str]


class SLAQueryParams(BaseModel):
    """Parámetros de `GET /api/v1/incidents/{incident_id}/sla`. Uno desconocido se rechaza con 400."""

    model_config = ConfigDict(extra="forbid")

    reference_time: Optional[StrictStr] = None


class SLAEvaluationResponse(BaseModel):
    """Respuesta `200` de la auditoría de SLA; idéntica al `sla --format json` del CLI."""

    incident_id: str
    title: str
    component: str
    severity: SeverityLevel
    status: IncidentStatus
    created_at: str = Field(json_schema_extra={"format": "date-time"})
    resolved_at: Optional[str] = Field(json_schema_extra={"format": "date-time"})
    reference_time: str = Field(json_schema_extra={"format": "date-time"})
    resolved_at_reference: bool
    elapsed_minutes: int
    allowed_minutes: int
    remaining_minutes: int
    is_breached: bool
    requires_escalation: bool


class ErrorBody(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class ErrorEnvelope(BaseModel):
    """Envoltura única de error (spec 001 §6.3)."""

    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
