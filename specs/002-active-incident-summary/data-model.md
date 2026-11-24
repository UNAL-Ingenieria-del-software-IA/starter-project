# Modelo de datos (Fase 1): Resumen de incidentes activos (H002)

Tres representaciones, cada una en su capa (ADR-003): entidades de dominio, vistas del
caso de uso y DTO/filas de los adaptadores. El mapeo entre ellas es explícito y vive en el
adaptador correspondiente.

---

## 1. Dominio (`src/domain/models.py`)

### `Incident` (existente, sin cambios de forma)

| Campo | Tipo | Regla |
|---|---|---|
| `incident_id` | `str` | Identidad; única en el almacén. |
| `title` | `str` | Título registrado (no el texto crudo del reporte). |
| `component` | `str` | Identificador canónico en minúsculas (p. ej. `payment-gateway`). |
| `severity` | `SeverityLevel` | `P0`…`P3`. |
| `status` | `IncidentStatus` | `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`, `RESOLVED`. |
| `created_at` | `datetime` | Naive = Bogotá (Art. 1.7); se normaliza con `to_bogota` al guardar y al leer. |
| `resolved_at` | `Optional[datetime]` | Obligatorio si `RESOLVED` (Art. 1.10); se asume `None` en activos. |

### Constantes nuevas (tras la Fase A)

| Nombre | Valor | Uso |
|---|---|---|
| `ACTIVE_STATUSES` | `frozenset({"OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED"})` | Única definición de «activo» (Art. 1.10 enmendado). |
| `SEVERITY_ORDER` | `("P0", "P1", "P2", "P3")` | Orden de criticidad para FR-011. |

### `SLAEvaluation` (existente)

Producida solo por `evaluate_sla_status(incident, reference_time)`. H002 consume
`elapsed_minutes`, `is_breached` y `requires_escalation`; nadie los recalcula (FR-005).
Invariante del dominio: `is_breached` y `requires_escalation` nunca son ambos verdaderos.

### Ciclo de vida

H002 es de solo lectura: no hay transiciones de estado. `ESCALATION_REQUIRED` es un estado
del ciclo de vida (lo fija H003); `requires_escalation` es un valor derivado del SLA y no
se persiste (Art. 1.8).

---

## 2. Caso de uso (`src/application/services.py`)

### `ActiveIncidentView` (nuevo, `@dataclass(frozen=True)`)

Una fila del detalle: datos del incidente más su evaluación.

| Campo | Origen |
|---|---|
| `incident_id`, `title`, `component`, `severity`, `status` | `Incident` |
| `elapsed_minutes`, `is_breached`, `requires_escalation` | `SLAEvaluation` |

### `ActiveIncidentsSummary` (nuevo, `@dataclass(frozen=True)`)

| Campo | Tipo | Regla |
|---|---|---|
| `reference_time` | `datetime` | Aware, Bogotá, truncado a segundos; es el instante evaluado (FR-008). |
| `component_filter` | `Optional[str]` | Filtro normalizado (`strip().lower()`) o `None`. |
| `incidents` | `Tuple[ActiveIncidentView, ...]` | Orden FR-011. |
| `total_active` | `int` (propiedad) | `len(incidents)` — consistencia por construcción (FR-010). |
| `breached_count` | `int` (propiedad) | Cantidad de `is_breached` verdaderos (FR-010). |

Los totales son propiedades derivadas del detalle, no campos independientes: no pueden
desincronizarse.

### Reglas de `get_active_incidents_summary(component_filter, reference_time)`

1. Validar `component_filter`: `None` admitido; vacío tras recortar →
   `ValidationError("invalid_payload", …, "component")`.
2. Resolver instante: `reference_time or clock.now()` → `to_bogota` → truncar a segundos.
3. Leer `repository.list_active_incidents(component)`.
4. Conservar solo `status in ACTIVE_STATUSES` y `to_bogota(created_at) <= instante`
   (FR-002, FR-009).
5. Evaluar cada uno con `evaluate_sla_status(incident, instante)`.
6. Ordenar por `(SEVERITY_ORDER.index(severity), -elapsed_minutes, incident_id)` (FR-011).
7. Devolver `ActiveIncidentsSummary`. No escribe en el repositorio (FR-015).

### `parse_reference_time(value: Optional[str]) -> Optional[datetime]`

`None` → `None`. Si no, `datetime.fromisoformat` (con `Z` traducido a `+00:00`); fallo →
`ValidationError("invalid_timestamp", "…", "reference_time")`. Usado por HTTP y CLI.

### `summary_to_contract(summary) -> Dict[str, Any]`

Única proyección al contrato público (ver
[contracts/http-incidents-summary.openapi.yaml](contracts/http-incidents-summary.openapi.yaml)).
`reference_time` se emite con `isoformat()` (p. ej. `2026-11-24T09:00:00-05:00`).

---

## 3. Persistencia SQLite (`src/adapters/outbound/sqlite_repository.py`)

Esquema, índice y consultas: [research.md §R3](research.md#r3).

| Columna `incidents` | ↔ `Incident` | Conversión |
|---|---|---|
| `incident_id TEXT PK` | `incident_id` | — |
| `title TEXT NOT NULL` | `title` | — |
| `component TEXT NOT NULL` | `component` | — |
| `severity TEXT NOT NULL FK → sla_policies` | `severity` | — |
| `status TEXT NOT NULL` | `status` | — |
| `created_at TEXT NOT NULL` | `created_at` | Escritura `to_bogota(x).isoformat()`; lectura `datetime.fromisoformat`. |
| `resolved_at TEXT NULL` | `resolved_at` | Igual que `created_at`; `NULL` ↔ `None`. |

`sla_policies(severity PK, max_resolution_minutes, operates_24x7)`: espejo de
`SLA_POLICY_TABLE`, sembrado al crear el esquema; no se lee para calcular.

`save_incident` es *upsert* por `incident_id` (`INSERT … ON CONFLICT(incident_id) DO
UPDATE`), con `?` en todos los valores.

---

## 4. Adaptador HTTP (`src/adapters/inbound/api/schemas.py`)

### `SummaryQueryParams` (consulta, `extra="forbid"`)

| Campo | Tipo | Nota |
|---|---|---|
| `component` | `Optional[StrictStr]` | Sin normalizar: lo hace el servicio. |
| `reference_time` | `Optional[StrictStr]` | Sin analizar: lo hace `parse_reference_time`. |

### `ActiveIncidentItem`

| Campo | Tipo |
|---|---|
| `incident_id` | `str` |
| `title` | `str` |
| `component` | `str` |
| `severity` | `SeverityLevel` (del dominio) |
| `status` | `IncidentStatus` (del dominio) |
| `elapsed_minutes` | `int` |
| `is_breached` | `bool` |
| `requires_escalation` | `bool` |

### `ActiveIncidentsSummaryResponse`

| Campo | Tipo |
|---|---|
| `reference_time` | `str` (ISO-8601 con desfase; ver [research.md §R9](research.md#r9)) |
| `component_filter` | `Optional[str]` |
| `total_active` | `int` |
| `breached_count` | `int` |
| `incidents` | `List[ActiveIncidentItem]` |

Los `Literal` de severidad y estado se importan del dominio; no se redefinen (Art. 1.1).

---

## 5. Validaciones y su origen

| Regla | Dónde | Resultado HTTP / CLI |
|---|---|---|
| Parámetro o bandera desconocidos | Pydantic `extra="forbid"` / Click | `400 invalid_payload` / `2` |
| `--format` inválido | Typer (enum) | — / `2` |
| `reference_time` no parseable | `parse_reference_time` | `422 invalid_timestamp` / `1` (antes `3`; spec 003 D8) |
| `component` vacío o solo espacios | Servicio | `422 invalid_payload` / `1` (antes `3`; spec 003 D8) |
| Componente sin coincidencias | Servicio | `200` vacío / `0` (FR-007) |
| Instante anterior a la creación | Servicio (exclusión) | `200` sin ese incidente (FR-009) |
| Severidad sin política | FK + `INNER JOIN` en SQLite | La fila no puede entrar ni leerse |

---

## 6. Conjunto de demostración (`src/adapters/outbound/demo_incidents.py`)

Tupla inmutable `INC-2001`…`INC-2008` con instantes fijos. Debe cubrir: los cuatro estados,
al menos tres componentes canónicos, las cuatro severidades, al menos un incidente
incumplido y uno que requiera escalamiento a `2026-11-24T09:00:00-05:00`, y un P2 creado en
fin de semana (exhibe el cómputo hábil). Las pruebas BDD **no** dependen de este conjunto
(spec, Supuestos).
