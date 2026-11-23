"""DTO del canal HTTP (spec 001 §5 y §6.3).

Solo describen la forma del contrato: los valores válidos de severidad, equipo, acción y
tipo de duplicado se toman de los `Literal` del dominio, nunca se redefinen aquí (Art. 1.1).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, StrictStr

from src.domain.models import DuplicateType, SeverityLevel, TeamName, TriageAction


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


class ErrorBody(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class ErrorEnvelope(BaseModel):
    """Envoltura única de error (spec 001 §6.3)."""

    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
