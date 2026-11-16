# ADR-001: Optimización de la Consulta de Incidentes Activos mediante Índice Parcial Cubriente y Evaluación Híbrida de SLA

- **Estado**: Aceptado
- **Fecha**: 2026-11-16
- **Autor(es)**: Equipo de Ingeniería IncidentOps
- **Componentes Afectados**: [`src/incident_repository.py`, `src/sla_calculator.py`, `src/models.py`]

---

## 1. Contexto y Problema

El método `get_active_incidents_summary(component_filter, reference_time)` en `src/incident_repository.py` constituye una ruta crítica de lectura dentro de IncidentOps. Actualmente, su implementación presenta severos cuellos de botella de rendimiento y consumo de recursos:

1. **Escaneo completo de tabla y materialización en memoria**: Ejecuta `SELECT * FROM incidents` recuperando las 10,000 filas completas con `cursor.fetchall()`, transfiriendo columnas innecesarias (como `title` o `resolved_at`) y delegando el filtrado de estado (`OPEN`, `IN_PROGRESS`) y componente (`component_filter`) a la capa de aplicación en Python.
2. **Anti-patrón de consultas N+1**: Por cada incidente activo coincidente, abre un nuevo cursor y ejecuta una consulta individual (`SELECT max_resolution_minutes FROM sla_policies WHERE severity = ?`) cuyo resultado además es descartado (`_ = policy_cursor.fetchone()`), ya que las reglas de SLA están definidas estáticamente en memoria en `SLA_POLICY_TABLE` (`src/sla_calculator.py`).
3. **Restricciones de negocio y arquitectura**:
   - **Cero dependencias externas**: Debe utilizarse exclusivamente el módulo `sqlite3` de la librería estándar de Python.
   - **Seguridad**: Toda consulta dinámica debe emplear parámetros enlazados (`?`) para prevenir inyección SQL.
   - **Determinismo e integridad de dominio**: El cálculo de SLA debe preservar la firma exacta `evaluate_sla_status(incident: Incident, reference_time: datetime)` y respetar la lógica de calendario laboral para severidades `P2` y `P3` (`operates_24x7=False`), lo cual impide delegar el cálculo de `elapsed_minutes` a funciones de fecha estándar en SQLite.

---

## 2. Opciones Consideradas

1. **Opción A — Mantener el diseño actual con caché en memoria para `sla_policies`**:
   - *Ventajas*: Cambios mínimos en el código existente; elimina el problema N+1 sobre `sla_policies`.
   - *Desventajas*: Mantiene el escaneo completo de tabla (`SELECT * FROM incidents`), la alta asignación de memoria por `fetchall()` y la deserialización innecesaria de registros inactivos o de otros componentes.

2. **Opción B — Cálculo integral de SLA y filtrado en SQLite o mediante un ORM externo**:
   - *Ventajas*: Reduce la transferencia de datos a una sola consulta agregada o abstrae el acceso a datos mediante modelos relacionales.
   - *Desventajas*: Calcular `elapsed_minutes` directamente en SQLite rompe la regla de negocio de horario no 24x7 (`operates_24x7=False`) para incidentes `P2` y `P3`. Asimismo, incorporar un ORM externo viola la restricción de utilizar únicamente `sqlite3` de la librería estándar.

3. **Opción C — Filtrado e índice parcial cubriente en SQLite + Streaming por cursor y evaluación de SLA en Python (Elegida)**:
   - *Ventajas*: Empuja el filtrado y la proyección mínima al motor de base de datos con acceso *Index-Only Scan*; elimina las consultas N+1 y la materialización masiva mediante iteración en *streaming* sobre el cursor; conserva intacta la lógica determinista de `evaluate_sla_status` y cumple todas las restricciones técnicas.
   - *Desventajas*: Requiere mantener sincronizado el índice parcial `idx_incidents_active_component` en el esquema DDL y construir instancias parciales/ligeras de `Incident` (`title=""`, `resolved_at=None`) en el repositorio.

---

## 3. Decisión Arquitectónica

Se adopta la **Opción C (Arquitectura Híbrida: Índice Parcial Cubriente en SQLite + Streaming y Evaluación de SLA en Python)**.

La responsabilidad se divide según las fortalezas de cada capa:
- **Capa de Persistencia (SQLite)**: Se crea un índice parcial cubriente (`idx_incidents_active_component`) sobre `(component, status, incident_id, severity, created_at) WHERE status IN ('OPEN', 'IN_PROGRESS')`. La consulta proyecta únicamente las cuatro columnas requeridas (`incident_id`, `severity`, `status`, `created_at`) filtrando por `WHERE component = ? AND status IN ('OPEN', 'IN_PROGRESS')` mediante marcadores de posición estrictos (`?`).
- **Capa de Aplicación (Python)**: Se elimina por completo la consulta N+1 a `sla_policies`. En lugar de invocar `fetchall()`, se itera directamente sobre el `cursor` en *streaming*, instanciando objetos `Incident` ligeros (`title=""`, `resolved_at=None`) y delegando el cálculo exacto de tiempos efectivos y cumplimiento de SLA a `evaluate_sla_status(incident, reference_time=reference_time)`.

```mermaid
flowchart LR
    subgraph Flujo_Anterior["Flujo Anterior (Anti-patrón N+1)"]
        direction LR
        A1["get_active_incidents_summary()"] --> B1["SELECT * FROM incidents\n(10,000 filas)"]
        B1 --> C1["cursor.fetchall()\nMaterialización en RAM"]
        C1 --> D1{"Filtro en Python\nstatus & component"}
        D1 -- "Por cada match (N)" --> E1["SELECT sla_policies\n(Consulta N+1 descartada)"]
        E1 --> F1["evaluate_sla_status()\n& append()"]
    end

    subgraph Flujo_Optimizado["Flujo Optimizado (Índice Cubriente + Streaming)"]
        direction LR
        A2["get_active_incidents_summary()"] --> B2["SELECT incident_id, severity,\nstatus, created_at\nWHERE component = ? AND status IN (...)"]
        B2 --> C2["Index-Only Scan\n(idx_incidents_active_component)"]
        C2 --> D2["Iteración Streaming\nsobre Cursor"]
        D2 --> E2["Incident ligero +\nevaluate_sla_status()"]
    end