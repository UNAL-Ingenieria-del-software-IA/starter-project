---

description: "Lista de tareas de la feature 004: persistencia PostgreSQL y runtime en contenedores"
---

# Tareas: Persistencia PostgreSQL y runtime en contenedores (H004)

**Entrada**: documentos de diseño en `specs/004-postgres-container-runtime/`.

**Prerrequisitos**: plan.md, spec.md, research.md, data-model.md, contracts/ y quickstart.md.

**Pruebas**: obligatorias. El usuario pidió `tests/test_spec_004_runtime_health.py`, y la
Constitución 5.2 y RNF-011 exigen una prueba automatizada por escenario. Las pruebas se
escriben **antes** que la implementación y deben fallar primero.

**Organización**: por historia de usuario de la spec. US1 es la sonda (P1), US2 la selección
de motor (P2) y US3 el runtime en contenedores (P3).

## Formato: `[ID] [P?] [Historia] Descripción`

- **[P]**: se puede ejecutar en paralelo (archivo distinto, sin dependencias pendientes).
- **[USn]**: historia de usuario a la que pertenece la tarea.
- Las rutas son relativas a la raíz del repositorio (un solo proyecto: `src/`, `tests/`).

## Trazabilidad

| Historia | Escenarios | Requisitos |
|---|---|---|
| US1 — Saber si el servicio puede atender (P1) 🎯 MVP | E1, E2, E3, E4 (doble), E5, E6 | FR-001–FR-007, RNF-002, RNF-006 |
| US2 — Elegir el motor sin tocar el código (P2) | E4 (camino real), E7, E8, E9, E10, E11, E17 (parte rápida) | FR-008–FR-014, FR-019, FR-020, RNF-001, RNF-003, RNF-005, RNF-007, RNF-009 |
| US3 — Levantar el servicio completo desde cero (P3) | E12–E17 | FR-015–FR-018, RNF-003, RNF-004, RNF-008, RNF-010, RNF-011 |

---

## Fase 1: Preparación — gobernanza (bloqueante, commit propio)

**Propósito**: cerrar los gates G17–G20 del plan (D-G1, D-G2, D-G3 y D-G5 de la spec) antes
de tocar código de producción.

**⚠️ T002 necesita la confirmación explícita del usuario en el chat.** Sin ella, ADR-004 no
pasa a «Aceptado» y la Fase 2 no empieza.

- [X] T001 Incorporar a docs/adr/004-persistencia-postgresql-y-runtime-contenedores.md, que sigue en «Propuesto» y por eso se puede editar, la inversión del fallo temprano de ADR-006 para el canal HTTP (D-G5, research.md §R3):
  - en los metadatos, **Reemplaza a**: añadir «ADR-006, parcialmente: la exigencia de que el almacén responda al componer el servicio HTTP»;
  - en §3, el elemento «**Arranque degradado del servicio HTTP.** Con una `DATABASE_URL` de esquema admitido, la API arranca aunque la base no responda. La disponibilidad la informa la sonda `GET /health`, no el arranque. La CLI conserva el fallo temprano salvo en `health`. Esto evita que reiniciar solo `api` con la base detenida provoque un bucle de caídas.»;
  - en §4, el trade-off «"Proceso en marcha" deja de implicar "base disponible". Los consumidores deben mirar la sonda.».
- [X] T002 Cambiar **Estado** a `Aceptado` en docs/adr/004-persistencia-postgresql-y-runtime-contenedores.md **solo tras la confirmación explícita del usuario** (D-G1)
- [X] T003 Enmendar .specify/memory/constitution.md a **Version** 3.2.0 (MINOR) con **Last Amended** de la fecha del cambio (D-G2). Antes, retirar el informe de impacto de la 3.1.0. Después, preparar el informe nuevo, revisarlo y retirarlo antes del commit (Gobernanza, punto 4). Cambios:
  - **F2**: agregar `docker compose up -d --build --wait`, `uv run python -X utf8 -m pytest -v -m postgres` y `uv run python -X utf8 -m pytest -v -m docker`;
  - **F3**: agregar «`GET /health` (`200 {"status":"ok","database":"connected"}` / `503 {"status":"error","database":"unavailable"}`, fuera del sobre común de errores)» y «`health` con `--format table|json`; códigos `0` / `4`», según contracts/http-health.openapi.yaml y contracts/cli-health.md;
  - **5.5**: «10 aserciones» → «12 aserciones» (P1);
  - **Governance**: retirar la desviación de ADR-004 «Propuesto».
- [X] T004 [P] Alinear docs/constitution.md con la 3.2.0 (D-G3):
  - Art. 2.6: sustituir «SQLite de la librería estándar con marcadores `?` … un adaptador alterno para la base dedicada de H004» por «persistencia dual (ADR-004): SQLite con `sqlite3` y PostgreSQL con `psycopg[binary]`, con consultas parametrizadas, instantes como texto ISO 8601 e intercalación `C`»;
  - Art. 3.2: añadir «Excepción vigente: `psycopg[binary]` para el adaptador PostgreSQL (ADR-004)»;
  - «Decisiones que la sustentan»: ADR-004;
  - el ADR de stack queda con número pendiente, ya no ADR-004.
- [X] T005 Ejecutar `uv run ruff check src/` y `uv run python -X utf8 -m pytest -v` en verde y hacer el commit propio de T001–T004 (`docs(governance): ADR-004 aceptado y Constitución 3.2.0 para H004`). En ese commit van también `pyproject.toml` y `uv.lock` con `psycopg[binary]` 3.3.9, que ya están en el árbol de trabajo (research.md §R14).

**Punto de control**: ADR-004 aceptado, F2 y F3 con la sonda y Constitución 3.2.0 adoptada.
Ya no queda ningún gate ❌.

---

## Fase 2: Fundamentos — fronteras, fábrica y composición

**Propósito**: lo que las tres historias necesitan (D-G4, gate G13).

**⚠️ CRÍTICO**: ninguna historia empieza antes de terminar esta fase.

- [X] T006 [P] Agregar `"psycopg".msg = "Art. 1.2: el dominio no accede a persistencia."` a la tabla `banned-api` de src/domain/ruff.toml
- [X] T007 [P] Agregar `"psycopg".msg = "Art. 2.3: la aplicación no conoce drivers; usa IncidentRepositoryPort."` a la tabla `banned-api` de src/application/ruff.toml
- [X] T008 [P] Agregar `"psycopg".msg = "Art. 2.4: un canal no accede a persistencia; llama al caso de uso."` a la tabla `banned-api` de src/adapters/inbound/ruff.toml
- [X] T009 [P] Agregar `"psycopg"` a `FORBIDDEN_ROOTS` y a la comprobación de canales de entrada (`test_canales_de_entrada_no_conocen_persistencia`) en tests/test_arquitectura.py
- [X] T010 [P] Registrar los marcadores `postgres` (necesita `INCIDENTOPS_TEST_POSTGRES_URL`) y `docker` (necesita Docker con Compose v2) en `[tool.pytest.ini_options] markers` de pyproject.toml
- [X] T011 Declarar `StoreUnavailableError(RuntimeError)` en src/application/ports.py, con docstring en español: «el almacén no responde, al componer el servicio o durante una operación» (data-model.md §3 `StoreUnavailableError`, research.md §R6). El `Protocol` del puerto no cambia (research.md §R3).
- [X] T012 Renombrar `create_incident_repository` → `create_repository` en src/adapters/outbound/factory.py, sin alias y por ahora solo con las ramas SQLite (research.md §R7). Actualizar el docstring del módulo y el mensaje de esquema no soportado a `DATABASE_URL no soportada (esquema '<s>'): use sqlite:///:memory:, sqlite:///<ruta> o postgresql://…`.
- [X] T013 Actualizar src/main.py (research.md §R3):
  - importar `create_repository`;
  - `build_repository(database_url=None, *, require_health=True)` lanza `StoreUnavailableError` en lugar de `RuntimeError`;
  - `build_service(now=None, repository=None, id_generator=None, *, require_health=True)`;
  - la `app` perezosa de `__getattr__` se construye con `build_service(require_health=False)` (FR-019);
  - `cli = create_cli(build_service)` no cambia.
- [X] T014 [P] Agregar a tests/doubles.py `ToggleHealthRepository(InMemoryIncidentRepository)`, con un atributo `available: bool` que `check_health()` devuelve y que las pruebas pueden alternar (E3, E5)
- [X] T015 Ejecutar `uv run ruff check src/` y `uv run python -X utf8 -m pytest -v` en verde. Las suites de las specs 001–003 deben seguir igual. Commit `chore(h004): fronteras psycopg, create_repository y require_health`.

**Punto de control**: Ruff veta `psycopg` fuera de `adapters/outbound`, la fábrica tiene su
nombre definitivo y la composición distingue HTTP de CLI.

---

## Fase 3: Historia de usuario 1 — Saber si el servicio puede atender (Prioridad: P1) 🎯 MVP

**Objetivo**: `GET /health` y el subcomando `health` consultan de verdad el almacén y
responden `connected` o `unavailable` con el mismo cuerpo por ambos canales.

**Prueba independiente**: con el almacén por defecto y con `ToggleHealthRepository`, sin
red ni contenedores.

### Pruebas de la historia 1 (escribir primero; deben fallar)

- [ ] T016 [P] [US1] Crear tests/test_spec_004_runtime_health.py con el bloque «US1 — sonda», con `TestClient` sobre `create_app(build_service(...))` y `CliRunner` sobre `create_cli(...)`, según contracts/http-health.openapi.yaml y contracts/cli-health.md:
  - `test_bdd_e1_health_200`: cuerpo exacto `{"status": "ok", "database": "connected"}`; con un doble que cuenta llamadas, comprobar que cada petición invoca `check_health()` (FR-001, sin caché);
  - `test_bdd_e2_cli_health_ok`: `health --format json` → código `0`, mismo JSON, stderr vacío; `--format table` muestra `estado`/`base de datos`;
  - `test_bdd_e3_health_503_con_doble`: `ToggleHealthRepository(available=False)` → `503` con cuerpo exacto `{"status": "error", "database": "unavailable"}`;
  - `test_bdd_e4_cli_health_unavailable_con_doble`: una fábrica que lanza `StoreUnavailableError` → código `4`, cuerpo `unavailable` en stdout y `error [database_unavailable]: …` en stderr;
  - `test_bdd_e5_recuperacion_sin_reinicio`: el mismo `TestClient`; `available=False` → `503`, `available=True` → `200`;
  - `test_bdd_e6_liveness_sin_cambios`: `/v1/health` → `200 {"status": "ok"}` aunque `available=False`;
  - `test_health_metodo_no_permitido`: `POST /health` → `405 method_not_allowed` con el sobre común;
  - `test_rnf006_registro_solo_cambios_de_estado`: con `caplog`, la secuencia ok, ok, ko, ko, ok produce exactamente 4 líneas (primera, ko, ko, recuperación), sin URL (data-model.md §3, máquina de estados);
  - `test_fr004_check_health_que_lanza_es_unavailable`: un doble cuyo `check_health()` lanza → `503`, nunca `500`.

### Implementación de la historia 1

- [ ] T017 [US1] Agregar a src/application/services.py (research.md §R8):
  - `IncidentService.check_health() -> bool`, que delega en el repositorio y convierte cualquier excepción en `False`;
  - la función `health_to_contract(available: bool) -> Dict[str, Any]`, que es la única proyección (data-model.md §3, «cuerpo de contrato»);
  - la docstring del módulo con la nueva proyección.
- [ ] T018 [P] [US1] En src/adapters/inbound/api/schemas.py (research.md §R9):
  - renombrar `HealthResponse` → `LivenessResponse` (`status: str`);
  - crear `HealthResponse` con `status: Literal["ok", "error"]`, `database: Literal["connected", "unavailable"]` y `extra="forbid"`.
- [ ] T019 [US1] En src/adapters/inbound/api/app.py:
  - `/v1/health` pasa a usar `LivenessResponse`;
  - agregar `GET /health` con `response_model=HealthResponse` y `responses={503: …}`. Llama a `service.check_health()`, proyecta con `health_to_contract` y devuelve `JSONResponse` `200`/`503`;
  - agregar el registro de cambios de estado por instancia de `create_app` (estado inicial «desconocido»; `INFO` en cada transición a `connected`; `WARNING` en cada `unavailable`; solo resultado, duración en ms y código; research.md §R8).
- [ ] T020 [US1] Agregar el subcomando `health` a src/adapters/inbound/cli.py, según contracts/cli-health.md:
  - `--format table|json`, con `table` por defecto;
  - construye el servicio y captura `StoreUnavailableError` → cuerpo `unavailable` en stdout, diagnóstico `error [database_unavailable]: el almacén de incidentes no responde.` en stderr y código `4`;
  - con el servicio construido, `check_health()` decide `0`/`4`;
  - la tabla tiene dos líneas (`estado`, `base de datos`);
  - actualizar la docstring del módulo con el comando nuevo.
- [ ] T021 [US1] Ejecutar `uv run ruff check src/` y `uv run python -X utf8 -m pytest -v` (T016 en verde) y hacer el commit `feat(h004): sonda GET /health y subcomando health (US1)`

**Punto de control**: la sonda funciona sobre SQLite y con dobles. MVP entregable.

---

## Fase 4: Historia de usuario 2 — Elegir el motor sin tocar el código (Prioridad: P2)

**Objetivo**: `DATABASE_URL=postgresql://…` selecciona `PostgresIncidentRepository`, que
cumple el puerto con la misma semántica y los mismos JSON que SQLite. Sin variable, todo
sigue en SQLite en memoria.

**Prueba independiente**: los casos rápidos corren sin base. Los casos `postgres` corren
contra `db-test` (FR-020) y se omiten de forma visible sin `INCIDENTOPS_TEST_POSTGRES_URL`.

### Pruebas de la historia 2 (escribir primero; deben fallar)

- [ ] T022 [P] [US2] Agregar a tests/test_spec_004_runtime_health.py el bloque «US2 — selección de motor (rápidas)»:
  - `test_bdd_e7_sin_database_url_usa_memoria`: `monkeypatch.delenv` y también `DATABASE_URL=""` → `summary --reference-time 2026-11-24T09:00:00 --format json` con `INC-2001`…`INC-2008`, y `health` `connected`;
  - `test_bdd_e8_sqlite_archivo`: `create` y `sla` en dos invocaciones con `sqlite:///<tmp_path>`; el archivo no tiene datos de demostración;
  - `test_bdd_e10_esquema_no_soportado`: `mysql://u:secreto@h/db`, `postgres://u:secreto@h/db` y `texto` → CLI código `4`, el mensaje nombra solo el esquema, sin `secreto`;
  - `test_create_repository_conformidad_estructural`: SQLite (`sqlite:///:memory:`) y PostgreSQL (`postgresql://u:p@127.0.0.1:1/db`) exponen los seis métodos con `inspect.signature` igual a `IncidentRepositoryPort`, y construir el de PostgreSQL no lanza (contracts/incident-repository-port.md, «Conformidad estructural»);
  - `test_bdd_e4_camino_real_puerto_muerto`: `DATABASE_URL=postgresql://u:secreto@127.0.0.1:1/db` → `health --format json` con código `4`, cuerpo `unavailable` en ≤ 3 s, sin `secreto` ni la URL en stdout o stderr;
  - `test_bdd_e17_arranque_degradado_rapido`: `create_app(build_service(require_health=False))` con la URL del puerto muerto → `/health` `503` y `/api/v1/incidents/summary` `500 internal_error`, sin la URL en el cuerpo;
  - `test_url_postgres_mal_formada`: una URL que `conninfo_to_dict` rechaza → `ValueError` que no contiene la URL;
  - `test_c11_error_del_driver_no_cruza_el_puerto`: `PostgresIncidentRepository` sobre `postgresql://u:secreto@127.0.0.1:1/db` → `list_active_incidents()` lanza `StoreUnavailableError` (no `psycopg.Error`, sin `__cause__`) en ≤ 3 s, y el mensaje no contiene `secreto` ni la URL (contracts/incident-repository-port.md C11).
- [ ] T023 [P] [US2] Agregar a tests/test_spec_004_runtime_health.py el bloque «US2 — PostgreSQL» con `@pytest.mark.postgres`:
  - fixture `pg_url`: lee `INCIDENTOPS_TEST_POSTGRES_URL` o hace `pytest.skip` con motivo visible; ejecuta `DROP TABLE IF EXISTS incidents, sla_policies` antes de cada prueba (data-model.md §4 `INCIDENTOPS_TEST_POSTGRES_URL`);
  - fixture `repositorio` parametrizado sobre SQLite (`tmp_path`) y PostgreSQL;
  - conformidad C1–C10 de contracts/incident-repository-port.md, incluida C7 con `INC-ABC1`/`INC-abc1` (orden por bytes) y C5 con microsegundos;
  - `test_bdd_e9_postgresql_persiste_entre_procesos`: `POST /api/v1/incidents` con un servicio y `sla` con otro servicio nuevo sobre la misma URL; la base tiene exactamente 8 incidentes de demostración más el creado;
  - `test_bdd_e11_paridad_byte_a_byte`: el mismo conjunto en ambos motores → `summary_to_contract`, `sla_audit_to_contract` y `creation_to_contract` (con duplicado) serializados con `json.dumps(..., ensure_ascii=False)` son idénticos;
  - `test_c10_siembra_unica`: dos adaptadores inicializados en secuencia sobre la misma base vacía → 8 incidentes; una base con un incidente previo → no siembra.
- [ ] T024 [P] [US2] Crear docker-compose.yml con el servicio `db-test` (FR-020, contracts/container-runtime.md):
  - `profiles: ["test"]`;
  - `postgres:16-alpine` y `POSTGRES_INITDB_ARGS="--locale=C --encoding=UTF8"`;
  - `tmpfs` en `/var/lib/postgresql/data`;
  - `ports: "127.0.0.1:${TEST_DB_HOST_PORT:-55432}:5432"` (data-model.md §4 `TEST_DB_HOST_PORT`);
  - chequeo `pg_isready`;
  - credenciales `${POSTGRES_USER:-incidentops}` / `${POSTGRES_PASSWORD:-incidentops}` / `${POSTGRES_DB:-incidentops}`;
  - `name: incidentops` (research.md §R11).

### Implementación de la historia 2

- [ ] T025 [US2] Extraer el mapeo compartido a src/adapters/outbound/row_mapping.py, para que el formato de instantes y el orden de parámetros tengan una sola fuente en ambos motores (FR-012, RNF-001):
  - `instant_to_text(value)`: `to_bogota(...).isoformat(timespec="microseconds")`;
  - `incident_params(incident)`: los nueve valores en el orden del DDL;
  - `text_to_instant(value)`.

  Usarlo en src/adapters/outbound/sqlite_repository.py sin cambiar su comportamiento: la conformidad de las specs 002 y 003 debe seguir en verde.
- [ ] T026 [US2] Crear src/adapters/outbound/postgres_repository.py con las sentencias constantes (marcadores `%s`, sin concatenar SQL) según data-model.md §1:
  - DDL de `sla_policies`: data-model.md `sla_policies.severity`, `sla_policies.max_resolution_minutes` y `sla_policies.operates_24x7`;
  - DDL de `incidents`: data-model.md `incidents.incident_id` (restricción `incidents_pkey`), `incidents.title`, `incidents.component`, `incidents.severity` (FK a `sla_policies`), `incidents.status`, `incidents.created_at`, `incidents.resolved_at`, `incidents.recommended_team` e `incidents.duplicate_group_key`, todos `TEXT COLLATE "C"` salvo los enteros;
  - los dos índices parciales de data-model.md §1 «Índices»;
  - *upsert* de políticas;
  - `_UPSERT_INCIDENT_SQL` (`INSERT … ON CONFLICT (incident_id) DO UPDATE SET … = EXCLUDED.…`);
  - `_INSERT_INCIDENT_SQL` (sin `ON CONFLICT`);
  - `_SEED_INCIDENT_SQL` (`ON CONFLICT (incident_id) DO NOTHING`);
  - las consultas `SELECT_ACTIVE_SQL`, `SELECT_ACTIVE_BY_COMPONENT_SQL` y `SELECT_OPEN_DUPLICATES_SQL`, con `INNER JOIN sla_policies` y el mismo `ORDER BY` que en SQLite;
  - el candado consultivo con clave entera constante.

  Docstring del módulo en español con las referencias a ADR-004 y a la Constitución 2.6 y T3.
- [ ] T027 [US2] Implementar en src/adapters/outbound/postgres_repository.py la clase `PostgresIncidentRepository(database_url, *, seed_if_empty=())`, con la conexión de research.md §R1:
  - el constructor no abre red;
  - conexión principal perezosa con `autocommit=True`, `row_factory=dict_row`, `connect_timeout=2`, `tcp_user_timeout=2000` y `options="-c statement_timeout=2000"`, protegida por un `threading.Lock`;
  - se descarta ante `OperationalError`, `InterfaceError` o conexión rota, y se lanza `StoreUnavailableError` `from None` (research.md §R6);
  - `close()` y `vacuum_analyze()` quedan fuera del puerto.
- [ ] T028 [US2] Implementar la inicialización única por proceso en src/adapters/outbound/postgres_repository.py (research.md §R4–R5, data-model.md §1 «Inicialización»), en una sola transacción:
  - `pg_advisory_xact_lock`;
  - DDL;
  - *upsert* de `sla_policies` desde `SLA_POLICY_TABLE`;
  - `SELECT EXISTS (SELECT 1 FROM incidents)`;
  - si no hay incidentes, siembra `seed_if_empty` con `_SEED_INCIDENT_SQL`;
  - por último, `self._initialized = True`.
- [ ] T029 [US2] Implementar los métodos del puerto en src/adapters/outbound/postgres_repository.py (data-model.md §2, research.md §R6):
  - `save_incident` y `add_incident` validan la severidad con `get_sla_rule_for_severity` antes de ir a la base;
  - `UniqueViolation` sobre `incidents_pkey` → `IncidentIdConflictError`;
  - otra violación de integridad → `ValueError` sin el mensaje del driver;
  - `get_incident` y `find_open_duplicates` mapean filas `dict_row` con row_mapping.py;
  - `list_active_incidents` recorre `cursor.stream()` dentro del candado, sin `fetchall()` (Constitución 2.6, ADR-001, research.md §R1), y mapea cada fila activa sin `resolved_at`, como en SQLite;
  - todas llaman antes a la inicialización si falta;
  - ninguna excepción de `psycopg` sale de los métodos del puerto (Constitución 3.3, contracts/incident-repository-port.md C11).
- [ ] T030 [US2] Implementar `check_health()` en src/adapters/outbound/postgres_repository.py según research.md §R2:
  - abre una conexión efímera con los mismos límites y ejecuta `SELECT 1`;
  - si falta, ejecuta la inicialización;
  - devuelve `True` solo si ambas tienen éxito;
  - cualquier `psycopg.Error` u `OSError` → `False`; nunca lanza.
- [ ] T031 [US2] Agregar la rama `postgresql://` a `create_repository` en src/adapters/outbound/factory.py (research.md §R7, data-model.md §4 `DATABASE_URL`):
  - importación perezosa de `postgres_repository`;
  - validación sin red con `psycopg.conninfo.conninfo_to_dict`; si falla, `ValueError("DATABASE_URL de PostgreSQL mal formada (esquema 'postgresql').")` `from None`;
  - `PostgresIncidentRepository(url, seed_if_empty=DEMO_INCIDENTS)`;
  - `postgres://` se sigue rechazando.
- [ ] T032 [US2] Agregar `--database-url` a src/incident_repository.py (research.md §R13). Si se indica, compone con `create_repository`, y sobre PostgreSQL llama a `vacuum_analyze()` antes de medir. Si no, sigue con SQLite como hoy. Sin SQL en el arnés.
- [ ] T033 [US2] Verificar:
  - pruebas rápidas: `uv run ruff check src/` y `uv run python -X utf8 -m pytest -v` (los casos `postgres` aparecen SKIPPED con motivo);
  - pruebas contra PostgreSQL: `docker compose --profile test up -d --wait db-test` y `INCIDENTOPS_TEST_POSTGRES_URL=…` → `uv run python -X utf8 -m pytest -v -m postgres` en verde;
  - SC-005: `uv run python -X utf8 -m src.incident_repository --database-url … --records 20000 --iterations 20` con promedio < 1 s;
  - `docker compose --profile test down -v`;
  - commit `feat(h004): adaptador PostgreSQL y selección por DATABASE_URL (US2)`.

**Punto de control**: dos motores con paridad verificada. El desarrollo sin contenedores
sigue intacto.

---

## Fase 5: Historia de usuario 3 — Levantar el servicio completo desde cero (Prioridad: P3)

**Objetivo**: con una sola orden se levantan `db` y `api`. La API arranca cuando la base está
sana, los datos sobreviven a los reinicios y la exposición es mínima.

**Prueba independiente**: pruebas `@pytest.mark.docker` sobre proyectos de composición
aislados, que se omiten de forma visible sin Docker.

### Pruebas de la historia 3 (escribir primero; deben fallar)

- [ ] T034 [P] [US3] Agregar a tests/test_spec_004_runtime_health.py el bloque «US3 — estructura Docker (rápidas)», con aserciones de texto y sin `pyyaml` (research.md §R12, contracts/container-runtime.md):
  - en Dockerfile: `FROM python:3.12-slim`, `ghcr.io/astral-sh/uv:0.13.8`, `uv sync --frozen --no-dev --no-install-project`, un `USER` distinto de `root`, `--host 0.0.0.0` y `PYTHONUTF8=1`;
  - en .dockerignore: cada entrada del contrato;
  - en docker-compose.yml:
    - `postgres:16-alpine`, `pg_isready`, `--locale=C`, el volumen `pgdata`;
    - el bloque de `db` sin `ports`;
    - `condition: service_healthy` y `/health` en el chequeo de `api`;
    - `127.0.0.1:` en todo `ports`;
    - `profiles` con `test` en `db-test`;
    - `DATABASE_URL` con el host `db`;
    - sin contraseñas fuera de `${…:-…}`.
- [ ] T035 [P] [US3] Agregar a tests/test_spec_004_runtime_health.py el bloque «US3 — contenedores» con `@pytest.mark.docker` (RNF-011):
  - fixture `compose_project`: se omite si `docker info` falla; usa `-p incidentops-t<uuid8>` y un `API_HOST_PORT` libre; hace `down -v` en `finally`;
  - `test_compose_config_valida`: `docker compose config --format json`, comprobando servicios, perfiles, puertos y volúmenes;
  - `test_bdd_e12_entorno_nuevo`: `up -d --build --wait`; `db` sano antes que `api`; `/health` `200`; resumen con `INC-2001`…`INC-2008`;
  - `test_bdd_e13_persistencia_tras_reinicio`: crear un incidente, `stop`, `up -d --wait`; el incidente sigue y los datos de demostración no se duplican;
  - `test_bdd_e14_caida_de_la_base`: `stop db`; `/health` `503` y `api` `unhealthy` en ≤ 60 s; `start db`; `healthy` en ≤ 60 s, sin reinicio (el `StartedAt` no cambia);
  - `test_bdd_e15_exposicion_minima`: `port api 8080` → `127.0.0.1:…`; `port db 5432` falla;
  - `test_bdd_e16_imagen_limpia`: en el contenedor, `id -u` ≠ 0, `import pytest` falla y `/app` no contiene `.git`, `.venv` del host, `tests`, `.env` ni `.claude`/`.opencode`/`.specify`;
  - `test_bdd_e17_arranque_degradado`: `up -d --no-deps api` con `db` detenida → `/health` `503`; `up -d --wait db` → `/health` `200` y datos de demostración presentes una sola vez.

### Implementación de la historia 3

- [ ] T036 [P] [US3] Crear el Dockerfile según research.md §R10 y contracts/container-runtime.md, con comentarios en español:
  - `python:3.12-slim`;
  - `uv` de `ghcr.io/astral-sh/uv:0.13.8`;
  - `UV_PYTHON_DOWNLOADS=never`, `UV_PROJECT_ENVIRONMENT=/app/.venv`, `UV_COMPILE_BYTECODE=1`, `UV_LINK_MODE=copy` y `PYTHONUTF8=1`;
  - copiar `pyproject.toml`, `uv.lock` y `README.md`, y ejecutar `uv sync --frozen --no-dev --no-install-project`;
  - copiar `src/`;
  - usuario de sistema con UID fijo y `USER`;
  - `PATH` con `/app/.venv/bin`;
  - `EXPOSE 8080`;
  - `CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]`.
- [ ] T037 [P] [US3] Crear .dockerignore con las exclusiones de contracts/container-runtime.md
- [ ] T038 [US3] Agregar a docker-compose.yml los servicios `db` y `api` y el volumen `pgdata`, según research.md §R11 y contracts/container-runtime.md (data-model.md §4 `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` y `API_HOST_PORT`):
  - `db`:
    - `postgres:16-alpine` e `initdb --locale=C --encoding=UTF8`;
    - volumen `pgdata`;
    - `pg_isready` cada `5s` / `3s` / `10` / `start_period 10s`;
    - `restart: unless-stopped`;
    - sin `ports`.
  - `api`:
    - `build: .`;
    - `DATABASE_URL` hacia `db`;
    - `depends_on` con `service_healthy`;
    - `127.0.0.1:${API_HOST_PORT:-8080}:8080`;
    - chequeo con Python y `urllib` contra `/health`, cada `10s` / `5s` / `3` / `start_period 15s` (≤ 60 s, RNF-008);
    - `restart: unless-stopped`.
- [ ] T039 [US3] Verificar:
  - `uv run python -X utf8 -m pytest -v` (estructura en verde; `docker` SKIPPED sin Docker);
  - `uv run python -X utf8 -m pytest -v -m docker` en verde;
  - el nivel 3 de quickstart.md a mano;
  - commit `feat(h004): runtime en contenedores api + db (US3)`.

**Punto de control**: entorno nuevo operativo sin pasos manuales y H004 funcionalmente
completo.

---

## Fase 6: Pulido y documentación operativa

**Propósito**: criterio de terminado F4 (f) y coherencia documental.

- [ ] T040 [P] Actualizar AGENTS.md:
  - dependencia `psycopg[binary]`;
  - `DATABASE_URL` con `postgresql://`, sembrado si está vacía;
  - `create_repository` en el mapa;
  - `postgres_repository.py`, `row_mapping.py` y `StoreUnavailableError`;
  - `GET /health` y `health` en los comandos;
  - arranque degradado HTTP;
  - comandos de composición y marcadores `postgres`/`docker`;
  - la desviación de gobernanza del stack, con número pendiente en lugar de ADR-004.
- [ ] T041 [P] Agregar a README.md una sección breve de H004 (runtime en contenedores y sonda) que remita a specs/004-postgres-container-runtime/quickstart.md
- [ ] T042 [P] Corregir en specs/002-active-incident-summary/quickstart.md el ejemplo `DATABASE_URL="postgresql://x"`, que ya no es un esquema no soportado: usar `mysql://x`
- [ ] T043 [P] Agregar en los metadatos de docs/adr/001-optimizacion-consulta-incidentes.md, y en ningún otro lugar, la línea «Reemplazado parcialmente por: ADR-004 (motor único `sqlite3`)», sin tocar su razonamiento (Art. 3.7, skill adr-writer)
- [ ] T044 Actualizar la línea **Estado** de specs/004-postgres-container-runtime/spec.md a «Implementada (fecha)» y retirar el bloqueo de gobernanza
- [ ] T045 Verificación completa F4:
  - `uv run ruff check src/`;
  - `uv run python -X utf8 -m pytest -v`;
  - `uv run python -X utf8 -m src.sla_calculator`;
  - `uv run python -X utf8 -m src.triage_rules`, con salida sin cambios;
  - `-m postgres` y `-m docker` en verde;
  - quickstart.md niveles 1 a 3.

  Commit `docs(h004): AGENTS, README y cierre de tareas`.

---

## Dependencias y orden de ejecución

### Dependencias entre fases

- **Fase 1 (gobernanza)**: sin dependencias. T002 espera la confirmación del usuario.
  **Bloquea todo lo demás.**
- **Fase 2 (fundamentos)**: depende de la Fase 1 y bloquea todas las historias.
- **Fase 3 (US1)**: depende de la Fase 2.
- **Fase 4 (US2)**: depende de la Fase 2. Sus pruebas E4 (camino real) y E17 (rápida) usan
  la sonda de US1, así que en la práctica va después de US1.
- **Fase 5 (US3)**: depende de US2 (adaptador PostgreSQL y `db-test` en el mismo
  docker-compose.yml) y de US1 (el chequeo de `api` usa `/health`).
- **Fase 6**: depende de las historias que se entreguen.

### Dentro de cada historia

- Las pruebas se escriben primero y deben fallar.
- Orden: aplicación → esquemas → rutas/CLI (US1), mapeo → SQL → conexión → métodos →
  fábrica (US2), imagen → composición (US3).
- Cada historia cierra con su verificación y su commit.

### Secuencias obligatorias por archivo

- tests/test_spec_004_runtime_health.py: T016 → T022/T023 → T034/T035. Son bloques
  distintos del mismo archivo: si se paralelizan, hay que integrarlos con cuidado.
- src/adapters/outbound/postgres_repository.py: T026 → T027 → T028 → T029 → T030.
- src/adapters/outbound/factory.py: T012 → T031.
- docker-compose.yml: T024 → T038.
- src/main.py: solo T013.

---

## Ejemplos de paralelismo

```text
# Fase 2, con la Fase 1 cerrada:
T006 src/domain/ruff.toml · T007 src/application/ruff.toml · T008 src/adapters/inbound/ruff.toml
T009 tests/test_arquitectura.py · T010 pyproject.toml · T014 tests/doubles.py

# US1:
T016 (pruebas) en paralelo con T018 (esquemas); después T017 → T019 → T020

# US2:
T022 / T023 (pruebas) en paralelo con T024 (db-test) y T025 (row_mapping)

# US3:
T034 / T035 (pruebas) en paralelo con T036 (Dockerfile) y T037 (.dockerignore); después T038
```

---

## Estrategia de implementación

### MVP primero (solo US1)

1. Fase 1: gobernanza (incluida la confirmación del usuario en T002).
2. Fase 2: fundamentos.
3. Fase 3: US1. **Parar y validar**: la sonda responde por HTTP y CLI sobre SQLite.

### Entrega incremental

1. US1 → sonda operativa (MVP).
2. US2 → PostgreSQL disponible por `DATABASE_URL`, con paridad verificada.
3. US3 → runtime reproducible en contenedores, que cierra H004.

Cada incremento tiene su commit y deja las specs 001–003 en verde.

## Notas

- `[P]` = archivo distinto y sin dependencias pendientes.
- No relajar aserciones de specs previas (Art. 5.6). Si una cambia, la spec se enmienda
  primero.
- `psycopg` solo se importa en src/adapters/outbound/postgres_repository.py,
  src/adapters/outbound/factory.py (de forma perezosa, para `conninfo`) y tests/.
- Nunca imprimir ni registrar `DATABASE_URL`. Las pruebas comprueban que no se filtra
  `secreto`.
