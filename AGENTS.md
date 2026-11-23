# AGENTS.md

IncidentOps: Python 3.10 + `uv`. Runtime deps: `tiktoken` (context audits) plus `fastapi`,
`uvicorn`, `pydantic`, `typer` (H001 inbound channels); dev: `pytest`, `httpx`.
This is a Week 1 ISIA teaching repo. Code, docstrings, CLI output, and docs are in Spanish — match that.

`docs/constitution.md` is the superior norm: it prevails over ADRs, specs and code. ADR-003
(hexagonal) is the accepted topology and the first H001 cut is migrated (see Architecture).

**Open governance deviation:** FastAPI/Typer/pytest were adopted without the stack ADR that
Constitution Art. 3.2 and spec 001 §3 require, and the inbound paths are `adapters/inbound/api/`
and `adapters/inbound/cli.py` instead of Art. 2.5's `rest/` and `cli/`. Both stay pending until
ADR-004 records the stack (and amends Art. 2.5 or the paths are renamed). Don't add further
dependencies on the strength of this exception.

## Commands (run from the repo root)

```bash
uv sync                                                      # behind the local TLS proxy: uv sync --system-certs
uv run python -X utf8 -m pytest -v                           # BDD acceptance (spec 001 E1–E4, E10) + architecture boundaries
uv run python -X utf8 -m src.sla_calculator                  # SLA regression: 10 assertions, exits 1 on failure
uv run python -X utf8 -m src.triage_rules                    # graded triage audit over data/sample_incidents.json (output must not change)
uv run python -X utf8 -m src.adapters.inbound.cli triage --raw-text "..." [--incident-id ID] [--created-at ISO] [--now ISO] [--format table|json]
uv run uvicorn src.main:app --host 127.0.0.1 --port 8080     # POST /v1/triage, GET /v1/health (loopback only: no auth)
uv run python -X utf8 -m src.context_audit --symbol evaluate_sla_status
uv run python -X utf8 -m src.context_audit --compare-formats
uv run python -X utf8 -m src.incident_repository --records 2000 --iterations 2   # quick benchmark smoke
```

- Always use `-m src.<module>`; files import via `from src...`, so `uv run python src/foo.py` or running from inside `src/` fails. `pyproject.toml` sets `package = false`, so the package is not installed; pytest finds `src` via `[tool.pytest.ini_options] pythonpath = ["."]`.
- Keep `-X utf8` on this Windows setup: demos print accented Spanish and otherwise die with `UnicodeEncodeError` under the local cp932 code page.
- Verification = `pytest` + `_run_demo()` (`-m src.sla_calculator`) + the triage audit. No ruff/mypy config.
- CLI exit codes: `0` ok · `2` usage error · `3` invalid input (≈ HTTP 400/422) · `4` internal error. Results go to stdout, diagnostics to stderr.

## Architecture

Dependencies point inward: `adapters → application → domain`; only `src/main.py` (composition root) knows concrete implementations. `tests/test_arquitectura.py` enforces it by AST.

- `src/domain/` — pure core, no `json`/`pathlib`/`sqlite3`/frameworks, never reads the clock:
  - `models.py` — dataclasses and `Literal` types (`SeverityLevel`, `TeamName`, `TriageAction`, `TriageResult.to_output_line()`).
  - `sla_calculator.py` — `SLA_POLICY_TABLE`, `evaluate_sla_status`: P0/P1 calendar 24x7, P2/P3 working minutes; escalation at 75%, breach only when elapsed `>` allowed.
  - `working_time_calculator.py` — fixed Bogotá UTC-5 (`COT`, `BOGOTA_TZ`, avoids tzdata), Mon–Fri 08:00–18:00, `to_bogota`.
  - `holidays.py` — Colombian holidays computed per year (Ley 51/1983; Easter-derived dates).
  - `triage_rules.py` — 4-stage pipeline `extract_signals` → `decide_severity` → `route_component` → `correlate_batch`; public API `classify_incident_batch`. Severity comes from impact signals, never from urgency words ("urgente", "hoy"), which are recorded as lexical traps.
- `src/application/`
  - `ports.py` — `ClockPort` (`typing.Protocol`).
  - `services.py` — `IncidentService.triage_incident(reports)` (validates before running the engine, fills missing `created_at` from the clock, uses positional labels `R1..Rn`), `ValidationError(code, message, field)`, `ReportInput`, and `to_contract()`: the single projection to spec 001 §5.2 fields, shared by both channels for parity.
- `src/adapters/inbound/api/` — `schemas.py` (pydantic DTOs, `extra="forbid"`), `app.py` (`create_app(service)`; maps pydantic errors → 400 `invalid_json`/`reserved_field`/`invalid_payload`, `ValidationError` → 422).
- `src/adapters/inbound/cli.py` — `create_cli(service_factory)`, Typer app with subcommand `triage` (one report per call in this cut).
- `src/adapters/outbound/clock.py` — `SystemClock`, `FixedClock`.
- `src/main.py` — composition root: `build_service(now=None)`, `app`, `cli`.
- Legacy bridges in `src/` (`models.py`, `sla_calculator.py`, `triage_rules.py`, `working_time_calculator.py`, `holidays.py`) only re-export from `src/domain/`. `src/sla_calculator.py` keeps `_run_demo()`; `src/triage_rules.py` keeps `load_reports` and `_run_triage_audit` (they need `json`/`pathlib`). Bridges disappear in a later milestone with its own ADR — never add rules there.
- `src/incident_repository.py` — in-memory SQLite benchmark; active-query path and partial index already match ADR-001. Not migrated to `adapters/outbound/` yet.
- `src/context_audit.py` — AST-based LSP emulation plus `tiktoken` token counting (scans `src/` recursively).

## Gotchas

- Pending in spec 001 (second cut): `IncidentRepositoryPort` + null repository, 413/415/405 errors and size limits, CLI `--file`/repeatable `--raw-text`/`audit`/`--format output`/`--explain`, scenarios E5–E9 and E11–E12.
- The venv runs CPython **3.10.0**, whose `dataclass(slots=True)` breaks pytest 9.2 (`AttributeError: _str_cache`); that's why dev deps pin `pytest<9.2`. Drop the cap after moving to a newer 3.10.x+.
- ADR-002 mentions `src/colombian_calendar.py`; it doesn't exist. Working-day logic lives in `src/domain/working_time_calculator.py`.
- `incident_repository.py`'s module docstring and the benchmark banner still describe the old full-scan/N+1 version ("Antes de Refactorizar"); the query is already filtered and indexed. Don't reintroduce that debt, and fix the stale comments if you touch them.
- README's `cd week-1/starter-project` is stale; this directory is the project root.
- ADR-001/002 forbid ORMs, pandas and calendar libraries. Keep DB access on stdlib `sqlite3` with `?` placeholders. Frameworks stay confined to `src/adapters/inbound/` and `tests/` (Art. 3.3).
- Naive datetimes are interpreted as Bogotá local time; `IncidentService` normalizes every `created_at` with `to_bogota` so naive and aware values never mix.
- Without `created_at`, every report in a batch gets the same clock instant, so two outages of the same component merge unless the text carries a recurrence marker (spec 001 §1.1).
- `data/sample_incidents.json` (`INC-1001`…`INC-1010`) is the fixture behind the triage audit, the E4 test and `CONTEXT_LOG.md`; changing it changes expected classifications.
- `CONTEXT_LOG.md` is a graded academic deliverable (prompt/context log). Don't rewrite or "clean up" its prose unless explicitly asked.
