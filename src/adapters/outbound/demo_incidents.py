"""Conjunto fijo de demostración de H002 (spec 002, D1; research §R6).

Se siembra al arrancar solo cuando el almacén es `sqlite:///:memory:`. Son constantes
Python (sin E/S), así que HTTP y CLI leen exactamente los mismos datos (FR-001). Los
identificadores `INC-2xxx` no chocan con el fixture graduado `data/sample_incidents.json`.

Evaluado a `2026-11-24T09:00:00-05:00` (martes):

| ID | Sev | Estado | Componente | Minutos | Incumplido | Escalar |
|---|---|---|---|---|---|---|
| INC-2001 | P0 | OPEN | payment-gateway | 90 | sí | no |
| INC-2002 | P2 | IN_PROGRESS | payment-gateway | 60 | no | no |
| INC-2003 | P1 | ESCALATION_REQUIRED | auth-identity | 180 | no | sí |
| INC-2004 | P2 | OPEN | database-cluster | 660 (creado en sábado) | sí | no |
| INC-2005 | P3 | IN_PROGRESS | database-cluster | 300 | no | no |
| INC-2006 | P0 | RESOLVED | auth-identity | — | — | — |
| INC-2007 | P3 | OPEN | frontend-ui | 1200 | no | sí |
| INC-2008 | P1 | RESOLVED | payment-gateway | — | — | — |
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Tuple

from src.application.ports import IncidentRepositoryPort
from src.domain.models import Incident, IncidentReport
from src.domain.triage_rules import classify_incident
from src.domain.working_time_calculator import BOGOTA_TZ


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=BOGOTA_TZ)


DEMO_INCIDENTS: Tuple[Incident, ...] = (
    Incident("INC-2001", "Caída de la pasarela de pagos", "payment-gateway", "P0", "OPEN", _at(24, 7, 30)),
    Incident("INC-2002", "Latencia en la confirmación de pagos", "payment-gateway", "P2", "IN_PROGRESS", _at(24, 8)),
    Incident(
        "INC-2003", "Fallos intermitentes de inicio de sesión", "auth-identity", "P1", "ESCALATION_REQUIRED", _at(24, 6)
    ),
    Incident("INC-2004", "Réplica de base de datos con retraso", "database-cluster", "P2", "OPEN", _at(21, 10)),
    Incident("INC-2005", "Consultas lentas en el clúster de reportes", "database-cluster", "P3", "IN_PROGRESS", _at(23, 14)),
    Incident(
        "INC-2006", "Bloqueo masivo de cuentas", "auth-identity", "P0", "RESOLVED", _at(23, 20), resolved_at=_at(23, 20, 40)
    ),
    Incident("INC-2007", "Botón de exportación desalineado", "frontend-ui", "P3", "OPEN", _at(20, 9)),
    Incident(
        "INC-2008", "Rechazos de tarjetas en el checkout", "payment-gateway", "P1", "RESOLVED", _at(22, 10), resolved_at=_at(22, 12)
    ),
)


def seed_demo_incidents(repository: IncidentRepositoryPort) -> None:
    """Guarda el conjunto fijo de demostración por el puerto.

    La clave de grupo y el equipo de cada demo los deriva el dominio aplicando el triaje a
    su título (spec 003 research §R9): así `INC-2001` queda con `payment-availability` sin
    escribir claves a mano. Severidad, componente, estado e instantes son los de las
    constantes, que son el contrato de demostración de spec 002.
    """
    for incident in DEMO_INCIDENTS:
        triage = classify_incident(IncidentReport(incident.incident_id, incident.title, incident.created_at))
        repository.save_incident(
            replace(
                incident,
                recommended_team=triage.recommended_team,
                duplicate_group_key=triage.duplicate_group_key,
            )
        )
