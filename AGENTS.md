# AGENTS.md

IncidentOps: Python 3.10 + `uv`, standard library only except `tiktoken` (context audits).
This is a Week 1 ISIA teaching repo. Code, docstrings, CLI output, and docs are in Spanish — match that.

## Commands (run from the repo root)

```bash
uv sync
uv run python -X utf8 -m src.sla_calculator                 # de facto regression suite: 10 SLA assertions, exits 1 on failure
uv run python -X utf8 -m src.triage_rules                   # triage audit over data/sample_incidents.json
uv run python -X utf8 -m src.context_audit --symbol evaluate_sla_status
uv run python -X utf8 -m src.context_audit --compare-formats
uv run python -X utf8 -m src.incident_repository --records 2000 --iterations 2   # quick benchmark smoke
```

- Always use `-m src.<module>`; files import via `from src...`, so `uv run python src/foo.py` or running from inside `src/` fails. `pyproject.toml` sets `package = false`, so the package is not installed.
- Keep `-X utf8` on this Windows setup: demos print accented Spanish and otherwise die with `UnicodeEncodeError` under the local cp932 code page.
- There is no pytest/ruff/mypy config and no `tests/` directory. `_run_demo()` in `src/sla_calculator.py` is the only verification harness; do not claim tests exist.

## Architecture

- `src/models.py` — shared dataclasses and `Literal` types (`SeverityLevel`, `SLAEvaluation`, `TriageResult.to_output_line()`).
- `src/sla_calculator.py` — `SLA_POLICY_TABLE` and `evaluate_sla_status`: P0/P1 use calendar 24x7, P2/P3 use working minutes; escalation at 75%, breach only when elapsed `>` allowed.
- `src/working_time_calculator.py` — fixed Bogotá UTC-5 (`COT`, avoids tzdata), Mon–Fri 08:00–18:00, `is_working_day`.
- `src/holidays.py` — Colombian holidays computed dynamically per year (Ley 51/1983; Easter-derived dates).
- `src/triage_rules.py` — pure 4-stage pipeline: `extract_signals` → `decide_severity` → `route_component` → `correlate_batch`. Severity is decided from impact signals, never from urgency words ("urgente", "hoy"), which are recorded as lexical traps.
- `src/incident_repository.py` — in-memory SQLite; active-query path and partial index already match ADR-001.
- `src/context_audit.py` — AST-based LSP emulation plus `tiktoken` token counting.

## Gotchas

- ADR-002 mentions `src/colombian_calendar.py` and `tests/`; neither exists. Working-day logic lives in `src/working_time_calculator.py`, and verification is the in-module `_run_demo()`.
- `incident_repository.py`'s module docstring and the benchmark banner still describe the old full-scan/N+1 version ("Antes de Refactorizar"); the query is already filtered and indexed. Don't reintroduce that debt, and fix the stale comments if you touch them.
- README's `cd week-1/starter-project` is stale; this directory is the project root.
- ADR-001/002 forbid new external dependencies (no ORM, pandas, calendar libraries). Keep DB access on stdlib `sqlite3` with `?` placeholders.
- Naive datetimes are interpreted as Bogotá local time; keep timezone handling consistent when changing SLA/calendar code.
- `data/sample_incidents.json` (`INC-1001`…`INC-1010`) is the fixture behind the triage demo and `CONTEXT_LOG.md`; changing it changes expected classifications.
- `CONTEXT_LOG.md` is a graded academic deliverable (prompt/context log). Don't rewrite or "clean up" its prose unless explicitly asked.
