"""Puente de compatibilidad: las entidades viven en `src.domain.models` (ADR-003).

Se conserva para no romper importaciones heredadas (`from src.models import ...`).
Desaparecerá en un hito posterior con su propio ADR (spec 001 §4.3).
"""

from src.domain.models import (  # noqa: F401
    DuplicateType,
    Incident,
    IncidentReport,
    IncidentStatus,
    SeverityLevel,
    SLAEvaluation,
    SLARule,
    TeamName,
    TriageAction,
    TriageResult,
)
