# Plan de implementación: Persistencia PostgreSQL y runtime en contenedores (H004)

**Rama**: `004-postgres-container-runtime` (pendiente de crear; el trabajo está hoy en `main`)
| **Fecha**: 2026-11-24 | **Spec**: [spec.md](spec.md)

**Entrada**: especificación de la funcionalidad en
`specs/004-postgres-container-runtime/spec.md`, clarificada el 2026-11-24 en dos sesiones.

**Autoridad**: subordinado a `.specify/memory/constitution.md` (3.1.0) y a
`docs/constitution.md`. Si este plan las contradice, prevalece la Constitución. Las
fronteras siguen la skill `hexagonal-architecture`.

## Resumen

H004 permite guardar los incidentes en una base PostgreSQL dedicada, en su propio
contenedor, y añade una sonda de disponibilidad real (`GET /health` y `health` en la CLI).
SQLite en memoria sigue siendo el almacén por defecto de desarrollo y pruebas. Solo
`DATABASE_URL` elige el motor (ADR-004).

Enfoque técnico, capa por capa, con las dependencias apuntando hacia adentro:

1. **Dominio** (`src/domain/`): **sin cambios**.
2. **Aplicación** (`src/application/`):
   - `IncidentService.check_health() -> bool` delega en el puerto y convierte cualquier
     excepción en `False`.
   - `health_to_contract(available)` es la única proyección del cuerpo de la sonda.
   - `ports.py` declara `StoreUnavailableError` para la composición y para los fallos de conexión que el adaptador PostgreSQL traduce.
   - El puerto **no cambia** ([research §R3, §R8](research.md#r3-arranque-degradado-http-frente-a-fallo-temprano-cli)).
3. **Adaptadores secundarios** (`src/adapters/outbound/`):
   - **`postgres_repository.py`** (nuevo): `PostgresIncidentRepository` implementa
     exactamente `IncidentRepositoryPort` con `psycopg`:
     - conexión perezosa, `autocommit` y `dict_row`, con un candado y reconexión;
     - SQL constante con `%s`;
     - `INSERT … ON CONFLICT DO UPDATE` en `save_incident` e `INSERT` simple en
       `add_incident`;
     - DDL con `COLLATE "C"` e índices parciales idénticos a los de SQLite;
     - inicialización y siembra «si está vacía» bajo un candado consultivo;
     - `check_health()` acotado a 3 s por una conexión efímera
       ([research §R1, §R2, §R4–R6](research.md)).
   - **`factory.py`**: `create_incident_repository` pasa a llamarse **`create_repository`**,
     selecciona por esquema, importa `psycopg` de forma perezosa y valida la URL sin red
     ([research §R7](research.md#r7-fábrica-create_repositorydatabase_url)).
4. **Raíz de composición** (`src/main.py`):
   - `build_repository` y `build_service` reciben `require_health`;
   - la `app` HTTP arranca degradada (`require_health=False`, FR-019);
   - la CLI conserva el fallo temprano.
5. **Adaptadores primarios** (`src/adapters/inbound/`):
   - `api/schemas.py`: `HealthResponse` (nuevo, `status` + `database`) y `LivenessResponse`
     (el antiguo `HealthResponse` de `/v1/health`);
   - `api/app.py`: `GET /health` responde `200` o `503` y registra solo los cambios de
     estado y los fallos;
   - `cli.py`: subcomando `health [--format table|json]` con códigos `0` y `4`
     ([research §R8, §R9](research.md#r9-esquemas-http)).
6. **Runtime**: `Dockerfile` (`python:3.12-slim` + `uv 0.13.8`, `--frozen --no-dev`, usuario
   sin privilegios), `.dockerignore` y `docker-compose.yml`:
   - `db`: `postgres:16-alpine`, volumen, `pg_isready`, `initdb --locale=C`, sin publicar;
   - `api`: `service_healthy`, chequeo sobre `/health`, publicado en `127.0.0.1:8080`;
   - `db-test`: perfil `test`, `tmpfs`, `127.0.0.1:55432`
   ([research §R10, §R11](research.md#r10-imagen-de-la-aplicación)).
7. **Fronteras**: veto de `psycopg` en los `ruff.toml` de `domain`, `application` y
   `adapters/inbound`, y en `tests/test_arquitectura.py` (Constitución 4.2, D-G4).
8. **Pruebas**: `tests/test_spec_004_runtime_health.py`
   ([research §R12](research.md#r12-estrategia-de-pruebas-teststest_spec_004_runtime_healthpy)):
   - **rápidas**:
     - `/health` 200;
     - `/health` 503 con un doble;
     - `create_repository` con conformidad estructural de SQLite y PostgreSQL al puerto;
     - CLI `health`;
     - estructura de los archivos Docker;
     - E4 por el camino real con un puerto muerto;
   - `@pytest.mark.postgres`: conformidad de comportamiento sobre ambos motores, E9 y E11;
   - `@pytest.mark.docker`: E12 a E17.

**Bloqueo declarado (Fase A).** El código no empieza hasta cerrar las dependencias de
gobernanza D-G1, D-G2, D-G3 y D-G5 de la spec. D-G4 es la Fase B de este plan.

## Contexto técnico

**Lenguaje/Versión**: Python ≥ 3.10. El venv local usa CPython 3.10.0 y la imagen usa
`python:3.12-slim` ([research §R14](research.md#r14-dependencia-y-entorno-de-python)).

**Dependencias principales**:

- en ejecución: `fastapi`, `uvicorn`, `pydantic` v2, `typer`, `tiktoken` y
  **`psycopg[binary]` 3.3.9**. Esta última ya está en `pyproject.toml` y `uv.lock`, sin
  confirmar;
- en desarrollo: `pytest<9.2`, `httpx`, `ruff`;
- sin dependencias nuevas: nada de pool, `testcontainers` ni `pyyaml`.

**Almacenamiento**: SQLite (`sqlite3`) en memoria o en archivo, y PostgreSQL 16 por
`psycopg`. Los instantes se guardan como texto ISO 8601 y el texto usa `COLLATE "C"`.

**Pruebas**: pytest con `TestClient` (FastAPI) y `CliRunner` (Typer). Hay dos marcadores
nuevos, `postgres` y `docker`, que se omiten de forma visible si falta su infraestructura.

**Plataforma objetivo**: desarrollo en Windows (PowerShell, `-X utf8`) y runtime Linux en
contenedores (Docker Compose v2).

**Tipo de proyecto**: servicio web y CLI sobre un núcleo hexagonal (un solo proyecto).

**Objetivos de rendimiento**:

- la sonda responde en 3 s o menos en el peor caso y en menos de 500 ms (p95) con la base
  disponible;
- el resumen de activos tarda menos de 1 s con 20 000 registros en ambos motores (SC-005);
- el estado de `api` en la composición refleja cada cambio en 60 s o menos.

**Restricciones**:

- sin ORM ni capa de abstracción SQL; SQL constante y parametrizado;
- el puerto no cambia;
- `DATABASE_URL` nunca aparece en salidas;
- API solo en el loopback del host y base sin publicar;
- imagen sin `root` y sin dependencias de desarrollo.

**Escala y alcance**:

- 1 adaptador nuevo y 2 servicios de runtime, más 1 de pruebas;
- 1 ruta HTTP y 1 subcomando nuevos;
- unas 25–35 pruebas nuevas.

## Constitution Check

*GATE: debe pasar antes de la Fase 0 y se revisa después de la Fase 1.*

| # | Norma | Evaluación del diseño | Antes | Después de la Fase 1 |
|---|---|---|---|---|
| G1 | 1.1 Fuente única | El adaptador PostgreSQL solo mapea filas. El SLA y el orden del resumen siguen en el dominio y la aplicación. `sla_policies` es un espejo sin lecturas. | ✅ | ✅ |
| G2 | 1.2 Pureza | `src/domain/` no se toca. | ✅ | ✅ |
| G3 | 1.3 Determinismo | Paridad entre motores: instantes como texto con ancho fijo y `COLLATE "C"` (R4); E11 la verifica byte a byte. | ✅ | ✅ |
| G4 | 2.1 Dirección de dependencias | La CLI captura `StoreUnavailableError` de `application`. `psycopg` solo se importa en `postgres_repository.py` y `tests/`. | ✅ | ✅ |
| G5 | 2.3 Aplicación sin E/S | `check_health` y `health_to_contract` no registran, ni hacen E/S ni importan drivers. | ✅ | ✅ |
| G6 | 2.4 Canales que solo traducen | `/health` y `health` llaman al caso de uso y a la proyección; el registro de estado es propio del canal. | ✅ | ✅ |
| G7 | 2.6 Persistencia dual | `%s` constante, índice parcial y streaming con `cursor.stream()` (research §R1), texto ISO e intercalación `C`. | ✅ | ✅ |
| G8 | 2.7 Paridad de canales | Un único `health_to_contract` para HTTP y CLI. | ✅ | ✅ |
| G9 | 3.2 Catálogo mínimo de puertos | El puerto no cambia. `check_health` es un método del servicio, no del puerto. | ✅ | ✅ |
| G10 | 3.3 Puerto sin motor | Los errores de `psycopg` se traducen en el adaptador (R6). No se filtran filas `dict_row`. | ✅ | ✅ |
| G11 | 3.5 Selección por `DATABASE_URL` | La fábrica admite los esquemas de 3.5 y rechaza `postgres://`. Los mensajes llevan solo el esquema. | ✅ | ✅ |
| G12 | 3.6 Intercambiabilidad | Conformidad estructural siempre y de comportamiento sobre ambos motores. Los casos PostgreSQL se omiten de forma visible sin base. | ✅ | ✅ |
| G13 | 4.2 Ruff veta `psycopg` | Hoy **no** lo veta (D-G4). La Fase B lo añade antes de escribir el adaptador. | ⚠️ Pendiente (Fase B) | ✅ tras la Fase B |
| G14 | V Verificación y BDD | E1–E17 automatizados (5.2), y oráculos de dominio intactos (5.5). | ✅ | ✅ |
| G15 | T2/T3 | `psycopg[binary]` declarado en T2; sin ORM, sin pool y sin dependencias nuevas. | ✅ | ✅ |
| G16 | T4 Confinamiento | `psycopg` solo en `src/adapters/outbound/` y `tests/`. | ✅ | ✅ |
| G17 | F3 Contrato de canales | `GET /health` y `health` **no** figuran en F3 (D-G2). | ❌ Bloquea la implementación | ✅ tras la Fase A |
| G18 | Governance (2) ADR aceptado | ADR-004 está «Propuesto» (D-G1). | ❌ Bloquea la implementación | ✅ tras la Fase A |
| G19 | ADR-006 (fallo temprano al componer) | FR-019 lo invierte para HTTP (D-G5). | ❌ Bloquea la implementación | ✅ tras la Fase A |
| G20 | Governance (3) `AGENTS.md` y `docs/constitution.md` | Siguen sin PostgreSQL ni la sonda, y llaman ADR-004 al ADR de stack (D-G3). | ❌ Bloquea el cierre | ✅ tras las Fases A y F |
| G21 | 2.5 / T5 Stack y rutas `api/`, `cli.py` | Desviación heredada (ADR de stack pendiente). H004 extiende esos archivos sin crear paquetes. | ⚠️ Heredada | ⚠️ Heredada; no se agrava |

**Resultado**: el diseño cumple todos los principios. G17–G20 son incumplimientos **de
gobernanza documental**, no de diseño. Están justificados y se resuelven en la Fase A, antes
de cualquier cambio de código, así que la planificación sigue y `/speckit.implement` queda
bloqueado hasta cerrarlos. G13 se resuelve en la Fase B.

## Estructura del proyecto

### Documentación (esta feature)

```text
specs/004-postgres-container-runtime/
├── spec.md                         # /speckit.specify + /speckit.clarify
├── plan.md                         # este archivo
├── research.md                     # Fase 0 (R1–R14)
├── data-model.md                   # Fase 1: esquema PostgreSQL, sonda, configuración
├── quickstart.md                   # Fase 1: validación por niveles
├── contracts/
│   ├── http-health.openapi.yaml    # GET /health y GET /v1/health
│   ├── cli-health.md               # subcomando health
│   ├── incident-repository-port.md # conformidad C1–C11 sobre ambos adaptadores
│   └── container-runtime.md        # Dockerfile, .dockerignore, compose
├── checklists/requirements.md
└── tasks.md                        # /speckit.tasks (no lo crea este comando)
```

### Código fuente (raíz del repositorio)

```text
Dockerfile                              # NUEVO
.dockerignore                           # NUEVO
docker-compose.yml                      # NUEVO (db, api, db-test[perfil test])
pyproject.toml                          # psycopg[binary] (ya en el árbol de trabajo); marcadores postgres/docker
uv.lock                                 # psycopg 3.3.9 (ya en el árbol de trabajo)

src/
├── domain/                             # sin cambios
│   └── ruff.toml                       # + veto "psycopg"
├── application/
│   ├── ports.py                        # + StoreUnavailableError (el puerto no cambia)
│   ├── services.py                     # + IncidentService.check_health(), + health_to_contract()
│   └── ruff.toml                       # + veto "psycopg"
├── adapters/
│   ├── inbound/
│   │   ├── api/schemas.py              # HealthResponse (nuevo) + LivenessResponse (renombrado)
│   │   ├── api/app.py                  # + GET /health (200/503) con registro de cambios de estado
│   │   ├── cli.py                      # + subcomando health
│   │   └── ruff.toml                   # + veto "psycopg"
│   └── outbound/
│       ├── postgres_repository.py      # NUEVO: PostgresIncidentRepository
│       ├── factory.py                  # create_incident_repository → create_repository (+ postgresql://)
│       └── demo_incidents.py           # sin cambios (DEMO_INCIDENTS como semilla)
├── incident_repository.py              # arnés: + --database-url (SC-005 sobre PostgreSQL)
└── main.py                             # require_health; la app HTTP arranca degradada

tests/
├── test_spec_004_runtime_health.py     # NUEVO (rápidas + postgres + docker)
├── test_arquitectura.py                # + psycopg en las listas prohibidas
└── doubles.py                          # + doble con check_health conmutable (si no basta el existente)
```

**Decisión de estructura**: un solo proyecto con la topología hexagonal vigente. No se crean
paquetes de canal nuevos (G21). El único módulo nuevo de `src/` es el adaptador de salida.

## Fases de implementación (insumo de `/speckit.tasks`)

| Fase | Contenido | Commit | Verificación de salida |
|---|---|---|---|
| **A — Gobernanza** (bloqueante) | ADR-004: incorporar el arranque degradado (D-G5) y pasar a «Aceptado» con la confirmación explícita del usuario (D-G1). Constitución 3.2.0 (MINOR): F2 con los comandos de composición y F3 con `GET /health` y `health` (D-G2), y retirar el informe de impacto anterior. `docs/constitution.md`: Art. 2.6 y 3.2 dual, ADR de stack con número pendiente (D-G3). | `docs(governance): …` | Revisión documental |
| **B — Fronteras** | Vetar `psycopg` en los tres `ruff.toml` y en `test_arquitectura.py` (D-G4). Registrar los marcadores `postgres` y `docker`. | `chore(boundaries): …` | `ruff check src/` y `pytest` en verde |
| **C — Sonda (US1)** | `StoreUnavailableError`, `check_health()`, `health_to_contract`; esquemas, `GET /health`, CLI `health`; `require_health` en `main.py`. Pruebas E1–E6 y la estructural de la sonda. | `feat(h004): sonda …` | Pruebas rápidas en verde |
| **D — PostgreSQL (US2)** | `postgres_repository.py`, `create_repository`, siembra «si está vacía», arnés `--database-url`. Pruebas E7–E11, conformidad estructural y de comportamiento, y E4 por el camino real. | `feat(h004): adaptador PostgreSQL …` | Rápidas en verde; `-m postgres` en verde contra `db-test`; SC-005 |
| **E — Contenedores (US3)** | `Dockerfile`, `.dockerignore`, `docker-compose.yml`. Pruebas de estructura (rápidas) y E12–E17 (`-m docker`). | `feat(h004): runtime en contenedores …` | `-m docker` en verde; quickstart, nivel 3 |
| **F — Documentación operativa** | `AGENTS.md` (comandos, `create_repository`, sonda, composición, marcadores) y `README.md`. Actualizar el ejemplo `postgresql://x` de `specs/002…/quickstart.md`, que ya no falla. | `docs(h004): …` | Verificación completa (F4) |

Orden: A → B → C → D → E → F. C y D tocan `main.py` y `factory.py`, así que van en
secuencia. E solo depende de D. Una vez cerrada la Fase A, B y la parte de pruebas de C se
pueden preparar en paralelo.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Una red colgada con la conexión ya abierta bloquea una operación de negocio más de 3 s | `tcp_user_timeout` y `statement_timeout` en la conexión principal (R1/R2). La sonda usa su propia conexión. |
| Diferencias de Python entre 3.10 (local) y 3.12 (imagen) | Las pruebas `docker` ejecutan la imagen real de principio a fin. El lock es universal. |
| Bases PostgreSQL externas con otra intercalación | `COLLATE "C"` por columna, independiente de la base (R4). |
| El proxy TLS local impide `uv sync` durante la construcción | Supuesto documentado en la spec. No se versionan certificados. |
| Pruebas `docker` lentas | Marcador propio, fuera de la suite rápida. Caché de capas: lock antes que `src/`. |
| Cambio del mensaje de la fábrica | Ninguna prueba vigente lo fija (la spec 002 usa un *stub*). Se revisan los ejemplos de documentación en la Fase F. |

## Seguimiento de complejidad

| Violación | Por qué se necesita | Alternativa más simple descartada |
|---|---|---|
| G17–G20: implementación bloqueada por gobernanza pendiente | ADR-004 «Propuesto», F3 sin la sonda, ADR-006 en conflicto con FR-019 y documentos desalineados. | Implementar primero y documentar después: repetiría la desviación 3.0.0 sin ADR que la Constitución ya registra como abierta. |
| Excepción al sobre común de errores en `503 /health` (D5) | Lo pide el usuario y es el estado de la sonda, no un error de la petición. Es el formato que consumen los orquestadores. | Usar el sobre común: rompe el cuerpo exacto de FR-003. |
| Una conexión efímera por sonda además de la principal | Acotar la sonda a 3 s sin competir por el candado (R2). | Sondear con la conexión principal: la sonda quedaría sujeta a consultas lentas. |
| Archivo de pruebas único con tres niveles | Pedido explícito del usuario. | Tres archivos: más ordenado, pero contradice el pedido. |
| G21 heredada (stack sin ADR; rutas `api/`, `cli.py`) | Desviación previa. | Resolverla aquí mezcla decisiones. H004 no la agrava. |
