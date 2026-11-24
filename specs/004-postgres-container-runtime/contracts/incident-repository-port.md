# Contrato: `IncidentRepositoryPort` con dos adaptadores (spec 004)

El puerto **no cambia** (Constitución 3.2): siguen los mismos seis métodos y las mismas
firmas que en `src/application/ports.py`. Este contrato fija lo que deben cumplir **los dos**
adaptadores, `SQLiteIncidentRepository` y `PostgresIncidentRepository`, y cómo se verifica.

## Conformidad estructural (siempre, sin base)

Para `create_repository("sqlite:///:memory:")` y
`create_repository("postgresql://u:p@127.0.0.1:1/db")`:

- se exponen los seis métodos públicos del puerto;
- `inspect.signature` de cada método coincide con la del puerto: nombres, orden,
  valores por defecto y anotaciones como texto;
- construir el adaptador PostgreSQL **no abre red** ([research §R1](../research.md#r1-gestión-de-la-conexión-postgresql)).

## Conformidad de comportamiento (parametrizada sobre ambos motores)

La parte de PostgreSQL necesita `INCIDENTOPS_TEST_POSTGRES_URL`. Sin ella se omite de forma
visible.

| # | Propiedad | Resultado esperado en ambos motores |
|---|---|---|
| C1 | `save_incident` dos veces con el mismo id | queda una fila, con los valores de la segunda |
| C2 | `add_incident` con id existente | `IncidentIdConflictError`; la fila existente no cambia |
| C3 | `add_incident` / `save_incident` con severidad sin política | `ValueError` |
| C4 | `get_incident` de un id inexistente | `None` |
| C5 | Ida y vuelta de instantes con microsegundos y desfase `-05:00` | `datetime` igual al guardado (FR-012) |
| C6 | `list_active_incidents()` y con componente | solo estados ≠ `RESOLVED`; el componente se compara tal cual |
| C7 | `find_open_duplicates(key, exclude)` | activos con esa clave, sin `exclude`, en orden `(created_at, incident_id)` por bytes (`INC-ABC1` antes que `INC-abc1`) |
| C8 | `check_health()` con el almacén disponible | `True` |
| C9 | `check_health()` con el almacén caído | `False` en 3 s o menos, sin excepción (solo PostgreSQL, puerto muerto) |
| C10 | Siembra «si está vacía» | en una base vacía quedan 8 incidentes de demostración; un segundo arranque o una base con datos no añade ninguno (solo PostgreSQL) |
| C11 | Operación del puerto con el almacén caído | `StoreUnavailableError` sin causa encadenada y sin la URL en el mensaje; nunca un tipo de `psycopg` (solo PostgreSQL, puerto muerto: no necesita base y corre siempre) |

El adaptador SQLite deja escapar hoy `sqlite3.Error` ante fallos de E/S. Es una deuda
anterior a esta feature y queda fuera de C11.

## Paridad de canales sobre ambos motores (E11)

Con el mismo conjunto de datos cargado en los dos motores, los JSON de
`summary_to_contract`, `sla_audit_to_contract` y `creation_to_contract` (con aviso de
duplicado) son **idénticos byte a byte** para la misma entrada y el mismo instante.
