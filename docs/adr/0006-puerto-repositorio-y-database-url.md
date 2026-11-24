# ADR-006: Puerto de repositorio de incidentes y selección del adaptador por `DATABASE_URL`

- **Estado**: Aceptado
- **Fecha**: 2026-11-24
- **Autor(es)**: Equipo de Ingeniería IncidentOps
- **Reemplaza a**: —

---

## 1. Contexto y Problema

ADR-003 adoptó la arquitectura hexagonal y anunció un `IncidentRepositoryPort` mínimo
(activos por componente y estado, guardar, localizar un equivalente abierto). Hasta H001
el puerto no existía: el triaje no tiene efectos y la persistencia seguía en el módulo plano
`src/incident_repository.py`, que mezclaba SQL, entidades y SLA.

H002 (resumen de incidentes activos) es el primer caso de uso que lee incidentes. Exige
decidir: (a) la forma exacta del puerto, que todos los adaptadores presentes y futuros
(SQLite, nulo, base dedicada de H004) deberán implementar; (b) cómo elige la raíz de
composición el adaptador; (c) el papel de la tabla `sla_policies` heredada; y (d) de dónde
salen los datos mientras nadie registra incidentes (H003).

El Art. III.2 de la Constitución exige justificar en un ADR o en la especificación todo
método que exceda el catálogo mínimo. Este ADR cumple ese requisito. También sustenta la
ampliación del contrato de canales (F3) con la consulta del resumen.

---

## 2. Opciones Consideradas

1. **Opción A — Puerto de un solo método (`list_active_incidents`)**:
   - *Ventajas*: mínimo absoluto; un solo método que mantener en cada adaptador.
   - *Desventajas*: H003 reabriría el puerto y todos sus adaptadores; la verificación de
     solo lectura (E12, SC-005) necesitaría leer el almacén por fuera del puerto.
2. **Opción B — Puerto de cinco métodos con consumidor declarado y selección por `DATABASE_URL`**:
   - *Ventajas*: cubre el catálogo de ADR-003 más dos operaciones con consumidor concreto;
     cada adaptador se escribe una vez; la selección por URL deja el cambio de motor de H004
     en un adaptador nuevo más una línea de composición.
   - *Desventajas*: dos métodos sin consumidor productivo en H002 (`find_open_duplicates`
     solo se ejercita en pruebas de conformidad hasta H003).
3. **Opción C — Repositorio concreto inyectado sin puerto**:
   - *Ventajas*: menos indirección.
   - *Desventajas*: la aplicación dependería de SQLite; viola Art. 2.3 y III.6.

---

## 3. Decisión Arquitectónica

Se adopta la **Opción B**.

**Puerto** (`src/application/ports.py`, `typing.Protocol`, sin `@runtime_checkable`):

| Método | Consumidor en H002 | Consumidor futuro |
|---|---|---|
| `save_incident(incident)` | Siembra de demostración; preparación de pruebas | Registro de incidentes (H003) |
| `get_incident(incident_id)` | Verificación de solo lectura (E12, SC-005) | Ciclo de vida (H003) |
| `find_open_duplicates(component, created_from, created_to)` | Conformidad | Alerta de duplicado abierto (H003, Art. 1.11) |
| `list_active_incidents(component=None)` | `IncidentService.get_active_incidents_summary` | — |
| `check_health()` | Fallo temprano en la raíz de composición | Sonda de disponibilidad (H004) |

«Abierto» en `find_open_duplicates` significa **activo** en el sentido del Art. 1.10
enmendado (ADR-005). La ventana la calcula quien llama, porque la ventana de fusión es
regla de dominio.

**Adaptadores** (`src/adapters/outbound/`): `SQLiteIncidentRepository` (`sqlite3` de la
librería estándar, marcadores `?`, una conexión `check_same_thread=False` protegida por un
candado), `NullIncidentRepository` para operaciones sin efectos (Art. III.4) y
`create_incident_repository(database_url)` en `factory.py`.

**Selección por `DATABASE_URL`**: solo `src/main.py` lee la variable (por defecto
`sqlite:///:memory:`). `sqlite:///:memory:` crea el almacén y siembra el conjunto fijo de
demostración (`demo_incidents.py`, `INC-2001`…`INC-2008`); `sqlite:///<ruta>` abre o crea
el archivo sin sembrar; cualquier otro esquema falla al arrancar con un mensaje que nombra
solo el esquema. Tras construir el adaptador, la raíz exige `check_health()`.

**`sla_policies`**: se conserva como espejo sembrado desde `SLA_POLICY_TABLE` y como destino
de la clave foránea `incidents.severity`. La consulta de activos hace `INNER JOIN
sla_policies` para garantizar que toda fila leída tenga política evaluable, pero no proyecta
ninguna columna de la tabla: la política sigue viviendo solo en el dominio (Art. 1.1).

**Contrato de canales de H002**: `GET /api/v1/incidents/summary` (parámetros `component` y
`reference_time`) y el subcomando CLI `summary` (`--component`, `--reference-time`,
`--format table|json`), con el mismo cuerpo JSON proyectado por `summary_to_contract`.

---

## 4. Consecuencias y Trade-offs

- **Positivas**:
  - Los casos de uso se prueban con dobles en memoria (Art. III.6); SQLite solo aparece en
    las pruebas de conformidad del adaptador.
  - H003 y H004 implementan contra un puerto estable; cambiar de motor es un adaptador más
    una rama en la fábrica.
  - Ruff y la prueba AST impiden que `application` importe adaptadores o lea el entorno.
- **Negativas / Trade-offs**:
  - Cinco métodos que todo adaptador debe implementar, dos de ellos sin uso productivo en
    H002.
  - Un único candado serializa el acceso a SQLite; suficiente para la consulta de H002
    (~200 ms con 12 857 activos), a revisar con escrituras concurrentes en H003.
  - Admitir `sqlite:///<ruta>` deja preparado el punto de extensión de H003, pero en H002 un
    archivo nuevo produce un resumen vacío: no hay persistencia de incidentes hasta H003.
