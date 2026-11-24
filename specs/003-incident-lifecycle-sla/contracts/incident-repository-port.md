# Contrato de puertos secundarios (spec 003)

Reemplaza a `specs/002-active-incident-summary/contracts/incident-repository-port.md` en
dos filas: `find_open_duplicates` (nueva firma) y el método nuevo `add_incident`. El
cambio lo respalda la enmienda 3.0.0 de la Constitución, sin ADR: la falta de ADR queda
registrada como desviación de gobernanza (plan G19). ADR-006 no se edita (Art. 3.7), y
sus filas sobre estos métodos quedan desplazadas por la Constitución hasta que un ADR las
reemplace.

```python
class IncidentIdConflictError(Exception):
    def __init__(self, incident_id: str) -> None: ...

class IncidentIdGeneratorPort(Protocol):
    def new_id(self) -> str: ...

class IncidentRepositoryPort(Protocol):
    def save_incident(self, incident: Incident) -> None: ...
    def add_incident(self, incident: Incident) -> None: ...
    def get_incident(self, incident_id: str) -> Optional[Incident]: ...
    def find_open_duplicates(self, duplicate_group_key: str, exclude_incident_id: str) -> Sequence[Incident]: ...
    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]: ...
    def check_health(self) -> bool: ...
```

Ningún método expone SQL, filas, tablas ni DSN (Art. 2.4). Los instantes se devuelven
normalizados a hora de Bogotá.

## `IncidentRepositoryPort`

| Método | Semántica | SQLite | Nulo | Consumidor |
|---|---|---|---|---|
| `save_incident` | Inserta o reemplaza por `incident_id` (**sin cambio**). Persiste también `recommended_team` y `duplicate_group_key`. Severidad sin política → `ValueError`. | `INSERT … ON CONFLICT DO UPDATE` | No hace nada | Siembra de demo, pruebas, benchmark |
| `add_incident` | **Nuevo.** Inserta sin reemplazar. Si el `incident_id` existe → `IncidentIdConflictError`, y el existente queda intacto. Severidad sin política → `ValueError`. | `INSERT` sin `ON CONFLICT`; `IntegrityError` de PK → conflicto | No hace nada | `create_incident` |
| `get_incident` | Entidad completa (nueve campos) o `None`. | `SELECT … WHERE incident_id = ?` | `None` | `evaluate_incident_sla` |
| `find_open_duplicates` | **Nueva firma.** Activos (`status <> 'RESOLVED'`) con `duplicate_group_key` igual al dado e `incident_id` distinto de `exclude_incident_id`, ordenados por `(created_at, incident_id)`. Quien llama nunca pasa una clave vacía o nula. | `idx_incidents_dup_key`, `INNER JOIN sla_policies` | `()` | `create_incident` |
| `list_active_incidents` | Sin cambio (H002). | Sin cambio | `()` | Resumen de activos |
| `check_health` | Sin cambio. | `SELECT 1` | `True` | Raíz de composición |

## `IncidentIdGeneratorPort`

| Implementación | Ubicación | Semántica |
|---|---|---|
| `RandomHexIdGenerator` | `src/adapters/outbound/id_generator.py` | `"INC-" + secrets.token_hex(4).upper()` |
| `SequenceIdGenerator` | `tests/doubles.py` | Devuelve una secuencia fija; pruebas deterministas y de colisión |

El servicio reintenta hasta 5 veces si un identificador **generado** choca con uno
existente. Un identificador **enviado** por el cliente nunca se reintenta: produce `409`.

## Conformidad

La batería de conformidad, en `tests/test_spec_003_lifecycle_sla.py`, ejecuta los mismos
casos contra `SQLiteIncidentRepository` (en `tmp_path`) y `InMemoryIncidentRepository`:

- `add_incident` dos veces con el mismo identificador → conflicto, sin cambios en el primero;
- `find_open_duplicates` excluye `RESOLVED`, el propio identificador y otras claves, y
  respeta el orden;
- `save_incident` y `get_incident` hacen el viaje de ida y vuelta de los nueve campos;
- un archivo de H002 sin las columnas nuevas se abre, migra y conserva sus filas.

Las pruebas de conformidad de spec 002 que fijan la firma de ventana de
`find_open_duplicates` (`tests/test_spec_002_summary.py`, líneas 196-201 y 274) se
actualizan a la firma nueva **después** de enmendar el contrato de spec 002 (Art. 5.6).
