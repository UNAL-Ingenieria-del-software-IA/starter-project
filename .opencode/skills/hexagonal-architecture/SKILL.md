---
name: hexagonal-architecture
description: Reglas de fronteras de la arquitectura hexagonal de IncidentOps. Úsala al crear o mover módulos en src/domain, src/application o src/adapters, al añadir canales o puertos, al revisar importaciones entre capas y al configurar o ejecutar la validación estática con Ruff.
---

# Arquitectura hexagonal de IncidentOps

Norma operativa para mantener las fronteras de ADR-003 y de la Constitución (Art. 2).
La regla base es una sola: **las dependencias apuntan hacia adentro**,
`adapters → application → domain`. La única excepción es la raíz de composición
(`src/main.py`), que conoce las implementaciones concretas y las inyecta.

```
src/adapters/inbound/  ──►  src/application/  ──►  src/domain/
src/adapters/outbound/ ──►  src/application/ports.py
        ▲
        └── implementaciones inyectadas por src/main.py
```

Antes de terminar cualquier cambio, deben seguir verdes:

```bash
uv run ruff check src/
uv run python -X utf8 -m pytest -v
```

## 1. Qué puede importar cada capa

| Capa | Puede importar | No puede importar |
|---|---|---|
| `src/domain/` | Solo stdlib pura (`datetime`, `typing`, `dataclasses`, `enum`, `re`, `unicodedata`, `functools`, `math`, `collections`) y otros módulos de `src.domain`. | Frameworks, HTTP, bases de datos, ORMs, `json`, `pathlib`, `os`, `argparse`, `sqlite3`, `src.application`, `src.adapters`, `src.main`. Tampoco lee el reloj (`datetime.now()`, `today()`, `utcnow()`). |
| `src/application/` | stdlib sin E/S, `src.application` y `src.domain`. Declara puertos con `typing.Protocol`. | Frameworks (`fastapi`, `typer`, `pydantic`, `click`, `starlette`, `uvicorn`), drivers/ORM (`sqlite3`, `sqlalchemy`, `psycopg`), `json`, `pathlib`, `os`, `argparse`, `src.adapters`, `src.main`. |
| `src/adapters/inbound/` | La librería de su canal (`fastapi`, `typer`, etc.), stdlib de traducción, `src.application` y tipos de `src.domain`. Para cablear dependencias, únicamente `src.adapters.outbound.factory`. | Reglas de triaje, SLA o duplicados; `sqlite3`/ORM; clases repositorio concretas; `src.main`; otro adaptador primario. |
| `src/adapters/outbound/` | stdlib de persistencia (`sqlite3` con marcadores `?`), `src.application.ports` y `src.domain`. | `src.adapters.inbound`, `src.main` y cualquier regla de negocio. |
| `src/main.py` | Todo. Es la raíz de composición. | — |

### `src/domain/` — reglas puras

- Entidades y valores (`Incident`, `TriageResult`, `SLAEvaluation`), `SLA_POLICY_TABLE`,
  `evaluate_sla_status`, horario hábil, festivos y el pipeline de triaje.
- Cero imports de frameworks, HTTP, BD, ORMs o capas externas. Cero lectura del reloj:
  el tiempo entra como parámetro (`datetime`) y el resultado es inmutable.
- La carga de fixtures, el parseo de JSON y la impresión de auditorías pertenecen a un
  adaptador primario, no al dominio.

### `src/application/` — casos de uso

- `IncidentService` es el único punto de entrada para clasificar reportes.
- Depende solo de stdlib y `src.domain`; no conoce HTTP, MCP ni SQL.
- Los puertos viven en `src/application/ports.py` y se declaran con `typing.Protocol`:
  `ClockPort` y `IncidentRepositoryPort` (activos por componente/estado, guardar y
  localizar equivalente abierto). Un puerto nunca expone SQL ni tipos de tabla.
- `to_contract()` es la única proyección del resultado de dominio al contrato público;
  los canales no reescriben esa proyección.

### `src/adapters/inbound/` — canales

- Solo traducen: entrada del canal → `ReportInput` → `IncidentService` → formato de
  salida. Nada de reglas de triaje, SLA o duplicados.
- Deben delegar **siempre** en `IncidentService`; no llaman directamente al pipeline de
  `src.domain` ni replican su lógica.
- No importan drivers de BD ni repositorios concretos. Si un adaptador necesita cablear
  dependencias, el único punto autorizado es `src.adapters.outbound.factory` (y lo
  preferible es que ese cableado lo haga `src/main.py`).

```python
# Correcto: el canal solo traduce y delega.
results = service.triage_incident([report])
payload = [to_contract(r) for r in results]
```

```python
# Incorrecto: el canal reimplementa o salta el caso de uso.
from src.domain.triage_rules import classify_incident_batch
severity = "P0" if "caída" in text else "P3"
```

### `src/adapters/outbound/` — persistencia

- Implementan `IncidentRepositoryPort` de forma estructural: no heredan de una clase
  base del núcleo; basta con satisfacer el `Protocol`.
- Aquí viven `sqlite3`, el DDL, el índice parcial, los marcadores `?` y el mapeo
  fila ↔ entidad. Nada de eso se filtra a `application` ni a `domain`.
- `src/adapters/outbound/factory.py` es la única puerta pública hacia las
  implementaciones concretas. Los módulos concretos deben vivir en subpaquetes
  (`sqlite/`, `memory/`, etc.) para poder prohibirlos por prefijo en Ruff.

```python
# src/adapters/outbound/factory.py
from src.application.ports import IncidentRepositoryPort
from src.adapters.outbound.sqlite.repository import SqliteIncidentRepository


def build_incident_repository(settings) -> IncidentRepositoryPort:
    return SqliteIncidentRepository(settings.database_path)
```

## 2. Paridad entre adaptadores primarios (REST y CLI)

REST y CLI deben producir la **misma clasificación** para el mismo reporte, y lo logran
por construcción: ambos invocan el mismo caso de uso y la misma proyección
`to_contract()`. La paridad no se obtiene replicando lógica ni ramificando por canal
dentro del núcleo.

Reglas concretas:

1. Todo canal nuevo (`rest/`, `cli/`, `mcp/`) llama a `IncidentService.triage_incident`.
2. Ningún canal importa el pipeline de `src.domain` para clasificar por su cuenta.
3. Los errores de negocio se traducen a códigos de cada canal en el adaptador
   (`400/422` en HTTP, `3/4` en CLI); el núcleo solo lanza `ValidationError`.
4. La suite de contrato compara las salidas de ambos canales para los mismos casos
   (`tests/test_spec_001_triage.py`; el caso compartido futuro es
   `tests/test_contrato_canales.py`).
5. Un canal nuevo es un paquete nuevo más su registro en `src/main.py`; el núcleo no se
   reabre.

## 3. Validación estática de fronteras con Ruff

Ruff se ejecuta con:

```bash
uv run ruff check src/
```

La configuración debe seleccionar `E4`, `E7`, `E9`, `F` y `TID`, y prohibir imports
relativos desde padres con `TID252`. `TID251` (`banned-api`) es el que convierte las
fronteras en errores de lint.

> Nota de estado: si `pyproject.toml` aún no tiene `[tool.ruff.lint]` o faltan los
> `ruff.toml` jerárquicos, créalos como se muestra aquí antes de confiar en el chequeo.
> Sin esa configuración, `ruff check src/` solo aplica las reglas por defecto y no
> detecta violaciones de capa.

### Configuración raíz (`pyproject.toml`)

```toml
[tool.ruff]
target-version = "py310"

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "TID"]

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "parents"
```

No pongas prohibiciones de capa en la configuración raíz: se aplicarían también a los
adaptadores. Cada capa declara su propio mapa `banned-api`.

### `src/domain/ruff.toml`

```toml
[lint]
select = ["E4", "E7", "E9", "F", "TID"]

[lint.flake8-tidy-imports]
ban-relative-imports = "parents"

[lint.flake8-tidy-imports.banned-api]
"json" = { msg = "El dominio es puro: la carga de JSON pertenece a un adaptador." }
"pathlib" = { msg = "El dominio no resuelve rutas ni toca el sistema de archivos." }
"os" = { msg = "El dominio no lee entorno ni sistema operativo." }
"argparse" = { msg = "El parseo de argumentos pertenece a un adaptador primario." }
"sqlite3" = { msg = "El dominio no conoce la base de datos; usa IncidentRepositoryPort." }
"sqlalchemy" = { msg = "Prohibido ORM (ADR-001/002)." }
"psycopg" = { msg = "El dominio no conoce drivers de base de datos." }
"fastapi" = { msg = "El dominio no conoce frameworks HTTP." }
"starlette" = { msg = "El dominio no conoce frameworks HTTP." }
"pydantic" = { msg = "El dominio no depende de DTOs de canal." }
"typer" = { msg = "El dominio no conoce frameworks de CLI." }
"click" = { msg = "El dominio no conoce frameworks de CLI." }
"uvicorn" = { msg = "El dominio no conoce el servidor HTTP." }
"httpx" = { msg = "El dominio no hace HTTP." }
"requests" = { msg = "El dominio no hace HTTP." }
"urllib" = { msg = "El dominio no hace HTTP." }
"http" = { msg = "El dominio no hace HTTP." }
"src.application" = { msg = "Dirección prohibida: domain no importa application." }
"src.adapters" = { msg = "Dirección prohibida: domain no importa adapters." }
"src.main" = { msg = "El dominio no conoce la raíz de composición." }
```

### `src/application/ruff.toml`

```toml
[lint]
select = ["E4", "E7", "E9", "F", "TID"]

[lint.flake8-tidy-imports]
ban-relative-imports = "parents"

[lint.flake8-tidy-imports.banned-api]
"json" = { msg = "La aplicación no hace E/S; el JSON pertenece al adaptador." }
"pathlib" = { msg = "La aplicación no resuelve rutas." }
"os" = { msg = "La aplicación no lee entorno ni sistema operativo." }
"argparse" = { msg = "El parseo de argumentos pertenece al adaptador CLI." }
"sqlite3" = { msg = "La aplicación no conoce la base de datos; usa IncidentRepositoryPort." }
"sqlalchemy" = { msg = "Prohibido ORM (ADR-001/002)." }
"psycopg" = { msg = "La aplicación no conoce drivers de base de datos." }
"fastapi" = { msg = "La aplicación no conoce frameworks HTTP." }
"starlette" = { msg = "La aplicación no conoce frameworks HTTP." }
"pydantic" = { msg = "La aplicación no depende de DTOs de canal." }
"typer" = { msg = "La aplicación no conoce frameworks de CLI." }
"click" = { msg = "La aplicación no conoce frameworks de CLI." }
"uvicorn" = { msg = "La aplicación no conoce el servidor HTTP." }
"httpx" = { msg = "La aplicación no hace HTTP." }
"requests" = { msg = "La aplicación no hace HTTP." }
"src.adapters" = { msg = "Dirección prohibida: application no importa adapters." }
"src.main" = { msg = "La aplicación no conoce la raíz de composición." }
```

### `src/adapters/inbound/ruff.toml`

```toml
[lint]
select = ["E4", "E7", "E9", "F", "TID"]

[lint.flake8-tidy-imports]
ban-relative-imports = "parents"

[lint.flake8-tidy-imports.banned-api]
"sqlite3" = { msg = "El canal no habla con la BD; delega en IncidentService." }
"sqlalchemy" = { msg = "Prohibido ORM (ADR-001/002)." }
"psycopg" = { msg = "El canal no conoce drivers de base de datos." }
"pymysql" = { msg = "El canal no conoce drivers de base de datos." }
"asyncpg" = { msg = "El canal no conoce drivers de base de datos." }
"src.main" = { msg = "La raíz de composición depende del canal, no al revés." }
"src.adapters.outbound.sqlite" = { msg = "Importa src.adapters.outbound.factory, no la implementación concreta." }
"src.adapters.outbound.memory" = { msg = "Importa src.adapters.outbound.factory, no la implementación concreta." }
"src.adapters.outbound.null_repository" = { msg = "Importa src.adapters.outbound.factory, no la implementación concreta." }
```

Añade a esa lista cada nuevo módulo concreto de `src/adapters/outbound/` que aparezca.
El único import permitido de esa rama es `src.adapters.outbound.factory`.

Opcionalmente, `src/adapters/outbound/ruff.toml` puede prohibir
`"src.adapters.inbound"` y `"src.main"` para cerrar también esa dirección.

### Reglas y trampas de Ruff

- `TID251` compara por **prefijo**: prohibir `"src.adapters.outbound.sqlite"` también
  bloquea `from src.adapters.outbound.sqlite.repository import ...`.
- En Ruff ≥ 0.17 cada entrada de `banned-api` debe ser una tabla con `msg`:
  `"json" = { msg = "..." }`. Una cadena suelta falla al parsear la configuración.
- Los `ruff.toml` jerárquicos **no fusionan** `banned-api` con el padre: el mapa del
  archivo más cercano lo reemplaza. Por eso cada capa repite su lista completa.
- `ban-relative-imports = "parents"` bloquea `from ..paquete import X`, pero permite
  `from .modulo import X`. En este repo usa siempre imports absolutos `from src...`.
- `TID251` solo inspecciona importaciones, no llamadas. Que el dominio no lea el reloj
  (`datetime.now()`) lo vigila `tests/test_arquitectura.py`, no Ruff.
- No silencies una violación con `# noqa: TID251` sin una excepción registrada en un ADR
  y aprobada en la revisión. Una frontera que se salta deja de ser una frontera.

## 4. Checklist antes de cerrar un cambio

- [ ] El módulo nuevo está en la capa correcta y sus imports apuntan hacia adentro.
- [ ] `src/domain/` no importa frameworks, HTTP, BD, ORMs, `json`, `pathlib`, `os` ni
      capas externas; tampoco lee el reloj.
- [ ] `src/application/` solo usa stdlib y `src.domain`; los puertos siguen siendo
      `Protocol` mínimos y sin SQL.
- [ ] `src/adapters/inbound/` delega en `IncidentService` y no importa drivers ni
      repositorios concretos (solo `src.adapters.outbound.factory` si hace falta cablear).
- [ ] `src/adapters/outbound/` implementa `IncidentRepositoryPort` y concentra DDL,
      SQL y mapeo de filas.
- [ ] REST y CLI siguen compartiendo caso de uso y `to_contract()`; la prueba de
      contrato sigue verde.
- [ ] `uv run ruff check src/` pasa sin `noqa` nuevos.
- [ ] `uv run python -X utf8 -m pytest -v` pasa, incluida `tests/test_arquitectura.py`.
