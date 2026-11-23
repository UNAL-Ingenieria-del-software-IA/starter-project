"""Adaptador HTTP del triaje (spec 001 §6) sobre FastAPI.

Solo traduce: cuerpo JSON → `ReportInput`, llamada a `IncidentService` y resultado →
`to_contract`. No contiene reglas de triaje, SLA ni duplicados (Constitución Art. 2.5).

Reparto de errores (spec 001 D11):
- `400`: la petición no es interpretable (JSON roto, tipo incorrecto, campo desconocido
  o reservado).
- `422`: la petición es interpretable pero su contenido es inaceptable (lo decide el caso
  de uso con `ValidationError`, o `created_at` no parseable).
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence, Tuple

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.adapters.inbound.api.schemas import (
    ErrorEnvelope,
    HealthResponse,
    TriageRequest,
    TriageResponse,
)
from src.application.services import IncidentService, ReportInput, to_contract
from src.application.services import ValidationError as TriageValidationError

logger = logging.getLogger(__name__)

_RESERVED_FIELDS = frozenset({"incident_id"})


def _error_response(status: int, code: str, message: str, field: Optional[str] = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if field is not None:
        body["error"]["field"] = field
    return JSONResponse(status_code=status, content=body)


def _format_loc(loc: Sequence[Any]) -> Optional[str]:
    """Convierte `("body", "reports", 0, "raw_text")` en `"reports[0].raw_text"`."""
    parts = [p for p in loc if p != "body"]
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
        title="IncidentOps — Triaje",
        version="0.1.0",
        description="Clasificación determinista de reportes de incidentes (spec 001).",
    )

    @app.exception_handler(RequestValidationError)
    async def _on_request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        status, code, message, field = _classify_request_error(exc.errors())
        return _error_response(status, code, message, field)

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

    return app
