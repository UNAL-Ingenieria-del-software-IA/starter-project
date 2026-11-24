# Investigación (Fase 0): Persistencia PostgreSQL y runtime en contenedores (H004)

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Fecha**: 2026-11-24

Cada sección resuelve una incógnita del contexto técnico con el formato Decisión /
Justificación / Alternativas. Ninguna queda como `NEEDS CLARIFICATION`.

---

## R1. Gestión de la conexión PostgreSQL

**Decisión**:

- `PostgresIncidentRepository` abre **una conexión principal**, en modo `autocommit=True`
  y con `row_factory=dict_row`, protegida por un `threading.Lock`. Es el mismo modelo que
  el adaptador SQLite.
- La conexión es **perezosa**: el constructor no abre red. Solo valida la URL (R7).
- La conexión se abre en la primera operación. Si una operación falla con
  `psycopg.OperationalError` o la conexión está rota (`conn.broken` o `conn.closed`), el
  adaptador la cierra, la descarta y lanza `StoreUnavailableError` sin encadenar la causa
  (`from None`), como exige la Constitución 3.3. La siguiente operación vuelve a conectar.
- Las escrituras de varias sentencias (esquema, siembra) usan `with conn.transaction():`.
- La lectura de activos (ADR-001, Constitución 2.6) usa `cursor.stream(sql, params)`: el
  servidor envía las filas de una en una y cada una se mapea a `Incident` sin acumular el
  resultado crudo. El recorrido ocurre dentro del candado y devuelve una lista ya
  construida, igual que en SQLite.
- La conexión principal usa los mismos límites que la sonda (R2): `connect_timeout=2`,
  `tcp_user_timeout=2000` y `statement_timeout` de 2 s. Así una red colgada no bloquea una
  operación de negocio de forma indefinida.

**Justificación**:

- El modo perezoso es lo que permite el arranque degradado (FR-019, R3) y que la
  conformidad estructural del puerto se pruebe sin base.
- Descartar la conexión ante un error de red da la recuperación sin reinicio (FR-014,
  RNF-008).
- `autocommit=True` evita transacciones implícitas abiertas que quedarían en estado
  `INERROR` tras un fallo.
- El candado reproduce la semántica ya medida del adaptador SQLite. FastAPI atiende las
  rutas síncronas en un pool de hilos.

**Alternativas descartadas**:

- `psycopg_pool`: es otra dependencia, así que exige un ADR propio (Constitución T3/T5,
  ADR-004).
- Una conexión por operación: añade unos milisegundos de conexión a cada consulta y pone
  en riesgo el objetivo de SC-005.
- Conexión abierta en el constructor: impide el arranque degradado.

---

## R2. Sonda acotada en el tiempo

**Decisión**:

- `check_health()` abre una **conexión dedicada y efímera** para cada sonda, con estos
  parámetros:
  - `connect_timeout=2`;
  - `options="-c statement_timeout=2000"`;
  - `tcp_user_timeout=2000`, que libpq aplica donde el sistema operativo lo soporta
    (Linux, es decir, el contenedor).
- Sobre esa conexión ejecuta `SELECT 1`.
- Si la consulta va bien y el adaptador aún no está inicializado, llama a la inicialización
  (R4, R5) por la conexión principal.
- Devuelve `True` solo si la consulta y la inicialización tuvieron éxito. Cualquier
  `psycopg.Error` o `OSError` devuelve `False`: nunca lanza (contrato del puerto).

**Justificación**:

- Una conexión propia no compite por el candado de la principal. Una consulta de negocio
  lenta no puede retrasar la sonda más allá de los 3 s de RNF-002.
- `connect_timeout` acota el caso «rechazo o red colgada al conectar», `statement_timeout`
  acota la consulta en el servidor y `tcp_user_timeout` acota una red que se cuelga con la
  conexión ya abierta.
- Exigir la inicialización hace que «sano» signifique «listo para atender» (E17): la sonda
  no dice `connected` sobre una base sin esquema.

**Alternativas descartadas**:

- Sondear con la conexión principal: queda sujeta al candado y no se acota sin lógica de
  tiempo propia.
- `pg_isready` desde la aplicación: no comprueba credenciales ni esquema, y la imagen
  `slim` no lo incluye.
- Cachear el resultado: lo prohíbe FR-001.

---

## R3. Arranque degradado (HTTP) frente a fallo temprano (CLI)

**Decisión**:

- `src/application/ports.py` declara `StoreUnavailableError(RuntimeError)`: «el almacén no
  responde, al componer el servicio o durante una operación» (la segunda causa, en R6).
- `src/main.py` cambia así:
  - `build_repository(database_url=None, *, require_health=True)` lanza
    `StoreUnavailableError` (antes `RuntimeError`) si `require_health` y `check_health()`
    es `False`;
  - `build_service(..., *, require_health=True)` lo propaga;
  - la `app` perezosa se construye con `require_health=False` (FR-019).
- La CLI conserva `require_health=True`. Su subcomando `health` captura
  `StoreUnavailableError` al construir el servicio e imprime el cuerpo `unavailable`
  (FR-007). Los demás subcomandos lo convierten en `internal_error`, con código `4`, como
  hoy.
- Un esquema no soportado o una URL mal formada siguen siendo `ValueError` en la fábrica y
  impiden el arranque en ambos canales (FR-013).

**Justificación**:

- La excepción vive en `application`, así que la CLI (inbound) puede capturarla sin
  importar la raíz de composición ni el adaptador (Art. 2.1).
- Distinguirla por tipo, y no por el texto del mensaje, separa «la base no responde» de
  «configuración inválida».
- El `require_health` por canal concreta la clarificación del 2026-11-24 sin ramificar
  dentro de `application`.

**Alternativas descartadas**:

- Una segunda fábrica de servicio para la CLI: añade un parámetro a `create_cli` solo para
  un subcomando.
- Que el adaptador lance un error propio del driver: la CLI tendría que conocer `psycopg`,
  lo que viola T4.

**Gobernanza**: invertir el fallo temprano de ADR-006 en HTTP es la dependencia D-G5. Se
registra en ADR-004 mientras siga «Propuesto» (Fase A del plan).

---

## R4. Esquema PostgreSQL, intercalación e instantes

**Decisión**: se usa un DDL constante, equivalente columna a columna al de SQLite (ver
[data-model.md](data-model.md)):

- Todas las columnas de texto son `TEXT COLLATE "C"`: `incident_id`, `component`,
  `status`, `created_at`, `resolved_at`, `duplicate_group_key`, entre otras.
- `created_at` y `resolved_at` son texto ISO 8601 en hora de Bogotá con microsegundos. Se
  usa el mismo `_to_text` que en SQLite (`to_bogota(value).isoformat(timespec="microseconds")`).
- `sla_policies` es un espejo de `SLA_POLICY_TABLE` y destino de una FK. `operates_24x7`
  es `INTEGER` 0/1, igual que en SQLite.
- Índices parciales idénticos: `idx_incidents_active_component (component, status,
  severity, created_at, incident_id, title) WHERE status <> 'RESOLVED'` e
  `idx_incidents_dup_key (duplicate_group_key, status) WHERE status <> 'RESOLVED' AND
  duplicate_group_key IS NOT NULL`.
- El DDL se ejecuta en una transacción precedida de `SELECT pg_advisory_xact_lock(%s)`, con
  una clave entera constante. Dos procesos que inicializan a la vez se serializan: en
  PostgreSQL, `CREATE TABLE IF NOT EXISTS` concurrente puede fallar con `UniqueViolation`
  sobre `pg_type`.
- No hay migración aditiva: no existen bases PostgreSQL anteriores a H004, así que el DDL
  ya nace con las nueve columnas.
- Además, `db` y `db-test` se inicializan con `POSTGRES_INITDB_ARGS="--locale=C
  --encoding=UTF8"`.

**Justificación**:

- `COLLATE "C"` por columna garantiza la paridad de RNF-001 aunque `DATABASE_URL` apunte a
  una base creada con otra intercalación. La de `initdb` es una segunda línea de defensa
  para cualquier texto sin intercalación explícita.
- El texto con ancho fijo y el mismo desfase hace que `ORDER BY created_at` sea
  cronológico en los dos motores, y la ida y vuelta es idéntica (FR-012). `timestamptz`
  devolvería instantes en la zona de la sesión (ADR-004).

**Alternativas descartadas**:

- Confiar solo en la intercalación de la base: es frágil frente a bases externas.
- `timestamptz`: rompe la paridad (ADR-004).
- `INCLUDE` en el índice: mejora un poco PostgreSQL, pero diverge del índice de ADR-001 sin
  beneficio medido.

---

## R5. Siembra de demostración «si está vacía»

**Decisión**:

- La fábrica construye el adaptador PostgreSQL con `seed_if_empty=DEMO_INCIDENTS`.
- En la inicialización (R4), dentro de la misma transacción con candado consultivo, el
  adaptador ejecuta `SELECT EXISTS (SELECT 1 FROM incidents)`. Si devuelve `false`,
  inserta la semilla con `INSERT … ON CONFLICT (incident_id) DO NOTHING`.
- La inicialización se marca hecha por proceso (`self._initialized`) y no se repite.
- La siembra del almacén en memoria sigue en `src/main.py` (`seed_demo_incidents`, sin
  cambios). Un archivo SQLite no se siembra.

**Justificación**:

- El candado consultivo serializa los arranques simultáneos.
- `DO NOTHING` hace la siembra idempotente aun sin el candado (caso borde de la spec).
- Pasar la semilla por constructor mantiene `demo_incidents` en la misma capa
  (`outbound`) y deja la decisión en la fábrica, que ya distingue los esquemas.

**Alternativas descartadas**:

- Sembrar desde `src/main.py` al arrancar: con la base caída no se puede, y FR-011 pide
  sembrar en la primera conexión correcta.
- Un script SQL en `docker-entrypoint-initdb.d`: duplicaría los datos de demostración
  fuera de Python y no sembraría bases ajenas a la composición.

---

## R6. Traducción de errores del driver

**Decisión**:

| Error de `psycopg` | Traducción |
|---|---|
| `errors.UniqueViolation` con `diag.constraint_name == "incidents_pkey"` en `add_incident` | `IncidentIdConflictError` (→ `409` / código `1`) |
| `errors.ForeignKeyViolation` u otra violación de integridad | `ValueError("El incidente viola la integridad del almacén.")`, sin el mensaje del driver |
| `OperationalError`, `InterfaceError` o conexión rota | descartar la conexión (R1) y lanzar `StoreUnavailableError` `from None` (→ `500 internal_error` / código `4`) |

**Justificación**: Constitución 3.3 (los errores del driver se traducen dentro del
adaptador) y RNF-003/006. El mensaje del driver puede incluir datos de la fila o de la
conexión, y el manejador genérico de la API solo registra `type(exc).__name__`.

**Alternativa descartada**: volver a consultar la existencia del identificador, como hace
SQLite. En PostgreSQL el nombre de la restricción es fiable y evita una segunda ida y
vuelta.

---

## R7. Fábrica `create_repository(database_url)`

**Decisión**:

- `create_incident_repository` pasa a llamarse **`create_repository`**, a petición del
  usuario. Se actualizan sus llamadores (`src/main.py`) y no se deja alias: no hay más usos
  en `src/` ni en `tests/`.
- Selección (FR-008):
  - `sqlite:///:memory:` y `sqlite:///<ruta>` → `SQLiteIncidentRepository`, sin cambios;
  - `postgresql://…` → `PostgresIncidentRepository(url, seed_if_empty=DEMO_INCIDENTS)`;
  - cualquier otro esquema → `ValueError`.
- `postgres_repository` (y con él `psycopg`) se **importa dentro de la rama
  `postgresql`**. Una invocación de la CLI sobre SQLite no paga la importación del driver.
- La URL se valida sin red con `psycopg.conninfo.conninfo_to_dict`. Si falla:
  `ValueError("DATABASE_URL de PostgreSQL mal formada (esquema 'postgresql').")`, sin
  encadenar la causa (`from None`).
- Mensaje de esquema no soportado: `DATABASE_URL no soportada (esquema '<s>'): use
  sqlite:///:memory:, sqlite:///<ruta> o postgresql://…`.
- `postgres://` se rechaza (D4).

**Justificación**:

- FR-008, FR-013 y RNF-003.
- La importación perezosa conserva el tiempo de arranque de la CLI en desarrollo.
- Validar sin red mantiene el adaptador perezoso y hace fallar pronto una URL inválida.

**Alternativa descartada**: aceptar `postgres://` por comodidad. La Constitución 3.5 enumera
solo `postgresql://`.

---

## R8. Caso de uso y proyección de la sonda

**Decisión**:

- `IncidentService.check_health() -> bool` delega en `repository.check_health()` y
  convierte cualquier excepción en `False` (FR-004, defensa ante adaptadores que incumplan
  «nunca lanza»).
- `health_to_contract(available: bool) -> dict` en `services.py` es la **única**
  proyección al contrato:
  - `True` → `{"status": "ok", "database": "connected"}`;
  - `False` → `{"status": "error", "database": "unavailable"}`.
- HTTP y CLI la comparten (Art. 2.7).
- El registro de cambios de estado (RNF-006) vive en el adaptador HTTP:
  - un objeto de estado por `create_app`, que empieza en «desconocido»;
  - `INFO` en cada cambio a `connected`;
  - `WARNING` en cada consulta `unavailable`;
  - cada línea lleva solo el resultado, la duración en ms y el código.
- La CLI no registra: imprime el diagnóstico en stderr.

**Justificación**: la aplicación no hace E/S de registros hoy y no debe empezar a hacerla.
El registro es un detalle del canal de larga vida, y la CLI es de un solo disparo.

**Alternativa descartada**: añadir un método al puerto (por ejemplo `describe_health`).
Viola la Constitución 3.2 sin necesidad.

---

## R9. Esquemas HTTP

**Decisión**:

- El `HealthResponse(status: str)` actual pasa a llamarse **`LivenessResponse`** y sigue
  sirviendo `GET /v1/health` sin cambios (FR-005).
- El nombre **`HealthResponse`** queda para la sonda nueva, como pidió el usuario:
  `status: Literal["ok", "error"]`, `database: Literal["connected", "unavailable"]`,
  `extra="forbid"`.
- `GET /health` declara `response_model=HealthResponse` y `responses={503: {"model":
  HealthResponse}}`, y devuelve `JSONResponse` con el código que corresponda.

**Justificación**: ampliar el modelo existente con un campo opcional haría que
`/v1/health` emitiera `"database": null` y rompería el cuerpo exacto de la spec 001.

---

## R10. Imagen de la aplicación

**Decisión**: un `Dockerfile` de una sola etapa:

- `FROM python:3.12-slim`;
- `uv` copiado de `ghcr.io/astral-sh/uv:0.13.8` (la misma versión que el entorno local);
- variables de entorno:
  - `UV_PYTHON_DOWNLOADS=never`, para usar el Python de la imagen;
  - `UV_PROJECT_ENVIRONMENT=/app/.venv`;
  - `UV_COMPILE_BYTECODE=1`;
  - `UV_LINK_MODE=copy`;
  - `PYTHONUTF8=1`, el equivalente de `-X utf8` (T1);
- copia `pyproject.toml`, `uv.lock` y `README.md` y ejecuta `uv sync --frozen --no-dev
  --no-install-project`;
- después copia `src/`;
- crea un usuario de sistema sin privilegios (UID fijo) y pasa a `USER` con él;
- `EXPOSE 8080`;
- `CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]`.

**Justificación**:

- FR-015 y RNF-004.
- `--frozen` instala exactamente lo que dice `uv.lock`, y `--no-dev` deja fuera pytest,
  httpx y ruff (E16).
- `--no-install-project` corresponde a `package = false` (T6).
- Copiar el lock antes que `src/` aprovecha la caché de capas.
- `0.0.0.0` es necesario dentro del contenedor. La exposición real la limita la
  publicación en loopback de la composición (R11, RNF-003).

**Alternativas descartadas**:

- Construcción en dos etapas: no hay nada que compilar porque `psycopg-binary` trae ruedas.
- Imagen `alpine` para la app: musl complica las ruedas de `tiktoken` y `psycopg-binary`.
- Fijar `python:3.12-slim` por *digest*: más reproducible, pero el usuario y la spec piden
  la etiqueta. Queda como mejora opcional.

**Riesgo conocido**: detrás del proxy TLS local, `uv sync` dentro de la construcción puede
fallar por certificados. Es un asunto del entorno (supuesto de la spec), no de la imagen.

---

## R11. Composición

**Decisión**: `docker-compose.yml` con `name: incidentops` y estos servicios:

- **`db`**:
  - `postgres:16-alpine`;
  - `POSTGRES_USER`, `POSTGRES_PASSWORD` y `POSTGRES_DB` con valores por defecto de
    desarrollo, sustituibles por el entorno (`${POSTGRES_PASSWORD:-incidentops}`);
  - `POSTGRES_INITDB_ARGS="--locale=C --encoding=UTF8"`;
  - volumen nombrado `pgdata`;
  - chequeo `pg_isready -U … -d …` cada `5s`, con `timeout 3s`, `retries 10` y
    `start_period 10s`;
  - `restart: unless-stopped`;
  - **sin `ports`**.
- **`api`**:
  - `build: .`;
  - `DATABASE_URL=postgresql://<user>:<password>@db:5432/<db>`, construida con las mismas
    variables;
  - `depends_on: db: condition: service_healthy`;
  - `ports: "127.0.0.1:${API_HOST_PORT:-8080}:8080"`;
  - chequeo con el Python de la imagen (`urllib.request` contra
    `http://127.0.0.1:8080/health`, con `timeout` de 4 s, sale con `1` si no es `200`) cada
    `10s`, con `timeout 5s`, `retries 3` y `start_period 15s`;
  - `restart: unless-stopped`.
- **`db-test`**:
  - `profiles: ["test"]`;
  - misma imagen y mismos `initdb` args;
  - `tmpfs` para los datos;
  - `ports: "127.0.0.1:${TEST_DB_HOST_PORT:-55432}:5432"`;
  - mismo chequeo.

**Cumplimiento de los 60 s (RNF-008)**:

- Pasar a «no sano» tarda como mucho `retries × interval + timeout` ≈ 35 s.
- Volver a «sano» basta con un chequeo correcto: ≤ 10 s más la latencia de la sonda.

**Justificación**:

- FR-017, FR-018, FR-020 y RNF-003.
- La imagen `slim` no trae `curl`, por eso el chequeo usa el Python de la imagen.
- `API_HOST_PORT` permite que las pruebas de contenedores no choquen con un runtime en
  marcha (RNF-011).

**Alternativas descartadas**:

- Un archivo `.env` versionado: un secreto versionado incumple FR-018, y uno sin versionar
  obliga a un paso manual.
- Publicar `db`: lo descartó la clarificación 2.

---

## R12. Estrategia de pruebas (`tests/test_spec_004_runtime_health.py`)

**Decisión**: un solo archivo, como pidió el usuario, en tres niveles:

1. **Rápidas** (sin marcador; corren siempre, sin red ni Docker):
   - E1 y E2 con el almacén por defecto;
   - E3 con un doble cuyo `check_health()` devuelve `False`;
   - E5 con un doble que alterna su estado;
   - E6;
   - E4 por el camino real: `DATABASE_URL=postgresql://u:secreto@127.0.0.1:1/db`. El
     puerto 1 rechaza la conexión al instante, así que se comprueba a la vez el código `4`,
     el cuerpo, que no se filtran `secreto`, `u@` ni la URL, y que la respuesta llega en 3 s
     o menos;
   - E7, E8 y E10;
   - conformidad **estructural** de `create_repository` para `sqlite:///:memory:` y
     `postgresql://…`: los seis métodos del puerto con la misma firma, comparada con
     `inspect.signature`, sin conectar gracias al adaptador perezoso;
   - estructura de `Dockerfile`, `.dockerignore` y `docker-compose.yml` por aserciones de
     texto: imágenes, `uv sync --frozen --no-dev`, `USER`, `127.0.0.1:` en `ports`, sin
     `ports` en `db`, `pg_isready`, `service_healthy`, `/health`, volumen, `--locale=C` y
     perfil `test`.
2. **`@pytest.mark.postgres`**:
   - conformidad **de comportamiento** del puerto, parametrizada sobre SQLite y
     PostgreSQL;
   - E9, E11 (paridad byte a byte de los JSON de resumen, SLA y creación con duplicado) y
     la siembra única.
   - Necesitan `INCIDENTOPS_TEST_POSTGRES_URL`, que apunta a `db-test`. Sin ella,
     `pytest.skip` con el motivo visible. Cada prueba empieza con `DROP TABLE IF EXISTS
     incidents, sla_policies` sobre esa base desechable.
3. **`@pytest.mark.docker`**:
   - E12 a E17 y `docker compose config --format json` (validación estructural real);
   - cada prueba usa `docker compose -p incidentops-t<uuid8>`, con `API_HOST_PORT` libre,
     `up -d --build --wait` y `down -v` en el `finally` (RNF-011);
   - se omiten si `docker info` falla.

Los marcadores se registran en `[tool.pytest.ini_options] markers` de `pyproject.toml`.

**Justificación**:

- El análisis del texto evita añadir `pyyaml` (T5). La validación semántica la da
  `docker compose config` cuando hay Docker.
- El puerto muerto ejercita el adaptador real, el arranque degradado y la ausencia de
  fugas sin infraestructura.

**Alternativas descartadas**:

- `testcontainers`: dependencia nueva (T5).
- Un archivo por nivel: el usuario pidió un único archivo de la spec 004.

---

## R13. Rendimiento sobre PostgreSQL (RNF-009, SC-005)

**Decisión**:

- El arnés `src/incident_repository.py` gana `--database-url`. Si se indica, compone el
  repositorio con `create_repository`; si no, usa SQLite como hoy.
- Antes de medir sobre PostgreSQL, el arnés llama a `vacuum_analyze()`. Es un método del
  adaptador PostgreSQL fuera del puerto, como `close()` en SQLite, y ejecuta `VACUUM
  ANALYZE incidents`. Así el planificador tiene estadísticas y el mapa de visibilidad
  permite *index-only scans* (ADR-004).
- El objetivo de 1 s con `--records 20000 --iterations 20` se verifica con el arnés, no en
  pytest.

**Justificación**: ADR-004 exige repetir la medición sobre el motor nuevo. Sin `VACUUM`, una
tabla recién cargada mide un plan peor que el de régimen.

---

## R14. Dependencia y entorno de Python

**Decisión**:

- `psycopg[binary]>=3.3.9` ya figura en `pyproject.toml`, y `uv.lock` resuelve
  `psycopg 3.3.9`, `psycopg-binary 3.3.9` y `tzdata` (dependencia de `psycopg` en Windows).
  Ambos cambios están en el árbol de trabajo, sin confirmar.
- El venv local sigue con CPython 3.10.0 y la imagen usa 3.12. El tope `pytest<9.2` solo
  afecta al grupo de desarrollo, que no entra en la imagen.

**Justificación**: Constitución T2 3.1.0, `uv sync` reproducible (T1). `tzdata` no cambia el
dominio: `COT` sigue siendo un desfase fijo sin base de zonas horarias.

**Riesgo**: el código corre en dos versiones de Python (3.10 en desarrollo, 3.12 en el
contenedor). Las pruebas `docker` de E12 a E17 ejercitan la versión del contenedor de
principio a fin.
