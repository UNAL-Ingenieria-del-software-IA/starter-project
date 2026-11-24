# AGENTS.md

IncidentOps: Python 3.10 + `uv`. Runtime deps: `tiktoken` (context audits) plus `fastapi`,
`uvicorn`, `pydantic`, `typer` (H001 inbound channels); dev: `pytest`, `httpx`, `ruff`.
This is a Week 1 ISIA teaching repo. Code, docstrings, CLI output, and docs are in Spanish — match that.

`docs/constitution.md` is the superior norm: it prevails over ADRs, specs and code. ADR-003
(hexagonal) is the accepted topology and the first H001 cut is migrated (see Architecture).

**Open governance deviation:** FastAPI/Typer/pytest were adopted without the stack ADR that
Constitution Art. 3.2 and spec 001 §3 require, and the inbound paths are `adapters/inbound/api/`
and `adapters/inbound/cli.py` instead of Art. 2.5's `rest/` and `cli/`. Both stay pending until
ADR-004 records the stack (and amends Art. 2.5 or the paths are renamed). Don't add further
dependencies on the strength of this exception.

**Open governance deviation (H003):** constitution 3.0.0 (`.specify/memory/constitution.md`)
and the `docs/constitution.md` Art. 1.8/2.4 amendments were adopted **without** the ADR that
Governance (2) and Art. 4.1 require (decision of 2026-11-24). They cover CLI exit codes
`0/1/2/4`, the `create`/`sla` contract, `IncidentIdGeneratorPort`, `add_incident`,
key-based `find_open_duplicates`, and escalation evaluated at the reference instant.
Justification lives in `specs/003-incident-lifecycle-sla/research.md`. ADR-006 is not edited;
its `find_open_duplicates`/catalog rows are superseded by the constitution until an ADR
replaces them. Until then, F4 (f) is not met for H003.

## Commands (run from the repo root)

```bash
uv sync                                                      # behind the local TLS proxy: uv sync --system-certs
uv run ruff check src/                                       # lint + hexagonal boundaries (TID251/TID252), run first
uv run python -X utf8 -m pytest -v                           # BDD acceptance (spec 001, spec 002 E1–E12, spec 003 E1–E23) + port conformance + architecture
uv run python -X utf8 -m src.sla_calculator                  # SLA regression: 12 assertions, exits 1 on failure
uv run python -X utf8 -m src.triage_rules                    # graded triage audit over data/sample_incidents.json (output must not change)
uv run python -X utf8 -m src.adapters.inbound.cli triage --raw-text "..." [--incident-id ID] [--created-at ISO] [--now ISO] [--format table|json]
uv run python -X utf8 -m src.adapters.inbound.cli summary [--component X] [--reference-time ISO] [--format table|json]
uv run python -X utf8 -m src.adapters.inbound.cli create --title "..." --raw-text "..." [--incident-id ID] [--created-at ISO] [--status S] [--resolved-at ISO] [--format table|json]
uv run python -X utf8 -m src.adapters.inbound.cli sla INCIDENT_ID [--reference-time ISO] [--format table|json]
uv run uvicorn src.main:app --host 127.0.0.1 --port 8080     # POST /v1/triage, GET /v1/health, GET /api/v1/incidents/summary, POST /api/v1/incidents, GET /api/v1/incidents/{id}/sla (loopback only: no auth)
uv run python -X utf8 -m src.context_audit --symbol evaluate_sla_status
uv run python -X utf8 -m src.context_audit --compare-formats
uv run python -X utf8 -m src.incident_repository --records 2000 --iterations 2   # quick benchmark smoke (SC-001: --records 20000 --iterations 20)
```

- `DATABASE_URL` selects the store (`src/adapters/outbound/factory.py`): default `sqlite:///:memory:`, seeded with demo incidents `INC-2001`…`INC-2008` (reference instant `2026-11-24T09:00:00`); `sqlite:///<path>` opens a file and seeds nothing. Any other scheme fails at startup (CLI exit `4`, uvicorn refuses to start); the message names the scheme, never the URL.

- Always use `-m src.<module>`; files import via `from src...`, so `uv run python src/foo.py` or running from inside `src/` fails. `pyproject.toml` sets `package = false`, so the package is not installed; pytest finds `src` via `[tool.pytest.ini_options] pythonpath = ["."]`.
- Keep `-X utf8` on this Windows setup: demos print accented Spanish and otherwise die with `UnicodeEncodeError` under the local cp932 code page.
- Verification = `ruff check src/` + `pytest` + `_run_demo()` (`-m src.sla_calculator`) + the triage audit. Ruff selects `E4,E7,E9,F,TID` (`pyproject.toml`); no mypy config.
- CLI exit codes (whole CLI, constitution 3.0.0 F3): `0` ok · `1` invalid input, unknown incident or id conflict (≈ HTTP 404/409/422) · `2` usage error (unknown/reserved option, ≈ HTTP 400) · `4` internal error. Code `3` is retired. Results go to stdout, diagnostics to stderr.

## Architecture

Dependencies point inward: `adapters → application → domain`; only `src/main.py` (composition root) knows concrete implementations. Two independent guards: `tests/test_arquitectura.py` (AST) and per-layer `ruff.toml` files (`src/domain/`, `src/application/`, `src/adapters/inbound/`) that ban imports with TID251 messages citing the constitution article.

- `src/domain/` — pure core, no `json`/`pathlib`/`sqlite3`/frameworks, never reads the clock:
  - `models.py` — dataclasses and `Literal` types (`SeverityLevel`, `TeamName`, `TriageAction`, `TriageResult.to_output_line()`), `ACTIVE_STATUSES`, `SEVERITY_ORDER`.
  - `sla_calculator.py` — `SLA_POLICY_TABLE`, `evaluate_sla_status`: P0/P1 calendar 24x7, P2/P3 working minutes; escalation at 75%, breach only when elapsed `>` allowed. Since H003 it reconstructs past instants: elapsed runs to `min(reference, resolved_at)`, `resolved_at_reference = resolved_at <= reference`, and escalation depends on that flag, not on `status` (Art. 1.8 as amended).
  - `working_time_calculator.py` — fixed Bogotá UTC-5 (`COT`, `BOGOTA_TZ`, avoids tzdata), Mon–Fri 08:00–18:00, `to_bogota`.
  - `holidays.py` — Colombian holidays computed per year (Ley 51/1983; Easter-derived dates).
  - `triage_rules.py` — 4-stage pipeline `extract_signals` → `decide_severity` → `route_component` → `correlate_batch`; public API `classify_incident_batch`. Severity comes from impact signals, never from urgency words ("urgente", "hoy"), which are recorded as lexical traps. H003 adds `group_key_for(component, signals)` (shared by batch correlation, which still needs ≥ 2 members) and `classify_incident(report)` for a single report with its group key.
- `src/application/`
  - `ports.py` — `ClockPort`, `IncidentIdGeneratorPort` (`new_id()`) and `IncidentRepositoryPort` (`typing.Protocol`): `save_incident` (upsert), `add_incident` (insert, `IncidentIdConflictError` if the id exists), `get_incident`, `find_open_duplicates(duplicate_group_key, exclude_incident_id)`, `list_active_incidents(component=None)`, `check_health`. Justification: ADR-006 plus spec 003 research (constitution 3.0.0, no ADR).
  - `services.py` — `IncidentService(clock, repository, id_generator=None)`:
    - `triage_incident(reports)` validates before running the engine, fills missing `created_at` from the clock and uses positional labels `R1..Rn`. It never touches the repository.
    - `get_active_incidents_summary(component_filter, reference_time)` is read-only. It normalizes the filter (strip + lower; an empty filter is a 422), truncates the instant to seconds in Bogotá time, excludes incidents created after that instant, evaluates each one with `evaluate_sla_status`, and sorts P0→P3, then by elapsed minutes (descending), then by ID.
    - `create_incident(CreateIncidentInput)` validates title (≤ 200), text (≤ 5 000), client id (`INC-[A-Za-z0-9-]{1,32}`), status and `RESOLVED` ⇔ `resolved_at` ≥ `created_at`. It takes `created_at` from the clock (truncated to seconds) when missing and classifies with `classify_incident`. Then it calls `add_incident` (a generated `INC-<HEX8>` is retried up to 5 times on conflict; a client id conflict propagates) and **then** `find_open_duplicates` (save-then-find, spec 003 research §R5).
    - `evaluate_incident_sla(incident_id, reference_time)` is read-only. Missing id → `IncidentNotFoundError`; the instant is truncated to seconds in Bogotá time; an instant before `created_at` → `ValidationError("reference_before_creation")`.
    - The module also defines `ValidationError(code, message, field)`, `ReportInput`, and `parse_instant(value, field)` (adds `Z` support, which CPython 3.10's `fromisoformat` lacks; `parse_reference_time` is its alias).
    - `to_contract()`, `summary_to_contract()`, `creation_to_contract()` and `sla_audit_to_contract()` are the only projections to the public contracts. Both channels share them, which guarantees parity.
- `src/adapters/inbound/api/` — `schemas.py` (pydantic DTOs, `extra="forbid"`, including `SummaryQueryParams`/`SLAQueryParams` for query strings and `CreateIncidentRequest`, whose fields all arrive as `StrictStr` so the service validates them) and `app.py` (`create_app(service)`):
  - Errors map as follows: pydantic → 400 `invalid_json`/`reserved_field`/`invalid_payload`; `ValidationError` → 422; `IncidentNotFoundError` → 404 `incident_not_found`; `IncidentIdConflictError` → 409 `incident_id_conflict`; 405 → `method_not_allowed`; anything else → 500 `internal_error`. All use the common envelope.
  - Reserved fields depend on the route: `incident_id` on `POST /v1/triage`; `severity`/`component`/`recommended_team`/`action`/`duplicate_group_key` on `POST /api/v1/incidents`.
  - Log lines carry only ids, counts, duration and status code, never titles or `raw_text`.
- `src/adapters/inbound/cli.py` — `create_cli(service_factory)` builds a Typer app with four subcommands: `triage` (one report per call in this cut), `summary`, `create` and `sla`. `_build_service` turns factory or config failures into exit `4`. The duplicate warning (`AVISO: …`) is a result, so it goes to stdout.
- `src/adapters/outbound/`:
  - `clock.py` — `SystemClock`, `FixedClock`.
  - `sqlite_repository.py` — `SQLiteIncidentRepository`:
    - Uses stdlib `sqlite3` with one connection plus a lock, and has an FK to `sla_policies`, which mirrors `SLA_POLICY_TABLE`.
    - Nine columns, including `recommended_team` and `duplicate_group_key` (H003).
    - Files created by H002 are migrated on open: `PRAGMA table_info` + constant `ALTER TABLE … ADD COLUMN`. The migration is additive and idempotent.
    - A partial covering index starts with `(component, status, …)` under `WHERE status <> 'RESOLVED'`. The partial index `idx_incidents_dup_key (duplicate_group_key, status)` is created after the migration.
    - The constants `SELECT_ACTIVE_SQL`/`SELECT_ACTIVE_BY_COMPONENT_SQL`/`SELECT_OPEN_DUPLICATES_SQL` use `INNER JOIN sla_policies`.
    - `add_incident` is a plain `INSERT`; a PK `IntegrityError` becomes `IncidentIdConflictError`. `close()` sits outside the port and releases the file on Windows.
  - `id_generator.py` — `RandomHexIdGenerator.new_id()` → `INC-` + 8 uppercase hex digits (`secrets`).
  - `null_repository.py` — the H001 triage path and its tests.
  - `demo_incidents.py` — `INC-2001`…`INC-2008`; group key and team derived from each title via `classify_incident` (only `INC-2001` gets `payment-availability`).
  - `factory.py` — `create_incident_repository(DATABASE_URL)`.
- `src/main.py` — composition root: `build_repository(database_url=None)` (health check + demo seed for in-memory stores), `build_service(now=None, repository=None, id_generator=None)` (defaults to `RandomHexIdGenerator`), `cli`, and a lazy `app` (module `__getattr__`, so CLI runs never import FastAPI).
- Legacy bridges in `src/` (`models.py`, `sla_calculator.py`, `triage_rules.py`, `working_time_calculator.py`, `holidays.py`) only re-export from `src/domain/`. `src/sla_calculator.py` keeps `_run_demo()`; `src/triage_rules.py` keeps `load_reports` and `_run_triage_audit` (they need `json`/`pathlib`). Bridges disappear in a later milestone with its own ADR — never add rules there.
- `src/incident_repository.py` — benchmark harness only (spec 002 SC-001). It composes `SQLiteIncidentRepository` + `IncidentService` + `FixedClock`, seeds synthetic incidents via `save_incident`, and prints the average and p95 with and without a filter. It contains no SQL; persistence lives in `src/adapters/outbound/`.
- `src/context_audit.py` — AST-based LSP emulation plus `tiktoken` token counting (scans `src/` recursively).

## Gotchas

- Pending in spec 001 (second cut): 413/415 errors and size limits on `POST /v1/triage`, CLI `--file`/repeatable `--raw-text`/`audit`/`--format output`/`--explain`, scenarios E5–E9 and E11–E12. (The port, the null repository and the 405 envelope landed with H002.)
- Ruff config is hierarchical: the closest `ruff.toml` wins. Each layer file must keep `extend = ".../pyproject.toml"`, and a child `banned-api` table replaces the parent's instead of merging with it. `ruff check --config <file>` or `--isolated` turns off the hierarchy, and with it the boundary checks, so always run plain `uv run ruff check src/`.
- The venv runs CPython **3.10.0**, whose `dataclass(slots=True)` breaks pytest 9.2 (`AttributeError: _str_cache`); that's why dev deps pin `pytest<9.2`. Drop the cap after moving to a newer 3.10.x+.
- ADR-002 mentions `src/colombian_calendar.py`; it doesn't exist. Working-day logic lives in `src/domain/working_time_calculator.py`.
- The old full-scan/N+1 `IncidentRepository` is gone. Don't reintroduce SQL in `src/incident_repository.py` or per-row queries to `sla_policies`. The benchmark's 1 s target is checked by the harness, not by pytest, apart from one coarse per-channel SC-001 test.
- README's `cd week-1/starter-project` is stale; this directory is the project root.
- ADR-001/002 forbid ORMs, pandas and calendar libraries. Keep DB access on stdlib `sqlite3` with `?` placeholders. Frameworks stay confined to `src/adapters/inbound/` and `tests/` (Art. 3.3).
- "Active" means every status except `RESOLVED` (`OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`) since the Art. 1.10 amendment (ADR-005, constitution 2.0.0). ADR-005 also replaces ADR-001's index predicate with `WHERE status <> 'RESOLVED'`.
- Naive datetimes are interpreted as Bogotá local time; `IncidentService` normalizes every `created_at` with `to_bogota` so naive and aware values never mix.
- With the default `sqlite:///:memory:`, every CLI invocation is a new process with a fresh demo store: `create` succeeds but a later `sla` call can't see it. To chain `create` → `sla` from the terminal, set `DATABASE_URL=sqlite:///<file>`.
- Save-then-find (spec 003 research §R5) is what makes two concurrent creations see each other. Residual risk: if the duplicate lookup fails after `add_incident`, the incident is stored complete but the client gets `500` without its id. A retry with the same `incident_id` returns `409`, which confirms it exists.
- Duplicates are matched by `duplicate_group_key` only: no time window, recurrence markers don't block it, `RESOLVED` incidents never appear in `duplicate_of`, and a report with no key is never a duplicate.
- Without `created_at`, every report in a batch gets the same clock instant, so two outages of the same component merge unless the text carries a recurrence marker (spec 001 §1.1).
- `data/sample_incidents.json` (`INC-1001`…`INC-1010`) is the fixture behind the triage audit, the E4 test and `CONTEXT_LOG.md`; changing it changes expected classifications.
- `CONTEXT_LOG.md` is a graded academic deliverable (prompt/context log). Don't rewrite or "clean up" its prose unless explicitly asked.
