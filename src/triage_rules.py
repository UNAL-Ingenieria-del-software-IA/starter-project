"""Puente de compatibilidad y auditoría del motor de triaje.

El pipeline puro vive en `src.domain.triage_rules` (ADR-003). Este módulo conserva la
carga del fixture `data/sample_incidents.json` y la auditoría graduada, que dependen de
`json` y `pathlib` y por eso no pueden vivir en el dominio (Constitución Art. 1.2).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List

from src.domain.models import IncidentReport
from src.domain.triage_rules import (  # noqa: F401
    DUPLICATE_MERGE_WINDOW,
    HIGH_VOLUME_THRESHOLD,
    INTERACTIVE_LATENCY_THRESHOLD_S,
    SATURATION_THRESHOLD_PCT,
    IncidentSignals,
    SeverityDecision,
    classify_incident_batch,
    classify_incident_report,
    decide_action,
    decide_severity,
    extract_signals,
    route_component,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample_incidents.json"


def load_reports(path: Path = SAMPLE_DATA_PATH) -> List[IncidentReport]:
    items = json.loads(path.read_text(encoding="utf-8"))
    return [
        IncidentReport(
            incident_id=item["id"],
            raw_text=item["raw_text"],
            created_at=datetime.fromisoformat(item["created_at"]) if item.get("created_at") else None,
        )
        for item in items
    ]


def _run_triage_audit() -> None:
    """Ejecuta el motor sobre los incidentes de prueba e imprime análisis + salida."""
    results = classify_incident_batch(load_reports())

    print("=== Auditoría del Motor de Triaje (`src/triage_rules.py`) ===\n")
    print(f"{'ID':<9} | {'Sev':<3} | {'Componente':<26} | {'Equipo':<12} | {'Grupo':<34} | Acción")
    print("-" * 125)
    for r in results:
        print(
            f"{r.incident_id:<9} | {r.severity:<3} | {r.component:<26} | {r.recommended_team or '-':<12} | "
            f"{(r.duplicate_group_key or 'none'):<34} | {r.action}"
        )
    print("-" * 125)
    for r in results:
        print(f"\n<incident id=\"{r.incident_id}\">\n  <analysis>")
        for step in r.analysis:
            print(f"    {step}")
        print(f"  </analysis>\n  <output>\n    {r.to_output_line()}\n  </output>\n</incident>")


if __name__ == "__main__":
    _run_triage_audit()