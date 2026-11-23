# ADR-003: Adopción de Arquitectura Hexagonal (Puertos y Adaptadores) para IncidentOps

- **Estado**: Aceptado
- **Fecha**: 2026-11-23
- **Autor(es)**: Equipo de Ingeniería IncidentOps
- **Reemplaza a**: —

---

## 1. Contexto y Problema

IncidentOps es hoy un conjunto plano de módulos en `src/` donde el mecanismo de entrega y de almacenamiento convive con la regla de negocio en el mismo archivo: `src/triage_rules.py` define el pipeline determinista pero también resuelve rutas del proyecto (`PROJECT_ROOT`, `data/sample_incidents.json`), lee JSON (`load_reports`) e imprime la auditoría (`_run_triage_audit`); `src/incident_repository.py` abre `sqlite3`, crea esquema e índice y, en la misma clase, instancia entidades y llama a `evaluate_sla_status`, además de fungir como CLI del benchmark vía `argparse`; `src/sla_calculator.py` contiene la política de dominio y, a la vez, el único arnés de verificación (`_run_demo`, `SLATestCase`).

El roadmap fuerza a esta base a sostener simultáneamente varios canales y varios motores: H001–H003 exigen el mismo resultado por web y por terminal, H004 reemplaza la persistencia por una base relacional dedicada en contenedores y deja abierta la convivencia con el entorno de demostración, y el canal MCP es un candidato explícito. Con la estructura actual, cada canal nuevo o cada cambio de motor obliga a editar los módulos que contienen las reglas, y cada edición arriesga alterar las clasificaciones que `data/sample_incidents.json` y `CONTEXT_LOG.md` gradúan.

La decisión a registrar es **una sola**: qué topología de dependencias gobierna el código de H001 a H004. No decide framework HTTP, contratos de rutas, esquema de datos ni la estrategia de despliegue, que quedan para ADR posteriores.

Restricciones vigentes: cero dependencias externas salvo `tiktoken` (ADR-001, ADR-002); sin ORM y con parámetros enlazados `?`; cálculo de SLA determinista con zona horaria de Bogotá y festivos calculados; importaciones `from src...` con `package = false`, ejecutables solo vía `-m src.<módulo>` con `-X utf8`; ausencia de `pytest`, por lo que el oráculo de regresión es `_run_demo()` y la auditoría de triaje.

Elegir esta topología condiciona todos los hitos siguientes y revertirla obliga a reescribir importaciones y puntos de composición; por eso se documenta como ADR y no como refactor táctico. La secuencia concreta de migración pertenece al `plan.md`.

---

## 2. Opciones Consideradas

1. **Opción A — Capas tradicionales acopladas a FastAPI y SQLite**:
   - *Ventajas*: camino corto a H001/H002; FastAPI aporta validación de DTO, inyección de dependencias, OpenAPI y asincronía sin escribirlos; un único stack idiomático y familiar; menos ceremonia y menos archivos que una topología de puertos.
   - *Desventajas*: introduce FastAPI, `uvicorn` y `pydantic` con su árbol de dependencias, lo que contradice la restricción de ADR-001/002 y exigiría derogarla antes de empezar; el dominio pasaría a heredar de `BaseModel` y a recibir `Request`/`Depends`, de modo que triaje y SLA dejarían de ser evaluables sin el framework; las suposiciones de SQLite (SQL, `sqlite3.Row`) se filtrarían al servicio, encareciendo el cambio de motor de H004 y la incorporación de MCP; la paridad web/terminal se lograría duplicando caminos en lugar de compartiendo uno.
   **Resultado:** Descartada por incompatibilidad con la restricción de dependencias y por acoplar las reglas graduadas al framework.

2. **Opción B — Arquitectura Hexagonal con dominio puro, `IncidentService` y puertos `typing.Protocol`**:
   - *Ventajas*: el dominio conserva `evaluate_sla_status`, `SLA_POLICY_TABLE` y el pipeline de triaje sin cambios de firma ni de resultado, por lo que la graduación no se altera; los canales (CLI hoy, REST en H001/H002, MCP futuro) se vuelven adaptadores intercambiables de un mismo caso de uso; el motor de persistencia es un adaptador de salida sustituible en H004 sin tocar reglas; `typing.Protocol` es de la librería estándar, así que los puertos no agregan dependencias ni obligan a heredar de tipos del núcleo; H001 «sin efectos secundarios» se expresa con un adaptador de repositorio nulo, sin condicionales en el servicio; el dominio se verifica con dobles en memoria, algo imposible hoy.
   - *Desventajas*: más indirección y más paquetes para un repositorio de curso; obliga a mantener mapeos entre entidades de dominio, filas y DTO de canal; exige disciplina sostenida para que `domain`/`application` no importen `sqlite3`, `argparse` ni frameworks, y `Protocol` no lo impide en tiempo de ejecución; durante la migración conviven módulos planos y paquetes nuevos, con riesgo de dos fuentes de verdad si se copia en vez de mover.
   **Resultado:** Seleccionada por alinear la estructura con los canales y motores que el roadmap ya compromete, sin agregar dependencias y preservando el determinismo graduado.

3. **Opción C — Monolito modular por capacidad, sin puertos formales**:
   - *Ventajas*: agrupa por capacidad (`triage/`, `sla/`, `incidents/`) con importaciones unidireccionales; mínima ceremonia y migración incremental barata; no introduce conceptos nuevos para un equipo pequeño.
   - *Desventajas*: la frontera queda implícita y depende de disciplina, que es precisamente el modo de falla actual; no declara contrato para el cambio de motor de H004 ni para el canal MCP; la paridad web/terminal no queda garantizada por construcción sino por revisión; el acceso a datos sigue siendo concreto, por lo que el servicio vuelve a depender de SQLite.
   **Resultado:** Descartada por no ofrecer un punto de sustitución verificable.

---

## 3. Decisión Arquitectónica

Se adopta la **Opción B — Arquitectura Hexagonal (Puertos y Adaptadores)**.

La motivación no es estética: el roadmap ya compromete al menos dos canales y dos motores sobre el mismo núcleo determinista, la restricción de dependencias veta la vía framework-first, y el resultado del triaje y del SLA está graduado, de modo que el núcleo debe poder moverse de lugar sin cambiar de comportamiento. Hexagonal es la única de las tres opciones que convierte esos requisitos en fronteras de compilación (importaciones) en lugar de convenciones.

**Capas y responsabilidades**

- **`src/domain/` — reglas puras.** Entidades y valores (`Incident`, `SLAEvaluation`, `TriageResult`), tabla de políticas y `evaluate_sla_status`, cálculo de minutos hábiles, festivos colombianos y el pipeline `extract_signals → decide_severity → route_component → correlate_batch`. No importa `sqlite3`, `argparse`, `json`, frameworks ni rutas del proyecto; recibe `datetime` como parámetro y devuelve valores inmutables.
- **`src/application/` — casos de uso.** `IncidentService` orquesta clasificar un reporte, registrar un incidente, resumir activos y evaluar ciclo de vida. Depende solo de `domain` y declara los puertos que necesita; no conoce HTTP, MCP ni SQL.
- **`src/adapters/inbound/` — canales.** `cli/` (los actuales `-m src...`), `rest/` (H001/H002) y `mcp/` (futuro). Traducen entrada a llamada del servicio y resultado a formato de salida. La paridad web/terminal de H001 se cumple porque ambos invocan el mismo caso de uso, no porque se replique la lógica.
- **`src/adapters/outbound/` — persistencia.** Implementaciones de `IncidentRepositoryPort`: `sqlite/` con `sqlite3` de la estándar y marcadores `?`, preservando el índice parcial y el streaming de ADR-001; un adaptador alterno para la base relacional dedicada de H004. El DDL y el mapeo fila ↔ entidad viven aquí, no en el dominio.
- **Raíz de composición.** Un único punto (`src/main.py` o equivalente) conoce las implementaciones concretas y las inyecta en `IncidentService`; es la única pieza autorizada a mirar hacia afuera.

**Puertos (deliberadamente mínimos)**

- `IncidentRepositoryPort`: buscar activos por componente y estado, guardar un incidente y localizar un equivalente abierto (insumo de duplicados en H003).
- `ClockPort`: obtener el instante actual cuando el canal no lo suministra, de modo que `application` nunca llame a `datetime.now()` y el determinismo se mantenga; H002 sigue pasando `reference_time` explícito.

Ambos se declaran con `typing.Protocol` (tipado estructural): los adaptadores no heredan de una clase base del núcleo, solo satisfacen la forma, y no se agrega ninguna dependencia externa.

**Regla de dependencia.** Las dependencias apuntan siempre hacia adentro: `adapters → application → domain`. Ningún módulo de `domain/` o `application/` importa `adapters/`; la única excepción deliberada es la raíz de composición.

**Correspondencia de responsabilidades**

| Responsabilidad actual | Destino |
|---|---|
| Entidades y tipos (`src/models.py`) | `src/domain/` |
| Pipeline de triaje (`src/triage_rules.py`) | `src/domain/` |
| SLA, horario hábil y festivos (`sla_calculator.py`, `working_time_calculator.py`, `holidays.py`) | `src/domain/` |
| Orquestación hoy dispersa en `incident_repository.py` | `src/application/IncidentService` |
| `sqlite3`, DDL, índice parcial, mapeo de filas | `src/adapters/outbound/` |
| `argparse`, `_run_demo`, `_run_benchmark`, `_run_triage_audit`, carga de fixtures | `src/adapters/inbound/cli/` |

Nota de frontera: la tabla `sla_policies` deja de ser fuente de verdad. ADR-001 ya determinó que su consulta era descartada porque la política vive en `SLA_POLICY_TABLE`; en hexagonal, el dominio es dueño de la política y el adaptador solo la refleja si necesita persistirla.

**Fronteras y dirección de dependencias**

```mermaid
flowchart TB
    subgraph INBOUND["adapters/inbound — canales"]
        CLI["CLI<br/>-m src.adapters.inbound.cli"] 
        REST["REST<br/>H001 / H002"]
        MCP["MCP<br/>futuro"]
    end

    subgraph APPLICATION["application — casos de uso"]
        SVC["IncidentService"]
        PREPO(["IncidentRepositoryPort<br/>typing.Protocol"])
        PCLOCK(["ClockPort<br/>typing.Protocol"])
    end

    subgraph DOMAIN["domain — reglas puras"]
        ENT["Entidades y valores<br/>Incident · TriageResult · SLAEvaluation"]
        TRI["Triaje<br/>señales a severidad y ruta"]
        SLA["SLA · horario hábil · festivos"]
    end

    subgraph OUTBOUND["adapters/outbound — persistencia"]
        SQLITE["SQLite<br/>stdlib sqlite3 + ?"]
        RDBMS["BD relacional dedicada<br/>H004"]
    end

    CLI --> SVC
    REST --> SVC
    MCP --> SVC
    SVC --> TRI
    SVC --> SLA
    SVC --> ENT
    SVC --> PREPO
    SVC --> PCLOCK
    SQLITE -.->|"implementa"| PREPO
    RDBMS -.->|"implementa"| PREPO
Todas las flechas apuntan hacia la capa de la que se depende; domain no tiene flechas salientes.
4. Consecuencias y Trade-offs
- Positivas:
- Paridad de canales por construcción (H001–H003). Web, terminal y MCP ejecutan el mismo caso de uso; la igualdad de clasificación deja de depender de mantener dos rutas sincronizadas.
- Sustitución de motor sin tocar reglas (H004). Cambiar de SQLite a la base dedicada es un adaptador nuevo más una línea en la raíz de composición; se conserva sqlite3 con ? mientras SQLite sea el motor, cumpliendo ADR-001.
- Determinismo graduado intacto. El pipeline y evaluate_sla_status se trasladan sin cambiar firma ni semántica; el oráculo sigue siendo _run_demo() y la auditoría sobre data/sample_incidents.json, de modo que cualquier desviación es detectable con los comandos ya documentados.
- Cero dependencias nuevas. Protocol es de la librería estándar; adoptar un framework HTTP o un SDK de MCP queda como decisión posterior y confinada a adapters/inbound/.
- Puertos comprobables sin base de datos. H001 «sin efectos secundarios» se expresa con un adaptador de repositorio nulo; los casos de uso se verifican con dobles en memoria, algo que hoy no es posible sin abrir SQLite.
- MCP sin reabrir el núcleo. Un servidor MCP es un adaptador de entrada más; su contrato de herramientas es un asunto del adaptador.
- Negativas / Trade-offs:
- Indirección asumida. Un reporte atraviesa adaptador, servicio y dominio; para un repositorio de curso, son varios paquetes frente a los siete módulos planos actuales, con más navegación para leer una regla.
- Riesgo de puertos «dios». Cada método añadido a IncidentRepositoryPort obliga a todos los adaptadores; si el puerto crece sin control se reproduce el acoplamiento actual con otra forma. La mitigación es mantenerlo mínimo (hoy dos puertos) y resistir la tentación de exponer SQL.
- Mapeo que mantener. Entidades de dominio, filas y DTO de canal son tres representaciones; el mapeo es código real que puede desincronizarse.
- Migración híbrida. Mientras convivan módulos planos y paquetes nuevos habrá dos fuentes de verdad para triaje y SLA; el traslado debe ser movimiento, no copia, y la secuencia corresponde a plan.md, no a este ADR.
- Protocol no valida en ejecución. Una violación de frontera —por ejemplo, domain importando sqlite3— no falla hasta que se lee o se ejecuta el código; sin pytest, ruff ni mypy configurados, la vigilancia depende de revisión y de ejecutar los comandos con -X utf8.
- Restricción de empaquetado. Con package = false el layout debe seguir siendo ejecutable como -m src.adapters.inbound.cli; no puede apoyarse en una instalación del paquete.
- Documentación por delante del código. src/domain/, src/application/ y src/adapters/ no existen todavía: este ADR describe un destino, no el estado actual, con el mismo riesgo de deriva que ya arrastra ADR-002 al citar src/colombian_calendar.py y tests/. Mientras la migración no se complete, el mapa vigente es AGENTS.md.