"""Adaptador HTTP del triaje (spec 001 §6), del resumen de activos (spec 002) y de la
creación y auditoría de SLA de incidentes (spec 003) sobre FastAPI.

Solo traduce: petición → llamada a `IncidentService` y resultado → `to_contract`,
`summary_to_contract`, `creation_to_contract` o `sla_audit_to_contract`. No contiene
reglas de triaje, SLA ni duplicados (Constitución Art. 2.4).

Reparto de errores (spec 001 D11, spec 002 FR-012, spec 003 FR-016–FR-018):
- `400`: la petición no es interpretable (JSON roto, tipo incorrecto, campo o parámetro
  desconocido o reservado).
- `404`: el incidente auditado no existe (`incident_not_found`).
- `405`: método no permitido, con la envoltura de error común.
- `409`: el identificador enviado ya existe (`incident_id_conflict`).
- `422`: la petición es interpretable pero su contenido es inaceptable (lo decide el caso
  de uso con `ValidationError`, o una fecha no parseable).
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any, Mapping, Optional, Sequence, Tuple

from fastapi import FastAPI, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.adapters.inbound.api.schemas import (
    ActiveIncidentsSummaryResponse,
    CreateIncidentRequest,
    ErrorEnvelope,
    HealthResponse,
    IncidentCreatedResponse,
    SLAEvaluationResponse,
    SLAQueryParams,
    SummaryQueryParams,
    TriageRequest,
    TriageResponse,
)
from src.application.ports import IncidentIdConflictError
from src.application.services import (
    CreateIncidentInput,
    IncidentNotFoundError,
    IncidentService,
    ReportInput,
    creation_to_contract,
    parse_instant,
    parse_reference_time,
    sla_audit_to_contract,
    summary_to_contract,
    to_contract,
)
from src.application.services import ValidationError as TriageValidationError

logger = logging.getLogger(__name__)

INCIDENTS_PATH = "/api/v1/incidents"

# Campos reservados por ruta: el triaje los asigna y el cliente no puede enviarlos.
_RESERVED_FIELDS = frozenset({"incident_id"})
_CREATE_RESERVED_FIELDS = frozenset({"severity", "component", "recommended_team", "action", "duplicate_group_key"})
_LOCATION_PREFIXES = frozenset({"body", "query"})


def _error_response(
    status: int,
    code: str,
    message: str,
    field: Optional[str] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if field is not None:
        body["error"]["field"] = field
    return JSONResponse(status_code=status, content=body, headers=dict(headers) if headers else None)


def _format_loc(loc: Sequence[Any]) -> Optional[str]:
    """Convierte `("body", "reports", 0, "raw_text")` en `"reports[0].raw_text"`."""
    parts = [p for p in loc if p not in _LOCATION_PREFIXES]
    if not parts:
        return None
    text = ""
    for part in parts:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}" if text else str(part)
    return text


def _classify_request_error(
    errors: Sequence[dict], reserved: frozenset = _RESERVED_FIELDS
) -> Tuple[int, str, str, Optional[str]]:
    """Elige estado, `code`, mensaje y campo a partir del primer error relevante de pydantic."""
    for err in errors:
        if err.get("type") == "json_invalid":
            return 400, "invalid_json", "El cuerpo no es JSON válido.", None
    for err in errors:
        loc = err.get("loc", ())
        if err.get("type") == "extra_forbidden" and loc and loc[-1] in reserved:
            return 400, "reserved_field", f"El campo '{loc[-1]}' está reservado y no forma parte del contrato.", _format_loc(loc)
    for err in errors:
        loc = err.get("loc", ())
        if loc and loc[-1] == "created_at" and str(err.get("type", "")).startswith("datetime"):
            return 422, "invalid_timestamp", "`created_at` no es una fecha ISO-8601 válida.", _format_loc(loc)
    first = errors[0] if errors else {}
    loc = first.get("loc", ())
    if loc and loc[0] == "query":
        return 400, "invalid_payload", "Los parámetros de consulta no cumplen el contrato de la petición.", _format_loc(loc)
    return 400, "invalid_payload", "El cuerpo no cumple el contrato de la petición.", _format_loc(loc)


def create_app(service: IncidentService) -> FastAPI:
    """Construye la aplicación HTTP con el caso de uso inyectado por la raíz de composición."""
    app = FastAPI(
        title="IncidentOps — Triaje y resumen de activos",
        version="0.2.0",
        description=(
            "Clasificación determinista de reportes de incidentes (spec 001) y resumen de "
            "incidentes activos (spec 002)."
        ),
    )

    @app.exception_handler(RequestValidationError)
    async def _on_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Los campos reservados de la creación solo se aplican a su ruta: así los códigos de
        # `POST /v1/triage` no cambian.
        reserved = _CREATE_RESERVED_FIELDS if request.url.path == INCIDENTS_PATH else _RESERVED_FIELDS
        status, code, message, field = _classify_request_error(exc.errors(), reserved)
        return _error_response(status, code, message, field)

    @app.exception_handler(IncidentIdConflictError)
    async def _on_id_conflict(_: Request, exc: IncidentIdConflictError) -> JSONResponse:
        return _error_response(409, "incident_id_conflict", str(exc), "incident_id")

    @app.exception_handler(IncidentNotFoundError)
    async def _on_not_found(_: Request, exc: IncidentNotFoundError) -> JSONResponse:
        return _error_response(404, "incident_not_found", str(exc), "incident_id")

    @app.exception_handler(StarletteHTTPException)
    async def _on_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Solo 405 adopta la envoltura común (spec 002 FR-012); el resto conserva su forma.
        if exc.status_code == 405:
            return _error_response(
                405, "method_not_allowed", "Método no permitido para este recurso.", headers=exc.headers
            )
        return await http_exception_handler(request, exc)

    @app.exception_handler(TriageValidationError)
    async def _on_triage_validation_error(_: Request, exc: TriageValidationError) -> JSONResponse:
        return _error_response(422, exc.code, exc.message, exc.field)

    @app.exception_handler(Exception)
    async def _on_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Nunca se registra el cuerpo ni `raw_text` (spec 001 §6.4).
        logger.error("Fallo interno en %s %s: %s", request.method, request.url.path, type(exc).__name__)
        return _error_response(500, "internal_error", "Error interno al procesar la petición.")

    @app.get("/v1/health", response_model=HealthResponse)
    def health() -> dict:
        return {"status": "ok"}

    @app.post(
        "/v1/triage",
        response_model=TriageResponse,
        responses={400: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
    )
    def triage(request: TriageRequest) -> dict:
        reports = [ReportInput(raw_text=r.raw_text, created_at=r.created_at) for r in request.reports]
        results = service.triage_incident(reports)
        return {"results": [to_contract(r) for r in results]}

    @app.get(
        "/api/v1/incidents/summary",
        response_model=ActiveIncidentsSummaryResponse,
        responses={
            400: {"model": ErrorEnvelope},
            405: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            500: {"model": ErrorEnvelope},
        },
    )
    def incidents_summary(params: Annotated[SummaryQueryParams, Query()]) -> dict:
        """Resumen de incidentes activos, con filtro de componente e instante opcionales."""
        started = time.perf_counter()
        summary = service.get_active_incidents_summary(
            params.component, parse_reference_time(params.reference_time)
        )
        body = summary_to_contract(summary)
        # Solo cifras, duración y estado: nunca títulos ni parámetros (spec 002 FR-015).
        logger.info(
            "Resumen de activos: total_active=%d breached_count=%d duracion_ms=%.1f estado=200",
            summary.total_active,
            summary.breached_count,
            (time.perf_counter() - started) * 1000,
        )
        return body

    @app.post(
        INCIDENTS_PATH,
        status_code=201,
        response_model=IncidentCreatedResponse,
        responses={
            400: {"model": ErrorEnvelope},
            405: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            500: {"model": ErrorEnvelope},
        },
    )
    def create_incident(request: CreateIncidentRequest) -> dict:
        """Crea un incidente clasificado y avisa si duplica uno abierto (spec 003 US1–US2)."""
        started = time.perf_counter()
        creation = service.create_incident(
            CreateIncidentInput(
                title=request.title,
                raw_text=request.raw_text,
                incident_id=request.incident_id,
                created_at=parse_instant(request.created_at, "created_at"),
                status=request.status,
                resolved_at=parse_instant(request.resolved_at, "resolved_at"),
            )
        )
        # Solo identificador, aviso, duración y código: nunca título ni texto (spec 003 FR-021).
        logger.info(
            "Incidente creado: incident_id=%s is_duplicate=%s duplicados=%d duracion_ms=%.1f codigo=201",
            creation.incident.incident_id,
            creation.is_duplicate,
            len(creation.duplicate_of),
            (time.perf_counter() - started) * 1000,
        )
        return creation_to_contract(creation)

    @app.get(
        INCIDENTS_PATH + "/{incident_id}/sla",
        response_model=SLAEvaluationResponse,
        responses={
            400: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            405: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            500: {"model": ErrorEnvelope},
        },
    )
    def incident_sla(incident_id: str, params: Annotated[SLAQueryParams, Query()]) -> dict:
        """Audita el SLA de un incidente en un instante, sin modificar nada (spec 003 US3)."""
        started = time.perf_counter()
        audit = service.evaluate_incident_sla(incident_id, parse_reference_time(params.reference_time))
        # Solo identificador, duración y código: nunca títulos (spec 003 FR-021).
        logger.info(
            "Auditoría de SLA: incident_id=%s duracion_ms=%.1f codigo=200",
            incident_id,
            (time.perf_counter() - started) * 1000,
        )
        return sla_audit_to_contract(audit)

    return app
