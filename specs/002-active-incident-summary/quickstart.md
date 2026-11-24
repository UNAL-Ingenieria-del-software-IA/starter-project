# Guía de validación (Fase 1): Resumen de incidentes activos (H002)

Escenarios ejecutables que prueban H002 de punta a punta. No contiene código de
implementación; los contratos están en [contracts/](contracts/) y las entidades en
[data-model.md](data-model.md).

## Requisitos previos

- Fase A completada (Art. 1.10 enmendado, ADR-005 aceptado). Sin ella, FR-002 no está
  implementado y los escenarios E1/E4 no aplican.
- Desde la raíz del repositorio:

```bash
uv sync                    # detrás del proxy TLS local: uv sync --system-certs
```

## 1. Verificación obligatoria (orden de la Constitución: lint primero)

```bash
uv run ruff check src/
uv run python -X utf8 -m pytest -v
uv run python -X utf8 -m src.sla_calculator
uv run python -X utf8 -m src.triage_rules
```

**Resultado esperado**: Ruff sin hallazgos y código `0`; pytest en verde con las pruebas
de spec 001 sin cambios más `tests/test_spec_002_summary.py` (E1–E12 y conformidad del
puerto); `_run_demo` con sus 10 aserciones en verde; la auditoría de triaje con salida
idéntica a la anterior al cambio.

Solo los escenarios de H002:

```bash
uv run python -X utf8 -m pytest tests/test_spec_002_summary.py -v
```

## 2. Prueba de humo de las fronteras Ruff

Comprueba que la frontera falla sola (Principio IV.2). Crear temporalmente un módulo con
una importación prohibida en cada capa, ejecutar Ruff y borrarlo:

| Archivo temporal | Contenido | Hallazgo esperado |
|---|---|---|
| `src/domain/_sonda.py` | `import sqlite3` | `TID251` con el mensaje del Art. 1.2 |
| `src/domain/_sonda.py` | `from datetime import datetime` + `datetime.now()` | `TID251` (Art. 1.3) |
| `src/application/_sonda.py` | `from src.adapters.outbound.factory import create_incident_repository` | `TID251` (Art. 2.1) |
| `src/application/_sonda.py` | `import os` | `TID251` (Art. III.5) |
| `src/adapters/inbound/_sonda.py` | `from src.domain.sla_calculator import evaluate_sla_status` | `TID251` (FR-005) |
| `src/adapters/inbound/api/_sonda.py` | `from ..cli import create_cli` | `TID252` (importación relativa a padre) |

```bash
uv run ruff check src/      # debe terminar con código 1 y señalar la sonda
```

Borrar la sonda y repetir: código `0`.

## 3. Canal HTTP

```bash
uv run uvicorn src.main:app --host 127.0.0.1 --port 8080
```

Con `DATABASE_URL` sin definir, el almacén es `sqlite:///:memory:` sembrado con
`INC-2001`…`INC-2008`.

| Petición | Esperado |
|---|---|
| `GET /api/v1/incidents/summary?reference_time=2026-11-24T09:00:00` | `200`; `reference_time` = `2026-11-24T09:00:00-05:00`; `component_filter` = `null`; ningún `RESOLVED`; `total_active` = longitud de `incidents`; `breached_count` = cantidad de `is_breached` verdaderos; orden P0→P3. |
| `…?component=%20Payment-Gateway%20&reference_time=2026-11-24T09:00:00` | `200`; `component_filter` = `payment-gateway`; solo ese componente. |
| `…?component=reporting-api` | `200` con `total_active: 0`, `breached_count: 0`, `incidents: []`. |
| `…?reference_time=ayer` | `422`, `error.code` = `invalid_timestamp`, `error.field` = `reference_time`. |
| `…?component=%20%20` | `422`, `error.code` = `invalid_payload`, `error.field` = `component`. |
| `…?componente=payment-gateway` | `400`, `error.code` = `invalid_payload`. |
| `POST /api/v1/incidents/summary` | `405`, `error.code` = `method_not_allowed`. |
| `POST /v1/triage` y `GET /v1/health` | Igual que en H001. |

Ejemplo:

```bash
curl -s "http://127.0.0.1:8080/api/v1/incidents/summary?reference_time=2026-11-24T09:00:00"
```

La documentación interactiva en `http://127.0.0.1:8080/docs` debe mostrar la ruta con los
esquemas `ActiveIncidentsSummaryResponse` y `ActiveIncidentItem`.

## 4. Canal CLI y paridad

```bash
uv run python -X utf8 -m src.adapters.inbound.cli summary --reference-time 2026-11-24T09:00:00 --format json
uv run python -X utf8 -m src.adapters.inbound.cli summary --component payment-gateway --reference-time 2026-11-24T09:00:00
uv run python -X utf8 -m src.adapters.inbound.cli summary --reference-time ayer        # exit 3
uv run python -X utf8 -m src.adapters.inbound.cli summary --componente x               # exit 2
```

**Paridad manual (E10)**: el JSON del primer comando es idéntico, campo a campo y en el
mismo orden del detalle, al cuerpo de `GET /api/v1/incidents/summary?reference_time=2026-11-24T09:00:00`
con el servidor recién arrancado. La prueba automatizada E10 hace la misma comparación en
proceso.

## 5. Selección por `DATABASE_URL`

```bash
# bash
DATABASE_URL="sqlite:///./tmp-h002.db" uv run python -X utf8 -m src.adapters.inbound.cli summary --format json
DATABASE_URL="postgresql://x" uv run python -X utf8 -m src.adapters.inbound.cli summary
```

```powershell
# PowerShell
$env:DATABASE_URL = "sqlite:///./tmp-h002.db"; uv run python -X utf8 -m src.adapters.inbound.cli summary --format json
Remove-Item Env:DATABASE_URL
```

**Esperado**: con archivo, esquema creado y resumen vacío (no se siembra, `0`); con un
esquema no soportado, fallo temprano con mensaje en español que nombra el esquema sin
repetir la URL. Borrar `tmp-h002.db` al terminar.

## 6. Rendimiento (SC-001)

```bash
uv run python -X utf8 -m src.incident_repository --records 20000 --iterations 20
uv run python -X utf8 -m src.incident_repository --records 2000 --iterations 2   # humo rápido
```

**Esperado**: el arnés informa el número de activos (≥ 10 000 en la primera corrida) y
el p95 de `get_active_incidents_summary` con y sin filtro, ambos < 1 000 ms. El banner ya
no dice «Antes de Refactorizar» ni describe N+1.

## 7. Solo lectura (E12 / SC-005)

Cubierto por la suite: mil consultas consecutivas sobre el doble y sobre SQLite dejan
idénticos todos los incidentes (`get_incident` antes y después) y ninguna traza del
adaptador HTTP contiene títulos.
