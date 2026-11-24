# ADR-005: Incidente activo es todo estado distinto de `RESOLVED`

- **Estado**: Aceptado
- **Fecha**: 2026-11-24
- **Autor(es)**: Equipo de Ingeniería IncidentOps
- **Reemplaza a**: ADR-001 §3, parcialmente (predicado y columnas del índice parcial)

---

## 1. Contexto y Problema

El Art. 1.10 de la Constitución consideraba activos solo los estados `OPEN` e
`IN_PROGRESS`, y ADR-001 fijó en consecuencia el índice parcial
`idx_incidents_active_component` con el predicado `status IN ('OPEN', 'IN_PROGRESS')`.

H002 (resumen de incidentes activos) obliga a decidir qué incidentes cuentan como
trabajo en curso. En la clarificación del 2026-11-24 de `specs/002-active-incident-summary`,
el producto decidió que un incidente en `ESCALATION_REQUIRED` sigue activo: es justo el
que la guardia debe ver primero. Con la definición vigente, el tablero ocultaría los
incidentes más urgentes y el índice de ADR-001 dejaría fuera esas filas.

La decisión es normativa (cambia un término de la Constitución) y estructural (cambia el
predicado del índice que sostiene la ruta crítica de lectura), por eso se registra como ADR
y se aplica antes de implementar cualquier requisito que dependa de ella.

---

## 2. Opciones Consideradas

1. **Opción A — Mantener `OPEN` e `IN_PROGRESS` como únicos activos**:
   - *Ventajas*: no exige enmienda; el índice de ADR-001 queda intacto.
   - *Desventajas*: los incidentes marcados para escalar desaparecen del resumen operativo;
     el total activo subestima la carga real de la guardia.
2. **Opción B — Activo = todo estado distinto de `RESOLVED`**:
   - *Ventajas*: una sola regla simple y estable ante estados futuros no terminales; el
     resumen refleja todo el trabajo pendiente; el predicado `status <> 'RESOLVED'` coincide
     literalmente con la regla.
   - *Desventajas*: enmienda MAJOR de la Constitución; el índice parcial cambia de
     predicado y crece con las filas `ESCALATION_REQUIRED`.
3. **Opción C — Lista explícita de tres estados (`IN ('OPEN', 'IN_PROGRESS', 'ESCALATION_REQUIRED')`)**:
   - *Ventajas*: el conjunto queda enumerado.
   - *Desventajas*: un estado no terminal nuevo quedaría fuera en silencio; misma enmienda
     que la opción B sin su simplicidad.

---

## 3. Decisión Arquitectónica

Se adopta la **Opción B**.

- **Dominio**: la definición vive en `src/domain/models.py` como
  `ACTIVE_STATUSES = frozenset({"OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED"})` (Art. 1.1).
  Los casos de uso filtran con esa constante.
- **Persistencia**: el adaptador SQLite reemplaza el índice de ADR-001 por un índice
  compuesto, parcial y cubriente que empieza por `(component, status)`:

  ```sql
  CREATE INDEX IF NOT EXISTS idx_incidents_active_component
      ON incidents (component, status, severity, created_at, incident_id, title)
      WHERE status <> 'RESOLVED';
  ```

  La consulta repite literalmente el predicado `status <> 'RESOLVED'` para que SQLite pueda
  usar el índice parcial (con parámetros `?` el planificador no demuestra la implicación).
  Se añade `title` porque el resumen lo proyecta. Una prueba de conformidad garantiza que el
  predicado SQL devuelve exactamente los estados de `ACTIVE_STATUSES`.
- **Se conserva de ADR-001**: filtrado en SQLite, marcadores `?`, iteración sobre el cursor
  sin consultas N+1 y evaluación del SLA en Python con `evaluate_sla_status`.

---

## 4. Consecuencias y Trade-offs

- **Positivas**:
  - El resumen operativo y cualquier consumidor futuro comparten una única definición de
    activo, declarada en el dominio.
  - El índice cubre también la consulta global (sin filtro de componente) con un recorrido
    del índice parcial, además de la búsqueda por componente.
- **Negativas / Trade-offs**:
  - Enmienda MAJOR (2.0.0) de `.specify/memory/constitution.md` y cambio idéntico en
    `docs/constitution.md`.
  - Dos expresiones de la misma regla (constante de dominio y predicado SQL literal) que
    deben mantenerse alineadas; la prueba de conformidad es la salvaguarda.
  - `requires_escalation` (derivado del SLA) y el estado `ESCALATION_REQUIRED` (ciclo de
    vida) siguen siendo conceptos distintos (Art. 1.8); este ADR no los fusiona.
