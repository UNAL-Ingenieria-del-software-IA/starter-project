# Quickstart (validación): Persistencia PostgreSQL y runtime en contenedores (H004)

Guía para comprobar la feature de punta a punta. Los contratos están en
[contracts/](contracts/) y el esquema en [data-model.md](data-model.md). Todos los comandos
se ejecutan desde la raíz del repositorio.

## Requisitos

- `uv` y el venv del proyecto (`uv sync`; detrás del proxy TLS, `uv sync --system-certs`).
- Para los niveles 2 y 3: Docker con Compose v2.

## Nivel 1 — Desarrollo sin contenedores (siempre)

```bash
uv run ruff check src/                       # incluye el veto a psycopg en dominio, aplicación y canales
uv run python -X utf8 -m pytest -v           # las pruebas postgres/docker aparecen como SKIPPED, con su motivo
uv run python -X utf8 -m src.sla_calculator
uv run python -X utf8 -m src.triage_rules
```

Sonda con el almacén por defecto (E2):

```bash
uv run python -X utf8 -m src.adapters.inbound.cli health --format json
# {"status": "ok", "database": "connected"}   → código 0
```

Sonda con la base inalcanzable (E4). El puerto 1 rechaza la conexión al instante:

```powershell
$env:DATABASE_URL = "postgresql://u:secreto@127.0.0.1:1/db"
uv run python -X utf8 -m src.adapters.inbound.cli health --format json
# stdout: {"status": "error", "database": "unavailable"}   → código 4, en 3 s o menos
# stderr: error [database_unavailable]: … (sin «secreto», sin la URL)
Remove-Item Env:DATABASE_URL
```

## Nivel 2 — Pruebas contra PostgreSQL (base de pruebas aparte)

```bash
docker compose --profile test up -d --wait db-test
```

```powershell
$env:INCIDENTOPS_TEST_POSTGRES_URL = "postgresql://incidentops:incidentops@127.0.0.1:55432/incidentops"
uv run python -X utf8 -m pytest -v -m postgres      # conformidad C1–C10, E9, E11
uv run python -X utf8 -m src.incident_repository --database-url $env:INCIDENTOPS_TEST_POSTGRES_URL --records 20000 --iterations 20   # SC-005
Remove-Item Env:INCIDENTOPS_TEST_POSTGRES_URL
```

```bash
docker compose --profile test down -v
```

Resultado esperado: las pruebas `postgres` pasan y el arnés informa un promedio por debajo
de 1 s.

## Nivel 3 — Runtime completo

```bash
docker compose up -d --build --wait          # E12: db sano → api sano, sin pasos previos
curl -s http://127.0.0.1:8080/health         # {"status":"ok","database":"connected"}
curl -s "http://127.0.0.1:8080/api/v1/incidents/summary?reference_time=2026-11-24T09:00:00"   # INC-2001…INC-2008
docker compose stop db                       # E14: /health → 503 y api «unhealthy» en 60 s o menos
docker compose start db                      # api vuelve a «healthy» en 60 s o menos, sin reiniciarse
docker compose down                          # los datos quedan en el volumen pgdata (E13)
docker compose down -v                       # borra el volumen: el siguiente up es un entorno nuevo
```

Automatización de E12 a E17 (proyectos aislados, se limpian solos):

```bash
uv run python -X utf8 -m pytest -v -m docker
```

## Comprobaciones de seguridad (E15, E16)

```bash
docker compose port api 8080                 # 127.0.0.1:8080
docker compose port db 5432                  # falla: la base no está publicada en el host
docker compose exec api id -u                # distinto de 0
docker compose exec api python -c "import pytest"   # ModuleNotFoundError: sin dependencias de desarrollo
```
