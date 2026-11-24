# Especificación de funcionalidad: Resumen de incidentes activos

**Rama de la funcionalidad**: `002-active-incident-summary`

**Creado**: 2026-11-24

**Estado**: Implementada (US1–US3). FR-002 desbloqueado: el Art. 1.10 quedó enmendado
(activo = todo estado distinto de `RESOLVED`) por ADR-005 y la Constitución 2.0.0; el
contrato de canales (F3) se amplió en la Constitución 2.1.0 con sustento en ADR-006.

**Entrada**: Descripción del usuario: "Necesitamos consultar el resumen de incidentes
actualmente activos (OPEN e IN_PROGRESS) tanto por API HTTP como por CLI, indicando el
total activo, cuántos incumplieron su SLA y el detalle de cada incidente (título,
componente, severidad, estado, minutos transcurridos y si requiere escalamiento),
permitiendo filtrar opcionalmente por componente."

**Hito**: H002 — Resumen de incidentes activos (`docs/ROADMAP.MD`).

**Autoridad**: subordinada a `docs/constitution.md`, que prevalece sobre esta
especificación, sobre los ADR y sobre el código.

---

## Resumen

Se expone una consulta de solo lectura que responde a la pregunta operativa "¿qué está
pasando ahora?": cuántos incidentes siguen activos, cuántos ya incumplieron su SLA,
cuáles requieren escalamiento y cuál es el detalle de cada uno. La
misma consulta se ofrece por HTTP y por CLI, con el mismo contrato y las mismas cifras
para el mismo almacén y el mismo instante de referencia (Art. 2.7).

El cálculo de minutos transcurridos, incumplimiento y escalamiento **no se define aquí**:
se toma de la evaluación canónica de SLA del dominio (Art. 1.6–1.8). Esta especificación
solo fija qué se muestra, con qué filtro, en qué orden y con qué garantías de paridad.

---

## Clarifications

### Session 2026-11-24

- Q: ¿El resumen debe considerar activos solo los estados `OPEN` e `IN_PROGRESS`, o todos
  los estados distintos de `RESOLVED`, incluido `ESCALATION_REQUIRED`? → A: Todos
  excepto `RESOLVED`; incluye `ESCALATION_REQUIRED`. Requiere enmienda del Art. 1.10
  antes de implementar.
- Q: ¿La especificación debe conservar exactamente los cuatro escenarios BDD indicados, o
  mantener esos cuatro como obligatorios y conservar además los complementarios? → A:
  Cuatro obligatorios (global, filtrado, vacío y CLI) más los complementarios.
- Q: ¿El JSON debe colocar `total_active`, `breached_count` e `incidents` en la raíz y
  limitarse a ellos, o conservar metadatos y el total de escalamiento? → A: Raíz con los
  tres campos más `reference_time` y `component_filter`; sin total de escalamiento.
- Q: En ejecución real, ¿de dónde obtiene el resumen sus incidentes y qué ocurre si el
  almacén no existe? → A: De un almacén en memoria de demostración, cargado al arrancar
  con un conjunto fijo de incidentes de ejemplo; sin persistencia hasta H003.
- Q: ¿El escenario obligatorio de caso vacío debe cubrir tanto un almacén sin incidentes
  activos como un filtro de componente sin coincidencias? → A: Sí; E3 es un solo
  escenario con dos ejemplos (solo `RESOLVED` sin filtro, y filtro sin coincidencias).
- Q: ¿Los cuatro escenarios obligatorios deben redactar sus pasos solo en lenguaje de
  negocio, dejando códigos HTTP y nombres de campos JSON en el contrato? → A: Sí, con un
  glosario que traduce cada término al campo o código del contrato; los complementarios
  pueden seguir siendo técnicos.
- Q: ¿La enmienda del Art. 1.10 se hace como cambio independiente antes de planificar o
  como primera tarea del plan de H002? → A: Primera tarea del plan, en commit propio
  (Constitución + ADR nuevo + `AGENTS.md`); la planificación arranca ya y FR-002 espera
  a esa tarea.

---

## Escenarios de usuario y pruebas

**Escenarios obligatorios del hito**: E1 (resumen global excluyendo `RESOLVED`), E2
(resumen filtrado por componente), E3 (caso vacío) y E10 (consulta equivalente por CLI).
El resto de escenarios son complementarios y se conservan para cubrir orden, política de
SLA, escalamiento, errores y solo lectura.

**Lenguaje de los escenarios**: los cuatro escenarios obligatorios se redactan en lenguaje
de negocio; los complementarios pueden citar códigos y campos del contrato. La
automatización traduce cada término de negocio con este glosario:

| Término de negocio | HTTP | CLI |
|---|---|---|
| consulta por la web | `GET /api/v1/incidents/summary` | — |
| consulta por la terminal | — | subcomando `summary` |
| formato estructurado | cuerpo JSON | `--format json` |
| respuesta exitosa | `200 OK` con JSON válido | código de salida `0`, resultado en `stdout` |
| aviso de recurso inexistente | `404` | — |
| instante de referencia | `reference_time` | `--reference-time` |
| componente filtrado | `component` (parámetro) y `component_filter` (respuesta) | `--component` y `component_filter` |
| total activo | `total_active` | `total_active` |
| total incumplido | `breached_count` | `breached_count` |
| detalle | `incidents` | `incidents` |
| identificador, título, componente, severidad, estado | `incident_id`, `title`, `component`, `severity`, `status` | ídem |
| minutos transcurridos | `elapsed_minutes` | `elapsed_minutes` |
| incumplido | `is_breached` | `is_breached` |
| requiere escalamiento | `requires_escalation` | `requires_escalation` |
| incidente activo | estado `OPEN`, `IN_PROGRESS` o `ESCALATION_REQUIRED` | ídem |
| incidente resuelto | estado `RESOLVED` | ídem |

### Historia 1 — Ver el estado operativo en una sola consulta (Prioridad: 1 — más crítica)

Como persona de guardia, quiero obtener en una sola consulta el total de incidentes
activos, cuántos incumplieron su SLA y el detalle de cada uno, para decidir dónde
intervenir primero sin recorrer incidentes uno por uno.

**Por qué esta prioridad**: es el valor central de H002. Sin esta vista, el operador no
puede priorizar la guardia y la capacidad no entrega valor aunque existan los canales.

**Prueba independiente**: con un almacén sembrado y un instante de referencia fijo, una
sola consulta devuelve los dos totales y el detalle completo con los campos acordados.

**Escenarios de aceptación**:

- **E1 — Resumen global excluyendo `RESOLVED`**
  > **Given** tres incidentes activos de severidades y componentes distintos, uno de ellos
  > con su SLA ya incumplido, y un incidente resuelto
  > **When** la persona de guardia consulta el resumen general en un instante de
  > referencia fijo
  > **Then** obtiene una respuesta exitosa
  > **And** el total activo es 3 y el total incumplido es 1
  > **And** el detalle muestra los tres incidentes activos con identificador, título,
  > componente, severidad, estado, minutos transcurridos, si está incumplido y si requiere
  > escalamiento
  > **And** el incidente resuelto no aparece en el detalle ni en los totales
  > **And** los totales coinciden con el detalle

- **E8 — Incumplimiento y escalamiento son excluyentes**
  > **Given** un incidente activo que superó el umbral de escalamiento sin superar el
  > límite de su SLA y otro que ya superó el límite
  > **When** se consulta el resumen
  > **Then** el primero requiere escalamiento y no está incumplido
  > **And** el segundo está incumplido y no requiere escalamiento

---

### Historia 2 — Enfocarse en un componente (Prioridad: 2)

Como responsable de un componente, quiero filtrar el resumen por componente para ver solo
mis incidentes y sus cifras, sin que el resto del tablero se mezcle con mi operación.

**Por qué esta prioridad**: el filtro es opcional y no bloquea la vista general, pero es
la consulta que usa el equipo dueño del componente durante un incidente.

**Prueba independiente**: dos componentes con incidentes activos; al filtrar por uno, el
detalle y los totales describen solo ese subconjunto.

**Escenarios de aceptación**:

- **E2 — Filtro por componente**
  > **Given** incidentes activos en los componentes `payment-gateway` y `auth-identity`
  > **When** la persona responsable del componente consulta el resumen filtrando por
  > `payment-gateway`
  > **Then** obtiene una respuesta exitosa
  > **And** el detalle muestra solo incidentes de `payment-gateway`
  > **And** el total activo y el total incumplido describen únicamente ese componente
  > **And** el resumen indica `payment-gateway` como componente filtrado

- **E3 — Caso vacío: sin incidentes activos o sin coincidencias**
  > **Given** <situación del almacén>
  > **When** se consulta el resumen <consulta>
  > **Then** obtiene una respuesta exitosa y no un aviso de recurso inexistente
  > **And** el total activo es 0, el total incumplido es 0 y el detalle está vacío
  >
  > | Ejemplo | Situación del almacén | Consulta |
  > |---|---|---|
  > | E3.1 — Sin activos | solo hay incidentes resueltos | sin filtro |
  > | E3.2 — Sin coincidencias | hay incidentes activos, ninguno del componente `reporting-api` | filtrando por `reporting-api` |

---

### Historia 3 — Confiar en una vista reproducible entre canales (Prioridad: 3)

Como operador, quiero que la web y la terminal muestren exactamente lo mismo para el
mismo instante de referencia, incluido un instante pasado, para investigar lo ocurrido
sin dudas sobre qué cifra es la correcta.

**Por qué esta prioridad**: la paridad es una norma de la arquitectura (Art. 2.7) y la
evaluación a un instante dado es una capacidad del roadmap; sin ella la vista sirve para
mirar "ahora", pero no para reconstruir un episodio.

**Prueba independiente**: el mismo almacén y el mismo instante producen el mismo cuerpo
JSON por HTTP y por CLI; un instante distinto cambia las banderas de SLA de forma
consistente con la política canónica.

**Escenarios de aceptación**:

- **E6 — El estado SLA se recalcula al instante consultado**
  > **Given** un incidente P0 activo que a las 09:00 aún no incumplía
  > **When** se consulta el resumen a las 10:30
  > **Then** el incidente aparece como incumplido
  > **And** sus minutos transcurridos corresponden al intervalo entre su creación y las
  > 10:30

- **E10 — Consulta equivalente por terminal (CLI)**
  > **Given** el mismo conjunto de incidentes activos y resueltos y el mismo instante de
  > referencia
  > **When** el operador consulta el resumen por la web y por la terminal en formato
  > estructurado
  > **Then** ambas consultas obtienen una respuesta exitosa
  > **And** muestran el mismo instante de referencia, el mismo componente filtrado, los
  > mismos totales y los mismos incidentes, valor a valor y en el mismo orden

---

### Escenarios transversales

- **E4 — Solo `RESOLVED` queda fuera del resumen**
  > **Given** un almacén con incidentes `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED` y
  > `RESOLVED`
  > **When** se consulta el resumen sin filtro
  > **Then** el detalle contiene los incidentes `OPEN`, `IN_PROGRESS` y
  > `ESCALATION_REQUIRED`
  > **And** el incidente `RESOLVED` no cuenta en ninguna cifra

- **E5 — Un instante de referencia anterior a la creación excluye el incidente**
  > **Given** un incidente activo creado después del instante de referencia consultado
  > **When** se consulta el resumen en ese instante
  > **Then** el incidente no aparece en el detalle ni en las cifras
  > **And** la consulta responde con éxito

- **E7 — Los minutos transcurridos respetan la política de la severidad**
  > **Given** un incidente P0 y un incidente P2 activos, ambos creados el mismo sábado
  > **When** se consulta el resumen en el mismo instante de referencia
  > **Then** el P0 acumula tiempo calendario y el P2 acumula solo minutos hábiles
  > **And** los minutos de cada uno coinciden con la evaluación canónica de SLA de su
  > severidad

- **E9 — Orden determinista del detalle**
  > **Given** incidentes activos de varias severidades y distintos tiempos transcurridos
  > **When** se consulta el resumen
  > **Then** el detalle va de la severidad más crítica a la menos crítica
  > **And** a igual severidad, aparece primero el mayor tiempo transcurrido
  > **And** a igual severidad y tiempo, el identificador ordena de forma ascendente

- **E11a — Invalidez semántica del instante y del filtro**
  > **Given** una consulta con un instante de referencia no parseable o con un filtro
  > vacío o compuesto solo por espacios
  > **When** se envía por HTTP o por CLI
  > **Then** se rechaza sin devolver resumen
  > **And** HTTP responde `422` con el código de error correspondiente
  > **And** el CLI termina con código de salida `3` y escribe el diagnóstico por `stderr`

- **E11b — Parámetro desconocido**
  > **Given** una consulta con un parámetro o una bandera que no forma parte del contrato
  > **When** se envía por HTTP o por CLI
  > **Then** se rechaza sin devolver resumen
  > **And** HTTP responde `400` y el CLI termina con código de salida `2`

- **E12 — La consulta no modifica los datos**
  > **Given** un almacén con incidentes activos y resueltos
  > **When** se consulta el resumen repetidamente
  > **Then** no se crea, modifica ni elimina ningún incidente
  > **And** ninguna traza registra títulos ni textos de reporte

### Trazabilidad de escenarios

| Escenario | Requisitos funcionales |
|---|---|
| E1 | FR-002, FR-003, FR-004, FR-010 |
| E2 | FR-006 |
| E3 (E3.1, E3.2) | FR-002, FR-006, FR-007 |
| E4 | FR-002 |
| E5 | FR-009 |
| E6 | FR-005, FR-008 |
| E7 | FR-005 |
| E8 | FR-005 |
| E9 | FR-011 |
| E10 | FR-001, FR-012, FR-013, FR-014 |
| E11a | FR-012, FR-013 |
| E11b | FR-012, FR-013 |
| E12 | FR-015 |

### Casos borde

| Caso | Comportamiento esperado |
|---|---|
| Almacén sin ningún incidente | Éxito con totales en cero y detalle vacío; no es un error. |
| Incidente creado exactamente en el instante de referencia | Se incluye con 0 minutos transcurridos. |
| Instante de referencia anterior a toda creación | Resumen vacío, sin error. |
| Instante de referencia futuro | Se admite; los minutos y las banderas se recalculan según la política. |
| Filtro con mayúsculas o espacios circundantes | Se normaliza y coincide con el componente canónico. |
| Título con acentos, emojis o caracteres de control escapados | Se devuelve tal cual en JSON, sin romper la salida ni reflejar contenido no escapado. |
| Incidente activo con instante de resolución informado | Dato inconsistente fuera de alcance; el almacén se asume consistente. |
| Consultas concurrentes | Cada consulta ve un estado consistente y no compite por escrituras. |
| `--format` distinto de `table` o `json` | Error de uso con código `2`. |
| Volumen de 10 000 activos | Se mantiene el criterio de éxito SC-001. |

---

## Requisitos

### Requisitos funcionales

- **FR-001**: El sistema DEBE exponer el resumen por los canales HTTP y CLI, y ambos
  DEBEN leer la misma fuente de verdad y evaluar el mismo instante de referencia.
- **FR-002**: El sistema DEBE considerar activos todos los incidentes cuyo estado sea
  distinto de `RESOLVED`, es decir, `OPEN`, `IN_PROGRESS` y `ESCALATION_REQUIRED`. Solo
  `RESOLVED` queda fuera del resumen. Esta definición difiere del Art. 1.10 vigente; su
  implementación DEBE esperar a la enmienda que realiza la primera tarea del plan de H002
  (ver D9).
- **FR-003**: El resumen DEBE informar el total de incidentes activos y el total de
  incidentes que incumplieron su SLA. La necesidad de escalamiento se informa por
  incidente en el detalle, no como total del resumen.
- **FR-004**: El detalle DEBE incluir, por cada incidente, identificador, título,
  componente, severidad, estado, minutos transcurridos, si está incumplido y si requiere
  escalamiento.
- **FR-005**: Los minutos transcurridos, el incumplimiento y el escalamiento DEBEN
  provenir de la evaluación canónica de SLA del dominio (Art. 1.6–1.8). Ningún canal los
  recalcula, aproxima ni sobrescribe.
- **FR-006**: El sistema DEBE permitir filtrar opcionalmente por componente. El filtro
  DEBE comparar el identificador canónico del componente, sin distinguir mayúsculas y
  sin espacios circundantes. Las cifras del resumen DEBEN describir únicamente el
  subconjunto filtrado.
- **FR-007**: Si no existen incidentes activos, o si el filtro no coincide con ningún
  incidente activo, la consulta DEBE responder con éxito, `total_active` 0,
  `breached_count` 0 e `incidents` vacío; no DEBE tratarse como recurso inexistente ni
  como error.
- **FR-008**: El sistema DEBE aceptar un instante de referencia opcional. Si no se
  informa, DEBE usar el reloj inyectado. Una fecha sin zona se interpreta como hora de
  Bogotá (Art. 1.7). La respuesta DEBE declarar el instante efectivamente evaluado.
- **FR-009**: Un incidente creado después del instante de referencia NO DEBE aparecer en
  el resumen de ese instante.
- **FR-010**: Las cifras del resumen DEBEN ser consistentes con el detalle:
  `total_active` DEBE igualar el número de elementos de `incidents`, y `breached_count`
  DEBE igualar el número de incidentes con `is_breached` verdadero.
- **FR-011**: El detalle DEBE tener un orden determinista: severidad de más crítica a
  menos crítica (`P0`, `P1`, `P2`, `P3`); a igual severidad, mayor tiempo transcurrido
  primero; a igualdad de ambos, identificador ascendente.
- **FR-012**: El canal HTTP DEBE exponer el resumen como una consulta de lectura en
  `GET /api/v1/incidents/summary`, con los parámetros opcionales `component` y
  `reference_time`. Un parámetro desconocido DEBE rechazarse como petición no
  interpretable (`400`); un instante no parseable o un filtro vacío DEBEN rechazarse como
  contenido inaceptable (`422`); cualquier otro método DEBE responder `405`.
- **FR-013**: El canal CLI DEBE ofrecer el subcomando `summary` con `--component`,
  `--reference-time` y `--format table|json`. DEBE escribir solo el resultado en
  `stdout` y los diagnósticos en `stderr`, y usar los códigos de salida vigentes: `0`
  éxito, `2` error de uso, `3` entrada inválida, `4` fallo interno.
- **FR-014**: La salida JSON DEBE ser el contrato estable y coincidir valor a valor entre
  HTTP y CLI para el mismo almacén e instante. La tabla del CLI es presentación y no
  forma parte del contrato.
- **FR-015**: La consulta DEBE ser de solo lectura: no DEBE crear, modificar ni eliminar
  incidentes, ni mantener estado entre consultas. Las trazas NO DEBEN registrar títulos
  ni textos de reporte; solo conteos, duración y código de resultado.

### Decisiones de alcance

| # | Decisión | Motivo |
|---|---|---|
| D1 | H002 lee un almacén en memoria de demostración, cargado al arrancar con un conjunto fijo de incidentes de ejemplo; la consulta lo lee en modo solo lectura. | Decisión de producto en la clarificación del 2026-11-24 (pendiente del roadmap). Nadie registra incidentes antes de H003; la persistencia real pertenece a H003/H004. |
| D2 | Activo significa todo estado distinto de `RESOLVED`: `OPEN`, `IN_PROGRESS` y `ESCALATION_REQUIRED`. | Decisión de producto en la clarificación del 2026-11-24. Difiere del Art. 1.10 vigente; se resuelve con D9. |
| D3 | Las cifras describen el subconjunto filtrado. | El operador que filtra espera el total de su componente, reconciliable con el detalle que ve. |
| D4 | El instante de referencia es opcional y se devuelve en la respuesta. | Reproducibilidad (Art. 1.3) y auditoría de qué se evaluó. |
| D5 | Sin paginación en H002. | El usuario pidió el detalle de cada incidente; paginar cambia el contrato y se decide en un hito posterior. |
| D6 | Los conteos van en la raíz del JSON, junto a `reference_time` y `component_filter`; no se publica un total de escalamiento. | La necesidad de escalamiento se deduce del detalle y no fue pedida como cifra; los metadatos permiten reproducir la consulta. |
| D7 | Se reutilizan la envoltura de errores y los códigos de salida de H001. | Una sola convención de error y paridad de canales (Art. 2.7). |
| D8 | La tabla del CLI no es contrato; el JSON sí. | Permite mejorar la presentación sin romper integraciones. |
| D9 | La enmienda del Art. 1.10 es la primera tarea del plan de H002, en commit propio: cambio explícito de la Constitución (`docs/constitution.md` y `.specify/memory/constitution.md`, que repiten el Art. 1.10), ADR nuevo aceptado (que además reemplaza el predicado del índice parcial de ADR-001, hoy limitado a `OPEN` e `IN_PROGRESS`) y actualización de `AGENTS.md`. Ninguna tarea que implemente FR-002 empieza antes. | Clarificación del 2026-11-24. Cumple el Art. 4.1 y el Art. 3.7 (los ADR se reemplazan, no se reescriben) sin bloquear la planificación; la desviación se registra en el seguimiento de complejidad del plan hasta que la tarea se complete. |

### Contrato observable

Los nombres de ruta, parámetros y campos son el contrato que consume el cliente. No
prescriben framework, almacenamiento ni estructura interna; el plan decide cómo se
satisfacen.

**HTTP**

```http
GET /api/v1/incidents/summary?component=payment-gateway&reference_time=2026-11-24T09:00:00
```

```json
{
  "reference_time": "2026-11-24T09:00:00-05:00",
  "component_filter": "payment-gateway",
  "total_active": 2,
  "breached_count": 1,
  "incidents": [
    {
      "incident_id": "INC-1001",
      "title": "Caída de la pasarela de pagos",
      "component": "payment-gateway",
      "severity": "P0",
      "status": "OPEN",
      "elapsed_minutes": 90,
      "is_breached": true,
      "requires_escalation": false
    }
  ]
}
```

Sin filtro, `component_filter` es `null`. Si no hay coincidencias, la respuesta es `200`
con `total_active: 0`, `breached_count: 0` e `incidents: []`.

**CLI**

```bash
uv run python -X utf8 -m src.adapters.inbound.cli summary
uv run python -X utf8 -m src.adapters.inbound.cli summary --component payment-gateway
uv run python -X utf8 -m src.adapters.inbound.cli summary --reference-time 2026-11-24T09:00:00 --format json
```

| Situación | HTTP | CLI |
|---|---|---|
| Consulta válida, con o sin coincidencias | `200` | `0` |
| Instante de referencia no parseable | `422 invalid_timestamp` | `3` |
| Filtro vacío o solo espacios | `422 invalid_payload` | `3` |
| Parámetro o bandera desconocida | `400 invalid_payload` | `2` |
| Método no permitido | `405 method_not_allowed` | — |
| Fallo inesperado | `500 internal_error` | `4` |

La envoltura de error es la de H001: `{"error": {"code", "message", "field"}}`. Los
mensajes van en español para humanos; `code` es estable para el cliente.

### Fuera de alcance

- Autenticación y autorización.
- Crear, modificar, cerrar o asignar incidentes.
- Paginación, exportación a archivos y reportes históricos.
- Alertas, notificaciones o acciones automáticas de escalamiento.
- Canal MCP.
- Cambios a la política de SLA, al calendario hábil o a los estados válidos.
- Persistencia de incidentes, migraciones de datos y carga de incidentes distintos del
  conjunto fijo de demostración.

### Entidades clave

- **Incidente activo**: registro existente con identificador, título, componente,
  severidad, estado y instante de creación; su estado es distinto de `RESOLVED` y no
  tiene instante de resolución.
- **Evaluación SLA**: minutos transcurridos, límite de la severidad, incumplimiento y
  necesidad de escalamiento, derivados de la política canónica.
- **Resumen de activos**: instante de referencia, filtro aplicado, dos totales y detalle
  ordenado.
- **Filtro por componente**: identificador canónico opcional que restringe el universo
  consultado sin alterar los datos.

---

## Criterios de éxito

### Resultados medibles

- **SC-001**: Con 10 000 incidentes activos en el almacén, una consulta del resumen tarda
  menos de 1 segundo por cada canal, medida en proceso (HTTP con el cliente de pruebas,
  CLI con el ejecutor de Typer) y sin contar el arranque del intérprete. El arnés de
  benchmark reporta además el percentil 95 del caso de uso sobre 20 consultas.
- **SC-002**: Para el mismo almacén y el mismo instante de referencia, HTTP y CLI
  coinciden en el 100 % de los campos del contrato y en el orden del detalle, sin
  discrepancias en la suite de referencia.
- **SC-003**: El 100 % de las banderas de incumplimiento y escalamiento coincide con la
  evaluación canónica de SLA en al menos tres instantes de referencia distintos,
  incluidos uno anterior a la creación y uno posterior al límite.
- **SC-004**: El filtro por componente devuelve únicamente incidentes de ese componente y
  no altera ninguna cifra de los demás componentes: 0 diferencias al comparar antes y
  después.
- **SC-005**: Mil consultas consecutivas producen 0 altas, 0 modificaciones y 0 bajas en
  el almacén.
- **SC-006**: En el 100 % de las consultas, `total_active` y `breached_count` igualan los
  conteos correspondientes del detalle.
- **SC-007**: Un operador responde "cuántos incidentes están incumplidos y cuáles
  requieren escalamiento" con una sola consulta, sin abrir el detalle de cada incidente.

---

## Supuestos

- **Fuente de datos**: en ejecución, H002 lee un almacén en memoria de demostración que
  se carga al arrancar con un conjunto fijo de incidentes de ejemplo; no hay persistencia
  hasta H003. La consulta no siembra, migra ni repara datos.
- **Datos de demostración**: el conjunto fijo cubre los estados `OPEN`, `IN_PROGRESS`,
  `ESCALATION_REQUIRED` y `RESOLVED` y al menos dos componentes. Es el mismo en HTTP y en
  CLI, de modo que ambos canales leen la misma fuente de verdad (FR-001). La carga ocurre
  al arrancar, fuera de la consulta; el resumen no la provoca ni la modifica. Los
  escenarios BDD declaran sus propios incidentes en el `Given` y no dependen de este
  conjunto.
- **Activo = todo estado distinto de `RESOLVED`**: incluye `OPEN`, `IN_PROGRESS` y
  `ESCALATION_REQUIRED`. Es una decisión de producto que difiere del Art. 1.10 vigente.
  La enmienda es la primera tarea del plan de H002 (D9); hasta completarla, la
  planificación avanza pero FR-002 no se implementa.
- **Semántica del filtro**: coincidencia exacta con el identificador canónico del
  componente, sin distinguir mayúsculas y recortando espacios. Un componente desconocido
  no es un error: devuelve un resumen vacío.
- **Instante de referencia**: si no se informa, se usa el reloj inyectado; una fecha sin
  zona se interpreta como hora de Bogotá (Art. 1.7). Se admiten instantes futuros. Un
  instante anterior a la creación de un incidente lo excluye de esa consulta.
- **Sin paginación**: H002 devuelve el detalle completo del universo consultado. El
  volumen de referencia es de 10 000 incidentes activos.
- **Orden**: severidad de más crítica a menos crítica, luego mayor tiempo transcurrido y
  luego identificador ascendente.
- **Consistencia del almacén**: se asume que un incidente activo no tiene instante de
  resolución. La reparación de datos inconsistentes está fuera de alcance.
- **Título**: el título registrado del incidente, no el texto crudo del reporte original.
- **Operación**: se hereda el despliegue en loopback sin autenticación de H001; la
  consulta no amplía la superficie de exposición.
- **Sin dependencias nuevas**: la capacidad se resuelve con el stack y los puertos
  existentes (T2, T5); no se introducen ORM, `pandas` ni librerías de calendario.
- **H001 intacto**: el triaje y sus contratos no cambian; esta capacidad agrega una
  consulta nueva.

---

## Dependencias

- **Canales de H001**: raíz de composición, adaptador HTTP y adaptador CLI existentes.
- **Evaluación canónica de SLA**: la evaluación de SLA y la política de severidad del
  dominio (Art. 1.6–1.8), única fuente de minutos, incumplimiento y escalamiento.
- **Almacén en memoria de demostración**: conjunto fijo de incidentes cargado al arrancar,
  con identificador, título, componente, severidad, estado, creación y resolución; la
  consulta lo lee en modo solo lectura.
- **Constitución**: Art. 1.3 (determinismo), 1.6–1.9 (SLA), 1.10 (estados; su enmienda
  sobre la definición de activo es la primera tarea del plan, D9), 2.7 (paridad), 3.2–3.5
  (puertos y repositorio), 4.1 (enmienda), 5.1–5.3 (BDD y verificación), T2 y T5 (stack).
- **Sin dependencias nuevas**: no se requieren paquetes de runtime ni de desarrollo
  adicionales.

---

## Preguntas abiertas

| Tema | Dueño | Efecto |
|---|---|---|
| Paginación o límite para volúmenes muy grandes | H003/H004 | Cambiaría el contrato de detalle; hoy se asume detalle completo. |
| Exponer minutos restantes por incidente | H003 | No fue pedido; el detalle actual permite calcularlo con el límite de la severidad. |
