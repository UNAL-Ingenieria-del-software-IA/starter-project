---

description: "Lista de tareas de implementación de H002 — Resumen de incidentes activos"
---

# Tareas: Resumen de incidentes activos (H002)

**Entrada**: documentos de diseño en `specs/002-active-incident-summary/`

**Prerrequisitos**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Pruebas**: obligatorias. La Constitución (Principio V.2) exige una prueba automatizada por
escenario aceptado, y el hito fija `tests/test_spec_002_summary.py`. Dentro de cada historia
las pruebas se escriben primero y deben fallar antes de implementar.

**Organización**: por historia de usuario de la spec (Historia 1 → US1, Historia 2 → US2,
Historia 3 → US3). Los escenarios transversales se asignan a la historia cuyo requisito
verifican.

## Formato: `[ID] [P?] [Historia] Descripción`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias pendientes).
- **[USn]**: historia de usuario a la que pertenece la tarea.
- Todas las rutas son relativas a la raíz del repositorio (proyecto único: `src/`, `tests/`).
- Comandos con `-X utf8` y `-m src.<módulo>` (ver `AGENTS.md`).

## Asignación de escenarios

| Historia | Escenarios | Requisitos |
|---|---|---|
| US1 — Estado operativo en una consulta (P1) 🎯 MVP | E1, E4, E7, E8, E9, E12 | FR-002–FR-005, FR-009 (base), FR-010–FR-012, FR-015 |
| US2 — Enfocarse en un componente (P2) | E2, E3 (E3.1, E3.2), parte HTTP de E11a (filtro vacío) | FR-006, FR-007 |
| US3 — Vista reproducible entre canales (P3) | E5, E6, E10, E11a, E11b | FR-001, FR-008, FR-009, FR-013, FR-014 |

---

## Fase 1: Preparación (enmienda D9 y fronteras Ruff)

**Propósito**: cumplir D9 (la enmienda del Art. 1.10 es la primera tarea del plan) y dejar
la verificación estática de fronteras activa antes de escribir código nuevo.

### 1A — Enmienda del Art. 1.10 (commit propio; bloquea FR-002)

- [X] T001 Enmendar el Art. 1.10 en docs/constitution.md: son activos `OPEN`, `IN_PROGRESS` y `ESCALATION_REQUIRED` (todo estado distinto de `RESOLVED`); conservar «un incidente `RESOLVED` exige `resolved_at`» y añadir ADR-005 a «Decisiones que la sustentan» (research.md §R1)
- [X] T002 [P] Enmendar el Art. 1.10 en .specify/memory/constitution.md con el mismo texto que T001, subir **Version** a 2.0.0 y **Last Amended** a la fecha de la enmienda; preparar el informe de impacto (Gobernanza, punto 4), revisarlo y retirarlo antes del commit
- [X] T003 [P] Crear docs/adr/0005-incidente-activo-distinto-de-resuelto.md a partir de docs/adr/000-template.md: estado Aceptado, decisión y alternativas de research.md §R1, y reemplazo del predicado e índice de ADR-001 §3 por el índice compuesto parcial y cubriente de research.md §R3 (no editar docs/adr/001-optimizacion-consulta-incidentes.md, Art. 3.7)
- [X] T004 Actualizar AGENTS.md (definición de activo y referencia a ADR-005) y la línea **Estado** de specs/002-active-incident-summary/spec.md para indicar que FR-002 queda desbloqueado
- [X] T005 Renombrar la variable `l` del algoritmo de Pascua en src/domain/holidays.py (hallazgo `E741` de la línea base, research.md §R12) sin `# noqa`; confirmar `uv run python -X utf8 -m src.sla_calculator` y `uv run python -X utf8 -m src.triage_rules` sin cambios de salida y hacer commit propio (`style(domain)`), requisito del punto 5 de la Gobernanza
- [X] T006 Ejecutar `uv run ruff check src/` y `uv run python -X utf8 -m pytest -v` en verde y hacer el commit propio de T001–T004 (`docs(constitution): enmendar Art. 1.10 …`)

### 1B — Configuración jerárquica de Ruff

- [X] T007 Agregar a pyproject.toml `[tool.ruff]` (`target-version = "py310"`), `[tool.ruff.lint]` (`select = ["E4", "E7", "E9", "F", "TID"]`) y `[tool.ruff.lint.flake8-tidy-imports]` (`ban-relative-imports = "parents"`) según research.md §R12
- [X] T008 [P] Crear src/domain/ruff.toml con `extend = "../../pyproject.toml"`, `[lint.flake8-tidy-imports]` `ban-relative-imports = "parents"` y la tabla `banned-api` completa de la capa `domain` (research.md §R12), cada entrada con `msg` en español que cite el artículo
- [X] T009 [P] Crear src/application/ruff.toml con `extend = "../../pyproject.toml"`, `ban-relative-imports = "parents"` y la tabla `banned-api` completa de la capa `application` (incluye `os`, Art. III.5)
- [X] T010 [P] Crear src/adapters/inbound/ruff.toml con `extend = "../../../pyproject.toml"`, `ban-relative-imports = "parents"` y la tabla `banned-api` de `adapters/inbound` (sin prohibir `src.main`, que `cli.py` usa en `__main__`)
- [X] T011 Ejecutar `uv run ruff check src/` (código 0) y la prueba de humo de fronteras de quickstart.md §2 con sondas temporales (borrarlas, no versionarlas); commit propio de T007–T010

**Punto de control**: Art. 1.10 enmendado y Ruff en verde con fronteras por capa.

---

## Fase 2: Fundamentos (puerto, adaptadores de salida y composición)

**Propósito**: infraestructura que todas las historias necesitan.

**⚠️ CRÍTICO**: ninguna historia empieza antes de terminar esta fase. T012 depende de T006.

- [X] T012 Agregar `ACTIVE_STATUSES` y `SEVERITY_ORDER` a src/domain/models.py según data-model.md §1 «Constantes nuevas» (definición de `Incident.status` activo y orden de `Incident.severity`)
- [X] T013 Declarar `IncidentRepositoryPort` (`typing.Protocol`, sin `@runtime_checkable`) en src/application/ports.py con la firma y docstrings en español de contracts/incident-repository-port.md y, en el mismo cambio, crear docs/adr/0006-puerto-repositorio-y-database-url.md (Aceptado) con la justificación por método de research.md §R7 (Art. III.2), la selección por `DATABASE_URL` (§R5), el papel del `INNER JOIN sla_policies` (§R3), la siembra de demostración (§R6), el repositorio nulo y el contrato de canales de H002 (`GET /api/v1/incidents/summary` y subcomando `summary`)
- [X] T014 [P] Crear tests/doubles.py con `InMemoryIncidentRepository` que cumpla la semántica de contracts/incident-repository-port.md: upsert por data-model.md `Incident.incident_id`, normalización de data-model.md `Incident.created_at` y `Incident.resolved_at` con `to_bogota`, activos según `ACTIVE_STATUSES`; agregar `FailingIncidentRepository`, cuyo `list_active_incidents` lanza `RuntimeError`
- [X] T015 Escribir en tests/test_spec_002_summary.py el bloque «Conformidad del puerto» de contracts/incident-repository-port.md (forma por `inspect.signature` para SQLite, nulo y doble; batería compartida doble vs `SQLiteIncidentRepository(":memory:")`; deriva del predicado con los cuatro estados; espejo `sla_policies` vs `SLA_POLICY_TABLE`; `EXPLAIN QUERY PLAN` con `idx_incidents_active_component` en ambas variantes; `ValueError` ante severidad sin política) y confirmar que falla
- [X] T016 [P] Crear src/adapters/outbound/null_repository.py con `NullIncidentRepository` según la columna «Nulo» de contracts/incident-repository-port.md
- [X] T017 Crear src/adapters/outbound/sqlite_repository.py con `SQLiteIncidentRepository`: DDL, `PRAGMA foreign_keys`, espejo `sla_policies` sembrado desde `SLA_POLICY_TABLE`, índice y dos `SELECT` constantes con `INNER JOIN sla_policies` (research.md §R3); mapeo fila ↔ entidad de data-model.md §3 para data-model.md `Incident.incident_id` (clave primaria, upsert `ON CONFLICT`), data-model.md `Incident.title`, data-model.md `Incident.component` (se guarda tal cual; ya llega canónico), data-model.md `Incident.created_at` y `Incident.resolved_at`; una conexión `check_same_thread=False` con `threading.Lock` (research.md §R4); validación de `Incident.severity` con `get_sla_rule_for_severity`; `check_health` con `SELECT 1` que nunca lanza
- [X] T018 [P] Crear src/adapters/outbound/demo_incidents.py con la tupla inmutable `INC-2001`…`INC-2008` que cumpla la cobertura de data-model.md §6, con todos los componentes en forma canónica en minúsculas (data-model.md `Incident.component`), y `seed_demo_incidents(repository)` vía `save_incident`
- [X] T019 Crear src/adapters/outbound/factory.py con `create_incident_repository(database_url: str)` según la tabla de research.md §R5 (sin leer el entorno; `ValueError` en español que nombra solo el esquema)
- [X] T020 Cambiar el constructor a `IncidentService(clock, repository)` en src/application/services.py sin alterar `triage_incident` ni `to_contract`
- [X] T021 Cambiar src/main.py: `build_service(now=None, repository=None)` lee `DATABASE_URL` (por defecto `sqlite:///:memory:`) solo cuando no recibe repositorio, usa `create_incident_repository`, falla al arrancar si `check_health()` es `False` y siembra la demo solo para `:memory:` (research.md §R5–§R6); `app` se construye bajo demanda con `__getattr__` de módulo (PEP 562) que importa `create_app` dentro de la función, de modo que importar `src.main` desde el CLI no crea el servicio HTTP ni importa FastAPI (`uvicorn src.main:app` sigue funcionando); `cli` sigue siendo `create_cli(build_service)`
- [X] T022 Actualizar tests/conftest.py para que las fixtures `service` y `cli_app` de spec 001 usen `build_service(..., repository=NullIncidentRepository())` sin cambiar ninguna aserción de tests/test_spec_001_triage.py (Art. III.4)
- [X] T023 [P] Ampliar tests/test_arquitectura.py con la frontera `src/adapters/inbound/` ↛ `src.adapters.outbound` y `sqlite3` (complemento AST de Ruff, Principio IV.5)
- [X] T024 Ejecutar `uv run ruff check src/` y `uv run python -X utf8 -m pytest -v`: spec 001 y arquitectura en verde, bloque de conformidad (T015) en verde

**Punto de control**: puerto, tres implementaciones y raíz de composición listos; H001 intacto.

---

## Fase 3: Historia 1 — Ver el estado operativo en una sola consulta (Prioridad: 1) 🎯 MVP

**Objetivo**: `GET /api/v1/incidents/summary` devuelve totales y detalle ordenado de todos
los activos, con minutos, incumplimiento y escalamiento del dominio.

**Prueba independiente**: con el doble sembrado y `FixedClock`, una consulta HTTP devuelve
los dos totales y el detalle completo; E1, E4, E7, E8, E9 y E12 en verde.

### Pruebas de la Historia 1 (escribir primero; deben fallar)

- [X] T025 [US1] Escribir en tests/test_spec_002_summary.py E1, E4, E7, E8 y E9 sobre `IncidentService` + `InMemoryIncidentRepository` + `FixedClock`, con docstrings `Given/When/Then` en español y cada `Given` declarando sus propios incidentes; E7 compara minutos con `evaluate_sla_status` directamente
- [X] T026 [US1] Escribir en tests/test_spec_002_summary.py E12 (mil consultas no alteran ningún incidente según `get_incident`, sobre el doble y sobre SQLite; `caplog` del adaptador HTTP sin títulos) y la variante HTTP de E1 con `TestClient` (200, campos de data-model.md `ActiveIncidentItem`, `POST` → `405 method_not_allowed`)

### Implementación de la Historia 1

- [X] T027 [US1] Agregar `ActiveIncidentView` y `ActiveIncidentsSummary` a src/application/services.py según data-model.md §2, con data-model.md `ActiveIncidentsSummary.total_active` y `ActiveIncidentsSummary.breached_count` como propiedades derivadas de data-model.md `ActiveIncidentsSummary.incidents`
- [X] T028 [US1] Agregar `parse_reference_time` a src/application/services.py según data-model.md §2 (sufijo `Z`, `ValidationError("invalid_timestamp", …, "reference_time")`, research.md §R8)
- [X] T029 [US1] Implementar `IncidentService.get_active_incidents_summary(component_filter, reference_time)` en src/application/services.py con los pasos 2–7 de data-model.md §2: data-model.md `ActiveIncidentsSummary.reference_time` (reloj, `to_bogota`, truncado a segundos), filtro por `ACTIVE_STATUSES`, exclusión por data-model.md `Incident.created_at` posterior al instante, evaluación con `evaluate_sla_status` y orden de data-model.md `ActiveIncidentsSummary.incidents`; en esta historia `component_filter` se reenvía sin normalizar
- [X] T030 [US1] Agregar `summary_to_contract` a src/application/services.py según data-model.md §2, emitiendo data-model.md `ActiveIncidentsSummaryResponse.reference_time` como cadena `isoformat()` (research.md §R9)
- [X] T031 [P] [US1] Agregar a src/adapters/inbound/api/schemas.py `SummaryQueryParams` (data-model.md `SummaryQueryParams.component` y `SummaryQueryParams.reference_time`, `extra="forbid"`), `ActiveIncidentItem` (data-model.md `ActiveIncidentItem.incident_id`, `ActiveIncidentItem.title`, `ActiveIncidentItem.component`, `ActiveIncidentItem.severity` y `ActiveIncidentItem.status` con los `Literal` del dominio, `ActiveIncidentItem.elapsed_minutes`, `ActiveIncidentItem.is_breached` y `ActiveIncidentItem.requires_escalation`) y `ActiveIncidentsSummaryResponse` (data-model.md `ActiveIncidentsSummaryResponse.reference_time` como `str`, `ActiveIncidentsSummaryResponse.component_filter` opcional, `ActiveIncidentsSummaryResponse.total_active`, `ActiveIncidentsSummaryResponse.breached_count` y `ActiveIncidentsSummaryResponse.incidents`)
- [X] T032 [US1] Agregar en src/adapters/inbound/api/app.py la ruta `GET /api/v1/incidents/summary` con `Annotated[SummaryQueryParams, Query()]`, `parse_reference_time`, llamada al servicio y `summary_to_contract`; ajustar `_format_loc` para omitir el prefijo `"query"`; registrar un manejador de `StarletteHTTPException` que convierta solo `405` en la envoltura `method_not_allowed`; documentar 400/405/422/500 en `responses` (contracts/http-incidents-summary.openapi.yaml)
- [X] T033 [US1] Agregar en src/adapters/inbound/api/app.py la traza por consulta de research.md §R14 (`total_active`, `breached_count`, duración en ms y estado HTTP; nunca títulos)

**Punto de control**: US1 funcional y comprobable sola por HTTP; E1, E4, E7, E8, E9 y E12 en verde.

---

## Fase 4: Historia 2 — Enfocarse en un componente (Prioridad: 2)

**Objetivo**: filtrar el resumen por componente con normalización, cifras del subconjunto y
caso vacío exitoso.

**Prueba independiente**: con incidentes activos en `payment-gateway` y `auth-identity`, el
filtro por uno devuelve solo ese subconjunto; un componente sin coincidencias devuelve 200
vacío.

### Pruebas de la Historia 2 (escribir primero; deben fallar)

- [ ] T034 [US2] Escribir en tests/test_spec_002_summary.py E2, E3 (E3.1 y E3.2 parametrizados), la normalización de `" Payment-Gateway "`, SC-004 (la suma de los resúmenes por componente reproduce el global sin diferencias) y el `422 invalid_payload` con `field = "component"` para `""` y `"   "`, por servicio y por HTTP

### Implementación de la Historia 2

- [ ] T035 [US2] Implementar en src/application/services.py la normalización `strip().lower()` y el rechazo de filtro vacío de data-model.md `ActiveIncidentsSummary.component_filter` (paso 1 de data-model.md §2, `ValidationError("invalid_payload", …, "component")`), reenviando al repositorio el valor normalizado

**Punto de control**: US1 y US2 funcionan cada una por separado.

---

## Fase 5: Historia 3 — Confiar en una vista reproducible entre canales (Prioridad: 3)

**Objetivo**: instante de referencia explícito y subcomando CLI `summary` con el mismo JSON
que HTTP.

**Prueba independiente**: el mismo almacén y el mismo instante producen el mismo cuerpo JSON
por HTTP y por CLI; un instante distinto cambia las banderas según la política canónica.

### Pruebas de la Historia 3 (escribir primero; deben fallar)

- [ ] T036 [US3] Escribir en tests/test_spec_002_summary.py E5, E6, el instante futuro admitido y los casos de `parse_reference_time` (naive = Bogotá, sufijo `Z`, desfase explícito, `"ayer"` → `invalid_timestamp`)
- [ ] T037 [US3] Escribir en tests/test_spec_002_summary.py E10 (paridad HTTP/CLI `--format json` valor a valor y en orden, con y sin filtro, mismo doble y mismo `--reference-time`), E11a (HTTP `422` y CLI código `3` con diagnóstico en `stderr` y `stdout` vacío) E11b (parámetro desconocido → HTTP `400`; bandera desconocida y `--format` inválido → CLI código `2`), el fallo interno con `FailingIncidentRepository` (HTTP `500 internal_error` sin títulos en `caplog`; CLI código `4` con `error [internal_error]: RuntimeError` en `stderr`) y SC-001 por canal (10 000 activos sembrados en `SQLiteIncidentRepository(":memory:")`; una consulta por `TestClient` y otra por `CliRunner`, cada una < 1 s)

### Implementación de la Historia 3

- [ ] T038 [US3] Agregar en src/adapters/inbound/cli.py el subcomando `summary` según contracts/cli-summary.md: `--component`, `--reference-time` (vía `parse_reference_time`), `--format table|json`, servicio desde `service_factory(None)`, `ValidationError` → `3`, excepción inesperada → `4`, JSON con `summary_to_contract` y `ensure_ascii=False`, tabla con línea de totales y `sí`/`no`; crear el helper `_build_service(service_factory, now)` y usarlo en `summary` y `triage` para que un `ValueError` de configuración (`DATABASE_URL` no soportada) termine con código `4` y `error [internal_error]: <mensaje>` en `stderr`, sin traceback ni cambios en las aserciones de spec 001; actualizar la docstring del módulo y la ayuda de Typer

**Punto de control**: las tres historias funcionan y E1–E12 están en verde.

---

## Fase 6: Pulido y aspectos transversales

**Propósito**: documentación, arnés de rendimiento y verificación final.

- [ ] T039 [P] Reducir src/incident_repository.py a arnés de benchmark según research.md §R15: eliminar `IncidentRepository` y su SQL, componer `SQLiteIncidentRepository` + `IncidentService` + `FixedClock`, sembrar sintéticos con componentes canónicos vía `save_incident`, medir promedio y p95 con y sin filtro, y corregir la docstring y el banner obsoletos («Antes de Refactorizar», N+1)
- [ ] T040 [P] Enmendar F3 en .specify/memory/constitution.md para agregar `GET /api/v1/incidents/summary` y el subcomando `summary` (`--component`, `--reference-time`, `--format table|json`), subir **Version** a 2.1.0 (MINOR: guía ampliada) con ADR-006 como sustento, preparar, revisar y retirar el informe de impacto, y comprobar `uv run ruff check src/` y pytest en verde (Gobernanza, puntos 1–5)
- [ ] T041 Actualizar AGENTS.md: comandos (`uv run ruff check src/`, subcomando `summary`, `GET /api/v1/incidents/summary`, `DATABASE_URL`), mapa de arquitectura (`IncidentRepositoryPort`, módulos de `src/adapters/outbound/`, `ruff.toml` por capa), retirar «Not migrated» de `incident_repository.py`, actualizar la lista de pendientes de spec 001 y agregar el gotcha de jerarquía de Ruff (`extend`; `--config` la desactiva)
- [ ] T042 [P] Agregar a README.md los comandos de consulta del resumen por HTTP y CLI
- [ ] T043 Ejecutar la validación completa de quickstart.md §1–§7 en el orden de la Constitución (Ruff, pytest, `_run_demo`, auditoría con salida idéntica, HTTP, CLI, `DATABASE_URL`, benchmark SC-001 con p95 < 1 000 ms) y corregir cualquier desviación
- [ ] T044 Revisar el criterio de terminado F4 (a–f) de .specify/memory/constitution.md y el Art. 3.6 de docs/constitution.md contra el cambio completo antes del commit final

---

## Dependencias y orden de ejecución

### Dependencias entre fases

- **Fase 1A (T001–T006)**: sin dependencias; T005 debe aterrizar antes del commit de T006.
- **Fase 1B (T007–T011)**: puede avanzar en paralelo con 1A (archivos distintos), pero T011
  necesita T005 para quedar en verde.
- **Fase 2 (T012–T024)**: depende de T006 (enmienda) y T011 (Ruff). Bloquea todas las historias.
- **US1 (Fase 3)**: depende de la Fase 2.
- **US2 (Fase 4)**: depende de la Fase 2 y de T029 (método del servicio) y T032 (ruta HTTP).
- **US3 (Fase 5)**: depende de la Fase 2 y de T028–T030 (analizador, método y proyección);
  E10 compara contra la ruta de T032.
- **Pulido (Fase 6)**: depende de las historias que se entreguen.

### Dependencias dentro de la Fase 2

T012 → T013 → (T014, T016, T018 en paralelo) → T015 → T017 → T019 → T020 → T021 → T022 →
T024. T023 puede correr en cualquier momento de la fase.

### Dentro de cada historia

- Pruebas primero y en rojo; luego vistas y proyección, después servicio, luego canales.
- Todas las pruebas de H002 viven en tests/test_spec_002_summary.py, así que las tareas de
  prueba no se paralelizan entre sí.
- src/application/services.py concentra T020, T027–T030 y T035: ejecutarlas en serie.

### Oportunidades de paralelismo

- Fase 1: T002 y T003 en paralelo tras T001; T008, T009 y T010 en paralelo tras T007.
- Fase 2: T014, T016, T018 y T023 en paralelo.
- US1: T031 (schemas.py) en paralelo con T027–T030 (services.py).
- Fase 6: T039, T040 y T042 en paralelo.

---

## Ejemplo de paralelismo: Historia 1

```text
# Mientras se implementa el servicio (T027 → T028 → T029 → T030 en services.py):
Tarea: "T031 Agregar SummaryQueryParams, ActiveIncidentItem y ActiveIncidentsSummaryResponse en src/adapters/inbound/api/schemas.py"
```

## Ejemplo de paralelismo: Fase 2

```text
Tarea: "T014 Crear InMemoryIncidentRepository en tests/doubles.py"
Tarea: "T016 Crear NullIncidentRepository en src/adapters/outbound/null_repository.py"
Tarea: "T018 Crear el conjunto de demostración en src/adapters/outbound/demo_incidents.py"
Tarea: "T023 Ampliar tests/test_arquitectura.py con la frontera inbound ↛ outbound"
```

---

## Estrategia de implementación

### MVP primero (solo Historia 1)

1. Fase 1: enmienda (commit propio) y Ruff (commit propio).
2. Fase 2: puerto, adaptadores y composición (H001 sigue en verde).
3. Fase 3: US1 por HTTP.
4. **Detenerse y validar**: E1, E4, E7, E8, E9 y E12 en verde; quickstart.md §1 y §3.

### Entrega incremental

1. Fases 1–2 → base lista.
2. US1 → resumen global por HTTP (MVP).
3. US2 → filtro por componente.
4. US3 → instante de referencia explícito, CLI y paridad.
5. Fase 6 → enmienda F3, documentación y benchmark SC-001 (ADR-006 ya se creó con el puerto en T013).

### Commits sugeridos

1. `style(domain)` — T005.
2. `docs(constitution)` — T001–T004 (D9).
3. `chore(ruff)` — T007–T010.
4. `feat(h002)` — Fase 2 y una entrega por historia.
5. `docs(h002)` — Fase 6.

---

## Notas

- Prohibido debilitar pruebas de spec 001 o la auditoría (Principio V.6).
- Prohibido `# noqa` para reglas de frontera (Principio IV.4).
- No tocar `data/sample_incidents.json` ni `CONTEXT_LOG.md`.
- La desviación heredada de ADR-004 (stack y rutas `api/`/`cli.py`) queda fuera de estas
  tareas; ver «Seguimiento de complejidad» en plan.md.
