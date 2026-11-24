# Investigación (Fase 0): Registro, duplicado abierto y auditoría de SLA (H003)

**Fecha**: 2026-11-24 | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Cada sección fija una decisión, su motivo y las alternativas descartadas. El contexto
técnico del plan no deja `NEEDS CLARIFICATION`: todo se resuelve aquí.

Línea base medida en el repositorio (2026-11-24, `main` @ `5155d35`):

- `IncidentRepositoryPort` ya declara `save_incident`, `get_incident` y
  `find_open_duplicates`, y `SQLiteIncidentRepository` ya los implementa.
  - `save_incident` hace **upsert** (`ON CONFLICT DO UPDATE`), y la conformidad de spec 002
    lo verifica (`tests/test_spec_002_summary.py:153-154`).
  - `find_open_duplicates(component, created_from, created_to)` usa la semántica de
    ventana de ADR-006 y no tiene consumidor productivo.
- `Incident` no tiene `recommended_team` ni `duplicate_group_key`.
- `classify_incident_batch` solo asigna `duplicate_group_key` dentro de un lote de ≥ 2
  reportes (`_correlate_availability`, `_correlate_performance`). Un reporte suelto tiene
  clave `null`.
- `evaluate_sla_status` mide hasta `resolved_at` aunque `reference_time` sea anterior. El
  escalamiento depende de `status != "RESOLVED"`, no del instante.
- El CLI usa `EXIT_INVALID_INPUT = 3`. `tests/test_spec_001_triage.py:151` y
  `tests/test_spec_002_summary.py:753` lo verifican.
- `ruff 0.17.6`. `docs/constitution.md` (superior según `AGENTS.md`) no fija códigos de
  salida. `.specify/memory/constitution.md` 2.1.0 sí, en F3.

---

## R1. Clave de grupo de un solo reporte

**Decisión.** Añadir a `src/domain/triage_rules.py` la función pública
`group_key_for(component: str, signals: IncidentSignals) -> Optional[str]`. Calcula las
formas canónicas del Art. 1.11 a partir de un solo reporte:

| Condición (mismas señales que la correlación por lote) | Clave |
|---|---|
| `signals.service_outage` y `component != "unclassified"` | `f"{component.split('-')[0]}-availability"` |
| `component == "application-performance"` y `signals.high_data_volume` | `"database-performance-investigation"` |
| `component == "database-cluster"` y `signals.infra_saturated` | `"database-performance-investigation"` |
| cualquier otro caso | `None` |

Las funciones de correlación por lote pasan a usar `group_key_for` para construir la clave.
**Siguen exigiendo ≥ 2 miembros para asignarla.** La salida de `classify_incident_batch`
no cambia: la auditoría `-m src.triage_rules` y spec 001 quedan idénticas (Art. 1.5, 1.12).

Una segunda función pública, `classify_incident(report) -> TriageResult`, clasifica un
reporte suelto y devuelve la clave candidata en `duplicate_group_key`, con
`duplicate_type="none"` y `merge=False`. Es lo que consume `create_incident`.

**Motivo.** La regla de clave pertenece al dominio (Art. 1.1, 1.11): el servicio solo
compara igualdad. Reutilizar la misma función en el lote garantiza un solo formato.

**Alternativas descartadas.**
- Calcular la clave en `IncidentService` repite la regla fuera del dominio (viola Art. 1.1).
- Llamar a `classify_incident_batch([report])`: devuelve `null` por diseño (spec 001 §5.2).
- Correlacionar el reporte nuevo en un lote con los abiertos del almacén: mezcla
  reportes con incidentes, cambia `analysis` y depende de cuántos haya.

## R2. Normalización naive/aware y reconstrucción en el dominio

**Decisión.** `evaluate_sla_status(incident, reference_time)` en
`src/domain/sla_calculator.py`:

1. Normaliza **las tres** marcas con `to_bogota` en la entrada (`created_at`,
   `resolved_at`, `reference_time`). Naive = Bogotá (Art. 1.7). Todas las comparaciones
   internas usan esos valores normalizados.
2. Calcula `resolved_at_reference = resolved_at is not None and resolved_at <= reference`.
3. Usa `end = resolved_at if resolved_at_reference else reference`, es decir, el menor de
   los dos instantes.
4. `requires_escalation = not resolved_at_reference and not is_breached and elapsed >= limit`.
   Deja de depender de `status`: el estado que importa es el que tenía el incidente en el
   instante consultado (FR-015).
5. `SLAEvaluation` gana `resolved_at_reference: bool = False` (valor por defecto
   compatible).
6. Si `reference < created_at`, sigue lanzando `ValueError`. El servicio valida antes y
   traduce a `reference_before_creation` (R6).

Regresión: los 10 casos de `_run_demo()` no tienen `resolved_at`, así que su resultado no
cambia. Se añaden dos casos (E10.1 y E10.2) para cubrir el cambio de regla, como exige el
Art. 1.12. H002 solo evalúa activos sin `resolved_at`: el resumen no cambia.

Hay un caso límite: un `RESOLVED` sin `resolved_at` es inconsistente (Art. 1.10), y
`create_incident` lo rechaza. Para datos heredados, el dominio lo trata como no resuelto
en el instante. Es el mismo comportamiento de hoy para un activo.

**Alternativas descartadas.** Calcular `min(reference, resolved_at)` en el servicio y
pasar un `Incident` modificado, que esconde una regla de SLA en `application`. Dejar
`status` como criterio de escalamiento: E10.1 fallaría (escalamiento "no" a las 11:30
cuando el incidente aún estaba abierto).

## R3. Entidad `Incident` extendida

**Decisión.** Añadir a `Incident` (`src/domain/models.py`) dos campos al final, con valor
por defecto `None`:

- `recommended_team: Optional[TeamName] = None`
- `duplicate_group_key: Optional[str] = None`

Esto conserva la construcción posicional existente (`demo_incidents.py`, pruebas de
spec 002).

**Motivo.** Pedido explícito del plan. El equipo forma parte de la clasificación que se
devuelve al crear. La clave es lo que se compara para detectar duplicados (D5: se persiste
la clave, no el aviso). La severidad y el componente ya estaban en la entidad.

**Alternativas descartadas.** Una entidad nueva `RegisteredIncident`: duplica `Incident` y
obliga al resumen de H002 a conocer dos tipos. Guardar el `TriageResult` completo: el
`analysis` es presentación (spec 001 D6) y no hace falta para auditar.

## R4. Contrato del puerto: inserción sin reemplazo y búsqueda por clave

**Decisión.** `IncidentRepositoryPort` queda así:

| Método | Cambio | Consumidor |
|---|---|---|
| `save_incident(incident)` | Sin cambio: upsert. | Siembra de demostración, preparación de pruebas, arnés de benchmark. |
| `add_incident(incident)` | **Nuevo.** Inserta sin reemplazar. Si el identificador existe, lanza `IncidentIdConflictError` (declarada en `ports.py`). | `create_incident` (FR-004, `409`). |
| `get_incident(incident_id)` | Sin cambio. Ahora devuelve también `recommended_team` y `duplicate_group_key`. | `evaluate_incident_sla`. |
| `find_open_duplicates(duplicate_group_key, exclude_incident_id)` | **Cambia de firma y semántica.** Devuelve los activos con esa clave y un identificador distinto, ordenados por `(created_at, incident_id)`. | `create_incident` (FR-007). |
| `list_active_incidents`, `check_health` | Sin cambio. | H002, composición. |

**Motivo.**
- **409 sin carrera.** Un `get_incident` seguido de `save_incident` deja una ventana en
  la que dos creaciones con el mismo identificador se pisan. La restricción de clave
  primaria resuelve el conflicto en un único `INSERT` atómico.
- **`save_incident` no cambia.** Cambiarlo a solo inserción rompería la conformidad de
  spec 002 (Art. 5.6). La siembra de demostración necesita idempotencia.
- **`find_open_duplicates` se reutiliza.** Es el método que el Art. 2.4 ya prevé
  ("localizar equivalente abierto"). Su semántica de ventana no tenía consumidor
  productivo (ADR-006). Cambiar su firma evita un sexto método muerto. No hay ADR que
  reemplace la fila correspondiente de ADR-006: la Constitución 3.0.0 la desplaza y la
  falta de ADR queda registrada como desviación de gobernanza (plan G19). La conformidad
  de spec 002 se adapta con la enmienda de su contrato de puerto (D8 de la spec).

**Alternativas descartadas.**
- Mantener la firma de ventana y añadir `find_open_by_group_key`: deja un método sin uso
  en todos los adaptadores.
- Validar el conflicto solo en el servicio: hay carrera.
- Que el puerto devuelva `bool` en lugar de lanzar: obliga a cada llamador a recordar
  comprobarlo.

## R5. Orden "guardar y luego buscar" (atomicidad de FR-011)

**Decisión.** `create_incident` hace `add_incident(nuevo)` y **después**
`find_open_duplicates(clave, exclude_incident_id=nuevo.id)`.

**Motivo.** Con este orden, de dos creaciones concurrentes con la misma clave, la que
guarda en segundo lugar busca después de que la primera ya está guardada, así que la ve.
Esto cumple FR-011 sin candados adicionales, incluso entre procesos (CLI y servidor sobre
el mismo archivo SQLite). Es exactamente el criterio clarificado: "excluyendo el propio
identificador recién creado".

**Riesgo residual.** Si la búsqueda falla después de guardar, el incidente queda
guardado y la respuesta es `500`. El registro está completo, no parcial, pero el cliente
no recibe su identificador. Se documenta en `quickstart.md` y se acepta: la lectura falla
mucho menos que la escritura, y el cliente puede enviar `incident_id` para reintentar de
forma idempotente (el reintento recibe `409`, lo que confirma que existe).

**Alternativas descartadas.**
- Buscar y luego guardar: dos creaciones simultáneas no se ven.
- Un método `add_and_find` transaccional en el puerto: mezcla dos responsabilidades y
  añade un método más.
- Un candado en el servicio: no protege entre procesos.

## R6. Validación y errores en la capa de aplicación

**Decisión.** Toda regla de aceptación vive en `IncidentService`, compartida por ambos
canales.

| Regla | Excepción | HTTP | CLI |
|---|---|---|---|
| `title`/`raw_text` vacío, solo espacios o demasiado largo (200/5 000) | `ValidationError("invalid_payload")` | 422 | 1 |
| `incident_id` que no cumple `^INC-[A-Za-z0-9-]{1,32}$` | `ValidationError("invalid_payload")` | 422 | 1 |
| `status` fuera del conjunto, `RESOLVED` sin `resolved_at`, `resolved_at` con estado activo o anterior a `created_at` | `ValidationError("invalid_payload")` | 422 | 1 |
| Instante no parseable (`created_at`, `resolved_at`, `reference_time`) | `ValidationError("invalid_timestamp")` | 422 | 1 |
| `reference_time < created_at` | `ValidationError("reference_before_creation")` | 422 | 1 |
| Identificador inexistente | `IncidentNotFoundError` (nueva, en `services.py`) | 404 `incident_not_found` | 1 |
| Identificador repetido | `IncidentIdConflictError` (nueva, en `ports.py`; la lanza el adaptador y el servicio la deja pasar) | 409 `incident_id_conflict` | 1 |
| Campo o bandera desconocidos, o campos reservados (`severity`, `component`, `recommended_team`, `action`, `duplicate_group_key`) | pydantic `extra="forbid"` / Typer | 400 | 2 |
| Fallo del almacén | cualquier otra | 500 `internal_error` | 4 |

`parse_reference_time` se generaliza a `parse_instant(value, field)`. Se conserva el
nombre anterior como alias para no tocar H002.

**Motivo.** Así, aceptación y rechazo son idénticos en los dos canales por construcción
(Art. 2.7). Los adaptadores solo traducen excepciones a códigos.

**Alternativas descartadas.** Validar longitudes con `Field(max_length=…)` en pydantic: el
CLI tendría que repetirlo y la paridad dependería de mantener dos copias.

## R7. Identificador generado `INC-<HEX8>`: puerto `IncidentIdGeneratorPort`

**Decisión.** Nuevo `Protocol` en `ports.py`: `IncidentIdGeneratorPort.new_id() -> str`.
Tiene dos implementaciones:

- `RandomHexIdGenerator` en `src/adapters/outbound/id_generator.py`: `secrets.token_hex(4).upper()`.
- `SequenceIdGenerator(ids)` en `tests/doubles.py`: secuencia fija, para pruebas
  deterministas.

`IncidentService(clock, repository, id_generator=None)`: el tercer parámetro es opcional
para no romper la construcción de H001 y H002. Si falta, `create_incident` falla con
`RuntimeError`, que se traduce a 500/4: el servicio nunca improvisa aleatoriedad. Ante
`IncidentIdConflictError` con un identificador **generado**, el servicio reintenta con
otro, hasta 5 veces. Con un identificador **enviado**, propaga el conflicto (409).

**Motivo.** Generar aleatoriedad dentro de `application` rompe el Art. 1.3 igual que leer
el reloj. Inyectarla mantiene el servicio determinista y comprobable. Es un puerto nuevo:
el Art. 2.4 de `docs/constitution.md` y el Art. 3.2 de spec-kit exigen justificarlo y
ampliar el catálogo. Este apartado es la justificación (el Art. 3.2 de spec-kit admite
que esté en la especificación); la ampliación del catálogo se hace con la enmienda D8,
sin ADR (plan G19).

**Alternativas descartadas.**
- `secrets` llamado directamente en el servicio: no determinista y no sustituible.
- Derivar el identificador del reloj o de un contador SQLite: rompe la forma `HEX8`
  pedida y acopla el formato al motor.
- `Callable[[], str]` sin `Protocol`: es el mismo puerto sin nombre ni verificación de
  conformidad.

## R8. Esquema SQLite e índice `idx_incidents_dup_key`

**Decisión.**
- `incidents` gana `recommended_team TEXT NULL` y `duplicate_group_key TEXT NULL`.
- Para almacenes de archivo creados por H002, `_init_schema` aplica una migración aditiva
  idempotente: lee `PRAGMA table_info(incidents)` y ejecuta `ALTER TABLE … ADD COLUMN`
  solo si la columna falta. Son sentencias constantes, sin concatenar valores.
- Índice nuevo:

```sql
CREATE INDEX IF NOT EXISTS idx_incidents_dup_key
ON incidents (duplicate_group_key, status)
WHERE status <> 'RESOLVED' AND duplicate_group_key IS NOT NULL
```

- `find_open_duplicates` usa el predicado literal
  `i.status <> 'RESOLVED' AND i.duplicate_group_key = ? AND i.incident_id <> ?`, con
  `INNER JOIN sla_policies`, y ordena por `(created_at, incident_id)`.
- `add_incident` usa `INSERT` sin `ON CONFLICT` y traduce `sqlite3.IntegrityError` sobre
  la clave primaria en `IncidentIdConflictError`. Otras violaciones de integridad (por
  ejemplo, la FK de severidad) siguen siendo `ValueError`, como en `save_incident`.

**Motivo.** El índice tiene exactamente las columnas que pidió el plan,
`(duplicate_group_key, status)`. Lleva el mismo predicado parcial que ADR-005, para que
SQLite lo use al buscar abiertos. Excluir las claves nulas lo mantiene pequeño: la
mayoría de los incidentes no tiene clave. Con 10 000 abiertos, la búsqueda es un rango
de índice, no un recorrido (SC-006).

**Alternativas descartadas.**
- Índice no parcial: indexa resueltos que nunca se consultan.
- Tabla `duplicate_groups` aparte: es vínculo persistente, fuera de alcance (D5).
- Recrear la tabla para migrar: arriesga datos en archivos existentes.

## R9. Clave y equipo de los incidentes de demostración

**Decisión.** `seed_demo_incidents` calcula `duplicate_group_key` y `recommended_team` de
cada demo con `classify_incident(IncidentReport(id, title, created_at))`, es decir,
aplicando el dominio al **título**. La siembra conserva la severidad, el componente y el
estado de las constantes, que son el contrato de demostración de spec 002. Solo añade los
dos campos derivados.

**Motivo.** Los demos no tienen texto crudo (spec, Supuestos). Así,
`INC-2001` ("Caída de la pasarela de pagos") recibe `payment-availability` y un `create`
de caída de pagos lo detecta como duplicado en la demo, sin escribir claves a mano.

**Alternativas descartadas.** Escribir las claves a mano en las constantes: es una
segunda fuente de verdad del Art. 1.11. Dejarlas nulas: la demo nunca mostraría un
duplicado.

## R10. Proyecciones únicas al contrato

**Decisión.** Dos funciones nuevas en `services.py`, usadas por ambos canales:

- `creation_to_contract(creation: IncidentCreation) -> Dict`
- `sla_audit_to_contract(audit: IncidentSLAAudit) -> Dict`

Los instantes salen ya como cadena ISO con desfase (`-05:00`), igual que
`summary_to_contract` (research de spec 002 §R9). Los DTO de respuesta los declaran como
`str`.

**Motivo.** Paridad por construcción (Art. 2.7): ningún canal re-serializa un `datetime`.

## R11. Códigos de salida del CLI (`3` → `1`)

**Decisión.** `EXIT_INVALID_INPUT = 1` en `cli.py` para **todos** los subcomandos. El
cambio se hace en la Fase A (enmienda), en su propio commit, junto con:

- spec-kit 3.0.0, F3, sin ADR (desviación registrada, plan G19);
- `AGENTS.md`;
- spec 001 §7 y spec 002 (contrato CLI);
- las dos aserciones `exit_code == 3`, que pasan a `== 1`.

Las aserciones se cambian **después** de enmendar sus specs, como exige el Art. 5.6.

**Motivo.** Clarificación del 2026-11-24. Cambiar el significado de un código publicado es
una redefinición incompatible: MAJOR según el versionado de la Constitución.

**Alternativas descartadas.** Usar `1` solo en `create`/`sla` (descartado por el usuario).
Mantener `3` (descartado por el usuario).

## R12. Pruebas de aceptación de spec 003

**Decisión.** `tests/test_spec_003_lifecycle_sla.py`, con una función `test_bdd_*` por
escenario (norma `bdd-acceptance`), sobre SQLite desechable en `tmp_path` por prueba y con
reloj fijo.

- **Los cinco pedidos** son el primer incremento (MVP de pruebas). Por la regla 1:1, el
  punto 4 son dos funciones (E13 y E14), así que suman **seis funciones**:
  `test_bdd_e1_…`, `test_bdd_e5_…`, `test_bdd_e12_…`, `test_bdd_e13_…`,
  `test_bdd_e14_…` y `test_bdd_e11_…`.
- **El resto de escenarios aceptados** (E2–E4, E6, E8–E10, E15a–E23) se automatiza en el
  mismo archivo en incrementos posteriores. El Art. 5.2 de spec-kit exige una prueba por
  escenario aceptado: entregar solo los cinco dejaría la capacidad sin cerrar (F4).
- La paridad E11 usa dos almacenes desechables equivalentes y un identificador informado
  en `create`. La conformidad del puerto nuevo (`add_incident`, `find_open_duplicates` v2)
  vive en el mismo archivo y compara `SQLiteIncidentRepository` con
  `InMemoryIncidentRepository`.
