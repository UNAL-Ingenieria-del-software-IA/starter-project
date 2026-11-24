"""Adaptador HTTP del triaje (spec 001 §6) y del resumen de activos (spec 002) sobre FastAPI.

Solo traduce: petición → llamada a `IncidentService` y resultado → `to_contract` o
`summary_to_contract`. No contiene reglas de triaje, SLA ni duplicados (Constitución
Art. 2.4).

Reparto de errores (spec 001 D11, spec 002 FR-012):
- `400`: la petición no es interpretable (JSON roto, tipo incorrecto, campo o parámetro
  desconocido o reservado).
- `405`: método no permitido, con la envoltura de error común.
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
    ErrorEnvelope,
    HealthResponse,
    SummaryQueryParams,
    TriageRequest,
    TriageResponse,
)
from src.application.services import (
    IncidentService,
    ReportInput,
    parse_reference_time,
    summary_to_contract,
    to_contract,
)
from src.application.services import ValidationError as TriageValidationError

logger = logging.getLogger(__name__)

_RESERVED_FIELDS = frozenset({"incident_id"})
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


def _classify_request_error(errors: Sequence[dict]) -> Tuple[int, str, str, Optional[str]]:
    """Elige estado, `code`, mensaje y campo a partir del primer error relevante de pydantic."""
    for err in errors:
        if err.get("type") == "json_invalid":
            return 400, "invalid_json", "El cuerpo no es JSON válido.", None
    for err in errors:
        loc = err.get("loc", ())
        if err.get("type") == "extra_forbidden" and loc and loc[-1] in _RESERVED_FIELDS:
            return 400, "reserved_field", f"El campo '{loc[-1]}' está reservado y no forma parte del contrato.", _format_loc(loc)
    for err in errors:
        loc = err.get("loc", ())
        if loc and loc[-1] == "created_at" and str(err.get("type", "")).startswith("datetime"):
            return 422, "invalid_timestamp", "`created_at` no es una fecha ISO-8601 válida.", _format_loc(loc)
    first = errors[0] if errors else {}
    return 400, "invalid_payload", "El cuerpo no cumple el contrato de la petición.", _format_loc(first.get("loc", ()))


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
    async def _on_request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        status, code, message, field = _classify_request_error(exc.errors())
        return _error_response(status, code, message, field)

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
        return _error_response(500, "internal_error", "Error interno al clasificar el lote.")

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

    return app
