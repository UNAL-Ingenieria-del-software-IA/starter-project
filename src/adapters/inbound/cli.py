"""Adaptador CLI del triaje (spec 001 §7) y del resumen de activos (spec 002) sobre Typer.

Uso:
    uv run python -X utf8 -m src.adapters.inbound.cli triage --raw-text "..." [--format json]
    uv run python -X utf8 -m src.adapters.inbound.cli summary [--component X] [--reference-time ISO] [--format json]

Solo traduce argumentos, llama a `IncidentService` y formatea la salida con las mismas
proyecciones que HTTP (`to_contract`, `summary_to_contract`). `stdout` lleva solo el
resultado; `stderr`, los diagnósticos.

Códigos de salida: 0 éxito · 2 error de uso · 3 entrada inválida · 4 fallo interno o
configuración inválida (p. ej. `DATABASE_URL` no soportada).

`triage`, primer corte: un reporte por invocación. `--file`, `--raw-text` repetible,
`audit`, `--format output` y `--explain` quedan pendientes.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Annotated, Callable, Optional

import typer

from src.application.services import (
    ActiveIncidentsSummary,
    IncidentService,
    ReportInput,
    parse_reference_time,
    summary_to_contract,
    to_contract,
)
from src.application.services import ValidationError as TriageValidationError

EXIT_INVALID_INPUT = 3
EXIT_INTERNAL_ERROR = 4

ServiceFactory = Callable[[Optional[datetime]], IncidentService]


class OutputFormat(str, Enum):
    table = "table"
    json = "json"


def _fail(message: str, code: int) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=code)


def _parse_iso(value: Optional[str], option: str) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise _fail(f"error [invalid_timestamp] {option}: '{value}' no es una fecha ISO-8601 válida.", EXIT_INVALID_INPUT)


def _build_service(service_factory: ServiceFactory, now: Optional[datetime]) -> IncidentService:
    """Obtiene el servicio; un fallo de configuración termina con código 4 y sin traceback.

    El mensaje de la fábrica nombra solo el esquema de `DATABASE_URL`, nunca la URL.
    """
    try:
        return service_factory(now)
    except Exception as exc:  # noqa: BLE001 — configuración inválida → código 4.
        raise _fail(f"error [internal_error]: {exc or type(exc).__name__}", EXIT_INTERNAL_ERROR)


def _yes_no(value: bool) -> str:
    return "sí" if value else "no"


def _render_summary_table(summary: ActiveIncidentsSummary) -> str:
    """Presentación humana del resumen (no es contrato, spec 002 D8)."""
    totals = (
        f"Instante: {summary.reference_time.isoformat()} | Filtro: {summary.component_filter or '(todos)'} | "
        f"total_active={summary.total_active} | breached_count={summary.breached_count}"
    )
    header = (
        f"{'ID':<12} | {'Sev':<3} | {'Estado':<19} | {'Componente':<26} | {'Minutos':>7} | "
        f"{'Incumplido':<10} | Escalar"
    )
    rule = "-" * len(header)
    rows = [
        f"{view.incident_id:<12} | {view.severity:<3} | {view.status:<19} | {view.component:<26} | "
        f"{view.elapsed_minutes:>7} | {_yes_no(view.is_breached):<10} | {_yes_no(view.requires_escalation)}"
        for view in summary.incidents
    ]
    return "\n".join([totals, header, rule, *rows, rule])


def _render_table(label: str, result: dict) -> str:
    header = f"{'ID':<9} | {'Sev':<3} | {'Componente':<26} | {'Equipo':<12} | {'Grupo':<34} | Acción"
    row = (
        f"{label:<9} | {result['severity']:<3} | {result['component']:<26} | {result['recommended_team']:<12} | "
        f"{(result['duplicate_group_key'] or 'none'):<34} | {result['action']}"
    )
    rule = "-" * 125
    return "\n".join([header, rule, row, rule])


def create_cli(service_factory: ServiceFactory) -> typer.Typer:
    """Construye la aplicación Typer; la raíz de composición inyecta la fábrica del servicio."""
    app = typer.Typer(
        help="IncidentOps: triaje determinista y resumen de incidentes activos desde la terminal.",
        add_completion=False,
        no_args_is_help=True,
    )

    @app.callback()
    def main() -> None:
        """IncidentOps: triaje determinista y resumen de incidentes activos desde la terminal."""

    @app.command("triage")
    def triage(
        raw_text: Annotated[str, typer.Option("--raw-text", help="Texto crudo del reporte.")],
        incident_id: Annotated[
            Optional[str],
            typer.Option("--incident-id", help="Etiqueta local de presentación; no aparece en --format json."),
        ] = None,
        created_at: Annotated[
            Optional[str], typer.Option("--created-at", help="Instante ISO-8601 del reporte (naive = Bogotá).")
        ] = None,
        now: Annotated[
            Optional[str], typer.Option("--now", help="Fija el instante de referencia (ClockPort) para reproducir.")
        ] = None,
        output_format: Annotated[
            OutputFormat, typer.Option("--format", help="table (por defecto) o json (mismo cuerpo que HTTP).")
        ] = OutputFormat.table,
    ) -> None:
        """Clasifica un reporte con el mismo caso de uso que el canal HTTP."""
        if incident_id is not None and not incident_id.strip():
            raise _fail("error [invalid_payload] --incident-id: la etiqueta no puede estar vacía.", EXIT_INVALID_INPUT)

        report = ReportInput(raw_text=raw_text, created_at=_parse_iso(created_at, "--created-at"))
        service = _build_service(service_factory, _parse_iso(now, "--now"))

        try:
            results = service.triage_incident([report])
        except TriageValidationError as exc:
            raise _fail(f"error [{exc.code}] {exc.field or '-'}: {exc.message}", EXIT_INVALID_INPUT)
        except Exception as exc:  # noqa: BLE001 — el canal traduce cualquier fallo a código 4.
            raise _fail(f"error [internal_error]: {type(exc).__name__}", EXIT_INTERNAL_ERROR)

        payload = [to_contract(r) for r in results]
        if output_format is OutputFormat.json:
            typer.echo(json.dumps({"results": payload}, ensure_ascii=False))
        else:
            typer.echo(_render_table(incident_id or "R1", payload[0]))

    @app.command("summary")
    def summary(
        component: Annotated[
            Optional[str], typer.Option("--component", help="Filtra por componente (sin mayúsculas ni espacios).")
        ] = None,
        reference_time: Annotated[
            Optional[str],
            typer.Option("--reference-time", help="Instante ISO-8601 a evaluar (naive = Bogotá); por defecto, ahora."),
        ] = None,
        output_format: Annotated[
            OutputFormat, typer.Option("--format", help="table (por defecto) o json (mismo cuerpo que HTTP).")
        ] = OutputFormat.table,
    ) -> None:
        """Resume los incidentes activos con el mismo caso de uso que el canal HTTP."""
        service = _build_service(service_factory, None)
        try:
            result = service.get_active_incidents_summary(component, parse_reference_time(reference_time))
        except TriageValidationError as exc:
            raise _fail(f"error [{exc.code}] {exc.field or '-'}: {exc.message}", EXIT_INVALID_INPUT)
        except Exception as exc:  # noqa: BLE001 — nunca se imprimen títulos (spec 002 FR-015).
            raise _fail(f"error [internal_error]: {type(exc).__name__}", EXIT_INTERNAL_ERROR)

        if output_format is OutputFormat.json:
            typer.echo(json.dumps(summary_to_contract(result), ensure_ascii=False))
        else:
            typer.echo(_render_summary_table(result))

    return app


if __name__ == "__main__":
    from src.main import cli

    cli(prog_name="python -m src.adapters.inbound.cli")
