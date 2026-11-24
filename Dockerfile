# Imagen de la API de IncidentOps (ADR-004, spec 004 FR-015, research §R10).
#
# Una sola etapa: `psycopg-binary` y `tiktoken` traen ruedas, no hay nada que compilar.
# Las dependencias salen exactamente de `uv.lock` y sin el grupo de desarrollo, así que
# pytest, httpx y ruff no entran en la imagen (E16).
FROM python:3.12-slim

# `uv` con la misma versión que el entorno local.
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/

# - UV_PYTHON_DOWNLOADS=never: usa el Python de la imagen, nunca descarga otro.
# - UV_PROJECT_ENVIRONMENT: el venv vive en /app/.venv, dentro de la imagen.
# - PYTHONUTF8=1: equivalente de `-X utf8` (Constitución T1).
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Primero los metadatos y el lock: la capa de dependencias se reutiliza mientras no cambien.
# `--no-install-project` corresponde a `package = false` (Constitución T6).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Después, solo el código de la aplicación.
COPY src/ ./src/

# Usuario de sistema sin privilegios, con UID fijo (RNF-004).
RUN groupadd --system --gid 10001 incidentops \
    && useradd --system --uid 10001 --gid incidentops --no-create-home --shell /usr/sbin/nologin incidentops
USER incidentops

ENV PATH="/app/.venv/bin:${PATH}"

# Dentro del contenedor escucha en todas las interfaces; la composición solo publica el
# puerto en loopback del host (RNF-003). `DATABASE_URL` la inyecta la composición.
EXPOSE 8080
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
