# Especificación de funcionalidad: Registro de incidentes, aviso de duplicado abierto y auditoría de SLA

**Rama de la funcionalidad**: `003-incident-lifecycle-sla`

**Creado**: 2026-11-24

**Estado**: Implementada (2026-11-24; F4 (f) pendiente: enmienda 3.0.0 sin ADR, desviación de gobernanza abierta)

**Entrada**: Descripción del usuario: "Necesitamos guardar los incidentes cuando llegan,
avisar si ya había otro equivalente abierto, y consultar cómo va su SLA tanto por API como
desde nuestra herramienta CLI."

**Hito**: H003 — Ciclo de vida, duplicados y SLA (`docs/ROADMAP.MD`), primer corte:
creación, aviso de duplicado abierto y auditoría de SLA por incidente. Las transiciones de
estado posteriores a la creación quedan para un corte posterior (D6).

**Autoridad**: subordinada a `docs/constitution.md`, que prevalece sobre esta
especificación, sobre los ADR y sobre el código.

---

## Resumen

IncidentOps deja de solo mirar incidentes y empieza a guardarlos. Al crear un incidente,
el sistema clasifica su texto con el motor de triaje existente y lo guarda con un
identificador: el que envía el cliente o uno generado. El incidente sobrevive al reinicio
del servicio.

Si al crearlo ya existe un incidente **abierto con la misma clave de grupo de
duplicados**, el sistema crea el nuevo de todos modos. En la misma respuesta indica que es
duplicado y de cuáles. Así quien recibe la respuesta puede decidir si los gestiona juntos.
Ningún reporte se pierde y ningún incidente existente se modifica.

Cualquier incidente puede auditarse después para saber cómo va su SLA, en el instante
actual o en cualquier instante de referencia. Esto incluye reconstruir lo que mostraba
antes de cerrarse y auditar un cierre posterior al plazo.

Ambas operaciones se ofrecen por HTTP y por CLI, con el mismo contrato JSON y los mismos
valores para el mismo almacén y el mismo instante (Art. 2.7).

La clasificación, la clave de grupo y la evaluación de SLA **no se definen aquí**: vienen
del dominio (Art. 1.1, 1.6–1.8, 1.11). Esta especificación fija qué se crea, cuándo se
avisa, qué se audita y con qué garantías.

---

## Clarifications

### Session 2026-11-24

- Q: ¿Qué cuenta como incidente "equivalente abierto"? (decisión pendiente del roadmap)
  → A: La regla de duplicado exacto del Art. 1.11: mismo componente, activo, ±30 min y
  sin marca de recurrencia. *Reemplazada por el criterio de `duplicate_group_key` más
  abajo.*
- Q: Cuando llega un reporte y ya existe un equivalente abierto, ¿qué hace el sistema?
  → A: Registra y avisa. El incidente nuevo se crea siempre y la respuesta incluye el
  aviso.
- Q: ¿Cuál es el contrato de creación? → A: `POST /api/v1/incidents` y el subcomando CLI
  `create`.
  - Obligatorios: `title` y `raw_text`. Si están vacíos o solo tienen espacios, se
    rechazan con `422` en la API y código de salida `1` en el CLI.
  - Opcionales: `incident_id` (si se omite, se genera `INC-<HEX8>`), `created_at` (si se
    omite, el instante actual) y `status` (por defecto `OPEN`).
  - Respuesta: `201 Created` en la API o JSON en el CLI, con la clasificación completa,
    `is_duplicate` (`bool`) y `duplicate_of` (`list[str]`).
- Q: ¿Cuál es el criterio exacto de duplicado abierto? → A: Coincidencia de
  `duplicate_group_key` únicamente, entre incidentes en estado abierto (`OPEN`,
  `IN_PROGRESS`, `ESCALATION_REQUIRED`). Se excluyen los `RESOLVED` y el propio
  identificador recién creado. Sin ventana de tiempo ni excepción por recurrencia.
- Q: ¿Cuál es el contrato de la auditoría de SLA? → A:
  `GET /api/v1/incidents/{incident_id}/sla` y el subcomando CLI `sla`, con
  `reference_time` opcional (ISO 8601) para evaluaciones deterministas.
  - Incidente inexistente: `404 Not Found`.
  - `reference_time` anterior a `created_at`: `422 Unprocessable Entity`.
  - En el CLI, ambos casos terminan con código de salida `1`.
- Q: La Constitución (F3) fija el código `3` para entrada inválida en el CLI. ¿Qué código
  usan `create` y `sla`? → A: El código `1`, y se usa en **todo** el CLI (`triage` y
  `summary` incluidos). Exige una enmienda MAJOR de F3 (D8).
- Q: Si el cliente envía un `incident_id` que ya existe, ¿qué hace el sistema? → A: Lo
  rechaza con `409 incident_id_conflict` (código de salida `1`). No se crea nada y el
  incidente existente queda intacto.
- Q: ¿Qué estados se aceptan al crear? → A: `OPEN`, `IN_PROGRESS` y
  `ESCALATION_REQUIRED`. `RESOLVED` solo se acepta con `resolved_at`, que es opcional y
  pasa a ser obligatorio con ese estado. `RESOLVED` sin `resolved_at`, `resolved_at` con
  un estado activo o cualquier otro valor de estado se rechazan con `422` (código `1`).
- Q: ¿La enmienda MAJOR se respalda con un ADR nuevo? → A: No. Se hace sin ADR y se
  registra como desviación de gobernanza abierta en ambas constituciones y en
  `AGENTS.md`, junto al ADR-004 pendiente. La justificación de cada cambio queda en el
  plan (research §R4, §R5, §R7 y §R11).

---

## Escenarios de usuario y pruebas

**Escenarios obligatorios del corte**: son el mínimo de cinco pedidos, redactados en
lenguaje de negocio:

| # | Comportamiento pedido | Escenario |
|---|---|---|
| 1 | Registro inicial sin duplicados previos | E1 |
| 2 | Detección de duplicado abierto, ignorando incidentes resueltos | E5 |
| 3 | Auditoría determinista de SLA en horario hábil | E12 |
| 4 | Auditoría de un identificador inexistente y de un instante anterior a la creación | E13 y E14 |
| 5 | Operación equivalente con los subcomandos CLI `create` y `sla` | E11 |

También son obligatorios E2 (el incidente sobrevive al reinicio), E9 (SLA de un incidente
activo) y E10 (reconstrucción del SLA a un instante pasado). El resto son complementarios.

**Lenguaje de los escenarios**: los escenarios obligatorios se redactan en lenguaje de
negocio. Cuando un paso verifica un valor exacto del contrato, ese valor se cita entre
paréntesis al final de la frase, para que la prueba no dependa de interpretación. Los
escenarios complementarios pueden citar códigos y campos del contrato directamente. La
automatización traduce cada término de negocio con este glosario:

| Término de negocio | HTTP | CLI |
|---|---|---|
| crear por la web | `POST /api/v1/incidents` | — |
| crear por la terminal | — | subcomando `create` |
| auditar el SLA por la web | `GET /api/v1/incidents/{incident_id}/sla` | — |
| auditar el SLA por la terminal | — | subcomando `sla <incident_id>` |
| formato estructurado | cuerpo JSON | `--format json` |
| creación exitosa | `201 Created` con JSON válido | código de salida `0`, resultado en `stdout` |
| consulta exitosa | `200 OK` con JSON válido | código de salida `0`, resultado en `stdout` |
| rechazo por entrada inválida | `422` (o `409` si el identificador ya existe) | código de salida `1` |
| rechazo por incidente inexistente | `404 Not Found` | código de salida `1` |
| rechazo por instante anterior a la creación | `422 Unprocessable Entity` | código de salida `1` |
| almacenes equivalentes | dos almacenes desechables con los mismos incidentes previos | ídem |
| título, texto del reporte | `title`, `raw_text` | `--title`, `--raw-text` |
| identificador | `incident_id` | `--incident-id` (creación), argumento posicional (auditoría) |
| instante de creación, de resolución | `created_at`, `resolved_at` | `--created-at`, `--resolved-at` |
| estado | `status` | `--status` |
| instante de referencia | `reference_time` | `--reference-time` |
| clave de grupo de duplicados | `duplicate_group_key` | `duplicate_group_key` |
| es duplicado de un abierto | `is_duplicate: true` y `duplicate_of` no vacío | ídem |
| no es duplicado | `is_duplicate: false` y `duplicate_of: []` | ídem |
| minutos transcurridos, permitidos, restantes | `elapsed_minutes`, `allowed_minutes`, `remaining_minutes` | ídem |
| incumplido | `is_breached` | `is_breached` |
| requiere escalamiento | `requires_escalation` | `requires_escalation` |
| resuelto en el instante consultado | `resolved_at_reference` | `resolved_at_reference` |
| incidente abierto | estado `OPEN`, `IN_PROGRESS` o `ESCALATION_REQUIRED` | ídem |
| incidente resuelto | estado `RESOLVED` con instante de resolución | ídem |
| reinicio del servicio | nuevo proceso sobre el mismo almacén persistente | nueva invocación sobre el mismo almacén persistente |

### Historia 1 — Crear un incidente cuando llega (Prioridad: 1 — más crítica)

Como persona de guardia, quiero crear cada reporte entrante como un incidente con
identificador propio, ya clasificado, para administrarlo desde ese momento sin depender de
que alguien lo transcriba ni de que el servicio siga encendido.

**Por qué esta prioridad**: sin incidentes guardados no hay duplicados que avisar ni SLA
que auditar. Es la capacidad que convierte el triaje de H001 en gestión de incidentes.

**Prueba independiente**: se crea un incidente en un almacén persistente, se reinicia el
servicio y el incidente sigue disponible con los mismos datos y la clasificación canónica.

**Escenarios de aceptación**:

- **E1 — Registro inicial sin duplicados previos**
  > **Given** que no hay ningún incidente abierto de la pasarela de pagos
  > **And** el reloj marca las 09:10 del 24 de noviembre de 2026
  > **When** la persona de guardia registra por la web un incidente titulado "Caída de la
  > pasarela de pagos" con el texto "La pasarela de pagos está caída, ningún cliente puede
  > pagar", sin identificador, sin estado y sin instante de creación
  > **Then** el registro es exitoso (`201 Created`)
  > **And** el incidente recibe un identificador generado: `INC-` seguido de 8 dígitos
  > hexadecimales
  > **And** queda abierto y creado a las 09:10 hora de Bogotá (`status` = `OPEN`)
  > **And** trae la clasificación completa que el triaje canónico asigna a ese texto,
  > incluida su clave de grupo de duplicados
  > **And** el sistema confirma que no duplica ningún incidente abierto
  > (`is_duplicate` = `false`, `duplicate_of` = `[]`)

- **E2 — El incidente sobrevive al reinicio**
  > **Given** un incidente creado en un almacén persistente
  > **And** el servicio reiniciado sobre el mismo almacén
  > **When** se audita el SLA de ese incidente por su identificador
  > **Then** la consulta es exitosa
  > **And** el título, el componente, la severidad, el estado y el instante de creación son
  > los mismos que devolvió la creación

- **E3 — La urgencia declarada no cambia la severidad**
  > **Given** dos reportes con el mismo texto de impacto, uno de ellos con las palabras
  > "URGENTE" y "para hoy"
  > **When** se crean ambos incidentes
  > **Then** los dos reciben la misma severidad (Art. 1.4)

- **E4 — Un incidente creado aparece en el resumen de activos**
  > **Given** un incidente abierto recién creado
  > **When** se consulta el resumen de incidentes activos de H002 en un instante posterior
  > a su creación
  > **Then** el incidente aparece en el detalle y cuenta en el total activo

- **E19 — El identificador enviado por el cliente se respeta**
  > **Given** que no existe el incidente `INC-CLIENTE-01`
  > **When** se crea un incidente con identificador `INC-CLIENTE-01`
  > **Then** la creación es exitosa y el incidente queda guardado con ese identificador

- **E20 — Un identificador repetido se rechaza sin tocar el existente**
  > **Given** el incidente existente `INC-2001`
  > **When** se crea otro incidente con identificador `INC-2001`
  > **Then** HTTP responde `409` con código `incident_id_conflict` y el CLI termina con
  > código de salida `1`
  > **And** `INC-2001` conserva todos sus datos

- **E21 — El estado inicial puede informarse**
  > **Given** una creación con estado <estado> y <resolución>
  > **When** se envía
  > **Then** el resultado es <resultado>
  >
  > | Ejemplo | Estado | Resolución | Resultado |
  > |---|---|---|---|
  > | E21.1 — En curso | `IN_PROGRESS` | sin `resolved_at` | creación exitosa en `IN_PROGRESS` |
  > | E21.2 — Escalado | `ESCALATION_REQUIRED` | sin `resolved_at` | creación exitosa en `ESCALATION_REQUIRED` |
  > | E21.3 — Resuelto completo | `RESOLVED` | `resolved_at` posterior a la creación | creación exitosa en `RESOLVED` |
  > | E21.4 — Resuelto incompleto | `RESOLVED` | sin `resolved_at` | `422 invalid_payload` / código `1` |
  > | E21.5 — Resolución en abierto | `OPEN` | con `resolved_at` | `422 invalid_payload` / código `1` |
  > | E21.6 — Resolución previa | `RESOLVED` | `resolved_at` anterior a la creación | `422 invalid_payload` / código `1` |
  > | E21.7 — Estado inexistente | `CLOSED` | sin `resolved_at` | `422 invalid_payload` / código `1` |

---

### Historia 2 — Enterarse de que ya existe un duplicado abierto (Prioridad: 2)

Como persona de guardia, quiero que al crear un incidente el sistema me diga si ya hay
otro abierto con la misma clave de grupo, para no gestionar dos veces el mismo problema ni
movilizar a dos equipos por la misma caída.

**Por qué esta prioridad**: es el valor diferencial del hito, pero depende de la creación.
Sin aviso, la creación sigue siendo útil; sin creación, el aviso no tiene sentido.

**Prueba independiente**: con incidentes sembrados abiertos y resueltos, se crean
incidentes con y sin clave coincidente. Solo los coincidentes con un abierto se marcan
duplicados, y los sembrados no cambian.

**Escenarios de aceptación**:

- **E5 — Detección de duplicado abierto, ignorando los resueltos**
  > **Given** un incidente abierto por caída de la pasarela de pagos, `INC-0000A001`
  > **And** un incidente ya resuelto por una caída anterior de la pasarela de pagos,
  > `INC-0000A002`
  > **When** la persona de guardia registra un incidente nuevo por otra caída de la
  > pasarela de pagos
  > **Then** el registro es exitoso (`201 Created`) con un identificador nuevo
  > **And** el sistema avisa que el incidente nuevo duplica uno abierto
  > (`is_duplicate` = `true`)
  > **And** el aviso señala solo al incidente abierto (`duplicate_of` = `["INC-0000A001"]`)
  > **And** el incidente resuelto `INC-0000A002` no aparece en el aviso, aunque trate del
  > mismo problema
  > **And** ninguno de los dos incidentes previos cambia de estado ni de datos

- **E6 — Sin aviso cuando no hay un abierto con la misma clave**
  > **Given** <situación del almacén>
  > **When** se crea <incidente>
  > **Then** la creación es exitosa y el incidente no es duplicado de ningún abierto
  >
  > | Ejemplo | Situación del almacén | Incidente |
  > |---|---|---|
  > | E6.1 — Otra clave | incidente abierto por caída de autenticación | caída de la pasarela de pagos |
  > | E6.2 — Coincidente resuelto | incidente `RESOLVED` por caída de la pasarela de pagos | caída de la pasarela de pagos |
  > | E6.3 — Sin clave | incidente abierto por botón desalineado en la interfaz | otro botón desalineado en la interfaz (el triaje no asigna clave de grupo) |
  > | E6.4 — Sin clasificar | incidente abierto con componente `unclassified` | otro reporte que el triaje deja `unclassified` |

- **E7 — Retirado.** La regla de ventana de 30 minutos que verificaba quedó reemplazada
  por el criterio de clave de grupo (ver Clarifications). El identificador no se recicla.

- **E8 — Creaciones simultáneas del mismo problema**
  > **Given** que no hay incidentes abiertos de la pasarela de pagos
  > **When** se crean al mismo tiempo dos incidentes por caída de la pasarela de pagos
  > **Then** ambos quedan guardados con identificadores distintos
  > **And** al menos uno de los dos es duplicado del otro

- **E22 — Ni la antigüedad ni la recurrencia impiden el aviso**
  > **Given** un incidente abierto por caída de la pasarela de pagos creado tres días antes
  > **When** se crea un incidente con el texto "Otra vez se cayó la pasarela de pagos"
  > **Then** el incidente nuevo es duplicado del abierto, porque comparten clave de grupo

- **E23 — Un incidente creado ya resuelto no genera avisos en otros**
  > **Given** un incidente por caída de la pasarela de pagos creado directamente en estado
  > `RESOLVED`
  > **When** se crea después otro incidente por caída de la pasarela de pagos
  > **Then** el segundo no es duplicado del primero

---

### Historia 3 — Auditar cómo va el SLA de un incidente (Prioridad: 3)

Como persona de guardia o auditora, quiero consultar por la web o por la terminal cómo va
el SLA de un incidente, ahora o en un instante pasado, para decidir si escalo o para
reconstruir si un cierre llegó fuera de plazo.

**Por qué esta prioridad**: completa el ciclo "creación → seguimiento". Requiere
incidentes guardados, pero se prueba sin el aviso de duplicados.

**Prueba independiente**: con incidentes sembrados de distintas severidades, abiertos y
resueltos, la auditoría en varios instantes devuelve las cifras de la evaluación canónica,
idénticas por ambos canales.

**Escenarios de aceptación**:

- **E9 — SLA de un incidente activo**
  > **Given** un incidente abierto de severidad P0 creado a las 09:00 del 24 de noviembre
  > de 2026
  > **When** la persona de guardia audita su SLA por la web con instante de referencia
  > 09:50
  > **Then** obtiene una consulta exitosa
  > **And** muestra 50 minutos transcurridos, 60 permitidos y 10 restantes
  > **And** el incidente requiere escalamiento y no está incumplido

- **E10 — Reconstrucción del SLA a un instante pasado, con cierre fuera de plazo**
  > **Given** un incidente P1 creado a las 08:00 del 24 de noviembre de 2026 y resuelto
  > a las 13:00 del mismo día
  > **When** la persona auditora consulta su SLA con instante de referencia <instante>
  > **Then** obtiene una consulta exitosa con <transcurridos> minutos transcurridos
  > **And** el incumplimiento es <incumplido>, el escalamiento es <escalamiento> y el
  > incidente <resuelto>
  >
  > | Ejemplo | Instante | Transcurridos | Incumplido | Escalamiento | Resuelto en el instante |
  > |---|---|---|---|---|---|
  > | E10.1 — Antes del cierre | 11:30 | 210 | no | sí | aún no estaba resuelto |
  > | E10.2 — Después del cierre | 14:00 | 300 | sí | no | ya estaba resuelto |

- **E11 — Operación equivalente por terminal con `create` y `sla`**
  > **Given** dos almacenes equivalentes, con un incidente abierto por caída de la
  > pasarela de pagos, y el mismo reloj
  > **When** el operador realiza <operación> por la web sobre un almacén y por la
  > terminal sobre el otro, en formato estructurado
  > **Then** ambos canales responden con éxito (<éxito web> por la web, código de salida
  > `0` por la terminal)
  > **And** ambos resultados coinciden campo a campo, incluido el aviso de duplicado
  >
  > | Ejemplo | Operación | Subcomando CLI | Éxito web |
  > |---|---|---|---|
  > | E11.1 — Registrar | registrar el incidente `INC-CLIENTE-02` por otra caída de la pasarela de pagos | `create` | `201 Created` |
  > | E11.2 — Auditar | auditar el SLA del incidente abierto con instante de referencia fijo | `sla` | `200 OK` |
  >
  > En E11.1 el identificador se informa para que ambos resultados sean comparables; un
  > identificador generado diferiría entre canales.

- **E12 — Auditoría determinista de SLA en horario hábil**
  > **Given** un incidente P2 abierto registrado el viernes 6 de noviembre de 2026 a las
  > 17:00 hora de Bogotá
  > **And** que el lunes 9 de noviembre de 2026 no es festivo en Colombia
  > **When** la persona auditora consulta su SLA con instante de referencia lunes 9 de
  > noviembre de 2026 a las 09:00
  > **Then** la consulta es exitosa (`200 OK`)
  > **And** muestra 120 minutos hábiles transcurridos: la última hora hábil del viernes y
  > la primera del lunes, porque el fin de semana no cuenta (`elapsed_minutes` = `120`)
  > **And** de los 480 minutos permitidos quedan 360 (`allowed_minutes` = `480`,
  > `remaining_minutes` = `360`)
  > **And** el incidente no está incumplido ni requiere escalamiento, porque 120 minutos
  > no alcanzan el umbral de 360 (`is_breached` = `false`,
  > `requires_escalation` = `false`)

---

### Escenarios transversales

- **E13 — Auditoría de un incidente inexistente**
  > **Given** que no existe ningún incidente con el identificador `INC-FFFFFFFF`
  > **When** la persona auditora consulta el SLA de `INC-FFFFFFFF` por la web y por la
  > terminal
  > **Then** ambos canales rechazan la consulta como incidente inexistente, sin devolver
  > evaluación (`404 Not Found` con código `incident_not_found`; código de salida `1`)
  > **And** la terminal explica el motivo por la salida de diagnóstico (`stderr`)

- **E14 — Auditoría en un instante anterior a la creación**
  > **Given** un incidente registrado el 24 de noviembre de 2026 a las 09:00
  > **When** la persona auditora consulta su SLA con instante de referencia 08:59 del
  > mismo día, por la web y por la terminal
  > **Then** ambos canales rechazan la consulta porque el incidente aún no existía en ese
  > instante (`422 Unprocessable Entity` con código `reference_before_creation`; código
  > de salida `1`)
  > **And** no se devuelve ninguna evaluación de SLA

- **E15a — Una creación con contenido inaceptable no guarda nada**
  > **Given** una creación con <defecto>
  > **When** se envía por la web y por la terminal
  > **Then** ambos canales la rechazan sin guardar nada
  > **And** HTTP responde `422` con código <código> y el CLI termina con código de
  > salida `1`
  >
  > | Ejemplo | Defecto | Código |
  > |---|---|---|
  > | E15a.1 — Título vacío | título vacío o solo espacios | `invalid_payload` |
  > | E15a.2 — Texto vacío | texto vacío o solo espacios | `invalid_payload` |
  > | E15a.3 — Texto largo | texto de 5 001 caracteres | `invalid_payload` |
  > | E15a.4 — Título largo | título de 201 caracteres | `invalid_payload` |
  > | E15a.5 — Identificador mal formado | identificador `incidente-7` | `invalid_payload` |
  > | E15a.6 — Instante ilegible | instante de creación `"ayer"` | `invalid_timestamp` |

- **E15b — Una creación que no respeta el contrato no guarda nada**
  > **Given** una creación que incluye <campo>
  > **When** se envía por la web y por la terminal
  > **Then** ambos canales la rechazan sin guardar nada
  > **And** HTTP responde `400` y el CLI termina con código de salida `2`
  >
  > | Ejemplo | Campo |
  > |---|---|
  > | E15b.1 — Desconocido | un campo o una bandera fuera del contrato (`priority`) |
  > | E15b.2 — Reservado | un campo que asigna el triaje (`severity`, `component`, `recommended_team`, `action` o `duplicate_group_key`) |

- **E16 — La auditoría de SLA no modifica datos ni expone contenido**
  > **Given** un almacén con incidentes abiertos y resueltos
  > **When** se audita el SLA de cada incidente repetidamente
  > **Then** no se crea, modifica ni elimina ningún incidente
  > **And** ninguna traza de la auditoría registra títulos

- **E17 — Fallo del almacén al crear**
  > **Given** un almacén que falla al guardar
  > **When** se crea un incidente
  > **Then** HTTP responde `500` con código `internal_error` y el CLI termina con código
  > de salida `4`
  > **And** no se devuelve identificador ni queda un registro parcial

- **E18 — La creación no expone el contenido del reporte en las trazas**
  > **Given** un incidente con un texto y un título identificables
  > **When** se crea
  > **Then** la creación es exitosa
  > **And** ninguna traza incluye el texto ni el título; solo el identificador, si es
  > duplicado, el número de duplicados, la duración y el código de resultado

### Trazabilidad de escenarios

| Escenario | Requisitos funcionales |
|---|---|
| E1 | FR-001, FR-002, FR-003, FR-004, FR-008, FR-023 |
| E2 | FR-006, FR-012 |
| E3 | FR-003 |
| E4 | FR-022 |
| E5 | FR-007, FR-008, FR-009, FR-010 |
| E6 (E6.1–E6.4) | FR-007, FR-008, FR-023 |
| E7 | — (retirado) |
| E8 | FR-011 |
| E9 | FR-012, FR-013, FR-014 |
| E10 (E10.1, E10.2) | FR-012, FR-013, FR-015 |
| E11 (E11.1, E11.2) | FR-001, FR-008, FR-018, FR-019, FR-020 |
| E12 | FR-012, FR-013, FR-014 |
| E13 | FR-016, FR-018, FR-019 |
| E14 | FR-016, FR-018, FR-019 |
| E15a (E15a.1–E15a.6) | FR-002, FR-004, FR-017, FR-018, FR-019 |
| E15b (E15b.1, E15b.2) | FR-003, FR-017, FR-018, FR-019 |
| E16 | FR-021 |
| E17 | FR-006, FR-018, FR-019 |
| E18 | FR-021 |
| E19 | FR-004 |
| E20 | FR-004, FR-017 |
| E21 (E21.1–E21.7) | FR-005, FR-017 |
| E22 | FR-007 |
| E23 | FR-005, FR-007 |

### Casos borde

| Caso | Comportamiento esperado |
|---|---|
| Varios abiertos con la misma clave | `duplicate_of` los lista todos, ordenados por instante de creación y luego por identificador. |
| Abierto coincidente creado mucho antes o después | Es duplicado: el criterio no tiene ventana de tiempo (E22). |
| Reporte con marca de recurrencia ("otra vez") | Es duplicado si comparte clave con un abierto (E22). |
| Reporte al que el triaje no asigna clave de grupo | Nunca es duplicado: `duplicate_group_key` es `null`, `is_duplicate` es falso y `duplicate_of` está vacío. |
| Abierto coincidente en `ESCALATION_REQUIRED` o `IN_PROGRESS` | Cuenta como abierto. |
| El propio incidente recién creado | Nunca aparece en su propio `duplicate_of`. |
| Incidente creado en estado `RESOLVED` | Se calcula su `is_duplicate` contra los abiertos, pero nunca aparece en el `duplicate_of` de otros (E23). |
| Identificador generado que coincide con uno existente | El sistema genera otro; el cliente nunca recibe un conflicto por un identificador que no envió. |
| Identificador enviado con minúsculas o espacios | Se compara tal cual tras recortar espacios; `INC-abc` e `INC-ABC` son identificadores distintos. |
| Instante de creación futuro respecto del reloj | Se admite. Auditar antes de él es E14. |
| Texto con acentos, emojis o caracteres de control | Se guarda tal cual y se devuelve escapado en JSON, sin romper la salida. |
| Auditoría en el instante exacto de creación | Éxito con 0 minutos transcurridos. |
| Auditoría en el instante exacto de resolución | El incidente cuenta como resuelto en ese instante. |
| Almacén en memoria por defecto | La creación funciona, pero no sobrevive al proceso. Una invocación CLI posterior no la ve (ver supuestos). |
| `--format` distinto de `table` o `json` | Error de uso con código `2`. |

---

## Requisitos

### Requisitos funcionales

**Creación**

- **FR-001**: El sistema DEBE permitir crear un incidente por HTTP y por CLI. Ambos
  canales DEBEN usar el mismo caso de uso, el mismo almacén y el mismo contrato JSON.
- **FR-002**: Una creación DEBE recibir:
  - `title`: obligatorio, no vacío ni solo espacios, de hasta 200 caracteres.
  - `raw_text`: obligatorio, no vacío ni solo espacios, de hasta 5 000 caracteres.
  - `incident_id`: opcional (FR-004).
  - `created_at`: opcional. Si se omite, se usa el reloj inyectado. Una fecha sin zona se
    interpreta como hora de Bogotá (Art. 1.7).
  - `status`: opcional, `OPEN` por defecto (FR-005).
  - `resolved_at`: opcional (FR-005).
- **FR-003**: La severidad, el componente, el equipo recomendado, la acción, la clave de
  grupo de duplicados y el análisis DEBEN provenir del triaje canónico del dominio
  aplicado a `raw_text` (Art. 1.1, 1.4). El cliente NO DEBE poder fijarlos: una creación
  que envíe `severity`, `component`, `recommended_team`, `action` o
  `duplicate_group_key` DEBE rechazarse como petición no interpretable.
- **FR-004**: Si se omite `incident_id`, el sistema DEBE generar uno con la forma
  `INC-<HEX8>`: el prefijo `INC-` seguido de 8 dígitos hexadecimales en mayúsculas. El
  identificador generado DEBE ser único: si coincide con uno existente, se genera otro.
  Si el cliente envía `incident_id`, DEBE cumplir la forma `INC-` seguida de 1 a 32
  letras, dígitos o guiones (si no, `422 invalid_payload`). Si ya existe, la creación DEBE
  rechazarse con `409 incident_id_conflict` sin modificar el incidente existente.
- **FR-005**: Los estados admitidos al crear son `OPEN`, `IN_PROGRESS`,
  `ESCALATION_REQUIRED` y `RESOLVED`:
  - `RESOLVED` exige `resolved_at`, igual o posterior a `created_at` (Art. 1.10).
  - `resolved_at` con un estado activo DEBE rechazarse.
  - Cualquier otro valor de estado DEBE rechazarse.

  Todos estos rechazos son `422 invalid_payload`.
- **FR-006**: Una creación solo DEBE confirmarse cuando el incidente quedó guardado. Si el
  almacén falla, la operación DEBE fallar sin devolver identificador y sin dejar registro
  parcial. Con un almacén persistente, el incidente DEBE sobrevivir al reinicio del
  servicio.

**Aviso de duplicado abierto**

- **FR-007**: Un incidente existente es **duplicado abierto** del recién creado solo si se
  cumplen todas estas condiciones:
  - su `duplicate_group_key` es igual a la del recién creado, y ninguna de las dos es
    nula;
  - está en estado `OPEN`, `IN_PROGRESS` o `ESCALATION_REQUIRED`; los `RESOLVED` quedan
    fuera;
  - su identificador es distinto del recién creado.

  No hay ventana de tiempo ni excepción por recurrencia. La clave la calcula el dominio
  (Art. 1.11); los canales y el caso de uso solo la comparan y transportan.
- **FR-008**: El incidente nuevo DEBE crearse siempre, haya o no duplicados abiertos. La
  respuesta DEBE incluir el incidente guardado, la clasificación completa (FR-003),
  `is_duplicate` y `duplicate_of`. `duplicate_of` es la lista de identificadores de los
  duplicados abiertos, ordenada por instante de creación y luego por identificador.
  `is_duplicate` es verdadero si y solo si `duplicate_of` no está vacío.
- **FR-009**: La creación NO DEBE modificar ningún incidente existente: no fusiona, no
  cambia estado y no reasigna componente, severidad ni clave.
- **FR-010**: El aviso es informativo. NO DEBE cambiar el código de éxito de la creación
  (`201` por HTTP, `0` por CLI).
- **FR-011**: La búsqueda de duplicados y el guardado DEBEN ser consistentes frente a
  creaciones simultáneas. De dos creaciones concurrentes con la misma clave, ambas se
  guardan, y la que se guarda en segundo lugar DEBE listar a la primera en `duplicate_of`
  si esta sigue abierta.
- **FR-023**: Todo incidente guardado DEBE conservar su `duplicate_group_key`. El dominio
  DEBE poder calcular la clave de **un solo** reporte, con las formas canónicas del
  Art. 1.11:
  - `<prefijo-componente>-availability` para una caída de un componente clasificado;
  - `database-performance-investigation` para rendimiento o base de datos con causa
    compartida;
  - `null` en cualquier otro caso.

  Hoy la clave solo existe dentro de un lote de dos o más reportes (D10).

**Auditoría de SLA**

- **FR-012**: El sistema DEBE permitir auditar, por HTTP y por CLI, el SLA de un incidente
  por su identificador, esté abierto o resuelto. La respuesta incluye identificador,
  título, componente, severidad, estado actual, instante de creación, instante de
  resolución (o nulo) e instante de referencia evaluado.
- **FR-013**: Los minutos transcurridos, permitidos y restantes, el incumplimiento y el
  escalamiento DEBEN provenir de la evaluación canónica de SLA del dominio (Art. 1.6–1.8).
  Ningún canal ni el caso de uso los recalcula, aproxima ni sobrescribe. Los minutos
  restantes pueden ser negativos cuando hay incumplimiento.
- **FR-014**: `reference_time` es opcional y se expresa en ISO 8601. Si no se informa, se
  usa el reloj inyectado. Una fecha sin zona se interpreta como hora de Bogotá. La
  respuesta declara el instante efectivamente evaluado, truncado a segundos.
- **FR-015**: La evaluación DEBE ser reconstruible en cualquier instante de referencia
  igual o posterior a la creación:
  - el incidente cuenta como resuelto en ese instante solo si su resolución ocurrió en ese
    instante o antes (`resolved_at_reference`);
  - el tiempo transcurrido se mide hasta el instante de referencia o hasta la resolución,
    lo que ocurra primero;
  - el escalamiento se evalúa como si el incidente siguiera activo, salvo que ya estuviera
    resuelto en ese instante.

  Un cierre posterior al plazo DEBE verse como incumplido en cualquier instante posterior
  al límite (E10).
- **FR-016**: Un identificador inexistente DEBE responder `404 incident_not_found` (código
  de salida `1`). Un `reference_time` anterior a `created_at` DEBE rechazarse con
  `422 reference_before_creation` (código de salida `1`).

**Canales y contrato**

- **FR-017**: Un campo o una bandera fuera del contrato, o un campo reservado (FR-003),
  DEBEN rechazarse como petición no interpretable (`400` / código `2`). Los siguientes
  casos DEBEN rechazarse como contenido inaceptable (`422` / código `1`):
  - un título o un texto vacíos o demasiado largos;
  - un identificador mal formado;
  - un estado o una resolución inválidos (FR-005);
  - un instante no parseable.

  Un identificador repetido DEBE rechazarse con `409` / código `1`. Ningún rechazo guarda
  nada.
- **FR-018**: El canal HTTP DEBE exponer `POST /api/v1/incidents` para la creación y
  `GET /api/v1/incidents/{incident_id}/sla` (parámetro opcional `reference_time`) para la
  auditoría. Cualquier otro método sobre esas rutas DEBE responder
  `405 method_not_allowed`. Los errores DEBEN usar la envoltura común de H001.
- **FR-019**: El canal CLI DEBE ofrecer dos subcomandos:
  - `create`, con `--title`, `--raw-text`, `--incident-id`, `--created-at`, `--status`,
    `--resolved-at` y `--format table|json`;
  - `sla <incident_id>`, con `--reference-time` y `--format table|json`.

  DEBE escribir solo el resultado en `stdout` y los diagnósticos en `stderr`. Los códigos
  de salida de **todo** el CLI pasan a ser: `0` éxito, `1` entrada inválida, incidente
  inexistente o identificador en conflicto, `2` error de uso y `4` fallo interno. El
  código `3` se retira, también en `triage` y `summary` (D8).
- **FR-020**: La salida JSON DEBE ser el contrato estable y coincidir campo a campo entre
  HTTP y CLI para el mismo almacén, la misma entrada y el mismo instante. La tabla del CLI
  es presentación y no forma parte del contrato.
- **FR-021**: La auditoría de SLA DEBE ser de solo lectura. Ninguna traza de creación ni
  de auditoría DEBE incluir textos de reporte ni títulos. Solo se registran el
  identificador, si es duplicado y cuántos, la duración y el código de resultado.
- **FR-022**: Los incidentes creados DEBEN ser visibles para el resumen de activos de H002
  sobre el mismo almacén, sin cambios en el contrato JSON de H002. El triaje de H001 sigue
  sin efectos secundarios.

### Decisiones de alcance

| # | Decisión | Motivo |
|---|---|---|
| D1 | Duplicado abierto = misma `duplicate_group_key` no nula, estado abierto, otro identificador. Sin ventana ni excepción por recurrencia. | Clarificación del 2026-11-24 (reemplaza la regla de ventana de 30 minutos). Una sola comparación, basada en la clave que ya calcula el dominio. Consecuencia aceptada: una recurrencia o una caída antigua aún abierta también se señalan como duplicado. |
| D2 | Crear y avisar: el incidente nuevo se guarda siempre y el aviso viaja en la misma respuesta. | Clarificación del 2026-11-24. Ningún reporte legítimo se pierde. El roadmap dice "antes de crear el duplicado"; aquí el aviso llega en la misma operación, antes de que nadie actúe. Se registra como desviación aceptada del texto del roadmap. |
| D3 | La clasificación la pone el triaje sobre `raw_text`; el cliente aporta además el título. | Art. 1.1 y 1.4: la severidad sale del impacto y el cliente no la declara. |
| D4 | El identificador es opcional para el cliente, generado como `INC-<HEX8>` si falta. Si se repite, la respuesta es `409`. | Clarificación del 2026-11-24. Cumple lo que spec 001 D4 reservó para H003. El rechazo evita el reemplazo silencioso que hoy hace el almacén. |
| D5 | Se persiste la clave de grupo de cada incidente, no el aviso ni un vínculo entre incidentes. | La clave basta para recalcular duplicados en cualquier momento. Gestionar grupos y su cierre es ciclo de vida. |
| D6 | Las transiciones de estado posteriores a la creación, la asignación y el rastro de cambios quedan fuera de este corte. | El pedido cubre creación, aviso y auditoría de SLA. El estado inicial sí se admite (FR-005). |
| D7 | La reconstrucción del SLA (FR-015) exige ajustar la evaluación canónica del dominio. Hoy, para un incidente resuelto, mide hasta la resolución aunque el instante consultado sea anterior. | Art. 1.12: el cambio de regla actualiza en el mismo cambio la regresión `_run_demo` y los escenarios afectados. |
| D8 | Enmienda MAJOR de F3 como primera tarea del plan, en commit propio, con: Constitución 3.0.0 sin ADR (desviación de gobernanza registrada; ver Clarifications), `AGENTS.md`, enmienda de spec 001 y spec 002 y sus pruebas. Contenido: rutas y subcomandos nuevos, más el cambio de códigos de salida de todo el CLI (`3` → `1`). | Clarificación del 2026-11-24. Cambiar el significado de un código vigente es una redefinición incompatible (Versionado: MAJOR) y rompe el contrato publicado de `triage` y `summary`. |
| D9 | Se reutilizan la envoltura de errores y la convención `400`/`422` de H001 y H002. Se añaden `404 incident_not_found` y `409 incident_id_conflict`. | Una sola convención de error y paridad de canales (Art. 2.7). |
| D10 | El dominio expone la clave de grupo de un reporte individual, con las mismas formas canónicas del Art. 1.11. | Hoy `duplicate_group_key` solo existe con dos o más reportes en un lote. Sin la clave individual, el criterio D1 no se puede evaluar. Es un cambio de dominio (Art. 1.12) que no altera la correlación por lote de H001. |

### Contrato observable

Los nombres de ruta, parámetros y campos son el contrato que consume el cliente. No
prescriben framework, almacenamiento ni estructura interna: el plan decide cómo se
cumplen.

**HTTP — creación**

```http
POST /api/v1/incidents
Content-Type: application/json

{
  "title": "Caída de la pasarela de pagos",
  "raw_text": "La pasarela de pagos está caída, ningún cliente puede pagar",
  "created_at": "2026-11-24T09:20:00"
}
```

```json
{
  "incident_id": "INC-3FA94C1B",
  "title": "Caída de la pasarela de pagos",
  "status": "OPEN",
  "created_at": "2026-11-24T09:20:00-05:00",
  "resolved_at": null,
  "severity": "P0",
  "component": "payment-gateway",
  "recommended_team": "Backend-Core",
  "action": "escalate_24x7",
  "duplicate_group_key": "payment-availability",
  "analysis": ["..."],
  "is_duplicate": true,
  "duplicate_of": ["INC-2001"]
}
```

Respuesta `201 Created`. Sin duplicados abiertos: `"is_duplicate": false` y
`"duplicate_of": []`. Los valores de clasificación del ejemplo son ilustrativos: los fija
el triaje canónico. `duplicate_type` y `merge` de H001 no forman parte de esta respuesta,
porque describen la correlación dentro de un lote.

**HTTP — auditoría de SLA**

```http
GET /api/v1/incidents/INC-3FA94C1B/sla?reference_time=2026-11-24T10:30:00
```

```json
{
  "incident_id": "INC-3FA94C1B",
  "title": "Caída de la pasarela de pagos",
  "component": "payment-gateway",
  "severity": "P0",
  "status": "OPEN",
  "created_at": "2026-11-24T09:20:00-05:00",
  "resolved_at": null,
  "reference_time": "2026-11-24T10:30:00-05:00",
  "resolved_at_reference": false,
  "elapsed_minutes": 70,
  "allowed_minutes": 60,
  "remaining_minutes": -10,
  "is_breached": true,
  "requires_escalation": false
}
```

**CLI**

```bash
uv run python -X utf8 -m src.adapters.inbound.cli create --title "Caída de la pasarela de pagos" --raw-text "La pasarela de pagos está caída" --format json
uv run python -X utf8 -m src.adapters.inbound.cli create --title "..." --raw-text "..." --incident-id INC-CLIENTE-01 --status IN_PROGRESS --created-at 2026-11-24T09:20:00
uv run python -X utf8 -m src.adapters.inbound.cli sla INC-3FA94C1B --reference-time 2026-11-24T10:30:00 --format json
```

| Situación | HTTP | CLI |
|---|---|---|
| Creación válida, duplicado o no | `201` | `0` |
| Auditoría de SLA válida | `200` | `0` |
| Incidente inexistente | `404 incident_not_found` | `1` |
| Identificador ya existente | `409 incident_id_conflict` | `1` |
| `reference_time` anterior a `created_at` | `422 reference_before_creation` | `1` |
| Título o texto vacío o largo, identificador mal formado, estado o resolución inválidos | `422 invalid_payload` | `1` |
| Instante no parseable | `422 invalid_timestamp` | `1` |
| Campo, parámetro o bandera desconocida, o campo reservado | `400 invalid_payload` / `reserved_field` | `2` |
| Método no permitido | `405 method_not_allowed` | — |
| Fallo del almacén o inesperado | `500 internal_error` | `4` |

La envoltura de error es la de H001: `{"error": {"code", "message", "field"}}`. Los
mensajes van en español, para humanos; `code` es estable para el cliente.

### Fuera de alcance

- Transiciones de estado posteriores a la creación, asignación, cierre y rastro de
  cambios.
- Fusionar incidentes o vincularlos persistentemente como grupo.
- Creación por lotes y lectura del reporte desde archivo o `stdin`.
- Alertas o notificaciones fuera de la respuesta (correo, chat, webhooks), incluida una
  alerta propia por cierre fuera de plazo.
- Listados o búsquedas de incidentes distintos del resumen de H002.
- Autenticación y autorización.
- Canal MCP.
- Cambios a la política de SLA, al calendario hábil, a los estados válidos o a la
  correlación por lote de H001.
- Base de datos dedicada y contenedores (H004).

### Entidades clave

- **Solicitud de creación**: título, texto crudo y, opcionalmente, identificador, instante
  de creación, estado e instante de resolución. Es lo único que aporta el cliente.
- **Incidente guardado**: identificador, título, componente, severidad, estado, instante de
  creación, instante de resolución opcional y clave de grupo de duplicados. Persiste.
- **Clasificación de triaje**: componente, severidad, equipo recomendado, acción, clave de
  grupo y análisis derivados del texto por el dominio.
- **Aviso de duplicado**: `is_duplicate` más la lista ordenada de identificadores de
  duplicados abiertos. Se devuelve con la creación y no se persiste.
- **Evaluación SLA en un instante**: instante evaluado, si estaba resuelto en ese
  instante, minutos transcurridos, permitidos y restantes, incumplimiento y escalamiento.

---

## Criterios de éxito

### Resultados medibles

- **SC-001**: El 100 % de los incidentes creados en un almacén persistente se recupera con
  los mismos datos después de reiniciar el servicio.
- **SC-002**: En la suite de referencia, `is_duplicate` es verdadero en el 100 % de los
  casos con un abierto de la misma clave no nula. Es falso en el 100 % de los casos sin
  esa coincidencia: otra clave, coincidente resuelto, sin clave, sin clasificar o el
  propio identificador.
- **SC-003**: Ninguna creación, duplicada o no, ni ningún rechazo (incluido `409`) altera
  un incidente existente: 0 diferencias al comparar el almacén antes y después.
- **SC-004**: Para el mismo almacén, la misma entrada y el mismo instante, HTTP y CLI
  coinciden en el 100 % de los campos del contrato de creación y de auditoría de SLA.
- **SC-005**: El 100 % de las cifras de SLA coincide con la evaluación canónica en al
  menos cuatro instantes por incidente de referencia: la creación, antes del umbral de
  escalamiento, antes de la resolución y después de una resolución fuera de plazo.
- **SC-006**: Con 10 000 incidentes abiertos en el almacén, una creación (con búsqueda de
  duplicados) y una auditoría de SLA tardan cada una menos de 1 segundo por canal,
  medidas en proceso y sin contar el arranque del intérprete.
- **SC-007**: Una persona de guardia sabe, con una sola operación de creación, si su
  incidente duplica uno abierto y cuál es, sin consultar el resumen por separado.

---

## Supuestos

- **Límites de tamaño**: los límites de 200 caracteres para el título y 5 000 para el
  texto son valores razonables por defecto. El segundo corte de spec 001 puede unificarlos
  con los límites de `POST /v1/triage`.
- **Clasificación de un solo reporte**: el triaje se aplica a `raw_text` como reporte
  individual. La relación con incidentes ya guardados la da la clave de grupo (FR-007), no
  la correlación por lote.
- **Clave de los incidentes de demostración**: `INC-2001`…`INC-2008` no tienen texto
  crudo. Su clave de grupo se obtiene aplicando la misma regla del dominio a su título, al
  sembrarlos.
- **Persistencia**: el almacén se sigue seleccionando por `DATABASE_URL`. Con el almacén
  en memoria por defecto, la creación funciona durante la vida del proceso (útil para
  demostración y pruebas), pero no sobrevive. Cada invocación CLI es un proceso nuevo, así
  que crear por terminal y auditar después exige un almacén persistente. SC-001 y E2 se
  verifican con almacén persistente.
- **Reconstrucción sin historial**: sin rastro de cambios de estado, el estado en un
  instante pasado se deduce solo de la creación y la resolución. Un incidente se considera
  activo entre ambos instantes. Los estados intermedios no se reconstruyen.
- **Formato CLI**: `create` y `sla` aceptan `--format table|json`, como `triage` y
  `summary`. El JSON es el contrato; la tabla es presentación.
- **Operación**: se mantiene el despliegue en loopback sin autenticación de H001 y H002.
- **Sin dependencias nuevas**: la capacidad se resuelve con el stack existente (T2, T5);
  no se introducen ORM, `pandas` ni librerías de calendario. El identificador hexadecimal
  se genera con la librería estándar.
- **H001 y H002**: sus contratos JSON no cambian. Solo cambia el código de salida del CLI
  para entrada inválida (`3` → `1`, D8). El resumen de H002 ve los incidentes creados.

---

## Dependencias

- **Triaje canónico** (Art. 1.1, 1.4, 1.5): clasificación del texto de la solicitud.
- **Clave de grupo individual** (Art. 1.11, 1.12): el dominio calcula la clave de un solo
  reporte con las formas canónicas, sin alterar la correlación por lote (D10).
- **Evaluación canónica de SLA** (Art. 1.6–1.8): ajuste previo para la reconstrucción a un
  instante anterior a la resolución (D7, Art. 1.12).
- **Puerto del repositorio** (Art. 3.2–3.5, ADR-006): hoy ofrece guardar, obtener por
  identificador y localizar activos. Varias necesidades pueden exigir un método nuevo:
  - buscar abiertos por clave de grupo;
  - persistir la clave;
  - insertar sin reemplazar (el `409` de FR-004);
  - garantizar la atomicidad de FR-011.

  El plan justifica cada método nuevo como pide el Art. 3.2.
- **Constitución**: enmienda MAJOR de F3 (rutas, subcomandos y códigos de salida, D8),
  Art. 1.10 (estados y `resolved_at`), 2.7 (paridad), 5.1–5.3 y 5.6 (BDD, verificación y
  enmienda previa de spec 001 y spec 002 antes de cambiar sus pruebas), T2, T3 y T5.
- **Canales de H001 y H002**: raíz de composición, adaptador HTTP, adaptador CLI y
  envoltura de errores existentes.

---

## Preguntas abiertas

| Tema | Dueño | Efecto |
|---|---|---|
| Persistir un vínculo explícito entre un incidente y sus duplicados | Corte de ciclo de vida de H003 | Hoy el grupo se deduce de la clave (D5). Un vínculo permitiría cerrar duplicados juntos. |
| Si el almacén por defecto debe pasar a ser persistente | Plan de H003 / H004 | Con el valor actual, la creación por CLI no persiste entre invocaciones sin configurar `DATABASE_URL`. |
| Si un cierre fuera de plazo genera una alerta propia | Corte de ciclo de vida de H003 | Decisión pendiente del roadmap; aquí solo se audita por consulta. |
