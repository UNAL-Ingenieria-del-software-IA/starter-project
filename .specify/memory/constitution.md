# Constitución — IncidentOps

## Core Principles

### I. Núcleo determinista único

**1.1 Fuente única de verdad.** Las reglas de triaje, la política SLA, el calendario,
los equipos, los estados y la clave de duplicados viven **solo** en `src/domain/`.
Los módulos canónicos son `models.py`, `triage_rules.py`, `sla_calculator.py`,
`working_time_calculator.py` y `holidays.py`. Ningún caso de uso, adaptador, DTO,
esquema, fixture o prueba DEBE reimplementar, aproximar ni sobrescribir esos valores.

**1.2 Pureza.** `src/domain/` NO DEBE importar `sqlite3`, `argparse`, `json`, `pathlib`,
`os`, HTTP, MCP, frameworks (`fastapi`, `pydantic`, `typer`, `uvicorn`), clientes de
canal ni variables de entorno. Recibe `datetime` como parámetro, no llama a
`datetime.now()`, `datetime.today()` ni `datetime.utcnow()`, no imprime y devuelve
valores inmutables.

**1.3 Determinismo.** Misma entrada + mismo `reference_time` ⇒ mismo resultado, en
cualquier canal, proceso o ejecución. El tiempo se inyecta explícitamente o vía
`ClockPort`; el núcleo nunca lee el reloj.

**1.4 Severidad por impacto, nunca por urgencia.** «urgente», «hoy» y «ASAP» se
registran como trampas léxicas y se documentan en el análisis; jamás cambian la
severidad.

**1.5 Pipeline de triaje invariante.** El orden
`extract_signals → decide_severity → route_component → correlate_batch`, sus umbrales
y la semántica de cada etapa forman parte del contrato de dominio y no pueden alterarse
sin enmienda de esta Constitución.

**1.6 Política SLA canónica.**

| Severidad | Límite (min) | Cómputo |
|---|---|---|
| P0 | 60 | Calendario 24x7 |
| P1 | 240 | Calendario 24x7 |
| P2 | 480 | Horario hábil |
| P3 | 1440 | Horario hábil |

**1.7 Horario hábil.** Lunes a viernes, 08:00–18:00, hora `America/Bogota`
(UTC-5 fijo, `COT`), excluyendo festivos nacionales colombianos calculados
dinámicamente (Ley 51/1983). Una fecha sin zona se interpreta como hora de Bogotá.

**1.8 Escalamiento e incumplimiento.** `escalation_limit = int(max * 0.75)`.
Se requiere escalamiento si el incidente no está `RESOLVED`, no está incumplido y
`elapsed >= escalation_limit`. Hay incumplimiento solo si `elapsed > max`; alcanzar el
límite exacto no incumple. Escalamiento e incumplimiento son excluyentes.
`requires_escalation` es un valor **derivado** del SLA: no se persiste ni se recalcula
en el adaptador. `ESCALATION_REQUIRED` es un estado del ciclo de vida, no un resultado
de la evaluación.

**1.9 Equipos válidos (conjunto cerrado).** `Backend-Core`, `Platform-SRE`, `Data-DBA`,
`Security-IAM`. Añadir o renombrar un equipo es cambio de dominio.

**1.10 Estados válidos.** `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`, `RESOLVED`.
Son activos todos los estados distintos de `RESOLVED`: `OPEN`, `IN_PROGRESS` y
`ESCALATION_REQUIRED` (ADR-005); un incidente `RESOLVED` exige `resolved_at`.

**1.11 Duplicados.** La clave de grupo la calcula el dominio; los adaptadores solo la
transportan. Formatos canónicos: `<prefijo-componente>-availability` para caídas del
mismo componente y `database-performance-investigation` para causa raíz compartida de
rendimiento/BD. Tipos: `none`, `exact_duplicate`, `recurrence`, `related_incidents`.
Ventana de fusión: 30 minutos. `merge=true` solo para el duplicado exacto posterior;
una recurrencia nunca fusiona.

**1.12 Cambio de regla.** Toda modificación de dominio DEBE actualizar en el mismo
cambio la regresión `_run_demo`, la auditoría de `data/sample_incidents.json` y los
escenarios BDD afectados. Cambiar `data/sample_incidents.json` cambia clasificaciones
graduadas y exige enmienda de especificación.

**Rationale:** el resultado de triaje y SLA está graduado y es comparable entre
canales; una segunda fuente de verdad o una lectura implícita del reloj rompe la
reproducibilidad que sostiene la evaluación y la paridad REST/CLI/MCP.

### II. Arquitectura hexagonal estricta

**2.1 Dirección de dependencias.** `adapters → application → domain`. Ningún módulo de
`domain/` o `application/` DEBE importar `adapters/`. La única excepción deliberada es
la raíz de composición `src/main.py`, que conoce las implementaciones concretas y las
inyecta.

**2.2 `src/domain/`.** Entidades y valores, política y evaluación SLA, horario hábil,
festivos, triaje y correlación. Sin dependencias externas ni de otras capas. Es el
núcleo puro descrito en el Principio I.

**2.3 `src/application/`.** Casos de uso compartidos. DEBE contener `ports.py` para los
puertos secundarios y `services.py` para la orquestación (`IncidentService`). Depende
solo de `domain`; no conoce HTTP, MCP, Typer ni SQL. Valida antes de invocar el motor,
completa `created_at` desde `ClockPort` y proyecta la salida contractual una sola vez
para todos los canales.

**2.4 Adaptadores primarios.** `src/adapters/inbound/api/` implementa el canal REST con
FastAPI y esquemas Pydantic v2 (`schemas.py`, `app.py`); `src/adapters/inbound/cli.py`
implementa el canal CLI con Typer. Cada adaptador solo traduce entrada a llamada del
caso de uso y resultado a formato de salida. Prohibido replicar triaje, SLA o duplicados
y prohibido ramificar por canal dentro de `domain/` o `application/`.

**2.5 Canales futuros.** MCP y cualquier otro canal futuro DEBE añadirse como paquete
nuevo en `src/adapters/inbound/` (por ejemplo `src/adapters/inbound/mcp/`) más su
registro en la raíz de composición. Un canal nuevo no reabre el núcleo ni modifica los
contratos de dominio.

**2.6 Adaptadores secundarios.** `src/adapters/outbound/` implementa los puertos
secundarios. La persistencia usa `sqlite3` de la librería estándar con marcadores `?`,
el índice parcial y el streaming de ADR-001, con el predicado que fija ADR-005. El DDL y el mapeo fila ↔ entidad viven
solo aquí. Otro motor relacional solo se admite mediante ADR aceptado que enmiende
ADR-001.

**2.7 Paridad de canales.** REST, CLI y el futuro MCP DEBEN producir la misma
clasificación para el mismo reporte. La paridad se verifica con una suite de contrato
compartida, no replicando lógica.

**Rationale:** el roadmap ya compromete al menos dos canales y dos motores sobre el
mismo núcleo graduado. Hexagonal convierte esos requisitos en fronteras de importación
verificables, en lugar de convenciones de revisión.

### III. Puertos mínimos y adaptadores intercambiables

**3.1 Declaración.** Los puertos secundarios se declaran con `typing.Protocol`
(tipado estructural), de la librería estándar. Los adaptadores no heredan de una clase
base del núcleo: solo satisfacen la forma del puerto.

**3.2 Catálogo mínimo.** `ClockPort` suministra el instante de referencia cuando el
canal no lo aporta. `IncidentRepositoryPort` localiza activos por componente y estado,
guarda un incidente y localiza un equivalente abierto para duplicados. Añadir un método
a un puerto obliga a todos los adaptadores y exige justificación en el ADR o
especificación correspondiente.

**3.3 Prohibiciones del puerto.** Un puerto NO DEBE exponer SQL, `sqlite3.Row`, nombres
de tabla, DSN ni detalles del motor. La semántica del puerto es de dominio y casos de
uso.

**3.4 Repositorio nulo.** Las operaciones sin efectos secundarios (por ejemplo, el
triaje de H001) DEBEN resolverse con un adaptador de repositorio nulo o doble en
memoria, sin condicionales de canal en el servicio.

**3.5 Selección por `DATABASE_URL`.** El adaptador de persistencia se selecciona
exclusivamente por `DATABASE_URL` en la raíz de composición. Ningún módulo de
`domain/` o `application/` lee esa variable ni conoce el motor elegido. Cambiar de
motor es un adaptador nuevo más una línea de composición.

**3.6 Verificación de intercambiabilidad.** Los casos de uso DEBEN poder ejecutarse con
dobles en memoria sin abrir una base de datos. Una prueba que requiera SQLite para
verificar una regla de negocio viola esta frontera.

**Rationale:** un puerto que filtra el motor reproduce el acoplamiento actual con otra
forma; un puerto mínimo mantiene el coste de sustitución en un solo adaptador.

### IV. Verificación estática de fronteras con Ruff

**4.1 Comando obligatorio.** `uv run ruff check src/` DEBE ejecutarse y terminar con
código 0 antes de integrar cualquier cambio. Un cambio con hallazgos de Ruff no está
terminado.

**4.2 Reglas de frontera codificadas.** La configuración de Ruff en `pyproject.toml`
DEBE expresar, como mínimo, que `src/domain/` no importa frameworks, E/S, `os` ni
`sqlite3`, y que `src/domain/` y `src/application/` no importan `src.adapters`.
La comprobación DEBE fallar de forma automática ante una importación prohibida; no
basta con una convención documentada.

**4.3 Dependencia de desarrollo.** Ruff DEBE declararse en el grupo de desarrollo y
ejecutarse con la versión fijada por `uv.lock`. No se admite una instalación global
como sustituto.

**4.4 Supresiones.** Prohibido silenciar reglas de frontera con `# noqa` genéricos o
por directorio. Una excepción puntual exige ADR aceptado con justificación y fecha de
expiración.

**4.5 Complementariedad.** La prueba AST de `tests/test_arquitectura.py` se mantiene:
Ruff aporta verificación estática y la prueba aporta verificación semántica (por
ejemplo, ausencia de lectura del reloj). Ninguna sustituye a la otra.

**4.6 Alcance.** Ruff no reemplaza `uv run pytest -v`; ambas verificaciones son
obligatorias y se ejecutan en ese orden: lint primero, pruebas después.

**Rationale:** `typing.Protocol` no valida en ejecución y el intérprete acepta una
importación prohibida hasta que se ejecuta. Ruff convierte la frontera hexagonal en un
fallo determinista y barato de detectar.

### V. Especificación BDD y verificación obligatoria

**5.1 Especificación previa.** Toda capacidad del roadmap DEBE especificarse en
`Given / When / Then`, en español, antes de implementarse: un escenario por regla
observable. El escenario es el criterio de aceptación.

**5.2 Automatización.** Cada escenario aceptado DEBE tener una prueba automatizada en
`tests/`. Una capacidad sin escenario verde no se considera entregada.

**5.3 Comando obligatorio.** `uv run pytest -v` DEBE ejecutarse y terminar con código 0.
Incluye como mínimo los escenarios BDD de la especificación vigente y las pruebas de
fronteras arquitectónicas.

**5.4 Confinamiento de frameworks de prueba.** `pytest`, `httpx` y cualquier utilidad
de prueba viven solo en `tests/` y en el grupo de desarrollo. No pueden importarse desde
`domain/` ni `application/`.

**5.5 Oráculos de regresión de dominio.** Además de pytest, todo cambio de dominio DEBE
mantener en verde:

```bash
uv run python -X utf8 -m src.sla_calculator
uv run python -X utf8 -m src.triage_rules
```

`src.sla_calculator` ejecuta 10 aserciones y sale con código 1 si falla. La auditoría de
`src.triage_rules` se ejecuta sobre `data/sample_incidents.json` y su salida no puede
cambiar sin enmienda de especificación.

**5.6 Prohibición de debilitar pruebas.** No se permite relajar una aserción, ampliar
una tolerancia o cambiar una clasificación esperada para hacer pasar una implementación.
Si el comportamiento correcto cambia, se enmienda primero la especificación y esta
Constitución.

**Rationale:** el proyecto es un repositorio docente con resultados graduados; la
verificación debe ser reproducible y no negociable en cada entrega.

## Restricciones tecnológicas

**T1 Runtime.** Python >=3.10 gestionado con `uv`; `uv sync` DEBE ser reproducible.
En Windows todos los comandos conservan `-X utf8` para evitar `UnicodeEncodeError` con
la salida acentuada. Detrás de un proxy TLS local se usa `uv sync --system-certs`.

**T2 Stack adoptado.** Las dependencias de ejecución permitidas son `fastapi`,
`uvicorn`, `pydantic` v2, `typer` y `tiktoken`. Las de desarrollo son `pytest`,
`httpx` y `ruff`. Pydantic v2 se usa solo en los esquemas de entrada/salida de
`src/adapters/inbound/api/`; los modelos de dominio son dataclasses puras.

**T3 Persistencia.** SQLite se usa exclusivamente a través de `sqlite3` de la librería
estándar, con marcadores `?` y sin concatenación de SQL. Prohibidos los ORM pesados,
`pandas` y las librerías de calendario. Un motor distinto de SQLite exige ADR aceptado
que enmiende ADR-001; hasta entonces, SQLite es el único motor admitido.

**T4 Confinamiento.** FastAPI, Pydantic, Typer, Uvicorn, httpx y pytest se confinan a
`src/adapters/inbound/` y `tests/`. Ningún artículo de esta Constitución autoriza a
`domain/` o `application/` a importarlos.

**T5 Dependencias nuevas.** Toda dependencia fuera de T2 exige ADR aceptado que
justifique la necesidad, el coste y el confinamiento. La excepción histórica que
introdujo el stack sin ADR queda cerrada con esta versión: ADR-004 DEBE registrar la
decisión y enmendar las rutas de ADR-003 §3.

**T6 Empaquetado.** `package = false` se mantiene: los módulos se ejecutan como
`-m src.<módulo>` y pytest resuelve `src` con `pythonpath = ["."]`. No se admite una
instalación del paquete como atajo.

**T7 Puentes heredados.** Los módulos planos de `src/` que aún reexportan desde
`src/domain/` solo pueden contener reexportaciones y funciones de arnés
(`_run_demo`, `load_reports`, `_run_triage_audit`). No pueden alojar reglas nuevas y
desaparecen en un hito con ADR propio.

## Flujo de desarrollo y calidad

**F1 Secuencia.** Especificación → plan → tareas → implementación. Ninguna
implementación de capacidad empieza sin especificación aceptada y escenarios BDD.

**F2 Comandos canónicos.** Desde la raíz del repositorio:

```bash
uv sync
uv run ruff check src/
uv run pytest -v
uv run python -X utf8 -m src.sla_calculator
uv run python -X utf8 -m src.triage_rules
uv run uvicorn src.main:app --host 127.0.0.1 --port 8080
```

**F3 Contrato de canales.** REST expone `POST /v1/triage` y `GET /v1/health`; el CLI
ejecuta `triage` con `--raw-text`, `--incident-id`, `--created-at`, `--now` y
`--format table|json`. Códigos de salida del CLI: `0` correcto, `2` error de uso,
`3` entrada inválida, `4` error interno. Resultados a stdout, diagnósticos a stderr.

**F4 Criterio de terminado.** Un cambio está terminado solo si: (a) `uv run ruff check
src/` pasa; (b) `uv run pytest -v` pasa; (c) los oráculos de dominio del Principio V.5
pasan; (d) no existe lógica de triaje, SLA o duplicados fuera de `domain/`; (e) REST y
CLI producen la misma clasificación; (f) ADR, especificación y documentación están
actualizados.

**F5 Trazabilidad.** `AGENTS.md` es la guía operativa de comandos y mapa de código;
esta Constitución manda en lo normativo. Los ADR no se reescriben: se reemplazan.

## Governance

**Supremacía.** Esta Constitución es la norma superior de IncidentOps y prevalece sobre
ADR, especificaciones, planes, código y documentación operativa. Toda contradicción se
resuelve a favor de este documento.

**Enmienda.** Toda modificación exige: (1) cambio explícito de
`.specify/memory/constitution.md`; (2) ADR aceptado que justifique la decisión;
(3) actualización de `AGENTS.md` si cambian comandos, rutas o stack; (4) informe de
impacto revisado y retirado antes de confirmar; (5) ejecución de
`uv run ruff check src/` y `uv run pytest -v` en verde.

**Versionado.** Se usa semver `MAJOR.MINOR.PATCH`:
`MAJOR` para eliminaciones o redefiniciones incompatibles de principios o gobernanza;
`MINOR` para principios o secciones nuevas, o guía ampliada materialmente;
`PATCH` para aclaraciones, correcciones de redacción o refinamientos no semánticos.

**Revisión de cumplimiento.** Toda revisión DEBE verificar los Principios I–V y las
restricciones T1–T7. Un cambio que los incumpla no se integra. La complejidad añadida
DEBE justificarse frente a la alternativa más simple.

**Excepciones.** Una excepción exige ADR aceptado con justificación, alcance y fecha de
expiración. Ninguna capa puede invocar «urgencia operativa» para saltarse un artículo
sin esa excepción documentada.

**Pendiente de registro.** ADR-004 DEBE registrar el stack adoptado (FastAPI,
Pydantic v2, Typer, pytest, Ruff) y enmendar las rutas de ADR-003 §3 (`rest/` y `cli/`)
a las rutas canónicas de esta Constitución (`api/` y `cli.py`). Mientras ADR-004 no
exista, rige el texto de esta Constitución.

**Version**: 2.0.0 | **Ratified**: 2026-11-23 | **Last Amended**: 2026-11-24
