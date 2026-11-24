# IncidentOps — Proyecto Semilla (Semana 1)

**IncidentOps** es un sistema backend en Python gestionado con [`uv`](https://docs.astral.sh/uv/) que administra reportes de incidentes de software, evalúa acuerdos de nivel de servicio (**SLA**) sobre SQLite y ejecuta reglas de **triaje y enrutamiento de tickets**.

Este repositorio sirve como banco de pruebas práctico para la **Semana 1** de *Ingeniería de Software Asistida por Inteligencia Artificial (ISIA)* bajo un enfoque **100% *AI for Software Engineering***.

---

## Requisitos e Instalación con `uv`

- **Python 3.10+** y **[`uv`](https://docs.astral.sh/uv/)**.
- Dependencias declaradas en [`pyproject.toml`](pyproject.toml):
  - `tiktoken`: Para medir con precisión matemática el consumo de tokens BPE (`o200k_base` / `cl100k_base`) en las distintas estrategias de recolección de contexto.

Para inicializar el entorno virtual e instalar `tiktoken`:

```bash
cd week-1/starter-project
uv sync
```

---

## Comandos Principales para la Práctica

Ejecuta todos los comandos desde `week-1/starter-project/` usando `uv run`:

### 1. Fase 1 — Auditoría de Tokens con `tiktoken`: Fuerza Bruta vs. `grep` vs. LSP
Compara cuántos tokens reales consume leer todos los archivos del repositorio (`glob` + `read`), leer los archivos `.py` coincidentes (`grep` + `read`) o extraer únicamente la definición, firmas de tipos y referencias de un símbolo como lo hace un servidor **LSP**:

```bash
uv run python -m src.context_audit --symbol evaluate_sla_status
uv run python -m src.context_audit --symbol get_active_incidents_summary
uv run python -m src.context_audit --symbol classify_incident_report
```

Para comparar el impacto en tokens de distintos formatos de serialización de datos (JSON indentado, JSON compacto, YAML, CSV):

```bash
uv run python -m src.context_audit --compare-formats
```

### 2. Fase 2 — Benchmark del resumen de incidentes activos
La deuda original (escaneo completo y consultas N+1) ya se corrigió (ADR-001, ADR-005, ADR-006). El arnés siembra incidentes sintéticos en SQLite en memoria y mide el resumen con y sin filtro de componente (promedio y p95; objetivo SC-001: < 1 000 ms con ≥ 10 000 activos):

```bash
uv run python -X utf8 -m src.incident_repository --records 20000 --iterations 20
```

### Consulta del resumen de incidentes activos (H002)
El mismo resumen por HTTP y por CLI. Sin `DATABASE_URL`, el almacén es `sqlite:///:memory:` con incidentes de demostración (`INC-2001`…`INC-2008`):

```bash
uv run uvicorn src.main:app --host 127.0.0.1 --port 8080
curl -s "http://127.0.0.1:8080/api/v1/incidents/summary?reference_time=2026-11-24T09:00:00"
curl -s "http://127.0.0.1:8080/api/v1/incidents/summary?component=payment-gateway"

uv run python -X utf8 -m src.adapters.inbound.cli summary --reference-time 2026-11-24T09:00:00
uv run python -X utf8 -m src.adapters.inbound.cli summary --component payment-gateway --format json
```

Con `DATABASE_URL="sqlite:///./incidentes.db"` se usa un archivo (sin datos de demostración). `--format json` imprime exactamente el cuerpo de la respuesta HTTP.

### Creación de incidentes y auditoría de SLA (H003)
Crear un incidente lo clasifica con el triaje canónico, lo guarda y avisa si duplica uno abierto con la misma clave de grupo (`is_duplicate`, `duplicate_of`). La auditoría devuelve la evaluación de SLA en cualquier instante, incluso antes de una resolución ya registrada. Con el almacén de demostración, una caída de pagos duplica `INC-2001`:

```bash
uv run uvicorn src.main:app --host 127.0.0.1 --port 8080
curl -s -X POST http://127.0.0.1:8080/api/v1/incidents -H "Content-Type: application/json" \
  -d '{"title":"Caída de la pasarela de pagos","raw_text":"La pasarela de pagos está caída, ningún cliente puede pagar"}'
curl -s "http://127.0.0.1:8080/api/v1/incidents/INC-2001/sla?reference_time=2026-11-24T08:15:00"
```

Por CLI, cada invocación es un proceso nuevo: con el almacén en memoria por defecto, un `sla` no ve lo que creó un `create` anterior. Para encadenarlos, usa un archivo:

```bash
export DATABASE_URL="sqlite:///./incidentes.db"   # PowerShell: $env:DATABASE_URL = "sqlite:///./incidentes.db"
uv run python -X utf8 -m src.adapters.inbound.cli create --title "Caída de la pasarela de pagos" --raw-text "La pasarela de pagos está caída" --incident-id INC-DEMO-01 --created-at 2026-11-06T17:00:00 --format json
uv run python -X utf8 -m src.adapters.inbound.cli sla INC-DEMO-01 --reference-time 2026-11-09T09:00:00 --format json
```

El segundo comando devuelve 120 minutos hábiles transcurridos de 480 (el fin de semana no cuenta). Códigos de salida del CLI: `0` correcto, `1` entrada inválida, incidente inexistente o identificador repetido, `2` error de uso y `4` error interno. Detalle: [`specs/003-incident-lifecycle-sla/quickstart.md`](specs/003-incident-lifecycle-sla/quickstart.md).

### 3. Fase 3 — Auditoría del Motor de Triaje (`src/triage_rules.py`)
Evalúa cómo el motor heurístico actual clasifica los 10 incidentes de [`data/sample_incidents.json`](data/sample_incidents.json) e identifica sus fallos de diseño:

```bash
uv run python -m src.triage_rules
```

### 4. Verificación del Cálculo Determinista de SLA (`src/sla_calculator.py`)
Ejecuta la demostración del cálculo de SLA actual (donde se evidencia el bug de horario hábil en tickets `P2`/`P3`):

```bash
uv run python -m src.sla_calculator
```
