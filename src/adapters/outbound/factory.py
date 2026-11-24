"""Selección del adaptador de persistencia a partir de `DATABASE_URL` (Art. III.5, ADR-004, ADR-006).

La fábrica recibe la URL como argumento: solo la raíz de composición (`src/main.py`) lee
el entorno. Los mensajes de error nombran el esquema, nunca la URL completa, porque la de
PostgreSQL lleva credenciales (spec 004 RNF-003).
"""

from __future__ import annotations

from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.ports import IncidentRepositoryPort

DEFAULT_DATABASE_URL = "sqlite:///:memory:"
_SQLITE_PREFIX = "sqlite:///"
_MEMORY = ":memory:"
_POSTGRESQL_SCHEME = "postgresql"
_SUPPORTED = "use sqlite:///:memory:, sqlite:///<ruta> o postgresql://…"


def is_in_memory_url(database_url: str) -> bool:
    """`True` para el almacén de demostración en memoria (se siembra al arrancar)."""
    return database_url == _SQLITE_PREFIX + _MEMORY


def create_repository(database_url: str) -> IncidentRepositoryPort:
    """Construye el repositorio que corresponde a la URL.

    | URL | Resultado |
    |---|---|
    | `sqlite:///:memory:` | SQLite en memoria |
    | `sqlite:///<ruta>` | SQLite en archivo (esquema `IF NOT EXISTS`, sin siembra) |
    | `postgresql://…` | PostgreSQL perezoso, sembrado con la demo si la base está vacía |
    | otro esquema (también `postgres://`) | `ValueError` |

    Raises:
        ValueError: si el esquema no está admitido o la URL no indica la base o está mal
            formada. El mensaje nombra solo el esquema.
    """
    scheme, separator, _ = database_url.partition("://")
    if separator and scheme == _POSTGRESQL_SCHEME:
        return _create_postgres_repository(database_url)
    if not separator or scheme != "sqlite" or not database_url.startswith(_SQLITE_PREFIX):
        shown = scheme if separator and scheme else "desconocido"
        raise ValueError(f"DATABASE_URL no soportada (esquema '{shown}'): {_SUPPORTED}.")
    database = database_url[len(_SQLITE_PREFIX):]
    if not database:
        raise ValueError(f"DATABASE_URL no indica la base de datos: {_SUPPORTED}.")
    return SQLiteIncidentRepository(database)


def _create_postgres_repository(database_url: str) -> IncidentRepositoryPort:
    """Rama `postgresql://` (research §R7).

    `psycopg` y el adaptador se importan solo aquí: una invocación sobre SQLite no paga la
    importación del driver. La URL se valida sin red; si libpq no la entiende, el error no
    encadena la causa porque su mensaje podría citar la URL.
    """
    from psycopg.conninfo import conninfo_to_dict

    from src.adapters.outbound.demo_incidents import classified_demo_incidents
    from src.adapters.outbound.postgres_repository import PostgresIncidentRepository

    try:
        conninfo_to_dict(database_url)
    except Exception:  # noqa: BLE001 — cualquier rechazo de libpq es una URL mal formada.
        raise ValueError(f"DATABASE_URL de PostgreSQL mal formada (esquema '{_POSTGRESQL_SCHEME}').") from None
    return PostgresIncidentRepository(database_url, seed_if_empty=classified_demo_incidents())
