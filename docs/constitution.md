# Constitución — IncidentOps

- **Estado**: Vigente
- **Fecha**: 2026-11-23
- **Alcance**: todo `src/`, `docs/` y `tests/`
- **Autoridad**: norma superior del proyecto. Todo ADR, módulo, prueba y documento
  operativo debe cumplirla. Toda excepción exige ADR aceptado que la enmiende.
- **Decisiones que la sustentan**: `docs/adr/0003-arquitectura-hexagonal.md` (topología);
  `docs/adr/0005-incidente-activo-distinto-de-resuelto.md` (definición de activo, Art. 1.10).

---

## Artículo 1 — Un único dominio determinista

1.1 **Fuente única de verdad.** Las reglas de triaje, la política SLA, el calendario,
los equipos, los estados y la clave de duplicados viven **solo** en `src/domain/`.
Ningún caso de uso, adaptador, DTO, esquema, fixture o prueba puede reimplementar,
aproximar ni sobrescribir esos valores.

1.2 **Pureza.** `domain/` no importa `sqlite3`, `argparse`, `json`, HTTP, MCP,
frameworks, rutas del proyecto ni variables de entorno. Recibe `datetime` como
parámetro, no llama a `datetime.now()`, no imprime y devuelve valores inmutables.

1.3 **Determinismo.** Misma entrada + mismo `reference_time` ⇒ mismo resultado, en
cualquier canal, proceso o ejecución. El tiempo se inyecta explícitamente o vía
`ClockPort`; nunca se lee del reloj dentro del núcleo.

1.4 **Severidad por impacto, nunca por urgencia.** "urgente", "hoy", "ASAP" se
registran como trampas léxicas y se documentan en el análisis; jamás cambian la
severidad.

1.5 **Pipeline de triaje invariante.** `extract_signals → decide_severity →
route_component → correlate_batch`. El orden, los umbrales y la semántica de cada
etapa son parte del contrato de dominio.

1.6 **Política SLA canónica.**

| Severidad | Límite (min) | Cómputo |
|---|---|---|
| P0 | 60 | Calendario 24x7 |
| P1 | 240 | Calendario 24x7 |
| P2 | 480 | Horario hábil |
| P3 | 1440 | Horario hábil |

1.7 **Horario hábil.** Lunes a viernes, 08:00–18:00, hora `America/Bogota`
(UTC-5 fijo, `COT`), excluyendo festivos nacionales colombianos calculados
dinámicamente (Ley 51/1983). Una fecha sin zona se interpreta como hora de Bogotá.

1.8 **Escalamiento e incumplimiento.** `escalation_limit = int(max * 0.75)`.
Requiere escalamiento si el incidente no está `RESOLVED`, no está incumplido y
`elapsed >= escalation_limit`. Hay incumplimiento solo si `elapsed > max`; alcanzar
el límite exacto no incumple. Escalamiento e incumplimiento son excluyentes.
`requires_escalation` es un valor **derivado** del SLA: no se persiste ni se recalcula
en el adaptador. `ESCALATION_REQUIRED` es un estado del ciclo de vida, no un resultado
de la evaluación.

1.9 **Equipos válidos (conjunto cerrado).** `Backend-Core`, `Platform-SRE`,
`Data-DBA`, `Security-IAM`. Añadir o renombrar un equipo es cambio de dominio.

1.10 **Estados válidos.** `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`, `RESOLVED`.
Se consideran activos todos los estados distintos de `RESOLVED`: `OPEN`, `IN_PROGRESS`
y `ESCALATION_REQUIRED` (ADR-005); un incidente `RESOLVED` exige `resolved_at`.

1.11 **Duplicados.** La clave de grupo la calcula el dominio; los adaptadores solo la
transportan. Formatos canónicos: `<prefijo-componente>-availability` para caídas del
mismo componente y `database-performance-investigation` para causa raíz compartida de
rendimiento/BD. Tipos: `none`, `exact_duplicate`, `recurrence`, `related_incidents`.
Ventana de fusión: 30 minutos. `merge=true` solo para el duplicado exacto posterior;
una recurrencia nunca fusiona.

1.12 **Cambio de regla.** Toda modificación de dominio actualiza en el mismo cambio la
regresión `_run_demo`, la auditoría de `data/sample_incidents.json` y los escenarios
BDD afectados.

## Artículo 2 — Arquitectura hexagonal (ADR-003)

2.1 **Dirección de dependencias.** `adapters → application → domain`. Prohibido el
import inverso. La única excepción es la raíz de composición (`src/main.py`).

2.2 **`src/domain/`** — entidades y valores, SLA, horario hábil, festivos, triaje y
correlación. Sin dependencias externas ni de otras capas.

2.3 **`src/application/`** — casos de uso compartidos (`IncidentService`). Depende solo
de `domain`; no conoce HTTP, MCP ni SQL.

2.4 **Puertos secundarios** — declarados con `typing.Protocol`, deliberadamente
mínimos: `IncidentRepositoryPort` (activos por componente/estado, guardar, localizar
equivalente abierto) y `ClockPort`. Un puerto no expone SQL ni tipos de tabla.
`Protocol` no valida en ejecución: la frontera se vigila con revisión y con prueba
automatizada de arquitectura.

2.5 **Adaptadores primarios** — `src/adapters/inbound/rest/` (canal REST),
`src/adapters/inbound/cli/` (canal CLI) y `src/adapters/inbound/mcp/` (previsto, aún no
implementado). La librería concreta de cada canal es la decisión pendiente del Art. 3.2.
Cada adaptador solo traduce entrada a llamada del caso de uso y resultado a formato de
salida. Prohibido replicar triaje, SLA o duplicados y prohibido ramificar por canal
dentro de `domain/` o `application/`. Un canal nuevo es un paquete nuevo más su registro
en la raíz de composición: el núcleo no se reabre.

2.6 **Adaptadores secundarios** — `src/adapters/outbound/`: SQLite de la librería
estándar con marcadores `?`, índice parcial de ADR-001 (con el predicado que fija
ADR-005) y streaming; un adaptador
alterno para la base dedicada de H004. DDL y mapeo fila ↔ entidad viven solo aquí.

2.7 **Paridad de canales.** REST, CLI y el futuro MCP deben producir la misma
clasificación para el mismo reporte. Se verifica con una suite de contrato compartida,
no replicando lógica.

2.8 **Raíz de composición.** Único punto que conoce implementaciones concretas y las
inyecta.

## Artículo 3 — Gobernanza técnica y calidad

3.1 **Runtime.** Python >=3.10 gestionado con `uv`; `uv sync` reproducible. En Windows
los comandos conservan `-X utf8`.

3.2 **Stack de canales y pruebas: decisión pendiente.** La elección de framework HTTP,
framework de CLI y herramienta de pruebas se registrará en un ADR propio cuando el hito
que la requiera se priorice. Hasta que ese ADR exista, rigen las restricciones de
ADR-001/002: solo librería estándar salvo `tiktoken`, `sqlite3` con marcadores `?`, sin
ORM, sin `pandas` y sin librerías de calendario. La decisión pendiente no autoriza a
adelantar dependencias.

3.3 **Independencia del núcleo.** Ningún artículo de este capítulo permite que `domain/`
o `application/` importen un framework, un ORM o un cliente de canal. Cuando se elija el
stack, quedará confinado a `src/adapters/inbound/` (canales) y a `tests/`.

3.4 **Especificación BDD.** Toda capacidad del roadmap se especifica en
`Given / When / Then`, en español, antes de implementarse: un escenario por regla
observable. El escenario es el criterio de aceptación; su automatización usará la
herramienta que defina el ADR de stack.

3.5 **Verificación.** Mientras ese ADR no exista, el oráculo son `_run_demo()` y la
auditoría sobre `data/sample_incidents.json`. Un cambio no está terminado sin esas
verificaciones en verde y sin comprobar que `domain/` y `application/` respetan la
dirección de dependencias.

3.6 **Criterio de terminado.** (a) mismo resultado por REST, CLI y MCP cuando exista;
(b) escenarios BDD verdes; (c) fronteras verificadas; (d) ninguna regla duplicada fuera
de `domain/`; (e) ADR y documentación actualizados.

3.7 **Trazabilidad documental.** Los ADR no se reescriben: se reemplazan. `AGENTS.md`
sigue siendo la guía operativa de comandos y mapa de código; esta Constitución manda en
lo normativo.

## Artículo 4 — Vigencia y enmienda

4.1 Toda enmienda requiere cambio explícito de este archivo, ADR aceptado y
actualización de `AGENTS.md` si cambian comandos o rutas.

4.2 Ninguna capa puede invocar "urgencia operativa" para saltarse un artículo sin
excepción documentada y con fecha de expiración.
