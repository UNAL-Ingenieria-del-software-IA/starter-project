"""Arnés de benchmark del resumen de incidentes activos (spec 002 SC-001, research §R15).

Compone lo mismo que la raíz de composición, sin canales: `SQLiteIncidentRepository`
(en memoria) + `IncidentService` + `FixedClock`. Siembra incidentes sintéticos con
componentes canónicos vía `save_incident` y mide `get_active_incidents_summary` con y sin
filtro de componente, informando promedio y p95.

La consulta ya filtra los activos en SQL (`status <> 'RESOLVED'`, ADR-005) con un índice
parcial cubriente y un único `INNER JOIN sla_policies` (ADR-001): no hay escaneo completo
ni consultas N+1. Este módulo no contiene SQL propio; la persistencia vive en
`src/adapters/outbound/sqlite_repository.py`.

Uso:
    uv run python -X utf8 -m src.incident_repository --records 20000 --iterations 20
"""

import argparse
import math
import time
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Tuple

from src.adapters.outbound.clock import FixedClock
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.services import ActiveIncidentsSummary, IncidentService
from src.domain.models import Incident, IncidentStatus, SeverityLevel
from src.domain.working_time_calculator import BOGOTA_TZ

COMPONENTS: Tuple[str, ...] = (
    "payment-gateway",
    "auth-identity",
    "database-cluster",
    "reporting-api",
    "frontend-ui",
)
SEVERITIES: Tuple[SeverityLevel, ...] = ("P0", "P1", "P2", "P3")
# 3 de cada 5 activos: con --records 20000 quedan 12 000 activos (SC-001 pide ≥ 10 000).
STATUSES: Tuple[IncidentStatus, ...] = ("OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED", "RESOLVED", "RESOLVED")
REFERENCE_TIME = datetime(2026, 11, 24, 9, 0, tzinfo=BOGOTA_TZ)
FILTERED_COMPONENT = "payment-gateway"
SC001_LIMIT_MS = 1000.0


def seed_synthetic_incidents(repository: SQLiteIncidentRepository, total_records: int) -> None:
    """Siembra incidentes deterministas por el puerto (mismas validaciones que producción)."""
    for index in range(1, total_records + 1):
        status = STATUSES[(index * 3 + index // 5) % len(STATUSES)]
        component = COMPONENTS[index % len(COMPONENTS)]
        created_at = REFERENCE_TIME - timedelta(minutes=(index % 10_000) * 2 + 1)
        repository.save_incident(
            Incident(
                incident_id=f"INC-{index:05d}",
                title=f"Reporte sintético #{index} en {component}",
                component=component,
                severity=SEVERITIES[index % len(SEVERITIES)],
                status=status,
                created_at=created_at,
                resolved_at=created_at + timedelta(minutes=45) if status == "RESOLVED" else None,
            )
        )


def _p95(samples_ms: List[float]) -> float:
    """Percentil 95 por rango más cercano (sin dependencias estadísticas)."""
    ordered = sorted(samples_ms)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _measure(
    query: Callable[[], ActiveIncidentsSummary], iterations: int
) -> Tuple[Optional[ActiveIncidentsSummary], List[float]]:
    samples: List[float] = []
    summary: Optional[ActiveIncidentsSummary] = None
    for _ in range(iterations):
        started = time.perf_counter()
        summary = query()
        samples.append((time.perf_counter() - started) * 1000)
    return summary, samples


def _run_benchmark() -> int:
    parser = argparse.ArgumentParser(description="Benchmark del resumen de incidentes activos (SC-001)")
    parser.add_argument("--records", type=int, default=20_000, help="Cantidad de incidentes a sembrar")
    parser.add_argument("--iterations", type=int, default=20, help="Consultas medidas por escenario")
    args = parser.parse_args()
    if args.records < 1 or args.iterations < 1:
        parser.error("--records y --iterations deben ser enteros positivos.")

    repository = SQLiteIncidentRepository(":memory:")
    service = IncidentService(FixedClock(REFERENCE_TIME), repository)
    print(f"Sembrando {args.records} incidentes sintéticos en SQLite en memoria (vía save_incident)...")
    seed_synthetic_incidents(repository, args.records)

    scenarios = (
        ("sin filtro", lambda: service.get_active_incidents_summary()),
        (f"component={FILTERED_COMPONENT}", lambda: service.get_active_incidents_summary(FILTERED_COMPONENT)),
    )

    print("=== Benchmark del resumen de incidentes activos (SC-001) ===")
    print(f"Instante de referencia: {REFERENCE_TIME.isoformat()} · {args.iterations} consultas por escenario")
    all_within_limit = True
    for label, query in scenarios:
        summary, samples = _measure(query, args.iterations)
        p95 = _p95(samples)
        within_limit = p95 < SC001_LIMIT_MS
        all_within_limit = all_within_limit and within_limit
        assert summary is not None
        print(
            f"- {label:<28} activos={summary.total_active:>6} incumplidos={summary.breached_count:>6} "
            f"promedio={sum(samples) / len(samples):8.2f} ms  p95={p95:8.2f} ms  "
            f"{'OK' if within_limit else 'FUERA DE OBJETIVO'} (< {SC001_LIMIT_MS:.0f} ms)"
        )
    return 0 if all_within_limit else 1


if __name__ == "__main__":
    raise SystemExit(_run_benchmark())
