# Modelo de datos (Fase 1): Persistencia PostgreSQL y runtime en contenedores (H004)

**Spec**: [spec.md](spec.md) · **Investigación**: [research.md](research.md)

H004 **no cambia el dominio**: `Incident`, `SLAEvaluation`, la política SLA y las claves de
duplicado siguen como en H003. Este documento describe solo lo nuevo: el esquema
PostgreSQL (espejo del de SQLite), los valores de la sonda y la configuración.

---

## 1. Esquema PostgreSQL

Todas las columnas de texto llevan `COLLATE "C"` ([research §R4](research.md#r4-esquema-postgresql-intercalación-e-instantes)).
Los nombres, tipos lógicos y restricciones coinciden con los del adaptador SQLite.

### `sla_policies` (espejo de `SLA_POLICY_TABLE`)

| Columna | Tipo | Restricción | Origen |
|---|---|---|---|
| `severity` | `TEXT COLLATE "C"` | `PRIMARY KEY` | `SLARule.severity` |
| `max_resolution_minutes` | `INTEGER` | `NOT NULL` | `SLARule.max_resolution_minutes` |
| `operates_24x7` | `INTEGER` (0/1) | `NOT NULL` | `SLARule.operates_24x7` |

- Se rellena con un *upsert* desde `SLA_POLICY_TABLE` en cada inicialización.
- Ninguna consulta lee sus columnas: solo existe como destino de la FK y del `INNER JOIN`
  (Art. 1.1, ADR-006).

### `incidents`

| Columna | Tipo | Restricción | Mapeo a `Incident` |
|---|---|---|---|
| `incident_id` | `TEXT COLLATE "C"` | `PRIMARY KEY` (restricción `incidents_pkey`) | `incident_id` |
| `title` | `TEXT COLLATE "C"` | `NOT NULL` | `title` |
| `component` | `TEXT COLLATE "C"` | `NOT NULL` | `component` |
| `severity` | `TEXT COLLATE "C"` | `NOT NULL`, `REFERENCES sla_policies (severity)` | `severity` |
| `status` | `TEXT COLLATE "C"` | `NOT NULL` | `status` |
| `created_at` | `TEXT COLLATE "C"` | `NOT NULL` | `datetime.fromisoformat(...)` |
| `resolved_at` | `TEXT COLLATE "C"` | nulo | `datetime` o `None` |
| `recommended_team` | `TEXT COLLATE "C"` | nulo | `recommended_team` |
| `duplicate_group_key` | `TEXT COLLATE "C"` | nulo | `duplicate_group_key` |

**Formato de instante** (FR-012): `to_bogota(value).isoformat(timespec="microseconds")`, por
ejemplo `2026-11-24T09:00:00.000000-05:00`. Tiene ancho fijo y desfase fijo, así que el orden
del texto coincide con el cronológico.

### Índices

| Índice | Columnas | Predicado | Consumidor |
|---|---|---|---|
| `idx_incidents_active_component` | `(component, status, severity, created_at, incident_id, title)` | `status <> 'RESOLVED'` | `list_active_incidents` (ADR-001, ADR-005) |
| `idx_incidents_dup_key` | `(duplicate_group_key, status)` | `status <> 'RESOLVED' AND duplicate_group_key IS NOT NULL` | `find_open_duplicates` (spec 003) |

### Inicialización (una vez por proceso, en la primera conexión correcta)

Todo ocurre en una sola transacción:

1. `pg_advisory_xact_lock(<clave constante>)`.
2. `CREATE TABLE IF NOT EXISTS` para las dos tablas y `CREATE INDEX IF NOT EXISTS` para los
   dos índices.
3. *Upsert* de `sla_policies`.
4. Si `NOT EXISTS (SELECT 1 FROM incidents)`, se inserta la semilla con `ON CONFLICT
   (incident_id) DO NOTHING` (FR-011).

No hay migración aditiva: no existen bases PostgreSQL anteriores a H004.

---

## 2. Correspondencia de operaciones del puerto

| Método del puerto | SQL PostgreSQL (constante, marcadores `%s`) | Errores traducidos |
|---|---|---|
| `save_incident` | `INSERT … ON CONFLICT (incident_id) DO UPDATE SET … = EXCLUDED.…` | `ValueError` si la severidad no tiene política (antes de ir a la base) |
| `add_incident` | `INSERT …` sin `ON CONFLICT` | `UniqueViolation` sobre `incidents_pkey` → `IncidentIdConflictError`; otra violación → `ValueError` sin el mensaje del driver |
| `get_incident` | `SELECT … WHERE incident_id = %s` | — |
| `find_open_duplicates` | `… WHERE status <> 'RESOLVED' AND duplicate_group_key IS NOT NULL AND duplicate_group_key = %s AND incident_id <> %s ORDER BY created_at, incident_id` | — |
| `list_active_incidents` | `SELECT_ACTIVE_SQL` / `SELECT_ACTIVE_BY_COMPONENT_SQL` con `INNER JOIN sla_policies`, leídas con `cursor.stream()` | — |
| `check_health` | `SELECT 1` por una conexión efímera acotada en el tiempo, y después la inicialización si falta | nunca lanza; cualquier fallo → `False` |

Ante `OperationalError`, `InterfaceError` o una conexión rota, las cinco primeras
operaciones descartan la conexión y lanzan `StoreUnavailableError` (declarada en el puerto)
sin encadenar la causa. Ningún tipo de `psycopg` sale del adaptador
([research §R1](research.md#r1-gestión-de-la-conexión-postgresql), §R6).

---

## 3. Valores de la sonda (aplicación)

| Valor | Tipo | Definición |
|---|---|---|
| disponibilidad | `bool` | resultado de `IncidentService.check_health()`; no se persiste |
| cuerpo de contrato | `dict` | `health_to_contract(available)`: `{"status": "ok", "database": "connected"}` o `{"status": "error", "database": "unavailable"}` |
| `StoreUnavailableError` | excepción (`RuntimeError`) en `application/ports.py` | la composición la lanza cuando `require_health=True` y el almacén no responde; el adaptador PostgreSQL la lanza cuando una operación del puerto pierde la conexión (§2) |

Estado de registro del canal HTTP (RNF-006), por instancia de `create_app`:

```text
desconocido ──(consulta ok)──▶ connected   [INFO]
desconocido ──(consulta ko)──▶ unavailable [WARNING]
connected   ──(consulta ko)──▶ unavailable [WARNING]
unavailable ──(consulta ko)──▶ unavailable [WARNING]   (cada fallo se registra)
unavailable ──(consulta ok)──▶ connected   [INFO]
connected   ──(consulta ok)──▶ connected   (no se registra)
```

---

## 4. Configuración

| Variable | Dónde se lee | Valores | Confidencialidad |
|---|---|---|---|
| `DATABASE_URL` | solo `src/main.py` | ausente o vacía, `sqlite:///:memory:`, `sqlite:///<ruta>` o `postgresql://…` | confidencial salvo el esquema |
| `INCIDENTOPS_TEST_POSTGRES_URL` | solo `tests/` | URL de `db-test` | solo de pruebas |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | composición | por defecto `incidentops` | valores de desarrollo |
| `API_HOST_PORT` / `TEST_DB_HOST_PORT` | composición | por defecto `8080` / `55432` | — |

**Ciclo de vida del volumen `pgdata`**: sobrevive a `stop`, `restart`, `down` y a la
recreación de contenedores. Solo `down -v` o borrarlo de forma explícita elimina los datos
(RNF-010).
