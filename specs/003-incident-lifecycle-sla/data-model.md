# Modelo de datos (Fase 1): Registro, duplicado abierto y auditoría de SLA (H003)

**Spec**: [spec.md](spec.md) | **Investigación**: [research.md](research.md)

Las entidades del dominio son dataclasses puras (Art. 1.2). Los tipos `SeverityLevel`,
`IncidentStatus`, `TeamName` y `TriageAction` se toman de `src/domain/models.py` y no se
redefinen en ninguna otra capa (Art. 1.1).

---

## 1. Dominio (`src/domain/`)

### `Incident` (extendida)

| Campo | Tipo | Nuevo | Regla |
|---|---|---|---|
| `incident_id` | `str` | | Único. Generado como `INC-<HEX8>` o enviado por el cliente (`^INC-[A-Za-z0-9-]{1,32}$`). |
| `title` | `str` | | 1–200 caracteres, no solo espacios. |
| `component` | `str` | | Lo asigna el triaje (`route_component`). |
| `severity` | `SeverityLevel` | | Lo asigna el triaje (`decide_severity`). |
| `status` | `IncidentStatus` | | `OPEN` por defecto al crear; ver estados admitidos. |
| `created_at` | `datetime` | | Se normaliza a Bogotá (`to_bogota`) antes de guardar. |
| `resolved_at` | `Optional[datetime]` | | Obligatorio si y solo si `status == "RESOLVED"`; `>= created_at`. |
| `recommended_team` | `Optional[TeamName]` | **sí**, por defecto `None` | Lo asigna el triaje; `None` en datos previos a H003. |
| `duplicate_group_key` | `Optional[str]` | **sí**, por defecto `None` | `group_key_for` (R1); `None` si el reporte no tiene clave. |

Los dos campos nuevos van al final, con valor por defecto, para conservar la construcción
posicional de H002 (`demo_incidents.py`, pruebas).

### `SLAEvaluation` (extendida)

| Campo | Tipo | Nuevo | Regla |
|---|---|---|---|
| `incident_id`, `severity` | | | Sin cambio. |
| `elapsed_minutes` | `int` | | Hasta `min(reference_time, resolved_at)` (R2). |
| `allowed_minutes` | `int` | | `SLA_POLICY_TABLE[severity].max_resolution_minutes`. |
| `remaining_minutes` | `int` | | `allowed - elapsed`; puede ser negativo. |
| `is_breached` | `bool` | | `elapsed > allowed`. |
| `requires_escalation` | `bool` | | `not resolved_at_reference and not is_breached and elapsed >= int(allowed * 0.75)`. |
| `resolved_at_reference` | `bool` | **sí**, por defecto `False` | `resolved_at is not None and resolved_at <= reference_time`. |

### Funciones nuevas en `triage_rules.py`

| Función | Entrada | Salida | Regla |
|---|---|---|---|
| `group_key_for(component, signals)` | componente y señales de un reporte | `Optional[str]` | Formas canónicas del Art. 1.11 (tabla en [research §R1](research.md#r1-clave-de-grupo-de-un-solo-reporte)). |
| `classify_incident(report)` | un `IncidentReport` | `TriageResult` | Pipeline de un solo reporte; `duplicate_group_key = group_key_for(...)`, `duplicate_type="none"`, `merge=False`. |

`classify_incident_batch` reutiliza `group_key_for` y su salida no cambia (auditoría
invariante).

### Estados admitidos al crear

```text
             ┌──────────────── crear con status ────────────────┐
             ▼                    ▼                    ▼          ▼
           OPEN            IN_PROGRESS     ESCALATION_REQUIRED   RESOLVED
       (por defecto)                                          (exige resolved_at
                                                               >= created_at)
```

Este corte no tiene transiciones posteriores a la creación (spec D6). "Abierto" (FR-007)
es `ACTIVE_STATUSES` = {`OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`}.

---

## 2. Aplicación (`src/application/`)

### Puertos (`ports.py`)

```python
class IncidentIdConflictError(Exception):
    """El identificador ya existe en el almacén (lo lanza add_incident)."""
    incident_id: str

class IncidentIdGeneratorPort(Protocol):
    def new_id(self) -> str: ...            # "INC-" + 8 dígitos hex en mayúsculas

class IncidentRepositoryPort(Protocol):
    def save_incident(self, incident: Incident) -> None: ...          # upsert (sin cambio)
    def add_incident(self, incident: Incident) -> None: ...           # NUEVO: insert; conflicto → IncidentIdConflictError
    def get_incident(self, incident_id: str) -> Optional[Incident]: ...
    def find_open_duplicates(
        self, duplicate_group_key: str, exclude_incident_id: str
    ) -> Sequence[Incident]: ...                                       # NUEVA FIRMA
    def list_active_incidents(self, component: Optional[str] = None) -> Sequence[Incident]: ...
    def check_health(self) -> bool: ...
```

Contrato completo: [contracts/incident-repository-port.md](contracts/incident-repository-port.md).

### Entradas y resultados del caso de uso (`services.py`)

| Tipo | Campos | Uso |
|---|---|---|
| `CreateIncidentInput` (frozen) | `title: str`, `raw_text: str`, `incident_id: Optional[str]`, `created_at: Optional[datetime]`, `status: Optional[str]`, `resolved_at: Optional[datetime]` | Lo que cada canal traduce. `status` llega como texto y lo valida el servicio. |
| `IncidentCreation` (frozen) | `incident: Incident`, `triage: TriageResult`, `duplicate_of: Tuple[str, ...]` | Resultado de `create_incident`. `is_duplicate` es la propiedad `bool(duplicate_of)`. |
| `IncidentSLAAudit` (frozen) | `incident: Incident`, `reference_time: datetime`, `evaluation: SLAEvaluation` | Resultado de `evaluate_incident_sla`. |
| `IncidentNotFoundError(incident_id)` | — | El identificador no existe (404 / 1). |
| `ValidationError(code, message, field)` | — | Sin cambio; códigos nuevos: `reference_before_creation`. |

### Operaciones de `IncidentService`

```text
IncidentService(clock: ClockPort, repository: IncidentRepositoryPort,
                id_generator: Optional[IncidentIdGeneratorPort] = None)

create_incident(request: CreateIncidentInput) -> IncidentCreation
  1. valida title, raw_text, incident_id, status/resolved_at        → ValidationError
  2. created_at = to_bogota(request.created_at or clock.now())
  3. triage = classify_incident(IncidentReport(id, raw_text, created_at))   # dominio
  4. incident = Incident(..., triage.component, triage.severity, status,
                         recommended_team=triage.recommended_team,
                         duplicate_group_key=triage.duplicate_group_key)
  5. repository.add_incident(incident)        # id generado: reintenta ante conflicto (≤5)
  6. duplicate_of = () si clave es None, si no
        ids de repository.find_open_duplicates(clave, incident.incident_id)
  7. devuelve IncidentCreation(incident, triage, duplicate_of)

evaluate_incident_sla(incident_id: str, reference_time: Optional[datetime]) -> IncidentSLAAudit
  1. incident = repository.get_incident(incident_id) o IncidentNotFoundError
  2. instant = to_bogota(reference_time or clock.now()).replace(microsecond=0)
  3. instant < incident.created_at → ValidationError("reference_before_creation")
  4. evaluation = evaluate_sla_status(incident, instant)                    # dominio
  5. devuelve IncidentSLAAudit(incident, instant, evaluation)
```

Paso 3 de `create_incident`: el servicio no decide nada de la clasificación. La
comparación de duplicados (paso 6) es igualdad de clave entre abiertos, la que define
FR-007. La clave la produce el dominio.

---

## 3. Persistencia (`src/adapters/outbound/sqlite_repository.py`)

```sql
CREATE TABLE IF NOT EXISTS incidents (
    incident_id         TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    component           TEXT NOT NULL,
    severity            TEXT NOT NULL REFERENCES sla_policies (severity),
    status              TEXT NOT NULL,
    created_at          TEXT NOT NULL,     -- ISO Bogotá, microsegundos, ancho fijo
    resolved_at         TEXT,
    recommended_team    TEXT,              -- NUEVO
    duplicate_group_key TEXT               -- NUEVO
);

-- Existente (ADR-001/ADR-005), sin cambio
CREATE INDEX IF NOT EXISTS idx_incidents_active_component
ON incidents (component, status, severity, created_at, incident_id, title)
WHERE status <> 'RESOLVED';

-- NUEVO (R8)
CREATE INDEX IF NOT EXISTS idx_incidents_dup_key
ON incidents (duplicate_group_key, status)
WHERE status <> 'RESOLVED' AND duplicate_group_key IS NOT NULL;
```

**Migración aditiva** para archivos de H002: tras `CREATE TABLE IF NOT EXISTS`, se lee
`PRAGMA table_info(incidents)` y se ejecuta `ALTER TABLE incidents ADD COLUMN …` solo para
las columnas que falten. Son dos sentencias constantes; ningún dato existente cambia.

**Mapeo fila ↔ entidad**: `get_incident` y `find_open_duplicates` proyectan las nueve
columnas. Las consultas cubrientes de H002 (`SELECT_ACTIVE_SQL`,
`SELECT_ACTIVE_BY_COMPONENT_SQL`) no cambian, y sus entidades llevan los dos campos
nuevos en `None`. El resumen no los usa.

---

## 4. Proyecciones al contrato (`services.py`)

| Proyección | Campos |
|---|---|
| `creation_to_contract` | `incident_id`, `title`, `status`, `created_at` (ISO), `resolved_at` (ISO o `null`), `severity`, `component`, `recommended_team`, `action`, `duplicate_group_key`, `analysis` (lista), `is_duplicate`, `duplicate_of` (lista) |
| `sla_audit_to_contract` | `incident_id`, `title`, `component`, `severity`, `status`, `created_at`, `resolved_at`, `reference_time`, `resolved_at_reference`, `elapsed_minutes`, `allowed_minutes`, `remaining_minutes`, `is_breached`, `requires_escalation` |

`duplicate_type` y `merge` no se proyectan: describen la correlación de un lote (spec,
contrato observable).
