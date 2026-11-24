# Contrato del puerto: `IncidentRepositoryPort`

**Ubicación**: `src/application/ports.py` · **Declaración**: `typing.Protocol` (sin
`@runtime_checkable`) · **Implementaciones**: `SQLiteIncidentRepository`,
`NullIncidentRepository` (`src/adapters/outbound/`) y `InMemoryIncidentRepository`
(`tests/doubles.py`).

Justificación de cada método frente al catálogo mínimo del Art. III.2: ADR-006 y
[research.md §R7](../research.md#r7).

> **Enmienda 2026-11-24 (spec 003).** La firma de `find_open_duplicates` y el método nuevo
> `add_incident` los rige
> [specs/003-incident-lifecycle-sla/contracts/incident-repository-port.md](../../003-incident-lifecycle-sla/contracts/incident-repository-port.md).
> La firma de ventana de abajo queda solo como registro histórico de H002. La conformidad
> de `tests/test_spec_002_summary.py` sigue la firma nueva.

## Firma

```python
class IncidentRepositoryPort(Protocol):
    def save_incident(self, incident: Incident) -> None: ...
    def get_incident(self, incident_id: str) -> Optional[Incident]: ...
    def find_open_duplicates(
        self, component: str, created_from: datetime, created_to: datetime
    ) -> Sequence[Incident]: ...
    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]: ...
    def check_health(self) -> bool: ...
```

## Semántica

| Método | Contrato | SQLite | Nulo |
|---|---|---|---|
| `save_incident` | Inserta o reemplaza por `incident_id`. Normaliza instantes con `to_bogota`. Severidad sin política → `ValueError`. | `INSERT … ON CONFLICT DO UPDATE` con `?` | No hace nada |
| `get_incident` | Devuelve la entidad o `None`. | `SELECT … WHERE incident_id = ?` | `None` |
| `find_open_duplicates` | Activos del `component` con `created_from <= created_at <= created_to`, por `created_at` ascendente. La ventana la calcula quien llama (Art. 1.11). | Lectura sobre el índice parcial | `()` |
| `list_active_incidents` | Activos (estado distinto de `RESOLVED`), del componente si se indica (comparación exacta; el servicio ya normalizó). Sin orden garantizado: ordena el servicio. | `INNER JOIN sla_policies`, índice `idx_incidents_active_component` | `()` |
| `check_health` | `True` si el almacén responde; nunca lanza. | `SELECT 1` dentro de `try` | `True` |

## Prohibiciones (Art. III.3)

- Ningún parámetro ni retorno expone `sqlite3.Row`, cursores, SQL, nombres de tabla ni DSN.
- El puerto no calcula SLA, no ordena por criticidad y no decide duplicados.
- `domain/` y `application/` no importan implementaciones (Ruff `TID251` + prueba AST).

## Verificación de conformidad (`tests/test_spec_002_summary.py`)

1. **Forma**: para cada método público del `Protocol`, cada implementación expone un
   invocable con los mismos nombres, tipos y valores por defecto de parámetros
   (`inspect.signature`).
2. **Comportamiento compartido**: la misma batería de casos corre contra el doble en
   memoria y contra `SQLiteIncidentRepository(":memory:")` y exige resultados idénticos.
3. **Deriva del predicado**: con los cuatro estados sembrados, `list_active_incidents`
   devuelve exactamente los de `ACTIVE_STATUSES`.
4. **Espejo de política**: `sla_policies` coincide fila a fila con `SLA_POLICY_TABLE`.
5. **Plan de consulta**: `EXPLAIN QUERY PLAN` de ambas variantes usa
   `idx_incidents_active_component`.
