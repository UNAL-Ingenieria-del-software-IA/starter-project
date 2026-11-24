# Plan de implementación: Registro de incidentes, aviso de duplicado abierto y auditoría de SLA (H003)

**Rama**: `003-incident-lifecycle-sla` | **Fecha**: 2026-11-24 | **Spec**: [spec.md](spec.md)

**Entrada**: especificación de la funcionalidad en `specs/003-incident-lifecycle-sla/spec.md`
(clarificada el 2026-11-24).

**Autoridad**: subordinado a `docs/constitution.md` y a `.specify/memory/constitution.md`
(2.1.0). Si este plan contradice a cualquiera de las dos, prevalece la Constitución. Las
fronteras siguen la skill `hexagonal-architecture`.

## Resumen

H003 (primer corte) deja que IncidentOps **guarde** incidentes, **avise** si el nuevo
duplica uno abierto y **audite** su SLA en cualquier instante, por HTTP
(`POST /api/v1/incidents`, `GET /api/v1/incidents/{incident_id}/sla`) y por CLI (`create`,
`sla`).

Enfoque técnico, capa por capa, con las dependencias apuntando hacia adentro:

1. **Dominio** (`src/domain/`):
   - `Incident` gana `recommended_team: Optional[TeamName] = None` y
     `duplicate_group_key: Optional[str] = None`.
   - `sla_calculator.evaluate_sla_status` normaliza de forma consistente las marcas
     naive/aware (`to_bogota` sobre creación, resolución y referencia) y reconstruye el
     estado en el instante consultado: mide hasta `min(referencia, resolución)` y añade
     `resolved_at_reference`.
   - `triage_rules` expone `group_key_for` y `classify_incident` para un solo reporte, sin
     alterar el lote ([research §R1–R3](research.md)).
2. **Aplicación** (`src/application/`):
   - `IncidentService` gana `create_incident` y `evaluate_incident_sla`, más
     `IncidentNotFoundError`.
   - `ports.py` gana `add_incident`, la firma nueva de `find_open_duplicates`,
     `IncidentIdConflictError` e `IncidentIdGeneratorPort`.
   - Dos proyecciones únicas al contrato (`creation_to_contract`,
     `sla_audit_to_contract`) garantizan la paridad ([research §R4–R7, R10](research.md)).
3. **Adaptador secundario** (`src/adapters/outbound/`):
   - `sqlite_repository.py` gana las columnas `recommended_team` y `duplicate_group_key`,
     con migración aditiva para archivos de H002.
   - Índice parcial nuevo `idx_incidents_dup_key` sobre `(duplicate_group_key, status)`.
   - Implementa `add_incident`, extiende `save_incident` y `get_incident` a nueve campos y
     reimplementa `find_open_duplicates` por clave.
   - `id_generator.py` genera `INC-<HEX8>`, y la siembra de demostración deriva clave y
     equipo desde el título ([research §R8–R9](research.md)).
4. **Adaptadores primarios** (`src/adapters/inbound/`):
   - `CreateIncidentRequest`, `IncidentCreatedResponse` y `SLAEvaluationResponse` en
     `schemas.py`, y las dos rutas en `app.py` (404, 409 y 422 con la envoltura común).
   - Subcomandos `create` y `sla` en `cli.py`, con código `1` para entrada inválida en
     todo el CLI. Ambos canales invocan exactamente `IncidentService`.
5. **Pruebas**: `tests/test_spec_003_lifecycle_sla.py`, con `TestClient` y `CliRunner`
   sobre SQLite desechable.
   - El primer incremento automatiza los cinco comportamientos pedidos: seis funciones
     `test_bdd_*` (E1, E5, E12, E13, E14, E11).
   - El resto de los escenarios aceptados y la conformidad del puerto completan la
     capacidad ([research §R12](research.md#r12-pruebas-de-aceptación-de-spec-003)).

**Bloqueo declarado (Fase A).** Varias decisiones necesitan la enmienda de la
Constitución antes de implementarse:

- el código de salida `1` en todo el CLI;
- las rutas y los subcomandos nuevos en F3;
- un tercer puerto;
- un método nuevo y una firma cambiada en el puerto del repositorio.

La primera fase es esa enmienda, en commit propio (spec D8).

## Contexto técnico

**Lenguaje/versión**: Python 3.10 (venv en CPython 3.10.0), gestionado con `uv`.

**Dependencias principales**: `fastapi`, `pydantic` v2, `typer`, `uvicorn`, `tiktoken`
(runtime); `pytest<9.2`, `httpx`, `ruff` 0.17.6 (desarrollo). **Sin dependencias
nuevas**: `secrets` y `sqlite3` son de la librería estándar.

**Almacenamiento**: SQLite vía `sqlite3` de la librería estándar, seleccionado por
`DATABASE_URL`. Por defecto, `:memory:` sembrado con `INC-2001`…`INC-2008`;
`sqlite:///<ruta>` persiste entre procesos. El archivo de H002 se migra con columnas
aditivas e idempotentes.

**Pruebas**: `pytest` + `fastapi.testclient.TestClient` + `typer.testing.CliRunner`, en
proceso. SQLite desechable en `tmp_path` por prueba, reloj fijo (`FixedClock`) y
generador de identificadores determinista en las pruebas de servicio.

**Plataforma**: Windows 11 de desarrollo (`-X utf8` obligatorio); servicio en loopback
`127.0.0.1:8080` sin autenticación.

**Tipo de proyecto**: servicio web + CLI sobre un núcleo de dominio compartido
(hexagonal, ADR-003).

**Objetivos de rendimiento**: SC-006, que pide una creación (con búsqueda de duplicados) y
una auditoría en < 1 s por canal con 10 000 abiertos, medidas en proceso.
`idx_incidents_dup_key` convierte la búsqueda en un rango de índice, y la auditoría es una
lectura por clave primaria.

**Restricciones**:
- dominio puro y determinista (Art. 1.2–1.3), también para identificadores: se inyectan
  por puerto;
- `sqlite3` con `?`, sin ORM (T3);
- frameworks solo en `src/adapters/inbound/` y `tests/` (T4);
- auditoría de triaje invariante (Art. 1.12);
- `ruff check src/` y `pytest` en verde (IV, V).

**Escala/alcance**:
- 2 campos de entidad y 1 campo de evaluación;
- 2 funciones de dominio;
- 1 puerto nuevo, 1 método nuevo y 1 firma cambiada;
- 2 casos de uso;
- 2 columnas, 1 índice y 1 adaptador nuevo;
- 2 rutas HTTP, 2 subcomandos y 3 DTO;
- 1 archivo de pruebas nuevo.

No quedan puntos `NEEDS CLARIFICATION`: todos se resolvieron en
[research.md](research.md).

## Verificación constitucional

*Compuerta: debe pasar antes de la Fase 0 y repetirse después del diseño de la Fase 1.*

Notación: «docs» = `docs/constitution.md` (superior según `AGENTS.md`); «sk» =
`.specify/memory/constitution.md` 2.1.0.

| # | Norma | Verificación | Antes del diseño | Después del diseño |
|---|---|---|---|---|
| G1 | docs 1.1 · sk 1.1 | Clasificación, clave de grupo y SLA salen solo del dominio. El servicio solo compara igualdad de clave entre abiertos (FR-007); `group_key_for` vive en `triage_rules`. | ⚠️ Riesgo de calcular la clave en el servicio | ✅ R1 |
| G2 | docs 1.2–1.3 · sk 1.2–1.3 | El dominio no lee el reloj ni genera aleatoriedad. El identificador se inyecta con `IncidentIdGeneratorPort`; `secrets` vive en `adapters/outbound/`. | ⚠️ `INC-<HEX8>` requiere aleatoriedad | ✅ R7 |
| G3 | docs 1.10 · sk 1.10 | `RESOLVED` exige `resolved_at`; `create_incident` lo valida (FR-005). | ✅ | ✅ |
| G4 | docs 1.11 · sk 1.11 | Las formas canónicas de clave no cambian; solo se calculan también para un reporte suelto. | ✅ | ✅ |
| G5 | docs 1.12 · sk 1.12, 5.5 | Cambian `evaluate_sla_status` y `triage_rules`: `_run_demo` gana E10.1/E10.2; la salida de la auditoría de triaje debe ser idéntica (quickstart §6). | ⚠️ | ✅ con Fase B |
| G6 | docs 2.1 · sk 2.1 | `adapters → application → domain`; solo `src/main.py` conoce `SQLiteIncidentRepository` y `RandomHexIdGenerator`. | ✅ | ✅ (AST + Ruff) |
| G7 | docs 2.4 · sk 3.2 | **Catálogo de puertos.** Se añade `IncidentIdGeneratorPort` (tercer puerto) y `add_incident`, y cambia la firma de `find_open_duplicates`. El catálogo mínimo enumera solo dos puertos, y añadir o cambiar métodos exige justificación. | ❌ Sin enmienda | ✅ con Fase A: el catálogo se amplía en ambas constituciones; la justificación de cada cambio está en R4, R5 y R7 (sin ADR, ver G19) |
| G8 | sk 3.3 | Los puertos solo exponen `Incident`, `str`, `bool` y excepciones propias; nada de SQL ni `sqlite3.Row`. | ✅ | ✅ |
| G9 | sk 3.4 · 3.6 | Triaje de H001 sigue con `NullIncidentRepository`; las reglas de `create_incident` se prueban con `InMemoryIncidentRepository`, y SQLite solo en conformidad y aceptación. | ✅ | ✅ |
| G10 | sk 3.5 | `DATABASE_URL` solo en `src/main.py`. | ✅ | ✅ |
| G11 | docs 2.6 · sk 2.6 · T3 | DDL, migración aditiva, índice parcial e `IntegrityError` → conflicto, solo en `sqlite_repository.py`; sentencias constantes con `?`. | ✅ | ✅ |
| G12 | docs 2.7 · sk 2.7 | Paridad por construcción: `creation_to_contract` y `sla_audit_to_contract` son la única proyección; E11 compara campo a campo. | ✅ | ✅ |
| G13 | sk F3 | **Contrato de canales.** F3 no lista las rutas ni los subcomandos nuevos, y fija `3` como código de entrada inválida; la spec exige `1` en todo el CLI. | ❌ Sin enmienda | ✅ con Fase A (sk 3.0.0, MAJOR) |
| G14 | sk 5.6 | Cambiar `exit_code == 3` → `1` en spec 001/002 y la firma de `find_open_duplicates` en la conformidad de spec 002 modifica pruebas existentes. | ⚠️ | ✅ Primero se enmiendan spec 001, spec 002 y su contrato de puerto (Fase A); después las aserciones |
| G15 | docs 3.4 · sk 5.1–5.2 | Escenarios escritos antes del código. Cada escenario aceptado tiene su `test_bdd_*`; los cinco pedidos son el primer incremento, no el total. | ✅ | ✅ (R12) |
| G16 | sk IV | `uv run ruff check src/` en 0. `id_generator.py` es un módulo concreto de `outbound/`. Ya queda prohibido para los canales, porque `src/adapters/inbound/ruff.toml` veta el prefijo completo `src.adapters.outbound` (TID251 compara por prefijo). | ✅ | ✅ |
| G17 | sk T2 · T5 | Sin dependencias nuevas. | ✅ | ✅ |
| G18 | docs 2.5 · 3.2 | Desviación heredada: stack sin ADR-004 y rutas `api/`/`cli.py`. H003 extiende esos archivos sin crear paquetes de canal. | ⚠️ Heredada | ⚠️ Heredada; no se agrava (ver Seguimiento de complejidad) |
| G19 | docs 4.1 · sk Gobernanza (2) | **Procedimiento de enmienda.** Toda enmienda exige ADR aceptado. Por decisión del usuario (2026-11-24), la enmienda 3.0.0 se hace **sin ADR-007**. | ❌ | ❌ Aceptada: se registra como desviación de gobernanza abierta en ambas constituciones y en `AGENTS.md` (T003, T006) |

**Resultado de la compuerta**: se puede pasar a la Fase 0. G7 y G13 son violaciones
**con tarea asignada** (Fase A), y ninguna tarea que dependa de ellas empieza antes. G18
es previa a H003. G19 es una violación **aceptada y registrada**, no resuelta: la
enmienda queda abierta hasta que un ADR la respalde.

**Divergencia entre los dos textos constitucionales.** `docs/constitution.md` no fija
códigos de salida ni el contrato de canales (F3 solo existe en spec-kit). Su Art. 2.4 sí
enumera el catálogo de puertos. La Fase A enmienda F3 y el catálogo en spec-kit, y el
Art. 2.4 en docs. Ambos textos quedan coherentes en lo que H003 toca.

## Estructura del proyecto

### Documentación (esta funcionalidad)

```text
specs/003-incident-lifecycle-sla/
├── spec.md                                  # Especificación clarificada (entrada)
├── plan.md                                  # Este archivo
├── research.md                              # Fase 0: R1–R12
├── data-model.md                            # Fase 1: entidades, puertos, esquema, proyecciones
├── quickstart.md                            # Fase 1: guía de validación
├── contracts/
│   ├── http-incidents.openapi.yaml          # POST /api/v1/incidents, GET …/{id}/sla
│   ├── cli-create-sla.md                    # Subcomandos create y sla; códigos 0/1/2/4
│   └── incident-repository-port.md          # Puertos v3: add_incident, find_open_duplicates, id
├── checklists/requirements.md               # Calidad de la spec (existente)
└── tasks.md                                 # Fase 2 (/speckit.tasks; no lo crea este comando)
```

### Código fuente (raíz del repositorio)

```text
src/
├── domain/
│   ├── models.py                  # Incident + recommended_team, duplicate_group_key;
│   │                              #   SLAEvaluation + resolved_at_reference
│   ├── sla_calculator.py          # normalización naive/aware; reconstrucción en el instante
│   └── triage_rules.py            # + group_key_for, classify_incident (lote sin cambios)
├── sla_calculator.py              # _run_demo: + E10.1, E10.2 (puente; solo arnés)
├── application/
│   ├── ports.py                   # + add_incident, find_open_duplicates(clave, excluir),
│   │                              #   IncidentIdConflictError, IncidentIdGeneratorPort
│   └── services.py                # + CreateIncidentInput, IncidentCreation, IncidentSLAAudit,
│                                  #   IncidentNotFoundError, create_incident,
│                                  #   evaluate_incident_sla, parse_instant,
│                                  #   creation_to_contract, sla_audit_to_contract
├── adapters/
│   ├── inbound/
│   │   ├── ruff.toml              # sin cambios: ya veta el prefijo src.adapters.outbound
│   │   ├── api/schemas.py         # + CreateIncidentRequest, IncidentCreatedResponse,
│   │   │                          #   SLAEvaluationResponse, SLAQueryParams
│   │   ├── api/app.py             # + POST /api/v1/incidents, GET /api/v1/incidents/{id}/sla;
│   │   │                          #   manejadores 404 y 409
│   │   └── cli.py                 # + create, sla; EXIT_INVALID_INPUT = 1
│   └── outbound/
│       ├── sqlite_repository.py   # + columnas, migración aditiva, idx_incidents_dup_key,
│       │                          #   add_incident, find_open_duplicates por clave
│       ├── null_repository.py     # + add_incident; find_open_duplicates con firma nueva
│       ├── id_generator.py        # NUEVO: RandomHexIdGenerator (secrets)
│       └── demo_incidents.py      # siembra con clave y equipo derivados del título (R9)
└── main.py                        # inyecta RandomHexIdGenerator en build_service

tests/
├── doubles.py                     # InMemoryIncidentRepository v3; SequenceIdGenerator
├── test_spec_001_triage.py        # exit_code 3 → 1 (tras enmendar spec 001)
├── test_spec_002_summary.py       # exit_code 3 → 1; conformidad de find_open_duplicates v3
└── test_spec_003_lifecycle_sla.py # NUEVO: BDD E1–E23 + conformidad + SC-006

docs/
└── constitution.md                # Art. 2.4: catálogo de puertos; nota de desviación (sin ADR)

.specify/memory/constitution.md    # 3.0.0: F3 (rutas, subcomandos, códigos), Art. 3.2;
                                   #   desviación «enmienda sin ADR» en Pendiente de registro
AGENTS.md                          # comandos create/sla, códigos, puertos, esquema
specs/001-…, specs/002-…           # enmienda del código de salida y del contrato de puerto
```

**Decisión de estructura**: se mantiene el proyecto único con la topología hexagonal de
H001/H002. H003 no crea paquetes de canal. Añade dos casos de uso, un puerto y un módulo
de salida; la raíz de composición sigue siendo el único punto que conoce
implementaciones concretas.

## Secuencia de implementación

El detalle de tareas lo genera `/speckit.tasks`. Este orden respeta las dependencias y la
compuerta de la Fase A.

| Fase | Contenido | Commit | Depende de |
|---|---|---|---|
| **A — Enmienda (bloqueante)** | spec-kit 2.1.0 → **3.0.0** (MAJOR):<br>• F3: rutas, subcomandos y códigos `0/1/2/4`.<br>• Art. 3.2: catálogo con `IncidentIdGeneratorPort`, `add_incident` y `find_open_duplicates` por clave.<br>`docs/constitution.md` Art. 2.4. Sin ADR: desviación de gobernanza registrada (G19); ADR-006 no se edita. `AGENTS.md`. Enmienda de spec 001 §7 y spec 002 (contrato CLI y del puerto). Aserciones `exit_code == 3` → `1` y `EXIT_INVALID_INPUT = 1`. | Propio | — |
| **B — Dominio** | Campos de `Incident` y `SLAEvaluation`; `evaluate_sla_status` con normalización y reconstrucción; `group_key_for` y `classify_incident`; `_run_demo` + E10.1/E10.2; auditoría idéntica. | Propio | — (paralela a A) |
| **C — Puertos y dobles** | `ports.py` (método nuevo, firma, error, puerto de identificadores); `InMemoryIncidentRepository` v3 y `SequenceIdGenerator`; conformidad de spec 002 adaptada. | | A |
| **D — Adaptadores de salida** | Columnas, migración aditiva, `idx_incidents_dup_key`, `add_incident`, `find_open_duplicates`; `null_repository.py`; `id_generator.py`; siembra derivada; conformidad SQLite ↔ memoria. | | B, C |
| **E — Casos de uso** | `create_incident`, `evaluate_incident_sla`, `IncidentNotFoundError`, `parse_instant`, proyecciones; reglas con el doble en memoria. | | B, C |
| **F — Canales y composición** | DTO, rutas, manejadores 404/409; subcomandos `create`/`sla`; `main.py` inyecta el generador. **Primer incremento de pruebas**: E1, E5, E12, E13, E14, E11. | | D, E |
| **G — Cobertura completa** | Resto de escenarios (E2–E4, E6, E8–E10, E15a–E23), SC-006 por canal, trazas sin contenido (E16, E18). | | F |
| **H — Verificación** | `ruff check src/` → `pytest -v` → `_run_demo` → auditoría idéntica → recorrido de [quickstart.md](quickstart.md). | | G |

## Riesgos

| Riesgo | Mitigación |
|---|---|
| `group_key_for` cambia la salida del lote y, con ella, la auditoría graduada. | El lote reutiliza la función, pero conserva el requisito de ≥ 2 miembros. Quickstart §6 compara la salida antes y después, y debe ser idéntica. |
| El cambio de `evaluate_sla_status` altera H002. | Solo cambia el resultado cuando hay `resolved_at > referencia`; H002 evalúa activos sin `resolved_at`. La suite de spec 002 lo confirma. |
| Archivo SQLite de H002 sin columnas nuevas. | Migración aditiva idempotente en `_init_schema` con prueba de conformidad sobre un archivo creado con el esquema previo. |
| Búsqueda de duplicados que falla después de guardar. | Riesgo residual aceptado (R5): el registro queda completo, la respuesta es `500`/`4` y un reintento con `incident_id` devuelve `409`. |
| Colisión de `INC-<HEX8>` generado. | `add_incident` es atómico; el servicio reintenta hasta 5 veces con otro identificador; `SequenceIdGenerator` lo prueba. |
| Ruta `GET /api/v1/incidents/{incident_id}/sla` y `GET /api/v1/incidents/summary` se confunden. | Profundidad distinta (`summary` no tiene `/sla`); una prueba de regresión del resumen sigue verde. |
| Romper consumidores del código de salida `3`. | MAJOR declarado y `AGENTS.md`; las specs 001/002 se enmiendan antes que sus pruebas. |
| Enmienda sin ADR (G19): ADR-006 sigue describiendo la firma de ventana de `find_open_duplicates`. | La Constitución 3.0.0 prevalece (Supremacía); la desviación queda registrada en ambas constituciones y en `AGENTS.md`, con la justificación en R4, R5, R7 y R11. |
| Fugas de título o texto en trazas. | El adaptador registra solo identificador, `is_duplicate`, número de duplicados, duración y estado (FR-021); E16/E18 lo verifican con `caplog`. |

## Seguimiento de complejidad

| Desviación | Por qué se necesita | Alternativa más simple descartada porque |
|---|---|---|
| Tercer puerto `IncidentIdGeneratorPort` (G7). | `INC-<HEX8>` exige aleatoriedad, y el Art. 1.3 prohíbe fuentes implícitas de no determinismo en el núcleo. | Llamar a `secrets` en el servicio hace no deterministas `create_incident` y sus pruebas. |
| `add_incident` además de `save_incident` (G7). | `409` sin carrera exige inserción atómica sin reemplazo; `save_incident` debe seguir siendo upsert para la siembra y la conformidad de spec 002. | Cambiar `save_incident` a solo inserción rompe un contrato verificado (Art. 5.6). Comprobar con `get_incident` antes de guardar tiene carrera. |
| Cambio de firma de `find_open_duplicates` (G7, G14). | El criterio clarificado es por clave, no por ventana; el método ya es el previsto por el Art. 2.4 y no tenía consumidor productivo. | Añadir un método nuevo deja uno muerto en todos los adaptadores. |
| Enmienda MAJOR por el código `1` (G13). | Decisión del usuario en la clarificación (spec D8). | Mantener `3` fue descartado por el usuario. |
| Stack sin ADR-004 y rutas `api/`/`cli.py` (G18). | Desviación previa. | Resolverla aquí mezcla decisiones; H003 no la agrava. |
| Enmienda 3.0.0 sin ADR (G19). | Decisión del usuario: no crear ADR-007. | Crear ADR-007 fue descartado por el usuario; justificar en ADR-004 mezcla decisiones. |

## Re-evaluación posterior al diseño

Tras la Fase 1 ([data-model.md](data-model.md), [contracts/](contracts/),
[quickstart.md](quickstart.md)), la compuerta se mantiene:

- ninguna regla de triaje, clave o SLA queda fuera del dominio;
- los puertos no filtran el motor;
- la aleatoriedad y el reloj se inyectan;
- la paridad es por construcción;
- no se agregan dependencias.

Las condiciones abiertas son G7 y G13, ambas bloqueadas tras la Fase A, y la desviación
heredada G18.
