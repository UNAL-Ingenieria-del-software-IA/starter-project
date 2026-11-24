# 001 — Triaje multiinterfaz (H001): servicio HTTP y CLI

- **Estado**: Propuesto — bloqueado para implementación hasta que exista ADR-004 (stack de canales y pruebas).
- **Fecha**: 2026-11-23
- **Hito**: H001 — Triaje multi-interfaz (`docs/ROADMAP.MD`)
- **Autoridad**: subordinada a `docs/constitution.md`, que prevalece sobre esta spec,
  sobre ADR-003 y sobre el código.
- **Trazabilidad**: Art. 1.1–1.12 (dominio), Art. 2.1–2.8 (hexagonal y paridad),
  Art. 3.1–3.7 (gobernanza, BDD, verificación), ADR-003 (topología).

---

## 0. Resumen

Se expone el motor de triaje existente por dos canales nuevos, ambos invocando el
mismo caso de uso y sin persistir nada:

1. **HTTP**: un recurso `POST /v1/triage` que recibe un lote de 1..N reportes y
   devuelve la clasificación correlacionada de cada uno.
2. **CLI**: un subcomando `triage` que recibe los mismos reportes por argumento,
   archivo o `stdin` y produce el mismo resultado.

La clasificación se define **una sola vez** en `src/domain/`; los adaptadores solo
traducen entrada y salida (Art. 2.5). La igualdad entre canales se verifica con una
suite de contrato compartida (Art. 2.7).

---

## 1. Decisiones fijadas por esta especificación

| # | Decisión | Motivo |
|---|---|---|
| D1 | Un **único** recurso HTTP `POST /v1/triage` con cuerpo `{"reports": [...]}` (1..N). | La correlación es de lote; separar unitario y lote crearía dos contratos con semánticas distintas. |
| D2 | La unidad de correlación es **siempre el lote**; un lote de 1 es válido. | `classify_incident_batch` es la única API pública con correlación; sin lote, `merge` y `group_key` serían inalcanzables por HTTP. |
| D3 | `created_at` es **opcional**; si falta, el servidor completa el instante vía `ClockPort`. | Satisface Art. 1.3: el reloj se inyecta, el dominio nunca lo lee. |
| D4 | `incident_id` **no** forma parte del contrato de H001; se reserva para H003. | H001 no persiste; inventar identidad es una decisión de H003. |
| D5 | No se añaden campos de urgencia ni `provisional` a la salida. | Decisión del producto; consecuencias en §1.1. |
| D6 | La salida es JSON con campos de dominio + `analysis` como **presentación**. | `rationale` es redundante, `consistency_ratio` es constante `1.0`. |
| D7 | Migración hexagonal **dentro del alcance** de este hito. | ADR-003 es la topología aceptada; los canales nuevos deben nacer en su capa. |
| D8 | Verificación de paridad con **un solo comando**, en proceso, sin levantar servidor. | Los estados se prueban porque el adaptador separa mapeo de E/S. |
| D9 | `-m src.triage_rules` se conserva como **puente** delgado. | Es oráculo graduado y aparece en `AGENTS.md` y `CONTEXT_LOG.md`. |
| D10 | `-X utf8` sigue siendo obligatorio en todos los comandos. | Art. 3.1. |
| D11 | `422` para invalidez **semántica**; `400` para invalidez **sintáctica**. | Separa "JSON roto o campo desconocido" de "JSON correcto con contenido inaceptable". |
| D12 | El CLI acepta `--incident-id` como **etiqueta local de presentación**. | Comodidad de soporte; nunca viaja por HTTP ni aparece en `--format json` (D4 intacto). |

### 1.1 Limitaciones aceptadas y declaradas

- **Urgencia como señal (Roadmap H001).** `extract_signals` detecta trampas léxicas
  (`lexical_traps`), pero `TriageResult` no las expone como campo. En H001 la urgencia
  declarada se expone **solo como prosa** dentro de `analysis` ("Nota léxica: ...").
  Se declara cumplimiento **parcial** del Roadmap y queda como entrada para H003.
- **`provisional`** tampoco es campo; solo aparece en el texto del último paso de
  `analysis` y en `rationale`, que no viaja por la red.
- **Colapso de la ventana temporal.** Si el cliente omite `created_at`, todos los
  reportes del lote comparten el instante del servidor y el lapso entre ellos es cero;
  dos caídas del mismo componente caen dentro de la ventana de fusión salvo que el
  texto traiga marca de recurrencia. Es comportamiento documentado, no defecto; el
  cliente que necesite distinguir episodios debe enviar `created_at`.
- **Ausencia de identidad.** Sin `incident_id` en el contrato, la prosa de correlación
  usa rótulos posicionales `R1..Rn`. Ese rótulo es presentación, no identidad.

---

## 2. Alcance

**Dentro:** los dos adaptadores de entrada, el caso de uso `IncidentService`, los
puertos `IncidentRepositoryPort` (implementación nula) y `ClockPort`, la raíz de
composición, la migración de triaje a `src/domain/`, la suite de contrato y este manual.

**Fuera:** autenticación y autorización, multi-cliente, alta disponibilidad,
persistencia de cualquier tipo, frontend (solo se define el contrato que consume),
canal MCP, SLA en tiempo real y contenedores (H002/H004).

---

## 3. Bloqueo de gobernanza

Art. 3.2 deja la elección de framework HTTP, framework de CLI y herramienta de pruebas
en un ADR pendiente. Esta spec **no elige stack**: define el contrato y lo deja
implementable con librería estándar (`http.server`, `argparse`, `unittest`), sin
adelantar dependencias (Art. 3.2, ADR-001/002). Mientras ADR-004 no exista, esta spec
está aprobada como contrato pero **no habilitada para codificación**.

---

## 4. Arquitectura destino

### 4.1 Layout

```
src/
  domain/
    models.py                 # entidades y Literal (movido desde src/models.py)
    triage/
      signals.py              # extract_signals
      severity.py             # decide_severity
      routing.py              # route_component, decide_action
      correlation.py          # correlate_batch
      pipeline.py             # classify_incident_batch
    sla/                      # sla_calculator, working_time_calculator, holidays
  application/
    incident_service.py       # IncidentService
    ports.py                  # IncidentRepositoryPort, ClockPort (typing.Protocol)
  adapters/
    inbound/
      rest/handler.py         # handle(payload: bytes, now: datetime) -> (status, dict)
      rest/server.py          # envoltura de http.server sobre handler
      cli/main.py             # entrada(argv, now) -> (exit_code, stdout, dict)
    outbound/
      null_repository.py      # IncidentRepositoryPort nulo (H001 sin efectos)
  main.py                     # raíz de composición
specs/001-triage-endpoint-manual.md
tests/test_contrato_canales.py
tests/contrato_casos.json
```

`src/domain/` no importa `json`, `argparse`, `sqlite3`, `pathlib`, HTTP ni variables de
entorno (Art. 1.2). Por eso `load_reports` (hoy en `triage_rules`) y `_run_triage_audit`
se trasladan al adaptador CLI, no al dominio.

### 4.2 Puertos

- `IncidentRepositoryPort`: mínimo, con la implementación **nula** para H001 (Art. 2.4;
  ADR-003 la usa para expresar "sin efectos secundarios").
- `ClockPort`: suministra el instante para completar `created_at` ausente. En la suite
  se inyecta un reloj fijo.

### 4.3 Migración

Movimiento, no copia (ADR-003): mientras existan módulos planos y paquetes nuevos no
puede haber dos fuentes de verdad. `src/triage_rules.py` y `src/models.py` quedan como
puentes de reexportación y desaparecen en un hito posterior con su propio ADR. Durante
toda la migración deben seguir verdes:

```
uv run python -X utf8 -m src.sla_calculator
uv run python -X utf8 -m src.triage_rules
```

(Art. 1.12 y 3.5.) Los cambios de dominio arrastran en el mismo cambio la regresión, la
auditoría del fixture y estos escenarios BDD.

---

## 5. Contrato funcional compartido

### 5.1 Entrada

| Campo | Tipo | Obligatorio | Reglas |
|---|---|---|---|
| `reports` | array | sí | 1..500 elementos; array vacío ⇒ `422` |
| `reports[].raw_text` | string | sí | 1..10 000 puntos de código; vacío o solo espacios ⇒ `422` |
| `reports[].created_at` | string ISO-8601 | no | Con offset o naive; naive = hora de Bogotá (Art. 1.7). Si falta, lo completa `ClockPort` |

Campos desconocidos se **rechazan** con `400`. `incident_id` está reservado en HTTP:
enviarlo produce `400` con `code: "reserved_field"` (D4). El CLI sí lo acepta como
etiqueta local (D12), sin cruzar a HTTP.

### 5.2 Salida

```json
{ "results": [ { "...": "..." } ] }
```

`results` conserva **el orden y la longitud** del arreglo de entrada.

| Campo | Tipo | Nulo | Estabilidad |
|---|---|---|---|
| `severity` | `"P0" \| "P1" \| "P2" \| "P3"` | no | contrato |
| `component` | string (incluye `"unclassified"`) | no | contrato |
| `recommended_team` | `"Backend-Core" \| "Platform-SRE" \| "Data-DBA" \| "Security-IAM"` | no | contrato |
| `action` | el `Literal` `TriageAction` del dominio | no | contrato |
| `duplicate_type` | `"none" \| "exact_duplicate" \| "recurrence" \| "related_incidents"` | no | contrato |
| `duplicate_group_key` | string | sí | contrato |
| `merge` | boolean | no | contrato |
| `analysis` | array de string (≥1) | no | **presentación**, no estable |

**No se publican**: `incident_id` (D4), `rationale` (redundante), `consistency_ratio`
(siempre `1.0`) ni `to_output_line()` (queda en CLI y auditoría legacy).

Los umbrales, el orden de las reglas de severidad, la precedencia de enrutamiento y la
forma canónica de `duplicate_group_key` son los del dominio (Art. 1.5, 1.6, 1.9, 1.11).
**Esta spec no los replica**: los cita por artículo, nunca por valor.

### 5.3 Semántica de lote

La correlación ocurre dentro del lote recibido y no trasciende la petición: el servicio
no recuerda nada entre llamadas. Dos peticiones iguales con el mismo instante de
referencia devuelven lo mismo; dos peticiones con instantes distintos pueden diferir en
`duplicate_type` y `merge` (D3).

Con un solo reporte no hay correlación posible: `duplicate_type` es `"none"`,
`duplicate_group_key` es `null` y `merge` es `false`.

---

## 6. Contrato HTTP

### 6.1 Recurso

| Método | Ruta | Semántica |
|---|---|---|
| `POST` | `/v1/triage` | Clasifica y correlaciona el lote. Sin efectos secundarios. |
| `GET` | `/v1/health` | `200 {"status":"ok"}`. No toca el motor. |
| otros | `/v1/triage`, `/v1/health` | `405` |

No se acepta `GET` con texto en la query: el cuerpo puede ser grande, multilínea y no
ASCII.

### 6.2 Ejemplo

```http
POST /v1/triage HTTP/1.1
Content-Type: application/json; charset=utf-8

{ "reports": [
    { "raw_text": "URGENTE: el gateway de pagos devuelve HTTP 502 en todas las transacciones",
      "created_at": "2026-11-05T08:15:00" },
    { "raw_text": "Otra vez cayó la pasarela de cobros con tarjeta, error 502" }
] }
```

```json
{ "results": [
    { "severity": "P0", "component": "payment-gateway", "recommended_team": "Backend-Core",
      "action": "escalate_24x7", "duplicate_type": "recurrence",
      "duplicate_group_key": "payment-availability", "merge": false,
      "analysis": ["1. Radio de afectación: ...", "..."] },
    { "severity": "P0", "component": "payment-gateway", "recommended_team": "Backend-Core",
      "action": "escalate_24x7", "duplicate_type": "recurrence",
      "duplicate_group_key": "payment-availability", "merge": false,
      "analysis": ["1. ..."] }
] }
```

`duplicate_type` y `duplicate_group_key` describen al **grupo**, no al reporte: todos los
miembros de un grupo comparten el mismo tipo y la misma clave. El único campo que
distingue al reporte dentro del grupo es `merge`, que es `true` solo en el duplicado
exacto posterior. En el ejemplo anterior, el segundo reporte trae la marca de
recurrencia ("Otra vez"), por eso el grupo entero es `recurrence` y nadie fusiona.

### 6.3 Errores

Envoltura única:

```json
{ "error": { "code": "invalid_payload", "message": "…", "field": "reports[1].raw_text" } }
```

`message` en español para humanos; `code` estable para el frontend; `field` opcional.

| Situación | Estado | `code` |
|---|---|---|
| JSON malformado o codificación no UTF-8 | 400 | `invalid_json` |
| Falta `reports`, tipo incorrecto (no-string donde se espera string) o campo desconocido | 400 | `invalid_payload` |
| `incident_id` o cualquier campo reservado | 400 | `reserved_field` |
| `reports` vacío | 422 | `invalid_payload` |
| `raw_text` vacío, solo espacios o cadena vacía en campo obligatorio | 422 | `invalid_payload` |
| `created_at` no parseable | 422 | `invalid_timestamp` |
| Cuerpo > 64 KB | 413 | `payload_too_large` |
| `raw_text` > 10 000 caracteres, o lote > 500 | 413 | `payload_too_large` |
| `Content-Type` distinto de `application/json` | 415 | `unsupported_media_type` |
| Método no permitido | 405 | `method_not_allowed` |
| Fallo inesperado del motor | 500 | `internal_error` |

Regla de reparto (D11): `400` = la petición no es interpretable; `422` = la petición es
interpretable y su contenido es inaceptable.

### 6.4 Operación

- **Bind**: `127.0.0.1` y puerto `8080` por defecto, ambos por bandera de arranque. No
  se expone en `0.0.0.0` por defecto.
- **CORS**: deshabilitado salvo allowlist explícita de orígenes por configuración; por
  defecto ningún origen cruzado.
- **Autenticación**: ninguna (fuera de alcance del roadmap). Consecuencia declarada: el
  servicio debe permanecer en loopback.
- **Logs**: nunca se registra `raw_text` ni el cuerpo. Solo método, ruta, estado y
  duración. Es dato personal del reportante.
- **Concurrencia**: sin estado compartido mutable; cada petición se resuelve con el
  motor puro.

---

## 7. Contrato CLI

```bash
uv run python -X utf8 -m src.adapters.inbound.cli triage --raw-text "..." [--created-at ISO]
uv run python -X utf8 -m src.adapters.inbound.cli triage --incident-id INC-1001 --raw-text "..."
uv run python -X utf8 -m src.adapters.inbound.cli triage --file reportes.json
uv run python -X utf8 -m src.adapters.inbound.cli triage --file - < reportes.json
uv run python -X utf8 -m src.adapters.inbound.cli triage --file data/sample_incidents.json --format json
uv run python -X utf8 -m src.adapters.inbound.cli audit
```

| Bandera | Efecto |
|---|---|
| `--raw-text TEXTO` | Un reporte. Repetible: cada ocurrencia añade un reporte al lote. |
| `--incident-id ID` | Etiqueta local del `--raw-text` inmediatamente anterior. Solo presentación: no viaja por HTTP y no aparece en `--format json` (D12). |
| `--created-at ISO` | Aplica al `--raw-text` inmediatamente anterior. |
| `--file RUTA` / `--file -` | Lote en JSON, con la misma forma que el cuerpo HTTP: arreglo de reportes o `{"reports": [...]}`. |
| `--now ISO` | Fija el instante de referencia (`ClockPort`) para demos y reproducción. |
| `--format table\|json\|output` | `table` por defecto; `json` imprime el mismo cuerpo que HTTP; `output` imprime `to_output_line()` por línea. |
| `-v`, `--explain` | Añade `analysis` a la salida de tabla. |

- **stdout**: solo el resultado. **stderr**: diagnósticos y mensajes de error.
- **Códigos de salida**: `0` éxito · `2` error de uso (argparse) · `1` entrada inválida
  (equivalente a `400`/`413`/`415`/`422`) · `4` fallo interno (equivalente a `500`).
  *Enmienda 2026-11-24 (spec 003 D8, Constitución 3.0.0): la entrada inválida pasa de
  `3` a `1` en todo el CLI.*
- `audit` reproduce exactamente la auditoría actual sobre `data/sample_incidents.json`;
  `-m src.triage_rules` delega en él (D9), por lo que su salida y su orden no cambian.

---

## 8. Paridad y verificación

**Definición operativa de paridad (Art. 2.7):** para el mismo lote y el mismo instante
de referencia, los campos de contrato de §5.2 coinciden valor a valor entre REST y CLI;
`analysis` coincide como lista ordenada. Los campos de presentación no eximen de la
igualdad.

**Diseño que lo hace verificable sin red (D8):** cada adaptador expone una función pura

```python
rest.handle(payload: bytes, now: datetime) -> tuple[int, dict]
cli.entrada(argv: Sequence[str], now: datetime) -> tuple[int, str, dict]
```

El servidor y `__main__` solo las envuelven; por eso los estados `200/400/413/415/422`
se prueban en proceso.

**Un solo comando:**

```bash
uv run python -X utf8 -m unittest tests.test_contrato_canales -v
```

Un único test `test_paridad` recorre `tests/contrato_casos.json` y, en **una pasada**:

1. Hace una llamada `handle()` y una `entrada()` por lote de casos válidos.
2. Compara ambos resultados entre sí (paridad) y contra la expectativa declarada.
3. Verifica que `results` conserva orden y longitud.
4. Verifica los estados `400/413/415/422` de los casos inválidos, incluidos los `code`.
5. Verifica el caso de un lote de 1 y el de 500.
6. Verifica que `audit` sobre el fixture produce la salida esperada (oráculo graduado).

No se levanta servidor ni se abre puerto en la suite. El arranque real y las cabeceras se
cubren con **un** `curl` de humo documentado en el Anexo, no automatizado.

---

## 9. Escenarios BDD

### 9.1 Escenarios obligatorios del hito

**E1 — Caída crítica en la pasarela de pagos**

> **Given** un reporte que describe una caída global del gateway de pagos con HTTP 502,
> múltiples comercios afectados y urgencia declarada
> **When** se clasifica mediante `POST /v1/triage` en un lote de un solo reporte
> **Then** la respuesta es `200`
> **And** `severity` es `"P0"`
> **And** `component` es `"payment-gateway"`
> **And** `recommended_team` es `"Backend-Core"`
> **And** `action` es `"escalate_24x7"`
> **And** `duplicate_group_key` es `null`, porque un lote de un reporte no tiene
> correlación
> **And** la nota léxica de "URGENTE" aparece en `analysis` sin alterar la severidad

**E1b — La caída se agrupa cuando hay más de un reporte**

> **Given** un lote con dos reportes de caída del mismo componente, sin marca de
> recurrencia y dentro de la ventana de fusión
> **When** se clasifican
> **Then** ambos comparten `duplicate_group_key` con la forma canónica
> `<prefijo-componente>-availability`, es decir `"payment-availability"` (Art. 1.11)
> **And** `duplicate_type` es `"exact_duplicate"` y `merge` es `true` solo en el segundo

**E2 — Cuenta individual bloqueada que menciona "hoy"**

> **Given** un reporte que dice que la cuenta de un usuario está bloqueada y que necesita
> acceder "hoy mismo" para enviar un informe
> **When** se clasifica en un lote de uno
> **Then** la respuesta es `200`
> **And** `severity` es `"P2"` y **no** `"P0"`, porque la urgencia declarada no decide
> la severidad (Art. 1.4)
> **And** `component` es `"auth-identity"`
> **And** `recommended_team` es `"Security-IAM"`
> **And** `action` es `"restore_account"`
> **And** `analysis` registra "hoy" como trampa léxica

**E3 — Entradas vacías o con solo espacios**

> **Given** una petición cuyo `raw_text` es `" "` o una cadena vacía
> **When** se envía a `POST /v1/triage`
> **Then** la respuesta es `422 Unprocessable Entity`
> **And** el cuerpo es `{"error": {"code": "invalid_payload", "field": "reports[N].raw_text"}}`
> **And** el motor no se ejecuta y no se devuelve ningún `result`

**E3b — Etiqueta vacía por CLI**

> **Given** una invocación `triage --incident-id "" --raw-text "..."`.
> **When** se ejecuta
> **Then** termina con código `1`, escribe el diagnóstico por `stderr` y no imprime
> resultado por `stdout` *(antes `3`; enmienda de spec 003 D8)*

**E4 — Paridad del canal CLI**

> **Given** el reporte `INC-1001` del fixture, invocado como
> `triage --incident-id INC-1001 --raw-text "URGENTE: El gateway de pagos devuelve HTTP 502 …"`
> **When** se ejecuta con `--format json`
> **Then** termina con código `0`
> **And** `stdout` es JSON válido con forma `{"results": [ ... ]}` y exactamente un elemento
> **And** `severity` es `"P0"` y `recommended_team` es `"Backend-Core"`
> **And** el JSON no incluye `incident_id`, porque la etiqueta es solo presentación (D12)
> **And** el mismo lote por HTTP produce los mismos campos de contrato (Art. 2.7)

### 9.2 Escenarios complementarios

**E5 — Degradación de rendimiento según métrica**
> **Given** un lote con latencia declarada superior al umbral, otro con lentitud sin
> métrica y otro batch que completa correctamente
> **When** se clasifican
> **Then** son `P2`, `P3` y `P3` respectivamente, y sus `analysis` declaran la severidad
> como provisional

**E6 — Saturación de infraestructura compartida**
> **Given** un reporte de `94 %` de conexiones con timeouts en el pool y otro idéntico
> que menciona `staging`
> **When** se clasifican
> **Then** el primero es `P1` con `mitigate_capacity_risk` y el segundo es `P3`

**E7 — Recurrencia que nunca fusiona**
> **Given** dos caídas del mismo componente donde la segunda dice "otra vez"
> **When** se clasifican
> **Then** `duplicate_type` es `"recurrence"` y `merge` es `false` en ambos

**E8 — Causa raíz compartida de rendimiento**
> **Given** dos degradaciones de alto volumen en módulos distintos y un reporte de
> presión sobre la base de datos
> **When** se clasifican
> **Then** los tres comparten `duplicate_group_key` canónico, `duplicate_type` es
> `"related_incidents"`, `merge` es `false` y las degradaciones reciben
> `investigate_shared_root_cause`

**E9 — Reporte sin señales suficientes**
> **Given** un reporte sin señales de impacto reconocibles
> **When** se clasifica
> **Then** la severidad es `P3`, el componente es `"unclassified"` y la acción es
> `"manual_review"`

**E10 — Contrato estricto**
> **Given** un cuerpo con `incident_id` o con un campo desconocido
> **When** se envía a `POST /v1/triage`
> **Then** se rechaza con `400` y el `code` correspondiente, sin clasificar nada

**E11 — Límites del lote**
> **Given** un lote de 501 reportes y otro cuyo `raw_text` supera los 10 000 caracteres
> **When** se envían
> **Then** se rechazan con `413` y `code: "payload_too_large"` sin ejecutar el motor

**E12 — Sin efectos secundarios**
> **Given** cualquier lote clasificado
> **When** termina la petición
> **Then** no se escribió ningún archivo ni registro persistente y ningún log contiene
> `raw_text`

### 9.3 Desviaciones respecto al borrador del solicitante

Estas cuatro diferencias son deliberadas y se documentan aquí para que la decisión no se
pierda. Cambiarlas exige enmendar el dominio y, en dos casos, un ADR.

| Borrador solicitado | Texto adoptado | Motivo |
|---|---|---|
| `component="payments-gateway"` | `component="payment-gateway"` | El valor canónico lo fija `_COMPONENT_ROUTES` en el dominio; renombrarlo en un DTO o en una prueba duplicaría la regla (Art. 1.1) y cambiaría la auditoría graduada. |
| `duplicate_group_key="payments-gateway:http-502-outage"` | `"payment-availability"` y solo con ≥2 reportes | Art. 1.11 fija el formato `<prefijo-componente>-availability`; la clave la calcula el dominio y el adaptador solo la transporta. El formato `componente:síntoma` sería un cambio de dominio con ADR y actualización de regresión (Art. 1.12). Además, un lote de un reporte no tiene correlación: la clave es `null`. |
| `422` para `incident_id=""` por HTTP | `400 reserved_field` si `incident_id` viaja por HTTP; `422` para `raw_text` vacío o solo espacios | D4 mantiene `incident_id` fuera del contrato de H001; el `422` se reserva para contenido inaceptable, no para campos prohibidos. |
| `triage --incident-id … --raw-text …` | Se adopta tal cual, con `--incident-id` como etiqueta local | Se acepta la comodidad de soporte sin reabrir el contrato HTTP: la etiqueta no viaja por la red ni aparece en `--format json`. |

---

## 10. Matriz de casos borde

| Caso | Comportamiento esperado |
|---|---|
| `raw_text` vacío o solo espacios | `422 invalid_payload` |
| `raw_text` = solo "urgente" | `P3` provisional, `unclassified`, `manual_review`, nota léxica presente |
| Texto en inglés o sin señales | `P3` provisional, `unclassified` |
| HTML o JSON embebido en `raw_text` | Se tratan como texto plano; se devuelven solo dentro de `analysis`, sin reflexión |
| Emojis y acentos | Aceptados; el dominio normaliza (NFKD) antes de decidir |
| Caracteres de control escapados en JSON | Aceptados; no rompen la salida |
| Texto que coincide con varias rutas | Gana la primera del orden de `_COMPONENT_ROUTES` (más específico/crítico primero) |
| `5xx` aislado sin alcance global | `P2` provisional con acción de revisión manual |
| `created_at` con offset explícito | Se respeta el offset; no se reinterpreta como Bogotá |
| `created_at` futuro | Aceptado; no hay validación de horizonte en H001 |
| Lote de 1 | Válido; `duplicate_type` `none`, `duplicate_group_key` `null` |
| Dos reportes con el mismo texto | Sin `incident_id` en el contrato no hay colisión de identidad; el resultado depende solo de componente, señal y tiempo |
| Fallo interno del motor | `500 internal_error`; nunca se filtra el texto del reporte |

---

## 11. Criterio de terminado

1. `uv run python -X utf8 -m unittest tests.test_contrato_canales` en verde, con los
   escenarios de §9 automatizados.
2. `uv run python -X utf8 -m src.sla_calculator` y
   `uv run python -X utf8 -m src.triage_rules` en verde y con salida sin cambios.
3. `src/domain/` y `src/application/` sin importaciones de `argparse`, `json`, `sqlite3`,
   HTTP ni `pathlib` (revisión explícita, Art. 3.5).
4. Ninguna regla de severidad, SLA, equipo, acción o duplicados fuera de `domain/`
   (Art. 3.6d).
5. `AGENTS.md` actualizado con los comandos nuevos y el layout, sin eliminar los
   existentes (Art. 4.1).

---

## 12. Preguntas abiertas

| Tema | Dueño |
|---|---|
| Stack de HTTP, CLI y pruebas (ADR-004) — **bloquea implementación** | ADR pendiente |
| Duración de los puentes `src/triage_rules.py` y `src/models.py` | H002 |
| Exponer urgencia declarada como campo estructurado | H003 |
| `incident_id` en el contrato | H003, al existir persistencia |
| Si `analysis` sigue siendo no estable o se congela | H002 |
| Si se adopta la clave de grupo `componente:síntoma` en lugar de la canónica | ADR de dominio |

---

## Anexo — Manual de uso

**HTTP, una vez implementado:**

```bash
curl -s http://127.0.0.1:8080/v1/health
curl -s -X POST http://127.0.0.1:8080/v1/triage \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"reports":[{"raw_text":"Los usuarios de varias organizaciones ven facturas ajenas"}]}'
```

**CLI:**

```bash
uv run python -X utf8 -m src.adapters.inbound.cli triage \
  --raw-text "URGENTE: el login de mi cuenta está bloqueado"
uv run python -X utf8 -m src.adapters.inbound.cli triage \
  --incident-id INC-1001 --raw-text "URGENTE: el gateway de pagos devuelve HTTP 502" --format json
uv run python -X utf8 -m src.adapters.inbound.cli triage \
  --file data/sample_incidents.json --format table
uv run python -X utf8 -m src.adapters.inbound.cli audit
```

Recordatorio operativo: en este equipo Windows todo comando conserva `-X utf8` (D10).
