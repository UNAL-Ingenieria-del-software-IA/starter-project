# Contrato: runtime en contenedores (spec 004)

Fija lo **observable** de `Dockerfile`, `.dockerignore` y `docker-compose.yml`. La
verificación estructural rápida lo comprueba por texto, y las pruebas `docker` lo comprueban
con `docker compose config` y ejecución real ([research §R12](../research.md#r12-estrategia-de-pruebas-teststest_spec_004_runtime_healthpy)).

## Imagen (`Dockerfile`)

| Propiedad | Valor |
|---|---|
| Base | `python:3.12-slim` |
| Gestor | `uv` copiado de `ghcr.io/astral-sh/uv:0.13.8` |
| Instalación | `uv sync --frozen --no-dev --no-install-project` desde `pyproject.toml` + `uv.lock` |
| Código | solo `src/`, más los metadatos necesarios para `uv sync` |
| Usuario | no `root`, UID fijo |
| Proceso | `uvicorn src.main:app --host 0.0.0.0 --port 8080` |
| Entorno | `PYTHONUTF8=1`; sin `DATABASE_URL` por defecto, porque la inyecta la composición |

## Contexto de construcción (`.dockerignore`)

Se excluye:

- `.git`;
- `.venv`;
- `__pycache__` y `*.pyc`;
- `.pytest_cache` y `.ruff_cache`;
- `.env` y `.env.*`;
- `tests/`, `specs/`, `docs/` y `data/`;
- `.claude/`, `.opencode/` y `.specify/`;
- `CONTEXT_LOG.md`;
- `*.db`, `*.sqlite` y `*.sqlite3`;
- los propios `Dockerfile`, `docker-compose.yml` y `.dockerignore`.

## Composición (`docker-compose.yml`)

| Servicio | Arranca con `up` | Imagen | Datos | Chequeo | Publicación en el host | Depende de |
|---|---|---|---|---|---|---|
| `db` | sí | `postgres:16-alpine`, `initdb --locale=C --encoding=UTF8` | volumen `pgdata` | `pg_isready` cada 5 s | **ninguna** | — |
| `api` | sí | `build: .` | — | `GET /health` cada 10 s, 3 reintentos | `127.0.0.1:${API_HOST_PORT:-8080}` → `8080` | `db` con `service_healthy` |
| `db-test` | no (perfil `test`) | `postgres:16-alpine`, mismo `initdb` | `tmpfs` | `pg_isready` | `127.0.0.1:${TEST_DB_HOST_PORT:-55432}` → `5432` | — |

Reglas:

- `DATABASE_URL` de `api` se construye con `POSTGRES_USER`, `POSTGRES_PASSWORD` y
  `POSTGRES_DB`, cuyos valores por defecto de desarrollo se pueden sustituir por el entorno.
  No hay secretos versionados ni archivos que crear (FR-018).
- `api` pasa a «no sano» en 60 s o menos tras caer la base y vuelve a «sano» en 60 s o
  menos tras recuperarse (RNF-008).
- `restart: unless-stopped` en `db` y `api`.
- Un entorno nuevo queda operativo con `docker compose up -d --build --wait`, sin pasos
  previos (E12).
