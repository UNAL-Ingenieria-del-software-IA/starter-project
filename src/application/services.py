"""Casos de uso compartidos: triaje (H001), resumen de activos (H002), y creación y
auditoría de SLA de incidentes (H003).

`IncidentService` es el único punto por el que REST y CLI clasifican reportes, consultan
el resumen, crean incidentes y auditan su SLA. `to_contract` (spec 001 §5.2),
`summary_to_contract` (spec 002), `creation_to_contract` y `sla_audit_to_contract`
(spec 003) son las únicas proyecciones al contrato público, de modo que la paridad entre
canales se obtiene por construcción (Art. 2.7). La clasificación y la clave de grupo
salen solo de `classify_incident`, y minutos, incumplimiento y escalamiento solo de
`evaluate_sla_status`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, get_args

from src.application.ports import (
    ClockPort,
    IncidentIdConflictError,
    IncidentIdGeneratorPort,
    IncidentRepositoryPort,
)
from src.domain.models import (
    ACTIVE_STATUSES,
    SEVERITY_ORDER,
    Incident,
    IncidentReport,
    IncidentStatus,
    SeverityLevel,
    SLAEvaluation,
    TriageResult,
)
from src.domain.sla_calculator import evaluate_sla_status
from src.domain.triage_rules import classify_incident, classify_incident_batch
from src.domain.working_time_calculator import to_bogota

# Límites de la solicitud de creación (spec 003 FR-002, FR-004).
TITLE_MAX_LENGTH = 200
RAW_TEXT_MAX_LENGTH = 5_000
_CLIENT_ID_PATTERN = re.compile(r"INC-[A-Za-z0-9-]{1,32}")
_GENERATED_ID_ATTEMPTS = 5
# Los estados válidos se toman del dominio (Art. 1.10), no se redefinen aquí.
_VALID_STATUSES = frozenset(get_args(IncidentStatus))


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


class IncidentNotFoundError(Exception):
    """El incidente pedido no existe en el almacén (spec 003 FR-016: 404 / código 1)."""

    def __init__(self, incident_id: str) -> None:
        super().__init__(f"No existe el incidente {incident_id}.")
        self.incident_id = incident_id


@dataclass(frozen=True)
class CreateIncidentInput:
    """Solicitud de creación ya traducida por el canal (spec 003 FR-002).

    `status` llega como texto: lo valida el servicio para que ambos canales acepten y
    rechacen lo mismo (research §R6).
    """

    title: str
    raw_text: str
    incident_id: Optional[str] = None
    created_at: Optional[datetime] = None
    status: Optional[str] = None
    resolved_at: Optional[datetime] = None


@dataclass(frozen=True)
class IncidentCreation:
    """Resultado de `create_incident`: el incidente guardado, su triaje y el aviso de duplicado."""

    incident: Incident
    triage: TriageResult
    duplicate_of: Tuple[str, ...]

    @property
    def is_duplicate(self) -> bool:
        return bool(self.duplicate_of)


@dataclass(frozen=True)
class IncidentSLAAudit:
    """Resultado de `evaluate_incident_sla`: incidente, instante evaluado y evaluación canónica."""

    incident: Incident
    reference_time: datetime
    evaluation: SLAEvaluation


def parse_instant(value: Optional[str], field: str) -> Optional[datetime]:
    """Analiza un instante de cualquier canal con una sola regla (spec 002 FR-008, spec 003 R6).

    Admite `datetime.fromisoformat` y un sufijo `Z` (CPython 3.10 no lo acepta). Sin zona =
    hora de Bogotá, lo resuelve el servicio.

    Raises:
        ValidationError: `invalid_timestamp` sobre `field` si la cadena no es ISO-8601.
    """
    if value is None:
        return None
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise ValidationError("invalid_timestamp", f"'{value}' no es una fecha ISO-8601 válida.", field) from None


def parse_reference_time(value: Optional[str]) -> Optional[datetime]:
    """Alias de `parse_instant` para `reference_time` (contrato de H002)."""
    return parse_instant(value, "reference_time")


class IncidentService:
    """Casos de uso compartidos por todos los canales.

    El triaje (H001) no usa el repositorio; el resumen de activos (H002) solo lo lee.
    """

    def __init__(
        self,
        clock: ClockPort,
        repository: IncidentRepositoryPort,
        id_generator: Optional[IncidentIdGeneratorPort] = None,
    ) -> None:
        self._clock = clock
        self._repository = repository
        self._id_generator = id_generator

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

        Solo lee el repositorio (FR-015). El filtro se compara sin mayúsculas y sin
        espacios circundantes (FR-006). El instante es `reference_time` o el reloj
        inyectado, en hora de Bogotá y truncado a segundos: el mismo que se evalúa y se
        declara (FR-008). Los creados después del instante no cuentan (FR-009).

        Raises:
            ValidationError: `invalid_payload` si el filtro está vacío o solo tiene espacios.
        """
        if component_filter is not None:
            component_filter = component_filter.strip().lower()
            if not component_filter:
                raise ValidationError(
                    "invalid_payload",
                    "El filtro de componente no puede estar vacío ni contener solo espacios.",
                    "component",
                )
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

    def create_incident(self, request: CreateIncidentInput) -> IncidentCreation:
        """Crea un incidente clasificado y avisa si duplica uno abierto (spec 003 US1–US2).

        1. Valida título, texto, identificador, estado y resolución (FR-002, FR-004, FR-005).
        2. Completa `created_at` con el reloj y normaliza a Bogotá (Art. 1.7).
        3. Clasifica el texto con el triaje canónico de un solo reporte (FR-003, FR-023).
        4. Guarda sin reemplazar (`add_incident`); un identificador generado que choca se
           regenera, uno enviado por el cliente propaga el conflicto (409).
        5. Después de guardar, busca abiertos con la misma clave (FR-007, FR-011).

        Nunca modifica otro incidente (FR-009).

        Raises:
            ValidationError: `invalid_payload` si el contenido es inaceptable.
            IncidentIdConflictError: si el identificador enviado ya existe.
            RuntimeError: si no hay generador de identificadores inyectado.
        """
        self._validate_creation(request)
        incident_id = request.incident_id.strip() if request.incident_id is not None else None
        status: IncidentStatus = request.status if request.status is not None else "OPEN"  # type: ignore[assignment]
        if request.created_at is not None:
            created_at = to_bogota(request.created_at)
        else:
            created_at = to_bogota(self._clock.now()).replace(microsecond=0)
        resolved_at = to_bogota(request.resolved_at) if request.resolved_at is not None else None
        if resolved_at is not None and resolved_at < created_at:
            raise ValidationError(
                "invalid_payload", "La resolución no puede ser anterior a la creación.", "resolved_at"
            )

        triage = classify_incident(
            IncidentReport(incident_id=incident_id or "R1", raw_text=request.raw_text, created_at=created_at)
        )

        def build(identifier: str) -> Incident:
            return Incident(
                incident_id=identifier,
                title=request.title,
                component=triage.component,
                severity=triage.severity,
                status=status,
                created_at=created_at,
                resolved_at=resolved_at,
                recommended_team=triage.recommended_team,
                duplicate_group_key=triage.duplicate_group_key,
            )

        if incident_id is not None:
            incident = build(incident_id)
            self._repository.add_incident(incident)
        else:
            incident = self._add_with_generated_id(build)

        duplicate_of: Tuple[str, ...] = ()
        if incident.duplicate_group_key is not None:
            duplicate_of = tuple(
                item.incident_id
                for item in self._repository.find_open_duplicates(incident.duplicate_group_key, incident.incident_id)
            )
        return IncidentCreation(incident=incident, triage=triage, duplicate_of=duplicate_of)

    def evaluate_incident_sla(
        self, incident_id: str, reference_time: Optional[datetime] = None
    ) -> IncidentSLAAudit:
        """Audita el SLA de un incidente en un instante, sin modificar nada (spec 003 US3).

        El instante es `reference_time` o el reloj, en Bogotá y truncado a segundos
        (FR-014). Las cifras salen solo de `evaluate_sla_status` (FR-013, FR-015).

        Raises:
            IncidentNotFoundError: si el identificador no existe (FR-016).
            ValidationError: `reference_before_creation` si el instante es anterior a la creación.
        """
        incident = self._repository.get_incident(incident_id)
        if incident is None:
            raise IncidentNotFoundError(incident_id)
        instant = to_bogota(reference_time or self._clock.now()).replace(microsecond=0)
        if instant < to_bogota(incident.created_at):
            raise ValidationError(
                "reference_before_creation",
                "El instante de referencia es anterior a la creación del incidente.",
                "reference_time",
            )
        return IncidentSLAAudit(incident=incident, reference_time=instant, evaluation=evaluate_sla_status(incident, instant))

    def _add_with_generated_id(self, build) -> Incident:
        if self._id_generator is None:
            raise RuntimeError("No hay generador de identificadores configurado.")
        for _ in range(_GENERATED_ID_ATTEMPTS):
            incident = build(self._id_generator.new_id())
            try:
                self._repository.add_incident(incident)
                return incident
            except IncidentIdConflictError:
                continue  # El cliente nunca recibe un conflicto por un identificador que no envió.
        raise RuntimeError("No se pudo generar un identificador libre.")

    @staticmethod
    def _validate_creation(request: CreateIncidentInput) -> None:
        for field, value, limit in (
            ("title", request.title, TITLE_MAX_LENGTH),
            ("raw_text", request.raw_text, RAW_TEXT_MAX_LENGTH),
        ):
            if not value.strip():
                raise ValidationError("invalid_payload", "El campo no puede estar vacío ni contener solo espacios.", field)
            if len(value) > limit:
                raise ValidationError("invalid_payload", f"El campo supera los {limit} caracteres.", field)
        if request.incident_id is not None and not _CLIENT_ID_PATTERN.fullmatch(request.incident_id.strip()):
            raise ValidationError(
                "invalid_payload",
                "El identificador debe ser 'INC-' seguido de 1 a 32 letras, dígitos o guiones.",
                "incident_id",
            )
        status = request.status if request.status is not None else "OPEN"
        if status not in _VALID_STATUSES:
            raise ValidationError("invalid_payload", f"Estado no admitido: '{status}'.", "status")
        if status == "RESOLVED" and request.resolved_at is None:
            raise ValidationError("invalid_payload", "Un incidente RESOLVED exige resolved_at.", "resolved_at")
        if status != "RESOLVED" and request.resolved_at is not None:
            raise ValidationError(
                "invalid_payload", "resolved_at solo se admite con el estado RESOLVED.", "resolved_at"
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


def _iso(value: Optional[datetime]) -> Optional[str]:
    return to_bogota(value).isoformat() if value is not None else None


def creation_to_contract(creation: IncidentCreation) -> Dict[str, Any]:
    """Proyecta una creación al cuerpo JSON de spec 003 (mismo valor por HTTP y CLI).

    No publica `duplicate_type` ni `merge`: describen la correlación de un lote.
    """
    incident, triage = creation.incident, creation.triage
    return {
        "incident_id": incident.incident_id,
        "title": incident.title,
        "status": incident.status,
        "created_at": _iso(incident.created_at),
        "resolved_at": _iso(incident.resolved_at),
        "severity": incident.severity,
        "component": incident.component,
        "recommended_team": incident.recommended_team,
        "action": triage.action,
        "duplicate_group_key": incident.duplicate_group_key,
        "analysis": list(triage.analysis),
        "is_duplicate": creation.is_duplicate,
        "duplicate_of": list(creation.duplicate_of),
    }


def sla_audit_to_contract(audit: IncidentSLAAudit) -> Dict[str, Any]:
    """Proyecta una auditoría de SLA al cuerpo JSON de spec 003 (mismo valor por HTTP y CLI)."""
    incident, evaluation = audit.incident, audit.evaluation
    return {
        "incident_id": incident.incident_id,
        "title": incident.title,
        "component": incident.component,
        "severity": incident.severity,
        "status": incident.status,
        "created_at": _iso(incident.created_at),
        "resolved_at": _iso(incident.resolved_at),
        "reference_time": _iso(audit.reference_time),
        "resolved_at_reference": evaluation.resolved_at_reference,
        "elapsed_minutes": evaluation.elapsed_minutes,
        "allowed_minutes": evaluation.allowed_minutes,
        "remaining_minutes": evaluation.remaining_minutes,
        "is_breached": evaluation.is_breached,
        "requires_escalation": evaluation.requires_escalation,
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
