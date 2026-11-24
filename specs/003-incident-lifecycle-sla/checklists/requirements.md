# Lista de verificación de calidad de la especificación: Registro de incidentes, aviso de equivalentes y consulta de SLA

**Propósito**: Validar que la especificación esté completa y sea de calidad antes de
pasar a la planificación.

**Creado**: 2026-11-24

**Funcionalidad**: [spec.md](../spec.md)

## Calidad del contenido

- [x] Sin detalles de implementación (lenguajes, frameworks, APIs)
      — Las rutas, los subcomandos y los campos son el contrato observable que pidió el
      usuario ("por API y desde nuestra herramienta CLI"). No se nombran frameworks,
      módulos internos, tablas ni métodos de puerto. El formato exacto del identificador
      y la forma de garantizar la atomicidad quedan para el plan.
- [x] Enfocada en el valor para el usuario y las necesidades del negocio
      — Que ningún reporte se pierda, que la guardia no gestione dos veces el mismo evento
      y que el SLA sea auditable en cualquier instante.
- [x] Redactada para partes interesadas no técnicas
      — El resumen y los escenarios obligatorios usan vocabulario de operación. Un
      glosario traduce cada término al contrato.
- [x] Todas las secciones obligatorias están completas
      — Escenarios de usuario y pruebas, requisitos, criterios de éxito y supuestos.

## Completitud de requisitos

- [x] No quedan marcadores `[NEEDS CLARIFICATION]`
      — Las dos decisiones de alcance (qué es "equivalente" y qué hacer al detectarlo) se
      resolvieron en la sesión de clarificación del 2026-11-24. El resto se resolvió como
      supuestos explícitos.
- [x] Los requisitos son verificables y no ambiguos
      — Cada FR tiene un escenario asociado en la tabla de trazabilidad. Los límites
      numéricos son explícitos: 5 000 y 200 caracteres, ventana de 30 minutos inclusiva y
      simétrica.
- [x] Los criterios de éxito son medibles
      — Porcentajes de recuperación, aviso y paridad, cero alteraciones, cuatro instantes
      por incidente y 1 s con 10 000 activos.
- [x] Los criterios de éxito son agnósticos a la tecnología
      — No mencionan frameworks, motores ni estructuras de datos.
- [x] Todos los escenarios de aceptación están definidos
      — E1–E23 (E7 retirado) en `Given / When / Then`, en español, con un solo `When`
      por escenario y tablas de ejemplos para las reglas con variantes (E6, E10, E11,
      E15a, E15b, E21). Los cinco comportamientos pedidos (registro inicial, duplicado
      abierto, SLA hábil determinista, 404/422 de auditoría y paridad CLI `create`/`sla`)
      son obligatorios y están mapeados a E1, E5, E12, E13–E14 y E11.
- [x] Los casos borde están identificados
      — Varios duplicados, duplicado antiguo o recurrente, reporte sin clave, componente
      sin clasificar, `ESCALATION_REQUIRED`, propio identificador, creación en `RESOLVED`,
      colisión de identificador generado, mayúsculas en el identificador, creación futura,
      caracteres especiales, instante igual a la creación o a la resolución, almacén en
      memoria y formato inválido.
- [x] El alcance está delimitado
      — La sección "Fuera de alcance" excluye ciclo de vida, fusión, lotes, notificaciones,
      listados, autenticación, MCP, cambios de reglas y H004.
- [x] Las dependencias y los supuestos están identificados
      — Triaje, clave de grupo individual (D10), evaluación de SLA (ajuste D7), puerto del
      repositorio, enmienda MAJOR de F3 (D8), canales existentes y `DATABASE_URL`.

## Preparación de la funcionalidad

- [x] Todos los requisitos funcionales tienen un criterio de aceptación claro
      — FR-001 a FR-023 aparecen en la tabla de trazabilidad.
- [x] Los escenarios de usuario cubren los flujos principales
      — Creación (US1), aviso de duplicado abierto (US2) y auditoría de SLA con
      reconstrucción y paridad (US3).
- [x] La funcionalidad cumple los resultados medibles definidos en los criterios de éxito
      — SC-001 a SC-007 son observables con el contrato y los escenarios definidos.
- [x] No se filtran detalles de implementación en la especificación
      — Las decisiones de stack, persistencia concreta y estructura quedan para el plan.

## Notas

- Validación completada en la primera iteración, después de ajustar los escenarios a la
  norma BDD del repositorio: un solo `When` por escenario, sin "y/o", y E18 separado de
  E16.
- **Trabajo previo que el plan debe ordenar primero** (no bloquea la planificación):
  - D7: la evaluación canónica de SLA hoy mide un incidente resuelto hasta su resolución
    aunque el instante consultado sea anterior. FR-015 exige corregirlo en el dominio, con
    la regresión `_run_demo` actualizada (Art. 1.12).
  - D8: enmienda MAJOR de F3 (Constitución 3.0.0): rutas y subcomandos nuevos, y código de
    salida `1` en lugar de `3` en todo el CLI, con spec 001 y spec 002 enmendadas.
  - D10: el dominio debe calcular la clave de grupo de un reporte individual (Art. 1.12).
- D2 se desvía del texto del roadmap ("antes de crear el duplicado"): por decisión de
  producto, el aviso viaja en la misma respuesta del registro.
- 2026-11-24: la carpeta pasó de `specs/003-incident-registration-sla/` a
  `specs/003-incident-lifecycle-sla/`, a pedido del usuario.
