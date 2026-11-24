---

description: "Lista de tareas de implementación de H003 — Registro, duplicado abierto y auditoría de SLA"
---

# Tareas: Registro de incidentes, aviso de duplicado abierto y auditoría de SLA (H003)

**Entrada**: documentos de diseño en `specs/003-incident-lifecycle-sla/`

**Prerrequisitos**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Pruebas**: obligatorias. La Constitución (Principio V.2) exige una prueba automatizada por
escenario aceptado, y el plan fija `tests/test_spec_003_lifecycle_sla.py` con una función
`test_bdd_*` por escenario (skill `bdd-acceptance`). Dentro de cada historia, las pruebas
se escriben primero y deben fallar antes de implementar.

Los **cinco comportamientos pedidos** se marcan con ⭐. Son seis funciones, porque E13 y
E14 son reglas distintas: E1, E5, E12, E13, E14 y E11. Forman el primer incremento de
pruebas.

**Organización**: por historia de usuario de la spec (Historia 1 → US1, Historia 2 → US2,
Historia 3 → US3). Los escenarios transversales se asignan a la historia cuyo requisito
verifican.

## Formato: `[ID] [P?] [Historia] Descripción`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias pendientes).
- **[USn]**: historia de usuario a la que pertenece la tarea.
- Todas las rutas son relativas a la raíz del repositorio (proyecto único: `src/`, `tests/`).
- Comandos con `-X utf8` y `-m src.<módulo>` (ver `AGENTS.md`).
- Pruebas de aceptación sobre SQLite desechable en `tmp_path` por prueba, con reloj fijo y
  conexiones cerradas en el finalizador del fixture (skill `bdd-acceptance` §4).

## Asignación de escenarios

| Historia | Escenarios | Requisitos |
|---|---|---|
| US1 — Crear un incidente cuando llega (P1) 🎯 MVP | ⭐E1, E3, E4, E15a, E15b, E17, E18, E19, E20, E21 | FR-001–FR-006, FR-017, FR-018 (POST), FR-019 (`create`), FR-021 (creación), FR-022, FR-023 |
| US2 — Enterarse de un duplicado abierto (P2) | ⭐E5, E6, E8, E22, E23 | FR-007–FR-011 |
| US3 — Auditar el SLA de un incidente (P3) | ⭐E12, ⭐E13, ⭐E14, ⭐E11, E2, E9, E10, E16 | FR-006 (reinicio), FR-012–FR-016, FR-018 (GET), FR-019 (`sla`), FR-020, FR-021 (auditoría) |
| Pulido | SC-006 por canal | SC-006 |

E7 está retirado (spec, Clarifications) y no tiene prueba.

---

## Fase 1: Preparación — enmienda constitucional (bloqueante, commit propio)

**Propósito**: cerrar las violaciones G7 y G13 del plan antes de tocar código de
producción. Abarca la Constitución 3.0.0, las enmiendas de spec 001 y spec 002 y el
código de salida `1` (spec D8, research.md §R4, §R7, §R11).

**Sin ADR-007 (decisión 2026-11-24).** La enmienda se hace sin ADR nuevo y queda
registrada como **desviación de gobernanza abierta**. Incumple el punto 2 de la
Gobernanza de .specify/memory/constitution.md y el Art. 4.1 de docs/constitution.md, que
exigen un ADR aceptado para toda enmienda. La justificación de cada cambio queda en
research.md §R4, §R5, §R7 y §R11. ADR-006 no se edita (Art. 3.7). Sus filas sobre
`find_open_duplicates` y el catálogo quedan desplazadas por la Constitución 3.0.0
(Supremacía) hasta que un ADR las reemplace formalmente.

- [X] T001 Enmendar .specify/memory/constitution.md a **Version** 3.0.0 (MAJOR) con **Last Amended** 2026-11-24, en tres puntos, y preparar, revisar y retirar el informe de impacto (Gobernanza, punto 4):
  - **F3, rutas**: agregar `POST /api/v1/incidents` y `GET /api/v1/incidents/{incident_id}/sla`.
  - **F3, subcomandos y códigos**: agregar `create` (`--title`, `--raw-text`, `--incident-id`, `--created-at`, `--status`, `--resolved-at`, `--format table|json`) y `sla <incident_id>` (`--reference-time`, `--format`); los códigos quedan en `0` correcto, `1` entrada inválida, `2` error de uso, `4` error interno, y se retira el `3`.
  - **Art. 3.2**: el catálogo incluye `IncidentIdGeneratorPort`, y `IncidentRepositoryPort` incluye `add_incident` y `find_open_duplicates` por clave de grupo.
- [X] T002 [P] Enmendar el Art. 2.4 de docs/constitution.md (catálogo de puertos: `IncidentIdGeneratorPort`; repositorio que guarda, inserta sin reemplazar y localiza abiertos por clave de grupo), sin agregar ningún ADR a «Decisiones que la sustentan»
- [X] T003 Registrar la desviación de gobernanza de la enmienda sin ADR, después de T001 y T002. No se crea ningún ADR ni se edita docs/adr/0006-puerto-repositorio-y-database-url.md (Art. 3.7).
  - **En .specify/memory/constitution.md**: junto al ADR-004 en «Pendiente de registro», declarar que la versión 3.0.0 se adoptó sin el ADR que exige el punto 2 de la Gobernanza. Nombrar los cambios: códigos `0/1/2/4`, rutas y subcomandos de F3, `IncidentIdGeneratorPort`, `add_incident` y `find_open_duplicates` por clave. Remitir su justificación a specs/003-incident-lifecycle-sla/research.md §R4, §R5, §R7 y §R11.
  - **En docs/constitution.md**: una nota equivalente junto al Art. 2.4 (o al Art. 4.1).
  - **ADR-006**: indicar que sus filas sobre `find_open_duplicates` y el catálogo quedan desplazadas por la Constitución 3.0.0 hasta que un ADR las reemplace.
  - **Informe de impacto** (T001): debe listar la desviación.
- [X] T004 [P] Enmendar los contratos previos:
  - specs/001-triage-endpoint-manual.md §7: código `3` → `1`.
  - specs/002-active-incident-summary/spec.md (tabla del contrato CLI y FR-013) y specs/002-active-incident-summary/contracts/cli-summary.md: código `3` → `1`.
  - specs/002-active-incident-summary/contracts/incident-repository-port.md: nota de que `find_open_duplicates` y `add_incident` los rige specs/003-incident-lifecycle-sla/contracts/incident-repository-port.md.
- [X] T005 Cambiar `EXIT_INVALID_INPUT = 3` por `1` en src/adapters/inbound/cli.py, junto con la docstring del módulo (códigos `0/1/2/4`). Después de T004, cambiar las aserciones `exit_code == 3` → `1` en tests/test_spec_001_triage.py (≈ línea 151) y tests/test_spec_002_summary.py (≈ línea 753), sin tocar ninguna otra aserción (Art. 5.6).
- [X] T006 Actualizar AGENTS.md:
  - códigos de salida del CLI;
  - comandos `create` y `sla`, y rutas HTTP nuevas;
  - mapa de puertos (`add_incident`, `find_open_duplicates` por clave, `IncidentIdGeneratorPort`);
  - referencia a Constitución 3.0.0;
  - en «Open governance deviation», la enmienda 3.0.0 sin ADR, junto a la del stack (ADR-004).
- [X] T007 Ejecutar `uv run ruff check src/`, `uv run python -X utf8 -m pytest -v`, `uv run python -X utf8 -m src.sla_calculator` y `uv run python -X utf8 -m src.triage_rules` en verde y hacer el commit propio de T001–T006 (`docs(constitution): 3.0.0 …`) — commit 7113da3

**Punto de control**: Constitución 3.0.0 adoptada, con la falta de ADR registrada como
desviación abierta; CLI con código `1`; H001 y H002 en verde.

---

## Fase 2: Fundamentos — entidad, puertos, persistencia y composición

**Propósito**: infraestructura que las tres historias necesitan.

**⚠️ CRÍTICO**: ninguna historia empieza antes de terminar esta fase. T008 puede empezar en
paralelo con la Fase 1 (dominio puro); T010 en adelante depende de T007.

- [X] T008 [P] Extender las entidades de src/domain/models.py:
  - `Incident`: agregar al final data-model.md `Incident.recommended_team` y data-model.md `Incident.duplicate_group_key`, ambos con valor por defecto `None`, sin romper la construcción posicional de src/adapters/outbound/demo_incidents.py.
  - `SLAEvaluation`: agregar data-model.md `SLAEvaluation.resolved_at_reference` con valor por defecto `False`.
- [X] T009 Ejecutar `uv run python -X utf8 -m src.sla_calculator`, `uv run python -X utf8 -m src.triage_rules` y la suite de spec 002 para confirmar que T008 no cambia ninguna salida
- [X] T010 Actualizar src/application/ports.py según contracts/incident-repository-port.md, con docstrings en español:
  - declarar `IncidentIdConflictError(incident_id)`;
  - declarar `IncidentIdGeneratorPort` (`new_id() -> str`, `typing.Protocol`);
  - agregar `add_incident(incident)` a `IncidentRepositoryPort`;
  - cambiar la firma a `find_open_duplicates(duplicate_group_key: str, exclude_incident_id: str)`.
- [X] T011 [P] Actualizar tests/doubles.py:
  - `InMemoryIncidentRepository` v3: `add_incident` lanza `IncidentIdConflictError` sin alterar el existente; `find_open_duplicates` por data-model.md `Incident.duplicate_group_key`, excluyendo `RESOLVED` y el propio identificador, ordenado por `(created_at, incident_id)`; `save_incident` y `get_incident` conservan data-model.md `Incident.recommended_team`.
  - `SequenceIdGenerator(ids)`: devuelve una secuencia fija, para pruebas deterministas y de colisión.
  - `FailingOnAddRepository`: `add_incident` lanza `RuntimeError`.
- [X] T012 Actualizar la conformidad de spec 002 en tests/test_spec_002_summary.py, después de T004:
  - la lista `PORT_METHODS` (≈ línea 110) pasa a seis métodos, con `add_incident`;
  - los casos de `find_open_duplicates` con ventana (≈ líneas 196-201 y 274) pasan a la firma por clave;
  - no se relaja ninguna otra aserción.
- [X] T013 Escribir en tests/test_spec_003_lifecycle_sla.py el bloque «Conformidad del puerto v3» de contracts/incident-repository-port.md y confirmar que falla:
  - forma por `inspect.signature` de SQLite, nulo y doble;
  - batería compartida entre `SQLiteIncidentRepository` en `tmp_path` e `InMemoryIncidentRepository`: conflicto de `add_incident`, filtro y orden de `find_open_duplicates`, ida y vuelta de los nueve campos;
  - migración: un archivo creado con el esquema de H002 se abre, gana columnas y conserva sus filas;
  - `EXPLAIN QUERY PLAN` de la búsqueda usa `idx_incidents_dup_key`.
- [X] T014 Extender src/adapters/outbound/sqlite_repository.py según data-model.md §3 y research.md §R8:
  - **Esquema**: columnas para data-model.md `Incident.recommended_team` y data-model.md `Incident.duplicate_group_key`; migración aditiva idempotente con `PRAGMA table_info(incidents)` y `ALTER TABLE … ADD COLUMN` constantes; índice parcial `idx_incidents_dup_key` sobre `(duplicate_group_key, status)` con `WHERE status <> 'RESOLVED' AND duplicate_group_key IS NOT NULL`.
  - **`save_incident` y `get_incident`**: pasan a nueve columnas.
  - **`add_incident`**: `INSERT` sin `ON CONFLICT`; un `IntegrityError` de PK sobre data-model.md `Incident.incident_id` se traduce en `IncidentIdConflictError`, y una severidad sin política, en `ValueError`.
  - **`find_open_duplicates`**: `SELECT` constante con `INNER JOIN sla_policies` y `?`.
  - **`close()`**: método nuevo, fuera del puerto, para liberar el archivo en Windows.
- [X] T015 [P] Actualizar src/adapters/outbound/null_repository.py: `add_incident` no hace nada y `find_open_duplicates(clave, excluir)` devuelve `()`
- [X] T016 [P] Crear src/adapters/outbound/id_generator.py con `RandomHexIdGenerator.new_id()` = `"INC-" + secrets.token_hex(4).upper()` (research.md §R7, data-model.md `Incident.incident_id` forma generada)
- [X] T017 Cambiar el constructor a `IncidentService(clock, repository, id_generator=None)` en src/application/services.py sin alterar `triage_incident` ni `get_active_incidents_summary`; generalizar `parse_reference_time` a `parse_instant(value, field)` y conservar `parse_reference_time` como alias que pasa `field="reference_time"` (research.md §R6)
- [X] T018 Cambiar src/main.py: `build_service(now=None, repository=None, id_generator=None)` inyecta `RandomHexIdGenerator()` si no recibe generador; `app` y `cli` siguen construyéndose igual
- [X] T019 Ejecutar `uv run ruff check src/` y `uv run python -X utf8 -m pytest -v`: spec 001, spec 002, arquitectura y conformidad v3 (T013) en verde

**Punto de control**: entidad, puertos, adaptador SQLite migrado, generador y composición
listos; H001 y H002 intactos.

---

## Fase 3: Historia 1 — Crear un incidente cuando llega (Prioridad: 1) 🎯 MVP

**Objetivo**: `POST /api/v1/incidents` y `create` guardan un incidente clasificado por el
triaje, con identificador enviado o `INC-<HEX8>`, estado inicial validado y persistencia
entre procesos.

**Prueba independiente**: se crea un incidente en un almacén SQLite de archivo, se abre un
segundo adaptador sobre el mismo archivo y el incidente está con los mismos datos.
⭐E1, E3, E4, E15a, E15b y E17–E21 en verde.

### Pruebas de la Historia 1 (escribir primero; deben fallar)

- [X] T020 [US1] ⭐ Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e1_registro_inicial_sin_duplicados`, con `TestClient`, almacén vacío en `tmp_path` y reloj fijo 2026-11-24T09:10. Verifica:
  - `201`;
  - `incident_id` con la forma `^INC-[0-9A-F]{8}$`;
  - `status` = `OPEN` y `created_at` = `2026-11-24T09:10:00-05:00`;
  - clasificación igual a la del triaje canónico del mismo texto (severidad, componente, equipo, acción y `duplicate_group_key`);
  - `is_duplicate` = `false` y `duplicate_of` = `[]`.
- [X] T021 [US1] Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e3_…` (misma severidad con y sin "URGENTE"/"para hoy") y `test_bdd_e4_…` (el incidente creado aparece en `GET /api/v1/incidents/summary`). E2 se prueba en US3 (T042) porque verifica el reinicio auditando el SLA.
- [X] T022 [US1] Escribir en tests/test_spec_003_lifecycle_sla.py:
  - `test_bdd_e19_…`: se respeta `INC-CLIENTE-01`.
  - `test_bdd_e20_…`: `INC-2001` repetido da `409 incident_id_conflict` por HTTP y código `1` por CLI, con el existente intacto.
  - `test_bdd_e21_…`: parametrizado E21.1–E21.7 según la tabla de la spec.
- [X] T023 [US1] Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e15a_…` (parametrizado E15a.1–E15a.6: `422` con su código por HTTP y código `1` por CLI, sin guardar nada) y `test_bdd_e15b_…` (`priority` desconocido y campos reservados: `400` por HTTP y código `2` por CLI)
- [X] T024 [US1] Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e17_…` (`FailingOnAddRepository`: `500 internal_error`, CLI código `4`, sin identificador en la respuesta) y `test_bdd_e18_…` (`caplog` del adaptador HTTP sin el texto ni el título)

### Implementación de la Historia 1

- [X] T025 [P] [US1] Agregar a src/domain/triage_rules.py, según research.md §R1 y data-model.md §1 «Funciones nuevas»:
  - `group_key_for(component, signals)`, que produce data-model.md `Incident.duplicate_group_key`;
  - `classify_incident(report)`, para un solo reporte, con `duplicate_type="none"` y `merge=False`.

  `_correlate_availability` y `_correlate_performance` reutilizan `group_key_for` conservando el requisito de ≥ 2 miembros.
- [X] T026 [US1] Comprobar la invariancia de T025: la salida de `uv run python -X utf8 -m src.triage_rules` es idéntica a la de antes del cambio (quickstart.md §6), y tests/test_spec_001_triage.py sigue en verde
- [X] T027 [US1] Agregar a src/application/services.py `CreateIncidentInput`, `IncidentCreation` (con la propiedad `is_duplicate`) e `IncidentService.create_incident` según data-model.md §2, pasos 1–5 y 7:
  - **Validación** (research.md §R6): data-model.md `Incident.title` y el texto del reporte; data-model.md `Incident.incident_id` con su patrón para el valor enviado; data-model.md `Incident.status` y data-model.md `Incident.resolved_at` (estados admitidos, `RESOLVED` ⇔ resolución, resolución ≥ creación).
  - **Instantes**: data-model.md `Incident.created_at` desde el reloj y `to_bogota`.
  - **Clasificación**: con `classify_incident`; data-model.md `Incident.component`, data-model.md `Incident.severity`, data-model.md `Incident.recommended_team` y data-model.md `Incident.duplicate_group_key` se toman del resultado, sin que el servicio decida ninguno.
  - **Guardado**: `add_incident`; con identificador generado, hasta 5 reintentos ante `IncidentIdConflictError`; con identificador enviado, el conflicto se propaga; sin generador inyectado, `RuntimeError`.

  En esta historia, `duplicate_of` es siempre `()`.
- [X] T028 [US1] Agregar `creation_to_contract` a src/application/services.py según data-model.md §4 (instantes como cadena ISO con desfase; sin `duplicate_type` ni `merge`)
- [X] T029 [P] [US1] Agregar a src/adapters/inbound/api/schemas.py:
  - `CreateIncidentRequest` (`extra="forbid"`, todos los campos `StrictStr`: data-model.md `Incident.title`, `raw_text`, data-model.md `Incident.incident_id`, `Incident.created_at`, `Incident.status` y `Incident.resolved_at` llegan como texto; el servicio los valida);
  - `IncidentCreatedResponse`, que refleja contracts/http-incidents.openapi.yaml con los `Literal` del dominio.
- [X] T030 [US1] Agregar en src/adapters/inbound/api/app.py:
  - **Ruta**: `POST /api/v1/incidents` con `status_code=201`, que traduce a `CreateIncidentInput`, llama a `create_incident` y devuelve `creation_to_contract`.
  - **Errores**: manejador de `IncidentIdConflictError` → `409 incident_id_conflict`; los campos reservados de la creación (`severity`, `component`, `recommended_team`, `action`, `duplicate_group_key`) → `400 reserved_field`, solo para esta ruta, para no cambiar los códigos de `POST /v1/triage`.
  - **Traza** (FR-021): solo identificador, `is_duplicate`, número de duplicados, duración y estado.
- [X] T031 [US1] Agregar el subcomando `create` en src/adapters/inbound/cli.py según contracts/cli-create-sla.md:
  - opciones `--title`, `--raw-text`, `--incident-id`, `--created-at`, `--status`, `--resolved-at` y `--format`;
  - servicio desde `_build_service(service_factory, None)`;
  - `ValidationError` e `IncidentIdConflictError` → código `1`; excepción inesperada → `4`;
  - JSON con `creation_to_contract` y `ensure_ascii=False`;
  - tabla con identificador, severidad, componente, equipo y clave;
  - docstring del módulo actualizada.

**Punto de control**: US1 funcional y comprobable sola por HTTP y CLI; ⭐E1 y el resto de
escenarios de US1 en verde.

---

## Fase 4: Historia 2 — Enterarse de que ya existe un duplicado abierto (Prioridad: 2)

**Objetivo**: la creación devuelve `is_duplicate` y `duplicate_of` con los abiertos de la
misma clave, sin tocarlos.

**Prueba independiente**: con incidentes abiertos y resueltos sembrados, solo los abiertos
con clave coincidente aparecen en `duplicate_of`, y los sembrados no cambian. ⭐E5, E6, E8,
E22 y E23 en verde.

### Pruebas de la Historia 2 (escribir primero; deben fallar)

- [X] T032 [US2] ⭐ Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e5_duplicado_abierto_ignora_resueltos`, con `TestClient`:
  - **Siembra**: `INC-0000A001` abierto y `INC-0000A002` `RESOLVED` (con `resolved_at`), ambos de caída de la pasarela de pagos y con clave derivada del dominio.
  - **Creación**: un incidente nuevo por otra caída de la pasarela de pagos.
  - **Verifica**: `201`; `is_duplicate` = `true`; `duplicate_of` = `["INC-0000A001"]`; los dos sembrados iguales según `get_incident`.
- [X] T033 [US2] Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e6_…` (parametrizado E6.1–E6.4), `test_bdd_e22_…` (abierto de hace tres días y texto "Otra vez se cayó la pasarela de pagos") y `test_bdd_e23_…` (primer incidente creado en `RESOLVED`)
- [X] T034 [US2] Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e8_…`: dos `create_incident` concurrentes en hilos sobre el mismo `SQLiteIncidentRepository` en `tmp_path`, con identificadores distintos; al menos uno lista al otro en `duplicate_of`

### Implementación de la Historia 2

- [X] T035 [US2] Completar `IncidentService.create_incident` en src/application/services.py con el paso 6 de data-model.md §2 (research.md §R5):
  - después de `add_incident`, si data-model.md `Incident.duplicate_group_key` no es `None`, `duplicate_of` son los identificadores de `find_open_duplicates(clave, incident.incident_id)`, en el orden del puerto;
  - si la clave es `None`, `duplicate_of` queda en `()`.
- [X] T036 [P] [US2] Cambiar `seed_demo_incidents` en src/adapters/outbound/demo_incidents.py para derivar data-model.md `Incident.duplicate_group_key` y data-model.md `Incident.recommended_team` de cada demo con `classify_incident` sobre su título (research.md §R9), conservando severidad, componente, estado e instantes de las constantes
- [X] T037 [US2] Agregar a la tabla de `create` en src/adapters/inbound/cli.py la línea `AVISO: duplica incidentes abiertos: …` en `stdout` cuando `is_duplicate` es verdadero (contracts/cli-create-sla.md)

**Punto de control**: US1 y US2 funcionan cada una por separado; la demo en memoria señala
`INC-2001` al crear una caída de pagos (quickstart.md §4).

---

## Fase 5: Historia 3 — Auditar cómo va el SLA de un incidente (Prioridad: 3)

**Objetivo**: `GET /api/v1/incidents/{incident_id}/sla` y `sla <id>` devuelven la
evaluación canónica en cualquier instante, reconstruyendo el estado antes de la
resolución, con paridad entre canales.

**Prueba independiente**: con incidentes sembrados por `save_incident` (sin necesidad de
`create`), la auditoría en varios instantes coincide con la evaluación canónica por ambos
canales. ⭐E11.2, ⭐E12, ⭐E13, ⭐E14, E9, E10 y E16 en verde. ⭐E11.1 y E2 (reinicio)
necesitan además `create` (US1).

### Pruebas de la Historia 3 (escribir primero; deben fallar)

- [X] T038 [US3] ⭐ Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e12_sla_habil_determinista`, con `TestClient`:
  - **Siembra**: un P2 abierto creado 2026-11-06T17:00.
  - **Consulta**: `reference_time=2026-11-09T09:00:00`.
  - **Verifica**: `200`; `elapsed_minutes` = `120`; `allowed_minutes` = `480`; `remaining_minutes` = `360`; `is_breached` = `false`; `requires_escalation` = `false`.
- [X] T039 [US3] ⭐ Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e13_auditoria_incidente_inexistente`: `INC-FFFFFFFF` → HTTP `404 incident_not_found`; CLI código `1`, diagnóstico en `stderr` y `stdout` vacío
- [X] T040 [US3] ⭐ Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e14_auditoria_antes_de_la_creacion`: creado a las 09:00 y consultado a las 08:59 → HTTP `422 reference_before_creation`; CLI código `1`; sin evaluación
- [X] T041 [US3] ⭐ Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e11_paridad_cli_create_y_sla`, parametrizado:
  - **E11.1**: `create` de `INC-CLIENTE-02`. Devuelve `201` y código `0`.
  - **E11.2**: `sla` con instante fijo. Devuelve `200` y código `0`.

  Ambos se ejecutan sobre dos almacenes `tmp_path` equivalentes (con un abierto de pagos sembrado) y el mismo reloj. El cuerpo HTTP debe ser igual a `json.loads(stdout)` del CLI, y `stderr` debe estar vacío.
- [X] T042 [US3] Escribir en tests/test_spec_003_lifecycle_sla.py `test_bdd_e2_…` (se crea un incidente por `POST /api/v1/incidents` sobre un `SQLiteIncidentRepository` en un archivo de `tmp_path`; se cierra y se abre otro sobre el mismo archivo; la auditoría devuelve el mismo título, componente, severidad, estado e instante de creación que la creación), `test_bdd_e9_…` (P0 a los 50 minutos: 50/60/10, escalamiento sí), `test_bdd_e10_…` (parametrizado E10.1 a las 11:30: 210, sin incumplir, con escalamiento, no resuelto; E10.2 a las 14:00: 300, incumplido, sin escalamiento, resuelto) y `test_bdd_e16_…` (auditorías repetidas no cambian `get_incident`; `caplog` sin títulos)

### Implementación de la Historia 3

- [X] T043 [P] [US3] Cambiar `evaluate_sla_status` en src/domain/sla_calculator.py según research.md §R2 y data-model.md §1 `SLAEvaluation`:
  - **Normalización**: aplicar `to_bogota` a data-model.md `Incident.created_at`, `Incident.resolved_at` y el instante de referencia.
  - **Resolución en el instante**: calcular data-model.md `SLAEvaluation.resolved_at_reference`.
  - **Minutos**: medir data-model.md `SLAEvaluation.elapsed_minutes` hasta el menor entre la referencia y la resolución; data-model.md `SLAEvaluation.allowed_minutes` sigue saliendo de `SLA_POLICY_TABLE`, sin cambio; derivar data-model.md `SLAEvaluation.remaining_minutes` y `SLAEvaluation.is_breached`.
  - **Escalamiento**: calcular data-model.md `SLAEvaluation.requires_escalation` según el estado en el instante, no según `status`.
  - **Error**: conservar el `ValueError` si la referencia es anterior a la creación.
- [X] T044 [US3] Agregar a `_run_demo()` en src/sla_calculator.py los casos E10.1 y E10.2 (P1 creado 08:00 y resuelto 13:00; referencias 11:30 y 14:00), extendiendo `SLATestCase` con `resolved_at` opcional, y confirmar 12 aserciones en verde y la suite de spec 002 sin cambios (Art. 1.12)
- [X] T045 [US3] Agregar a src/application/services.py `IncidentNotFoundError(incident_id)`, `IncidentSLAAudit` e `IncidentService.evaluate_incident_sla(incident_id, reference_time)` según data-model.md §2, pasos 1–5: instante truncado a segundos en Bogotá y `ValidationError("reference_before_creation", …, "reference_time")` si es anterior a data-model.md `Incident.created_at`
- [X] T046 [US3] Agregar `sla_audit_to_contract` a src/application/services.py según data-model.md §4 (instantes como cadena ISO con desfase)
- [X] T047 [P] [US3] Agregar a src/adapters/inbound/api/schemas.py `SLAQueryParams` (`reference_time: Optional[StrictStr]`, `extra="forbid"`) y `SLAEvaluationResponse` según contracts/http-incidents.openapi.yaml
- [X] T048 [US3] Agregar en src/adapters/inbound/api/app.py:
  - **Ruta**: `GET /api/v1/incidents/{incident_id}/sla` con `Annotated[SLAQueryParams, Query()]`, `parse_instant`, `evaluate_incident_sla` y `sla_audit_to_contract`.
  - **Errores**: manejador de `IncidentNotFoundError` → `404 incident_not_found`.
  - **Traza**: solo identificador, duración y estado.
  - **Documentación**: `responses` 400/404/405/422/500.
- [X] T049 [US3] Agregar el subcomando `sla` en src/adapters/inbound/cli.py según contracts/cli-create-sla.md:
  - argumento posicional `INCIDENT_ID`, `--reference-time` y `--format`;
  - `ValidationError` e `IncidentNotFoundError` → código `1`; excepción inesperada → `4`;
  - JSON con `sla_audit_to_contract`;
  - tabla con minutos, límite, restantes, `sí`/`no` y estado en el instante.

**Punto de control**: las tres historias funcionan; los seis ⭐ y E1–E23 (sin E7) en verde.

---

## Fase 6: Pulido y aspectos transversales

**Propósito**: rendimiento, documentación y verificación final.

- [X] T050 Escribir en tests/test_spec_003_lifecycle_sla.py la prueba SC-006 por canal:
  - sembrar 10 000 abiertos con `save_incident` en `SQLiteIncidentRepository` sobre `tmp_path`;
  - medir un `create` con búsqueda de duplicados y una auditoría, por `TestClient` y por `CliRunner`;
  - exigir < 1 s en cada caso, en proceso.
- [X] T051 [P] Completar AGENTS.md con el mapa de código de H003: `create_incident`, `evaluate_incident_sla`, `id_generator.py`, columnas e índice `idx_incidents_dup_key`, migración aditiva, gotcha de persistencia del CLI con `:memory:` y el riesgo residual de research.md §R5
- [X] T052 [P] Agregar a README.md los comandos de creación y auditoría por HTTP y CLI de quickstart.md §4–§5
- [X] T053 [P] Actualizar la línea **Estado** de specs/003-incident-lifecycle-sla/spec.md a implementada y confirmar que specs/003-incident-lifecycle-sla/checklists/requirements.md sigue vigente
- [X] T054 Ejecutar la validación completa de quickstart.md §2–§7 en el orden de la Constitución y corregir cualquier desviación:
  1. Ruff;
  2. pytest;
  3. `_run_demo` con 12 aserciones;
  4. auditoría de triaje con salida idéntica;
  5. recorrido HTTP;
  6. recorrido CLI con `DATABASE_URL` de archivo.
- [X] T055 Revisar el criterio de terminado F4 (a–f) de .specify/memory/constitution.md y el Art. 3.6 de docs/constitution.md contra el cambio completo antes del commit final

---

## Dependencias y orden de ejecución

### Dependencias entre fases

- **Fase 1 (T001–T007)**: sin dependencias. T003 necesita T001 y T002; T005 necesita T004 para cambiar aserciones. Commit propio.
- **Fase 2 (T008–T019)**:
  - T008 y T009 pueden empezar en paralelo con la Fase 1, porque son dominio puro.
  - T010–T019 dependen de T007.
  - La fase bloquea todas las historias.
- **US1 (Fase 3)**: depende de la Fase 2.
- **US2 (Fase 4)**: depende de la Fase 2 y de T027 (`create_incident`), T030 (ruta POST) y T025 (`classify_incident`, también para la siembra de T036).
- **US3 (Fase 5)**: depende de la Fase 2. Sus pruebas siembran con `save_incident` y no necesitan US1, salvo ⭐E11.1 y E2, que usan T030 (y T031 en E11.1).
- **Pulido (Fase 6)**: depende de las historias que se entreguen.

### Dependencias dentro de la Fase 2

T008 → T009. T007 → T010 → (T011, T015, T016 en paralelo) → T012 → T013 → T014 → T017 →
T018 → T019.

### Dentro de cada historia

- Pruebas primero y en rojo; luego dominio, servicio y proyección; después los canales.
- Todas las pruebas de H003 viven en tests/test_spec_003_lifecycle_sla.py: las tareas de
  prueba no se paralelizan entre sí.
- src/application/services.py concentra T017, T027, T028, T035, T045 y T046, así que esas tareas van en serie.
- src/adapters/inbound/cli.py concentra T005, T031, T037 y T049; src/adapters/inbound/api/app.py concentra T030 y T048. Cada grupo va en serie.

### Oportunidades de paralelismo

- **Fase 1**: T002 y T004 en paralelo tras T001; T003 espera a T001 y T002 porque toca
  los mismos archivos.
- **Fase 2**:
  - T008 en paralelo con toda la Fase 1;
  - T011, T015 y T016 en paralelo tras T010.
- **US1**: T025 (triage_rules.py) y T029 (schemas.py) en paralelo con T027–T028 (services.py).
- **US2**: T036 (demo_incidents.py) en paralelo con T035 (services.py).
- **US3**:
  - T043 (sla_calculator.py del dominio) y T047 (schemas.py) en paralelo con T045–T046 (services.py);
  - T043 puede adelantarse incluso a la Fase 2, porque solo depende de T008.
- **Pulido**: T051, T052 y T053 en paralelo.

---

## Ejemplo de paralelismo por historia

```text
# US1, tras escribir T020–T024 en rojo:
Tarea: "T025 group_key_for y classify_incident en src/domain/triage_rules.py"
Tarea: "T029 CreateIncidentRequest e IncidentCreatedResponse en src/adapters/inbound/api/schemas.py"
Tarea: "T027 CreateIncidentInput, IncidentCreation y create_incident en src/application/services.py"

# US2, tras escribir T032–T034 en rojo:
Tarea: "T035 paso 6 de create_incident en src/application/services.py"
Tarea: "T036 siembra derivada en src/adapters/outbound/demo_incidents.py"

# US3, tras escribir T038–T042 en rojo:
Tarea: "T043 reconstrucción del SLA en src/domain/sla_calculator.py"
Tarea: "T047 SLAQueryParams y SLAEvaluationResponse en src/adapters/inbound/api/schemas.py"
Tarea: "T045 evaluate_incident_sla en src/application/services.py"
```

---

## Estrategia de implementación

### MVP (solo US1)

1. Fase 1 (enmienda, commit propio) y Fase 2 (fundamentos).
2. Fase 3: US1.
3. **Parar y validar**: ⭐E1 y el resto de US1 en verde; `create` persiste entre
   procesos con `DATABASE_URL` de archivo (quickstart.md §5).

### Primer incremento pedido (los cinco comportamientos ⭐)

Si se prioriza demostrar los cinco comportamientos pedidos antes de la cobertura
completa, el orden es:

1. Fases 1 y 2.
2. **Escenarios ⭐** (pruebas en rojo), junto con la implementación que cada uno necesita:
   - ⭐E1 (T020) con T025 y T027–T031;
   - ⭐E5 (T032) con T035;
   - ⭐E12, ⭐E13 y ⭐E14 (T038–T040) con T043–T049;
   - ⭐E11 (T041).
3. Validar con:
   `uv run python -X utf8 -m pytest -v tests/test_spec_003_lifecycle_sla.py -k "e1_ or e5_ or e11_ or e12_ or e13_ or e14_"`.
4. Completar después T021–T024, T026, T033–T034, T036–T037, T042, T044 y la Fase 6.

La capacidad **no** está terminada (F4, Principio V.2) hasta que todos los escenarios
aceptados tengan su prueba en verde.

### Entrega incremental

1. Preparación y fundamentos: la base está lista y H001/H002 siguen intactos.
2. US1: se crean incidentes persistentes (MVP).
3. US2: aviso de duplicados.
4. US3: auditoría de SLA con reconstrucción y paridad.
5. Pulido: SC-006, documentación y verificación F4.

Cada historia agrega valor sin romper las anteriores.

---

## Notas

- [P] = archivos distintos y sin dependencias pendientes.
- [USn] mapea la tarea a su historia para la trazabilidad.
- ⭐ = escenario pedido explícitamente (primer incremento de pruebas).
- Verificar que las pruebas fallan antes de implementar.
- Hacer commit por tarea o por grupo lógico; la Fase 1 siempre en commit propio.
- No relajar aserciones de spec 001 o spec 002 salvo T005 y T012, que siguen a sus
  enmiendas (T004).
- Ninguna regla de triaje, clave de grupo o SLA fuera de src/domain/; los canales solo
  traducen y delegan en `IncidentService`.
