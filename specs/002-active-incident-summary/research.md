# Investigación (Fase 0): Resumen de incidentes activos (H002)

Cada decisión sigue el formato **Decisión / Motivo / Alternativas consideradas**. Las
mediciones se tomaron el 2026-11-24 en el venv del proyecto (CPython 3.10.0, Ruff 0.17.6).

---

<a id="r1"></a>
## R1 — Definición de activo y orden de la enmienda

**Decisión**: activo = `OPEN`, `IN_PROGRESS` y `ESCALATION_REQUIRED` (todo estado distinto
de `RESOLVED`). La enmienda del Art. 1.10 es la Fase A, en commit propio, y toca:
`docs/constitution.md`, `.specify/memory/constitution.md` (v1.0.0 → 2.0.0), ADR-005 nuevo
y `AGENTS.md`. Ninguna tarea que implemente FR-002 empieza antes.

**Motivo**: clarificación del 2026-11-24 y D9 de la spec. La Gobernanza de spec-kit trata
como `MAJOR` toda «redefinición incompatible»: un sistema que cumple el texto anterior
(dos estados activos) deja de cumplir el nuevo. ADR-005 además **reemplaza** el predicado
del índice parcial de ADR-001 (Art. 3.7: los ADR se reemplazan, no se reescriben).

**Alternativas consideradas**:
- Implementar primero y enmendar después: viola Art. 4.1 y F1.
- Versión `MINOR`: subestima el cambio; el término «activo» es normativo y su ampliación
  cambia cifras observables.

---

<a id="r2"></a>
## R2 — Dónde vive la definición de activo y el orden de severidad

**Decisión**: el dominio publica dos constantes en `src/domain/models.py`:

- `ACTIVE_STATUSES: FrozenSet[IncidentStatus] = frozenset({"OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED"})`
- `SEVERITY_ORDER: Tuple[SeverityLevel, ...] = ("P0", "P1", "P2", "P3")`

El servicio filtra con `ACTIVE_STATUSES` y ordena con `SEVERITY_ORDER`. El adaptador SQLite
usa el predicado literal `status <> 'RESOLVED'` como optimización de lectura, y una prueba
de conformidad garantiza que ambos coinciden.

**Motivo**: Art. 1.1 — los estados viven solo en el dominio. El predicado SQL no puede
derivarse en tiempo de ejecución sin concatenar SQL (T3) y SQLite solo usa un índice
parcial cuando la consulta repite literalmente su predicado; con parámetros `?` no puede
demostrar la implicación. El doble filtro cuesta una comparación por fila y elimina el
riesgo de deriva.

**Alternativas consideradas**:
- Construir `IN (?, ?, ?)` desde `ACTIVE_STATUSES`: el planificador deja de usar el índice
  parcial.
- Ordenar por la cadena `"P0" < "P1"`: funciona por casualidad léxica y oculta una regla de
  dominio.

---

<a id="r3"></a>
## R3 — Esquema SQLite, `INNER JOIN sla_policies` e índice compuesto

**Decisión**:

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sla_policies (
    severity TEXT PRIMARY KEY,
    max_resolution_minutes INTEGER NOT NULL,
    operates_24x7 INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    component   TEXT NOT NULL,
    severity    TEXT NOT NULL REFERENCES sla_policies (severity),
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,   -- ISO-8601 con desfase, normalizado a Bogotá
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_active_component
    ON incidents (component, status, severity, created_at, incident_id, title)
    WHERE status <> 'RESOLVED';
```

Dos sentencias de lectura constantes (sin concatenación):

```sql
SELECT i.incident_id, i.title, i.component, i.severity, i.status, i.created_at
FROM incidents AS i
INNER JOIN sla_policies AS p ON p.severity = i.severity
WHERE i.status <> 'RESOLVED'
-- variante filtrada: ... AND i.component = ?
```

- `sla_policies` se siembra al crear el esquema **desde `SLA_POLICY_TABLE`**; es un espejo,
  no una fuente. La consulta no proyecta columnas de `p` y ningún cálculo las lee (Art. 1.1,
  nota de frontera de ADR-003).
- El `INNER JOIN` y la clave foránea garantizan que toda fila leída tenga severidad con
  política, es decir, evaluable por `evaluate_sla_status` sin `ValueError`.
- El índice empieza por `(component, status)` como pidió el hito, es parcial (predicado
  enmendado) y cubriente (incluye `title`, que H002 ahora proyecta).

**Evidencia (prototipo en memoria, 20 000 filas, 12 857 activas, `ANALYZE` ejecutado)**:

| Consulta | `EXPLAIN QUERY PLAN` |
|---|---|
| Sin filtro | `SCAN incidents AS i USING COVERING INDEX idx_incidents_active_component` · `SEARCH sla_policies AS p USING COVERING INDEX sqlite_autoindex_sla_policies_1 (severity=?)` |
| Con componente | `SEARCH incidents AS i USING COVERING INDEX idx_incidents_active_component (component=?)` · `SEARCH sla_policies …` |

Lectura + construcción de `Incident` + `evaluate_sla_status` para las 12 857 activas:
**~195 ms**, holgado frente a SC-001 (< 1 s p95 con 10 000).

**Motivo**: conserva las garantías de ADR-001 (sin N+1, índice cubriente, iteración sobre
el cursor, `?`) y cubre el caso global, que ADR-001 no tenía.

**Alternativas consideradas**:
- Índice no parcial `(component, status)`: indexa también los resueltos, que son la
  mayoría del volumen histórico.
- Índice no cubriente: obliga a ir a la tabla por cada fila para leer `title`.
- Calcular minutos en SQL: imposible para P2/P3 (horario hábil y festivos), como ya
  estableció ADR-001.

---

<a id="r4"></a>
## R4 — Concurrencia con SQLite en memoria

**Decisión**: `SQLiteIncidentRepository` abre **una** conexión con
`check_same_thread=False` y serializa todo acceso con un `threading.Lock`. Cada lectura
recorre el cursor dentro del candado y devuelve una lista de `Incident` ya construida.

**Motivo**: FastAPI ejecuta rutas síncronas en un pool de hilos; con `:memory:` cada
conexión es una base distinta, así que no sirve abrir una por hilo. La consulta es de
solo lectura y corta (R3), de modo que serializar no compromete SC-001. Devolver una lista
evita que un iterador vivo retenga el candado fuera del adaptador.

**Alternativas consideradas**:
- URI de caché compartida (`file:…?mode=memory&cache=shared`) con conexión por hilo: más
  piezas móviles y bloqueos de tabla propios de la caché compartida.
- Rutas `async` con una sola conexión: no elimina el problema de hilos de `sqlite3` y
  cambia el estilo de H001.

---

<a id="r5"></a>
## R5 — Selección por `DATABASE_URL`

**Decisión**: `src/main.py` es el único lector de la variable
(`os.environ.get("DATABASE_URL", "sqlite:///:memory:")`) y llama a
`create_incident_repository(database_url: str)` de `src/adapters/outbound/factory.py`.

| URL | Resultado |
|---|---|
| `sqlite:///:memory:` (por defecto) | `SQLiteIncidentRepository(":memory:")` + siembra de la demo |
| `sqlite:///<ruta>` | `SQLiteIncidentRepository("<ruta>")`; esquema `IF NOT EXISTS`, sin siembra |
| cualquier otro esquema | `ValueError` en español al arrancar (fallo temprano) |

Tras construir el repositorio, la raíz llama a `check_health()`; si devuelve `False`, el
arranque falla. Los mensajes nunca incluyen la URL completa (en H004 podrá llevar
credenciales): solo el esquema.

**Motivo**: Art. III.5 (selección exclusiva por `DATABASE_URL` en la raíz) y D1 (demo en
memoria sin persistencia hasta H003). Admitir rutas de archivo no agrega persistencia de
incidentes —nadie los registra en H002— pero deja listo el punto de extensión de H003.

**Alternativas consideradas**:
- Leer la variable en la fábrica: viola III.5 (la fábrica es un adaptador y debe recibir la
  URL).
- Solo admitir `:memory:`: obligaría a reabrir la fábrica en H003.

---

<a id="r6"></a>
## R6 — Conjunto fijo de demostración

**Decisión**: `src/adapters/outbound/demo_incidents.py` declara una tupla inmutable de
`Incident` (`INC-2001`…`INC-2008`) con instantes fijos, y `seed_demo_incidents(repository)`
los guarda vía `save_incident`. La raíz de composición la llama solo para `:memory:`.
Cubre los cuatro estados y al menos tres componentes canónicos (`payment-gateway`,
`auth-identity`, `database-cluster`), severidades P0–P3, un incumplido y uno en umbral de
escalamiento a `2026-11-24T09:00:00-05:00`.

**Motivo**: D1 y los supuestos de la spec. Al ser constantes Python no hay E/S de archivos
y HTTP y CLI siembran exactamente lo mismo (FR-001). Los identificadores `INC-2xxx` no
chocan con `INC-1001`…`INC-1010` de `data/sample_incidents.json`, que no se toca.

**Alternativas consideradas**:
- Archivo `data/demo_incidents.json`: agrega E/S y un segundo fixture con riesgo de
  confundirse con el graduado.
- Reutilizar `data/sample_incidents.json`: son reportes crudos sin estado ni título y
  cambiarlo altera clasificaciones graduadas.

---

<a id="r7"></a>
## R7 — Forma de `IncidentRepositoryPort`

**Decisión** (contrato completo en
[contracts/incident-repository-port.md](contracts/incident-repository-port.md)):

| Método | Consumidor en H002 | Consumidor futuro |
|---|---|---|
| `save_incident(incident) -> None` | Siembra de demo; `Given` de las pruebas de conformidad | Registro (H003) |
| `get_incident(incident_id) -> Optional[Incident]` | Verificación de solo lectura (E12, SC-005) | Ciclo de vida (H003) |
| `find_open_duplicates(component, created_from, created_to) -> Sequence[Incident]` | Solo conformidad | Alerta de duplicado abierto (H003, Art. 1.11) |
| `list_active_incidents(component=None) -> Sequence[Incident]` | `get_active_incidents_summary` | — |
| `check_health() -> bool` | Fallo temprano en `src/main.py` | Sonda de disponibilidad (H004) |

Reglas comunes: entidades de dominio de entrada y salida; instantes normalizados con
`to_bogota`; `component` comparado tal cual (el servicio ya lo normalizó);
`find_open_duplicates` recibe la ventana ya calculada, porque la ventana de 30 minutos es
regla de dominio (Art. 1.11) y el puerto solo transporta.

**Motivo**: es el puerto pedido por el hito. Dos métodos (`get_incident`, `check_health`)
exceden el catálogo mínimo del Art. III.2, que exige justificarlo: ADR-006 registra esta
tabla.

**Alternativas consideradas**:
- Puerto mínimo de un solo método: obliga a modificar todos los adaptadores en H003.
- `find_open_duplicates(duplicate_group_key)`: exigiría persistir la clave de grupo y
  ampliar `Incident`, un cambio de dominio que H002 no necesita.

---

<a id="r8"></a>
## R8 — Instante de referencia y filtro

**Decisión**:

- `parse_reference_time(value: Optional[str]) -> Optional[datetime]` vive en
  `src/application/services.py` y lo usan **ambos** canales. Acepta
  `datetime.fromisoformat` de 3.10 y además un sufijo `Z` (lo traduce a `+00:00`, porque
  3.10 no lo admite). Si falla, `ValidationError("invalid_timestamp", …, "reference_time")`.
- El servicio resuelve `reference_time or clock.now()`, lo normaliza con `to_bogota` y lo
  trunca a segundos; ese es el instante evaluado **y** el declarado (FR-008).
- `component_filter`: `None` = sin filtro; si no es `None`, `strip().lower()`; vacío tras
  recortar → `ValidationError("invalid_payload", …, "component")`.
- Se excluyen los incidentes con `created_at > reference_time` antes de evaluar (FR-009);
  así el dominio nunca recibe un instante anterior a la creación.

**Motivo**: un único analizador garantiza que HTTP y CLI acepten y rechacen exactamente
las mismas cadenas (paridad, E11a). Pydantic acepta formatos que `fromisoformat` rechaza
(por ejemplo, enteros como marcas Unix), lo que rompería la paridad si cada canal
analizara por su cuenta.

**Alternativas consideradas**:
- Declarar `reference_time: datetime` en el DTO HTTP: Pydantic y Typer divergen.
- Filtrar por instante en SQL: compara texto ISO y mueve una regla de inclusión al
  adaptador.

---

<a id="r9"></a>
## R9 — Proyección única y paridad

**Decisión**: `summary_to_contract(summary) -> Dict[str, Any]` produce el JSON del
contrato con `reference_time` ya como cadena ISO con desfase. HTTP la valida con
`ActiveIncidentsSummaryResponse` (`reference_time: str`) y CLI la imprime con
`json.dumps(..., ensure_ascii=False)`. E10 compara ambos cuerpos ya decodificados, valor a
valor y en orden.

**Motivo**: misma estrategia que `to_contract` en H001: paridad por construcción
(Art. 2.7). Ningún canal re-serializa un `datetime`.

**Alternativas consideradas**: DTO con `datetime` re-serializado por Pydantic: introduce
una segunda serialización con sus propias reglas (por ejemplo, `Z` para UTC).

---

<a id="r10"></a>
## R10 — Validación y errores HTTP

**Decisión**:

- Parámetros con un modelo de consulta Pydantic `SummaryQueryParams` (`extra="forbid"`,
  `component: Optional[str]`, `reference_time: Optional[str]`) inyectado con
  `Annotated[SummaryQueryParams, Query()]`.
- Parámetro desconocido → `extra_forbidden` → `400 invalid_payload` (cae en la regla
  existente de `_classify_request_error`). `_format_loc` debe ignorar también el prefijo
  `"query"`, no solo `"body"`.
- Filtro vacío y fecha no parseable → `ValidationError` del servicio → `422` con la
  envoltura existente.
- `405`: manejador de `StarletteHTTPException` que, para `405`, devuelve
  `{"error": {"code": "method_not_allowed", …}}`; los demás estados conservan su
  comportamiento.
- Parámetro repetido (`component=a&component=b`): gana el último, igual que una bandera
  Typer repetida; se documenta, no se prueba como error.

**Motivo**: reutiliza la envoltura y el reparto 400/422 de H001 (D7). `405` estaba
prometido en el segundo corte de la spec 001 y la spec 002 lo exige (FR-012).

**Alternativas consideradas**: parámetros sueltos con `Query()`: FastAPI ignora en
silencio los desconocidos, lo que incumple E11b.

---

<a id="r11"></a>
## R11 — Subcomando CLI `summary`

**Decisión**: `summary [--component TEXTO] [--reference-time ISO] [--format table|json]`.
Bandera desconocida o `--format` inválido → Click/Typer terminan con `2`. `ValidationError`
→ `3` con `error [<code>] <campo>: <mensaje>` en `stderr`. Excepción inesperada → `4`.
La tabla muestra ID, severidad, estado, componente, minutos, incumplido y escalamiento,
precedidos por una línea con los totales; no es contrato (D8).

**Motivo**: códigos y estilo de diagnóstico de H001 (F3). La fábrica del servicio ya
existe; `--reference-time` se pasa al método, no al reloj.

**Alternativas consideradas**: reutilizar `--now` de `triage`: la spec fija
`--reference-time` en el glosario.

---

<a id="r12"></a>
## R12 — Configuración jerárquica de Ruff

**Decisión**:

- `pyproject.toml`:

  ```toml
  [tool.ruff]
  target-version = "py310"

  [tool.ruff.lint]
  select = ["E4", "E7", "E9", "F", "TID"]

  [tool.ruff.lint.flake8-tidy-imports]
  ban-relative-imports = "parents"
  ```

- `src/domain/ruff.toml` y `src/application/ruff.toml` con
  `extend = "../../pyproject.toml"`; `src/adapters/inbound/ruff.toml` con
  `extend = "../../../pyproject.toml"`. Cada uno declara `[lint.flake8-tidy-imports]` con
  `ban-relative-imports = "parents"` y su tabla `banned-api` completa:

| Capa | `banned-api` |
|---|---|
| `domain` | `sqlite3`, `json`, `pathlib`, `os`, `argparse`, `fastapi`, `starlette`, `pydantic`, `typer`, `click`, `uvicorn`, `httpx`, `pytest`, `src.application`, `src.adapters`, `src.main`, `datetime.datetime.now`, `datetime.datetime.utcnow`, `datetime.datetime.today`, `datetime.date.today` |
| `application` | `sqlite3`, `json`, `pathlib`, `os`, `argparse`, `fastapi`, `starlette`, `pydantic`, `typer`, `click`, `uvicorn`, `httpx`, `pytest`, `src.adapters`, `src.main`, `datetime.datetime.now`, `datetime.datetime.utcnow`, `datetime.datetime.today` |
| `adapters/inbound` | `sqlite3`, `src.adapters.outbound`, `src.domain.sla_calculator`, `src.domain.triage_rules`, `src.domain.working_time_calculator`, `src.domain.holidays` |

Cada entrada lleva un `msg` en español que cita el artículo (por ejemplo,
`"Art. 1.2: el dominio no accede a persistencia."`).

**Hechos de Ruff que condicionan el diseño**:

- Ruff usa el archivo de configuración **más cercano** a cada archivo; no fusiona
  jerarquías por sí solo. Sin `extend`, un `ruff.toml` anidado descartaría el `select` de
  la raíz.
- Con `extend`, una tabla como `banned-api` del hijo **reemplaza** la del padre; por eso
  cada capa declara su lista completa.
- Prohibir un módulo prohíbe también sus submódulos (`src.adapters` cubre
  `src.adapters.outbound.clock`), y las entradas con atributo (`datetime.datetime.now`) se
  resuelven por nombre calificado, también tras `from datetime import datetime`.
- `uv run ruff check --config pyproject.toml` desactiva la jerarquía: el comando canónico
  es `uv run ruff check src/` sin `--config`.
- `src/adapters/inbound/cli.py` importa `src.main` dentro de `if __name__ == "__main__"`;
  por eso `src.main` **no** se prohíbe en `inbound`.

**Línea base**: `uv run ruff check src/ --select E4,E7,E9,F,TID` → 1 hallazgo,
`E741 Ambiguous variable name: l` en `src/domain/holidays.py:18`. Se corrige renombrando
la variable del algoritmo de Pascua; `_run_demo` y la auditoría confirman que no cambia
ningún resultado. Prohibido `# noqa` (IV.4).

**Motivo**: Principio IV — la frontera falla automáticamente. Ruff es estático;
`tests/test_arquitectura.py` se conserva como verificación semántica (IV.5) y se amplía
con `inbound ↛ outbound`.

**Alternativas consideradas**: una sola configuración con `per-file-ignores`: Ruff no
admite `banned-api` por directorio en un único archivo, así que no se puede expresar la
frontera por capa.

---

<a id="r13"></a>
## R13 — Estrategia de pruebas

**Decisión**: `tests/test_spec_002_summary.py` con tres bloques:

1. **Aceptación BDD (E1–E9, E12)** sobre `IncidentService` + `InMemoryIncidentRepository`
   (`tests/doubles.py`) + `FixedClock`; cada escenario declara sus incidentes en el
   `Given`. Docstrings `Given/When/Then` en español, como en spec 001.
2. **Canales (E1, E2, E3 vía HTTP; E10, E11a, E11b)** con `TestClient` y `CliRunner` sobre
   el mismo servicio sembrado con el doble.
3. **Conformidad del puerto** sobre `SQLiteIncidentRepository(":memory:")`:
   - Forma: para cada método público de `IncidentRepositoryPort` (enumerado por
     introspección), el adaptador tiene un invocable con los mismos nombres y tipos de
     parámetros (`inspect.signature`). También para `NullIncidentRepository` y el doble.
   - Comportamiento: suite paramétrica que corre contra el doble y contra SQLite con los
     mismos datos y exige resultados idénticos (estados, filtro, `get_incident`,
     `find_open_duplicates`, `check_health`).
   - Deriva del predicado: los cuatro estados sembrados; el adaptador devuelve exactamente
     los de `ACTIVE_STATUSES`.
   - Espejo: `sla_policies` coincide con `SLA_POLICY_TABLE`.
   - Plan de consulta: `EXPLAIN QUERY PLAN` usa `idx_incidents_active_component` en ambas
     variantes.

`tests/conftest.py` pasa a construir el servicio de spec 001 con `NullIncidentRepository`
sin cambiar ninguna aserción.

**Motivo**: Art. III.6 — las reglas no requieren SQLite; la conformidad sí. `Protocol` sin
`@runtime_checkable` no admite `isinstance`, e `isinstance` tampoco revisaría firmas.

**Alternativas consideradas**: `@runtime_checkable` + `isinstance`: solo comprueba nombres
de atributos.

---

<a id="r14"></a>
## R14 — Trazas y solo lectura

**Decisión**: el adaptador HTTP registra una línea por consulta con `total_active`,
`breached_count`, duración en ms y estado HTTP; nunca títulos, componentes de texto libre
ni cuerpos. El CLI no registra nada. E12 lo verifica con `caplog` y con `get_incident`
antes y después de N consultas.

**Motivo**: FR-015 y la política de trazas de H001 (spec 001 §6.4).

**Alternativas consideradas**: registrar en el servicio: el servicio no debe conocer
`logging` de canal ni el estado HTTP.

---

<a id="r15"></a>
## R15 — Destino de `src/incident_repository.py`

**Decisión**: queda como arnés de benchmark: elimina la clase `IncidentRepository` y su
SQL, compone `SQLiteIncidentRepository` + `IncidentService` + `FixedClock`, siembra
sintéticos vía `save_incident` (componentes canónicos, p. ej. `payment-gateway`) y mide
`get_active_incidents_summary` con y sin filtro, imprimiendo promedio y p95. Se corrigen la
docstring y el banner obsoletos («Antes de Refactorizar», «N+1»), como pide `AGENTS.md`.

**Motivo**: conserva el comando documentado y da un oráculo reproducible para SC-001 fuera
de la suite de pytest (una aserción de tiempo en pytest sería frágil).

**Alternativas consideradas**: subcomando CLI `benchmark`: amplía el contrato de canal fuera
de la spec.
