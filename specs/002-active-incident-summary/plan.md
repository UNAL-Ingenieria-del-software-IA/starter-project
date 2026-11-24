# Plan de implementación: Resumen de incidentes activos (H002)

**Rama**: `002-active-incident-summary` | **Fecha**: 2026-11-24 | **Spec**: [spec.md](spec.md)

**Entrada**: especificación de la funcionalidad en `specs/002-active-incident-summary/spec.md`.

**Autoridad**: subordinado a `docs/constitution.md` y a `.specify/memory/constitution.md`
(v1.0.0). Si este plan contradice a cualquiera de las dos, prevalece la Constitución.

## Resumen

H002 expone una consulta de solo lectura —`GET /api/v1/incidents/summary` y el subcomando
CLI `summary`— que devuelve el total de incidentes activos, cuántos incumplieron su SLA y
el detalle ordenado de cada uno, con filtro opcional por componente y un instante de
referencia opcional.

Enfoque técnico, respetando la arquitectura hexagonal (ADR-003):

1. **Puerto de persistencia.** `src/application/ports.py` declara `IncidentRepositoryPort`
   (`typing.Protocol`) con `save_incident`, `get_incident`, `find_open_duplicates`,
   `list_active_incidents` y `check_health`. El puerto solo habla en entidades de dominio
   (`Incident`); no expone SQL, filas ni DSN.
2. **Adaptadores de salida.** `src/adapters/outbound/sqlite_repository.py` extrae la
   persistencia optimizada de Semana 1 (`src/incident_repository.py`): `sqlite3` de la
   librería estándar, marcadores `?`, `INNER JOIN sla_policies` como garantía de
   integridad referencial e índice compuesto parcial y cubriente que empieza por
   `(component, status)`. `src/adapters/outbound/factory.py` selecciona el adaptador a
   partir de `DATABASE_URL` (por defecto `sqlite:///:memory:`), y
   `src/adapters/outbound/null_repository.py` sirve al triaje sin efectos (Art. III.4).
3. **Caso de uso.** `IncidentService.get_active_incidents_summary(component_filter,
   reference_time)` valida, lee activos por el puerto, excluye los creados después del
   instante, evalúa cada uno con `evaluate_sla_status` (única fuente de minutos,
   incumplimiento y escalamiento), ordena y proyecta una sola vez con
   `summary_to_contract` para ambos canales.
4. **Adaptadores de entrada.** DTO `ActiveIncidentItem` y `ActiveIncidentsSummaryResponse`
   en `schemas.py`, ruta FastAPI y subcomando Typer `summary`, ambos sobre la misma
   proyección, con la envoltura de errores y los códigos de salida de H001.
5. **Fronteras estáticas.** `[tool.ruff.lint]` en `pyproject.toml` y tres `ruff.toml`
   jerárquicos (`domain`, `application`, `adapters/inbound`) que extienden la raíz y
   codifican `TID251` (`banned-api`) y `TID252` (`ban-relative-imports = "parents"`).
6. **Aceptación.** `tests/test_spec_002_summary.py` automatiza E1–E12 y verifica que
   `SQLiteIncidentRepository` cumple `IncidentRepositoryPort` en forma y en comportamiento.

**Bloqueo declarado (D9).** La definición de activo de la spec (todo estado distinto de
`RESOLVED`) contradice el Art. 1.10 vigente. La primera tarea del plan es la enmienda, en
commit propio; ninguna tarea que implemente FR-002 empieza antes (ver Fase A).

## Contexto técnico

**Lenguaje/versión**: Python 3.10 (venv en CPython 3.10.0), gestionado con `uv`.

**Dependencias principales**: `fastapi`, `pydantic` v2, `typer`, `uvicorn`, `tiktoken`
(runtime); `pytest<9.2`, `httpx`, `ruff` 0.17.6 (desarrollo). **Sin dependencias nuevas**:
`ruff` ya está en el grupo `dev` y fijado por `uv.lock`.

**Almacenamiento**: SQLite vía `sqlite3` de la librería estándar. En H002, almacén en
memoria (`sqlite:///:memory:`) sembrado al arrancar con un conjunto fijo de demostración
(D1). Una ruta de archivo `sqlite:///<ruta>` se admite pero no se siembra ni se migra.

**Pruebas**: `pytest` + `fastapi.testclient` + `typer.testing.CliRunner`, en proceso, sin
red. Oráculos de dominio `_run_demo()` y auditoría de triaje sin cambios.

**Plataforma**: Windows 11 de desarrollo (`-X utf8` obligatorio), servicio en loopback
`127.0.0.1:8080` sin autenticación.

**Tipo de proyecto**: servicio web + CLI sobre un núcleo de dominio compartido.

**Objetivos de rendimiento**: SC-001 — resumen de 10 000 activos en < 1 s (p95) por
canal. Prototipo medido (ver [research.md](research.md#r3)): 12 857 activos leídos y
evaluados en ~195 ms con el índice propuesto.

**Restricciones**: dominio puro y determinista (Art. 1.2–1.3); `sqlite3` con `?`, sin ORM
ni `pandas` (T3); frameworks confinados a `src/adapters/inbound/` y `tests/` (T4);
`uv run ruff check src/` y `uv run pytest -v` en verde (IV, V); salida de la auditoría de
triaje invariante.

**Escala/alcance**: volumen de referencia 10 000 activos, sin paginación (D5); 1 puerto
nuevo, 3 adaptadores de salida, 1 ruta HTTP, 1 subcomando CLI, 4 archivos de
configuración Ruff.

No quedan puntos `NEEDS CLARIFICATION`: todos se resolvieron en
[research.md](research.md).

## Verificación constitucional

*Compuerta: debe pasar antes de la Fase 0 y repetirse después del diseño de la Fase 1.*

Se evalúa contra ambos textos constitucionales. Notación: «docs» = `docs/constitution.md`;
«spec-kit» = `.specify/memory/constitution.md` v1.0.0.

| # | Norma | Verificación | Antes del diseño | Después del diseño |
|---|---|---|---|---|
| G1 | docs 1.1–1.3 · spec-kit I | Minutos, incumplimiento y escalamiento salen solo de `evaluate_sla_status`; el dominio no lee reloj ni importa E/S. El dominio solo gana constantes (`ACTIVE_STATUSES`, `SEVERITY_ORDER`). | ✅ | ✅ |
| G2 | docs 1.10 · spec-kit 1.10 | «Activo = distinto de `RESOLVED`» contradice el texto vigente. | ⚠️ Desviación declarada | ⚠️ Se cierra con la Fase A (enmienda + ADR-005 + `AGENTS.md`). FR-002 bloqueado hasta entonces. |
| G3 | docs 1.12 · spec-kit 1.12 | Añadir constantes al dominio exige `_run_demo`, auditoría y BDD en verde en el mismo cambio. Ninguna regla de triaje ni SLA cambia. | ✅ | ✅ |
| G4 | docs 2.1 · spec-kit 2.1 | `adapters → application → domain`; solo `src/main.py` conoce `SQLiteIncidentRepository`, `NullIncidentRepository` y `create_incident_repository`. | ✅ | ✅ (AST + Ruff) |
| G5 | docs 2.4 · spec-kit III.2 | El puerto gana dos métodos fuera del catálogo mínimo (`get_incident`, `check_health`). III.2 exige justificarlo en ADR o especificación. | ⚠️ | ✅ Justificado en ADR-006 (Fase F) y en [research.md](research.md#r7). |
| G6 | spec-kit III.3 | El puerto expone solo `Incident`, `str`, `datetime`, `bool`; nada de `sqlite3.Row`, tablas ni DSN. | ✅ | ✅ |
| G7 | spec-kit III.4 | Triaje sin efectos con `NullIncidentRepository`; sin condicionales de canal en el servicio. | ✅ | ✅ |
| G8 | spec-kit III.5 | `DATABASE_URL` se lee solo en `src/main.py`; la fábrica recibe la URL como argumento y no lee el entorno. | ✅ | ✅ (Ruff prohíbe `os` en `domain`/`application`) |
| G9 | spec-kit III.6 | Las reglas del resumen se prueban con un doble en memoria; SQLite solo se usa para la conformidad del adaptador. | ✅ | ✅ |
| G10 | docs 2.6 · spec-kit 2.6 · T3 · ADR-001 | `sqlite3` + `?`, DDL y mapeo fila ↔ entidad solo en `adapters/outbound/`; índice parcial conservado. El predicado del índice cambia: ADR-005 reemplaza esa parte de ADR-001 (Art. 3.7: se reemplaza, no se reescribe). | ⚠️ | ✅ con ADR-005 |
| G11 | docs 1.1 · ADR-003 nota de frontera | `sla_policies` es un espejo sembrado desde `SLA_POLICY_TABLE`; el `INNER JOIN` no proyecta ninguna columna de política y ningún cálculo la usa. | ✅ | ✅ (prueba de espejo) |
| G12 | docs 2.7 · spec-kit 2.7 | Paridad por construcción: una sola proyección `summary_to_contract` para HTTP y CLI; E10 la verifica valor a valor. | ✅ | ✅ |
| G13 | spec-kit IV.1–IV.6 | `uv run ruff check src/` en 0. Línea base medida: 1 hallazgo (`E741` en `src/domain/holidays.py:18`), que se corrige renombrando la variable, sin `# noqa`. | ⚠️ | ✅ tras Fase B |
| G14 | docs 3.4 · spec-kit V.1–V.3 | Escenarios E1–E12 escritos en la spec; cada uno con prueba en `tests/test_spec_002_summary.py`. | ✅ | ✅ |
| G15 | spec-kit V.5–V.6 | `_run_demo` y la auditoría no cambian; ninguna aserción de spec 001 se relaja. | ✅ | ✅ |
| G16 | docs 3.2 · spec-kit T2/T5 | Sin dependencias nuevas. | ✅ | ✅ |
| G17 | docs 2.5 · spec-kit T5 y «Pendiente de registro» | Desviación previa a H002: stack sin ADR-004 y rutas `api/`/`cli.py` en lugar de `rest/`/`cli/`. H002 no crea rutas nuevas de canal: extiende las existentes. | ⚠️ Heredada | ⚠️ Heredada; no la agrava ni la resuelve (ver Seguimiento de complejidad). |
| G18 | spec-kit T7 | `src/incident_repository.py` deja de contener persistencia y queda como arnés de benchmark que compone el adaptador nuevo. | ⚠️ | ✅ (justificado abajo) |

**Resultado de la compuerta**: se puede pasar a la Fase 0. Las desviaciones G2, G5, G10 y
G18 tienen tarea y ADR asignados; G17 es previa y queda registrada.

**Divergencia entre los dos textos constitucionales.** `docs/constitution.md` (sin
versión) y `.specify/memory/constitution.md` (v1.0.0) no dicen lo mismo: rutas de canal
(Art. 2.5 frente a 2.4), estado del stack (Art. 3.2 «pendiente» frente a T2 «adoptado») y
Ruff (ausente frente a Principio IV). `AGENTS.md` declara superior a `docs/constitution.md`
y la Gobernanza de spec-kit se declara superior a sí misma. Este plan cumple **ambos**
textos donde no chocan y, donde chocan, aplica el más estricto (Ruff obligatorio). La
enmienda de la Fase A debe tocar los dos archivos de forma idéntica en el Art. 1.10; su
reconciliación completa queda fuera de H002.

## Estructura del proyecto

### Documentación (esta funcionalidad)

```text
specs/002-active-incident-summary/
├── spec.md                             # Especificación (entrada)
├── plan.md                             # Este archivo
├── research.md                         # Fase 0: decisiones técnicas
├── data-model.md                       # Fase 1: entidades, esquema y mapeos
├── quickstart.md                       # Fase 1: guía de validación
├── contracts/
│   ├── http-incidents-summary.openapi.yaml   # Contrato HTTP
│   ├── cli-summary.md                         # Contrato CLI
│   └── incident-repository-port.md            # Contrato del puerto
├── checklists/requirements.md          # Lista de calidad de la spec (existente)
└── tasks.md                            # Fase 2 (/speckit.tasks; no lo crea este comando)
```

### Código fuente (raíz del repositorio)

```text
pyproject.toml                          # + [tool.ruff] y [tool.ruff.lint]
src/
├── domain/
│   ├── ruff.toml                       # NUEVO: extend + TID251/TID252 del núcleo
│   ├── models.py                       # + ACTIVE_STATUSES, SEVERITY_ORDER (tras Fase A)
│   ├── holidays.py                     # E741: renombrar `l` (sin cambio de semántica)
│   └── sla_calculator.py               # sin cambios
├── application/
│   ├── ruff.toml                       # NUEVO: extend + TID251/TID252 de casos de uso
│   ├── ports.py                        # + IncidentRepositoryPort
│   └── services.py                     # + get_active_incidents_summary, parse_reference_time,
│                                       #   ActiveIncidentView, ActiveIncidentsSummary,
│                                       #   summary_to_contract; IncidentService(clock, repository)
├── adapters/
│   ├── inbound/
│   │   ├── ruff.toml                   # NUEVO: extend + TID251/TID252 de canales
│   │   ├── api/schemas.py              # + ActiveIncidentItem, ActiveIncidentsSummaryResponse,
│   │   │                               #   SummaryQueryParams
│   │   ├── api/app.py                  # + GET /api/v1/incidents/summary, manejador 405
│   │   └── cli.py                      # + subcomando `summary`
│   └── outbound/
│       ├── clock.py                    # sin cambios
│       ├── sqlite_repository.py        # NUEVO: SQLiteIncidentRepository
│       ├── null_repository.py          # NUEVO: NullIncidentRepository
│       ├── demo_incidents.py           # NUEVO: conjunto fijo de demostración (constantes)
│       └── factory.py                  # NUEVO: create_incident_repository(database_url)
├── main.py                             # lee DATABASE_URL, compone y siembra la demo
└── incident_repository.py              # queda como arnés de benchmark (SC-001)

tests/
├── conftest.py                         # build_service con NullIncidentRepository para spec 001
├── doubles.py                          # NUEVO: InMemoryIncidentRepository (doble de prueba)
├── test_arquitectura.py                # + frontera inbound ↛ outbound
├── test_spec_001_triage.py             # sin cambios de aserciones
└── test_spec_002_summary.py            # NUEVO: E1–E12 + conformidad del puerto

docs/adr/
├── 0005-incidente-activo-distinto-de-resuelto.md     # NUEVO (Fase A)
└── 0006-puerto-repositorio-y-database-url.md         # NUEVO (Fase F)
```

**Decisión de estructura**: se mantiene el proyecto único con la topología hexagonal ya
migrada en H001. H002 no crea paquetes de canal nuevos; añade un puerto, tres módulos de
salida, un DTO y una ruta por canal, y la raíz de composición sigue siendo el único punto
que conoce implementaciones concretas.

## Secuencia de implementación

El detalle de tareas lo genera `/speckit.tasks`. Este orden respeta dependencias y la
compuerta D9.

| Fase | Contenido | Commit | Depende de |
|---|---|---|---|
| **A — Enmienda (bloqueante)** | Art. 1.10 en `docs/constitution.md` y `.specify/memory/constitution.md` (activo = `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`); versión spec-kit 1.0.0 → 2.0.0 (redefinición incompatible de un término normativo); ADR-005 aceptado que además reemplaza el predicado del índice parcial de ADR-001; `AGENTS.md`. | Propio | — |
| **B — Ruff** | `[tool.ruff]`/`[tool.ruff.lint]` en `pyproject.toml`; `ruff.toml` en `domain`, `application`, `adapters/inbound`; corrección de `E741`; prueba de humo de frontera (ver [quickstart.md](quickstart.md)). | Propio | — (paralela a A) |
| **C — Dominio y puerto** | `ACTIVE_STATUSES` y `SEVERITY_ORDER` en `domain/models.py`; `IncidentRepositoryPort` en `ports.py`; doble en memoria en `tests/doubles.py`. | | A |
| **D — Adaptadores de salida** | `sqlite_repository.py`, `null_repository.py`, `demo_incidents.py`, `factory.py`; pruebas de conformidad del puerto. | | C |
| **E — Caso de uso** | `get_active_incidents_summary`, `parse_reference_time`, `summary_to_contract`; `IncidentService(clock, repository)`; escenarios E1–E9 y E12 con el doble. | | C |
| **F — Canales y composición** | DTO, ruta HTTP, manejador 405, subcomando `summary`; `src/main.py` con `DATABASE_URL`; arnés `src/incident_repository.py`; ADR-006; `AGENTS.md` y `README.md`; E10, E11a, E11b. | | D, E |
| **G — Verificación** | `uv run ruff check src/` → `uv run python -X utf8 -m pytest -v` → `_run_demo` → auditoría → benchmark SC-001 (ver [quickstart.md](quickstart.md)). | | F |

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El predicado SQL `status <> 'RESOLVED'` se desincroniza de `ACTIVE_STATUSES` del dominio. | El servicio vuelve a filtrar con `ACTIVE_STATUSES` (fuente de verdad) y una prueba de conformidad siembra los cuatro estados y exige que el adaptador devuelva exactamente los activos del dominio. |
| Conexión SQLite en memoria usada desde los hilos del pool de FastAPI. | Una sola conexión `check_same_thread=False` protegida por `threading.Lock` ([research.md](research.md#r4)). |
| Un `ruff.toml` anidado reemplaza la configuración raíz en lugar de sumarse. | Cada `ruff.toml` declara `extend = "../../pyproject.toml"` (o `../../../`) y repite la lista completa de `banned-api` de su capa. |
| La serialización de `reference_time` difiere entre FastAPI y `json.dumps`. | La proyección entrega la cadena ISO ya formada y el DTO la declara `str`; nadie re-serializa un `datetime`. |
| `evaluate_sla_status` lanza `ValueError` si el instante es anterior a la creación. | El servicio excluye antes esos incidentes (FR-009), de modo que el dominio nunca recibe ese caso. |
| Cambios accidentales a la salida de H001 (404/405). | El manejador de `405` solo cambia el cuerpo al formato de envoltura ya prometido en spec 001 (pendiente de su segundo corte); las pruebas de spec 001 siguen sin cambios. |

## Seguimiento de complejidad

| Desviación | Por qué se necesita | Alternativa más simple descartada porque |
|---|---|---|
| Art. 1.10 (G2): activo incluye `ESCALATION_REQUIRED`. | Decisión de producto de la clarificación del 2026-11-24: un incidente marcado para escalar sigue siendo trabajo en curso. | Mantener `OPEN`/`IN_PROGRESS` ocultaría justo los incidentes más urgentes del tablero. Se resuelve con la Fase A antes de implementar FR-002. |
| Puerto con 5 métodos, 2 fuera del catálogo mínimo (G5). | Pedido explícito del hito: `get_incident` verifica solo lectura (E12, SC-005) y prepara el ciclo de vida de H003; `check_health` permite fallo temprano en la composición y la sonda de H004. | Un puerto de un solo método obligaría a reabrir todos los adaptadores en H003. ADR-006 registra la justificación y el consumidor de cada método. |
| `INNER JOIN sla_policies` (G11). | Pedido explícito del hito; junto con la clave foránea garantiza que toda fila leída tenga política evaluable por el dominio. | Omitir la tabla perdería la integridad referencial que ADR-001 heredó; usarla como fuente de valores violaría el Art. 1.1. |
| `src/incident_repository.py` sigue existiendo (G18). | `AGENTS.md` documenta `-m src.incident_repository` como benchmark; SC-001 necesita un arnés reproducible. | Borrarlo rompe un comando documentado; moverlo al CLI agrega un subcomando fuera del contrato de la spec. Su retiro va con el ADR que elimine los puentes (T7). |
| Stack sin ADR-004 y rutas `api/`/`cli.py` (G17). | Desviación previa a H002. | Resolverla aquí mezcla dos decisiones en un hito ajeno. Se recomienda redactar ADR-004 en paralelo; H002 no la agrava. |

## Re-evaluación posterior al diseño

Tras la Fase 1 ([data-model.md](data-model.md), [contracts/](contracts/),
[quickstart.md](quickstart.md)) la compuerta se mantiene: ningún diseño introduce lógica de
SLA fuera del dominio, el puerto no filtra el motor, `DATABASE_URL` queda confinada a la
raíz de composición y no se agregan dependencias. Las únicas condiciones abiertas son las
desviaciones con tarea asignada (Fases A, B y F) y la desviación heredada G17.
