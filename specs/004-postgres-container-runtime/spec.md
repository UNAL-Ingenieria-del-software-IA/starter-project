# Especificación de funcionalidad: Persistencia PostgreSQL y runtime en contenedores

**Rama de la funcionalidad**: `004-postgres-container-runtime`

**Creado**: 2026-11-24

**Estado**: Borrador, bloqueada para implementación hasta que se cumplan las dependencias de
gobernanza (D-G1 a D-G5).

**Entrada**: Descripción del usuario: "Especifica la Feature 004-postgres-container-runtime
respaldada por ADR-004 y la Constitución actualizada, incluyendo requisitos funcionales y
Requisitos No Funcionales (RNF) con al menos 4 escenarios BDD: (1) GET /health operativo y
comando CLI health con consulta real a la base; (2) GET /health ante fallo de conectividad
(503); (3) selección transparente SQLite/PostgreSQL vía DATABASE_URL; (4) orquestación
reproducible en 2 contenedores (api + db)."

**Hito**: H004 — Persistencia relacional dedicada y runtime en contenedores
(`docs/ROADMAP.MD`).

**Respaldo**: ADR-004 (persistencia dual SQLite/PostgreSQL sin ORM en runtime
multi-contenedor) y Constitución 3.1.0 (`.specify/memory/constitution.md`, Principios 2.6,
3.3, 3.5 y 3.6; restricciones T2–T4).

**Autoridad**: subordinada a la Constitución, que prevalece sobre esta especificación,
sobre los ADR y sobre el código.

---

## Resumen

IncidentOps puede guardar sus incidentes en una base de datos PostgreSQL dedicada que corre
en su propio contenedor, separada del proceso de aplicación. El servicio completo se levanta
con una sola orden: un contenedor para la aplicación y otro para la base. Un entorno nuevo
queda operativo sin pasos manuales y con los datos de referencia cargados.

El desarrollo local no cambia. Sin configurar nada, la aplicación sigue usando SQLite en
memoria con los incidentes de demostración. Las pruebas, la CLI y las auditorías siguen
corriendo sin contenedores ni red. La variable `DATABASE_URL` es lo único que decide qué
motor se usa, y el resto del sistema no lo sabe.

Una sonda nueva de disponibilidad, `GET /health` y el subcomando CLI `health`, consulta de
verdad la base configurada. Así distingue «la base no responde» de «la aplicación falla». La
orquestación de contenedores la usa para arrancar la aplicación solo cuando la base está
lista y para saber si el servicio está sano.

## Clarifications

### Session 2026-11-24

- Q: ¿Qué número lleva el ADR que respalda esta feature? → A: ADR-004, por decisión del
  usuario. El ADR de stack (FastAPI/Typer/pytest), antes reservado como ADR-004, queda con
  número pendiente (Constitución 3.1.0, Governance).
- Q: Ya existe `GET /v1/health`, que no consulta la base. ¿Qué pasa con él? → A: se
  conserva sin cambios como sonda de *liveness* («el proceso vive»). `GET /health` es la
  sonda nueva de disponibilidad («la base responde»).
- Q: ¿Se siembra una base PostgreSQL vacía con datos de referencia? → A: sí, solo si no
  contiene ningún incidente al arrancar. Se cargan los incidentes de demostración
  `INC-2001`…`INC-2008` una sola vez. Un reinicio no duplica ni pisa datos.
- Q: ¿Con qué código sale `health` en la CLI cuando la base no responde? → A: con `4` (error
  interno, código vigente), imprimiendo en stdout el cuerpo `unavailable`. «No hay base» se
  distingue de «la aplicación falla» por el cuerpo, no por el código. No se enmiendan los
  códigos de salida.
- Q: Si la base no responde cuando arranca la API, ¿la API se niega a arrancar o arranca
  degradada? → A: arranca degradada. Con una configuración válida la API arranca siempre,
  `GET /health` responde `503` hasta que la base conteste, y el esquema y la siembra se
  aplican en la primera conexión correcta. Un esquema de URL no soportado sigue impidiendo el
  arranque. La CLI mantiene el fallo temprano salvo en `health`. Reemplaza el fallo temprano
  del servicio HTTP (antes D6).
- Q: ¿Cómo llega la suite de pruebas a una base PostgreSQL si la base del runtime no se
  publica? → A: con una base de pruebas aparte. Es un servicio PostgreSQL opcional, que no
  arranca por defecto, publicado solo en loopback y con almacenamiento desechable. Las
  pruebas lo usan solo si una variable de entorno de pruebas apunta a él. La base del
  runtime sigue sin publicarse y las pruebas nunca la tocan.
- Q: ¿Cómo se verifican los escenarios de contenedores E12–E17? → A: con pruebas pytest en
  `tests/` bajo un marcador propio. Manejan la composición con un nombre de proyecto aislado
  y se omiten de forma visible si Docker no está disponible (Constitución 5.2).
- Q: ¿Cuánto puede tardar como máximo `api` en pasar a «no sano» tras caer la base, y a
  «sano» tras volver? → A: 60 segundos en cada sentido. Se privilegia tolerar pausas breves
  de la base sobre detectar más rápido.
- Q: ¿Qué consultas a la sonda quedan en el registro? → A: los cambios de estado
  (`connected` ↔ `unavailable`) y cada consulta fallida. Las consultas correctas repetidas no
  se registran.

---

## Escenarios de usuario y pruebas

### Historia 1 — Saber si el servicio puede atender (Prioridad: P1)

Un operador o el orquestador de contenedores necesita saber, en cualquier momento, si el
servicio puede atender: si el proceso vive **y** la base de datos configurada responde. La
respuesta debe distinguir una base caída de una aplicación rota, y debe ser la misma por
HTTP y por CLI.

**Por qué esta prioridad**: es la condición de terminado de H004 («el chequeo de
conectividad falla de forma explícita cuando la base no responde»). La orquestación de la
Historia 3 depende de ella: sin sonda no hay arranque ordenado ni estado de salud.

**Prueba independiente**: con el almacén por defecto (SQLite en memoria) se consulta
`GET /health` y `health` por CLI. Después se sustituye el repositorio por un doble cuyo
`check_health()` devuelve `False` y se repiten las consultas. No hacen falta contenedores.

**Escenarios de aceptación**:

- **E1 — Sonda HTTP con la base disponible**
  - **Given** el servicio arrancado con un almacén configurado que responde a una consulta
    real,
  - **When** se consulta `GET /health`,
  - **Then** responde `200` con el cuerpo exacto `{"status": "ok", "database": "connected"}`,
  - **And** la consulta llegó de verdad a la base en esa misma petición, sin reutilizar un
    resultado anterior.

- **E2 — Sonda CLI con la base disponible**
  - **Given** un almacén configurado que responde,
  - **When** se ejecuta `health --format json`,
  - **Then** el proceso sale con código `0`,
  - **And** stdout contiene exactamente el mismo cuerpo JSON que E1,
  - **And** stderr queda vacío.

- **E3 — Sonda HTTP con la base caída**
  - **Given** el servicio arrancado y un almacén que deja de responder (`check_health()`
    devuelve `False`),
  - **When** se consulta `GET /health`,
  - **Then** responde `503` con el cuerpo exacto `{"status": "error", "database":
    "unavailable"}`,
  - **And** ni el cuerpo ni los registros del servicio contienen `DATABASE_URL` ni ninguna de
    sus partes (usuario, contraseña, host, puerto, nombre de la base).

- **E4 — Sonda CLI con la base caída**
  - **Given** un almacén configurado que no responde, tanto si deja de responder durante la
    ejecución como si ya no responde al arrancar el proceso,
  - **When** se ejecuta `health --format json`,
  - **Then** el proceso sale con código `4`,
  - **And** stdout contiene exactamente el cuerpo de E3,
  - **And** stderr contiene un diagnóstico de una línea sin la URL ni ninguna de sus partes.

- **E5 — Recuperación sin reinicio**
  - **Given** el servicio arrancado, cuya sonda respondió `503` porque la base no respondía,
  - **When** la base vuelve a responder y se consulta de nuevo `GET /health`,
  - **Then** responde `200` con el cuerpo de E1, sin reiniciar el proceso de aplicación.

- **E6 — La sonda de *liveness* no cambia**
  - **Given** el servicio arrancado y un almacén que no responde,
  - **When** se consulta `GET /v1/health`,
  - **Then** responde `200` con el cuerpo exacto `{"status": "ok"}`, igual que antes de esta
    feature.

---

### Historia 2 — Elegir el motor sin tocar el código (Prioridad: P2)

Un desarrollador trabaja en local sin contenedores y quiere pruebas rápidas sobre SQLite.
El runtime en contenedores debe usar PostgreSQL. Ambos ejecutan el mismo código y dan los
mismos resultados: solo cambia `DATABASE_URL`.

**Por qué esta prioridad**: es el núcleo de ADR-004 (persistencia dual) y la base de la
Historia 3. Sin ella no hay adaptador PostgreSQL que orquestar. Va después de la sonda
porque la sonda ya da valor sobre SQLite.

**Prueba independiente**: los escenarios E7, E8 y E10 corren sin PostgreSQL. E9 y E11
necesitan una base PostgreSQL para pruebas y, sin ella, se omiten de forma visible
(Constitución 3.6).

**Escenarios de aceptación**:

- **E7 — Sin `DATABASE_URL` se usa SQLite en memoria**
  - **Given** un entorno en el que `DATABASE_URL` no está definida o está vacía, y ningún
    contenedor en marcha,
  - **When** se ejecuta `summary --format json` con `--reference-time
    2026-11-24T09:00:00`,
  - **Then** el proceso sale con código `0`,
  - **And** el resumen contiene los incidentes de demostración `INC-2001`…`INC-2008`, igual
    que antes de esta feature,
  - **And** `health --format json` informa `connected`.

- **E8 — `sqlite:///<ruta>` usa un archivo SQLite**
  - **Given** `DATABASE_URL=sqlite:///<ruta>` sobre un archivo inexistente,
  - **When** se crea un incidente con `create` y después, en otro proceso, se consulta con
    `sla`,
  - **Then** el incidente existe en el segundo proceso,
  - **And** el archivo no contiene incidentes de demostración.

- **E9 — `postgresql://…` usa PostgreSQL**
  - **Given** `DATABASE_URL=postgresql://…` apuntando a una base PostgreSQL de pruebas que
    responde y está vacía,
  - **When** la aplicación arranca, se crea un incidente con `POST /api/v1/incidents` y
    después, desde otro proceso con la misma URL, se consulta su SLA,
  - **Then** el incidente existe en el segundo proceso,
  - **And** la base contiene, además, los ocho incidentes de demostración, cargados una
    sola vez.

- **E10 — Esquema no soportado**
  - **Given** `DATABASE_URL` con un esquema no soportado (`mysql://…`, `postgres://…`, o un
    texto sin `://`),
  - **When** se ejecuta cualquier subcomando de la CLI distinto de `health`, o se arranca el
    servicio HTTP,
  - **Then** la CLI sale con código `4` y el servicio HTTP no llega a arrancar,
  - **And** el mensaje nombra solo el esquema recibido y los esquemas admitidos, nunca la
    URL ni sus credenciales.

- **E11 — Paridad entre motores**
  - **Given** el mismo conjunto de incidentes cargado en SQLite y en PostgreSQL, incluidos
    identificadores que solo se diferencian por mayúsculas y minúsculas
    (`INC-abc1`, `INC-ABC1`) e instantes con microsegundos,
  - **When** se piden el resumen, la auditoría de SLA y la creación con aviso de duplicado
    con la misma entrada y el mismo instante de referencia,
  - **Then** los cuerpos JSON son idénticos byte a byte en ambos motores, incluidos el orden
    de las listas y la representación de los instantes.

---

### Historia 3 — Levantar el servicio completo desde cero (Prioridad: P3)

Quien recibe el repositorio, con Docker y nada más, levanta el servicio completo con una
sola orden. La base vive en su propio contenedor con almacenamiento persistente, y la
aplicación arranca solo cuando la base está lista. Los datos sobreviven a los reinicios.

**Por qué esta prioridad**: cierra H004 («un entorno nuevo queda operativo sin pasos
manuales», «los datos sobreviven al reinicio del runtime»). Depende de las Historias 1 y 2.

**Prueba independiente**: pruebas automatizadas bajo un marcador propio (RNF-011). Levantan
la composición con un nombre de proyecto aislado y sin volúmenes previos, y la desmontan al
terminar. Sin Docker se omiten de forma visible.

**Escenarios de aceptación**:

- **E12 — Entorno nuevo operativo sin pasos manuales**
  - **Given** un clon limpio del repositorio, Docker con Compose y ningún volumen previo del
    proyecto,
  - **When** se levanta la composición con una sola orden, sin crear ni editar archivos,
  - **Then** el servicio `db` pasa a sano antes de que arranque el servicio `api`,
  - **And** el servicio `api` pasa a sano,
  - **And** `GET http://127.0.0.1:8080/health` desde el host responde `200` con el cuerpo
    de E1,
  - **And** `GET /api/v1/incidents/summary?reference_time=2026-11-24T09:00:00` devuelve los
    incidentes de demostración.

- **E13 — Los datos sobreviven al reinicio**
  - **Given** la composición en marcha y un incidente creado por `POST /api/v1/incidents`,
  - **When** se detienen y se vuelven a levantar ambos servicios sin borrar el volumen,
  - **Then** el incidente creado sigue existiendo con los mismos valores,
  - **And** los incidentes de demostración no se duplican ni se sobrescriben.

- **E14 — La aplicación detecta la caída de la base**
  - **Given** la composición en marcha y sana,
  - **When** se detiene solo el servicio `db`,
  - **Then** `GET /health` responde `503` con el cuerpo de E3,
  - **And** el servicio `api` pasa a no sano en 60 segundos o menos,
  - **And** al volver a levantar `db`, `api` vuelve a sano sin reiniciarse, en 60 segundos o
    menos (E5).

- **E17 — La API arranca degradada sin base**
  - **Given** una `DATABASE_URL` válida de PostgreSQL y una base vacía que todavía no
    responde,
  - **When** se arranca el servicio HTTP,
  - **Then** el proceso arranca y `GET /health` responde `503` con el cuerpo de E3,
  - **And** las operaciones de negocio responden `500 internal_error` con el sobre común,
  - **And** cuando la base empieza a responder, sin reiniciar la API, `GET /health` responde
    `200` y el resumen muestra los incidentes de demostración, sembrados una sola vez.

- **E15 — Exposición mínima**
  - **Given** la composición en marcha,
  - **When** se intenta conectar desde el host,
  - **Then** la API responde solo en la interfaz de loopback del host (`127.0.0.1:8080`),
  - **And** el puerto de la base no está publicado en el host.

- **E16 — Imagen limpia**
  - **Given** la imagen de la aplicación construida desde el repositorio,
  - **When** se inspecciona su sistema de archivos y el usuario con el que corre el proceso,
  - **Then** no contiene metadatos de control de versiones, entornos virtuales locales,
    cachés, archivos `.env`, pruebas ni directorios de herramientas o agentes,
  - **And** no contiene dependencias de desarrollo,
  - **And** el proceso no corre como `root`.

---

### Trazabilidad de escenarios

| Escenario | Requisitos |
|---|---|
| E1, E2 | FR-001, FR-002, FR-006, RNF-002 |
| E3, E4 | FR-003, FR-004, FR-006, FR-007, RNF-003, RNF-006 |
| E5, E14 | FR-014, RNF-008 |
| E17 | FR-010, FR-011, FR-019, RNF-008 |
| E6 | FR-005 |
| E7, E8 | FR-008, RNF-005 |
| E9 | FR-008, FR-009, FR-010, FR-011, FR-020 |
| E10 | FR-008, FR-013, RNF-003 |
| E11 | FR-009, FR-012, FR-020, RNF-001 |
| E12 | FR-011, FR-015, FR-017, FR-018, RNF-004, RNF-011 |
| E13 | FR-010, FR-011, RNF-010 |
| E15 | FR-017, RNF-003 |
| E16 | FR-015, FR-016, RNF-003 |

### Casos borde

- **`DATABASE_URL` definida pero vacía**: se trata como ausente; se usa el almacén en
  memoria (comportamiento vigente).
- **`postgres://` en lugar de `postgresql://`**: se rechaza como esquema no soportado
  (E10). La Constitución 3.5 enumera solo `postgresql://`.
- **La base no responde al arrancar el servicio HTTP**: el servicio arranca degradado
  (FR-019, E17). Queda «no sano» hasta que la base conteste; nunca responde con datos
  vacíos como si fueran reales. Reiniciar solo `api` con `db` detenida no provoca un bucle de
  caídas.
- **La base deja de responder a mitad de una petición de negocio**: esa petición responde
  `500 internal_error` con el sobre común (CLI: código `4`). No se pierden ni se corrompen
  datos ya confirmados.
- **La base tarda en responder sin rechazar la conexión** (red colgada): la sonda responde
  `503` dentro del límite de RNF-002, sin quedarse esperando indefinidamente.
- **Error de autenticación contra PostgreSQL**: es «base no disponible» (`503`, `unavailable`).
  El diagnóstico no incluye usuario, host ni contraseña, aunque el driver los incluya en su
  mensaje.
- **Base PostgreSQL con incidentes creados antes de la primera siembra**: no se siembra; la
  siembra ocurre solo si no hay ningún incidente.
- **Todos los incidentes borrados a mano entre reinicios**: el siguiente arranque vuelve a
  sembrar los datos de demostración. Es consecuencia aceptada de la regla «sembrar si está
  vacía».
- **Dos arranques simultáneos de la aplicación contra la misma base vacía**: la siembra no
  produce duplicados ni hace fallar el arranque. Un conflicto de identificador en la
  siembra no es un error.
- **`GET /health` con otro método (`POST`, `DELETE`)**: `405 method_not_allowed` con el sobre
  común (comportamiento vigente para cualquier ruta).
- **Volumen eliminado**: la siguiente puesta en marcha equivale a un entorno nuevo (E12). Es
  la única operación que borra los datos.

---

## Requisitos

### Requisitos funcionales

**Sonda de disponibilidad**

- **FR-001**: El sistema DEBE exponer `GET /health`. En cada petición ejecuta una consulta
  trivial real, de ida y vuelta, contra el almacén configurado mediante `check_health()`
  del puerto. El resultado no se cachea entre peticiones.
- **FR-002**: Si el almacén responde, `GET /health` DEBE devolver `200` con el cuerpo exacto
  `{"status": "ok", "database": "connected"}`.
- **FR-003**: Si `check_health()` devuelve `False`, `GET /health` DEBE devolver `503` con el
  cuerpo exacto `{"status": "error", "database": "unavailable"}`. Este cuerpo es el estado
  de la sonda, no un error de la petición. Por eso, como excepción documentada, no usa el
  sobre común de errores.
- **FR-004**: La sonda NO DEBE responder `500` por un fallo de la base. Cualquier fallo al
  comprobar el almacén (rechazo, autenticación, tiempo agotado) se informa como
  `unavailable`.
- **FR-005**: `GET /v1/health` DEBE conservar su contrato: `200 {"status": "ok"}`, sin
  consultar el almacén.
- **FR-006**: La CLI DEBE ofrecer el subcomando `health` con `--format table|json`
  (`table` por defecto, como los demás subcomandos). Con `json`, stdout contiene
  exactamente el mismo cuerpo que `GET /health`. Sale con `0` si el almacén responde y con
  `4` si no.
- **FR-007**: El subcomando `health` DEBE informar `unavailable` (stdout, código `4`)
  también cuando el almacén ya no responde al construir el servicio. En ese caso no aparece
  el error genérico de arranque. El diagnóstico va a stderr, en una línea, sin la URL.

**Selección de motor**

- **FR-008**: La raíz de composición DEBE elegir el adaptador solo por `DATABASE_URL`:

  | Valor | Adaptador | Siembra de demostración |
  |---|---|---|
  | ausente o vacía | SQLite en memoria | sí, siempre |
  | `sqlite:///:memory:` | SQLite en memoria | sí, siempre |
  | `sqlite:///<ruta>` | SQLite en archivo | no |
  | `postgresql://…` | PostgreSQL | sí, solo si no hay incidentes (FR-011) |
  | cualquier otro | — | falla al arrancar (FR-013) |

- **FR-009**: El adaptador PostgreSQL DEBE implementar `IncidentRepositoryPort` sin añadir ni
  cambiar métodos, con la misma semántica observable que el adaptador SQLite en cada
  operación:
  - guardar con reemplazo;
  - insertar sin reemplazo, con conflicto de identificador → `409 incident_id_conflict` /
    código `1`;
  - obtener por identificador;
  - listar activos con y sin filtro de componente;
  - localizar abiertos por clave de grupo;
  - comprobar salud.
- **FR-010**: En la primera conexión correcta a PostgreSQL de cada proceso, el sistema DEBE
  crear de forma idempotente el esquema que necesita. Si el esquema ya existe, no se pierden
  ni se alteran datos.
- **FR-011**: En esa misma primera conexión correcta, si el almacén no contiene ningún
  incidente, el sistema DEBE cargar una vez los incidentes de demostración
  `INC-2001`…`INC-2008`, los mismos que el almacén en memoria. Si contiene al menos uno, no
  carga nada.
- **FR-012**: Los instantes guardados DEBEN devolverse en ambos motores con exactamente el
  mismo valor con el que se guardaron (hora de Bogotá, desfase explícito, misma precisión).
- **FR-013**: Un esquema de `DATABASE_URL` no soportado DEBE impedir el arranque: la CLI sale
  con `4` y el servicio HTTP no arranca. El mensaje nombra el esquema recibido y los
  admitidos, nunca la URL.
- **FR-014**: Si el almacén deja de responder con el servicio en marcha, las operaciones de
  negocio DEBEN fallar con el error interno vigente (`500 internal_error` / código `4`). Al
  volver la base, el servicio DEBE recuperarse sin reiniciar el proceso.
- **FR-019**: Con una `DATABASE_URL` de esquema admitido, el servicio HTTP DEBE arrancar
  aunque la base no responda. Mientras no responda se comporta como en FR-003 y FR-014, y al
  primer contacto correcto aplica FR-010 y FR-011. La CLI conserva el fallo temprano (código
  `4`) en todos los subcomandos salvo `health` (FR-007).
- **FR-020**: La composición DEBE ofrecer un servicio PostgreSQL de pruebas, opcional y que
  no arranca por defecto. Debe cumplir:
  - misma imagen e intercalación `C` que `db`;
  - almacenamiento desechable, sin volumen nombrado;
  - publicado solo en `127.0.0.1` del host, en un puerto distinto del de la API.

  Las pruebas que necesitan PostgreSQL lo usan solo cuando una variable de entorno de
  pruebas, distinta de `DATABASE_URL`, apunta a él; sin ella se omiten de forma visible
  (RNF-005). Las pruebas NO DEBEN conectarse nunca a la base del runtime.

**Runtime en contenedores**

- **FR-015**: El repositorio DEBE incluir una definición de imagen de la aplicación con estas
  características:
  - parte de `python:3.12-slim`;
  - instala las dependencias de ejecución con `uv` desde el archivo de bloqueo, sin
    resolver versiones nuevas y sin dependencias de desarrollo;
  - corre como usuario no privilegiado;
  - dentro del contenedor, sirve la API en todas las interfaces, puerto `8080`.
- **FR-016**: El repositorio DEBE incluir un archivo de exclusiones de contexto de
  construcción que deje fuera de la imagen:
  - metadatos de control de versiones;
  - entornos virtuales;
  - cachés de Python y de herramientas;
  - archivos `.env*`;
  - pruebas;
  - especificaciones y documentación;
  - directorios de herramientas y agentes.
- **FR-017**: El repositorio DEBE incluir una definición de composición cuyo arranque por
  defecto levante exactamente dos servicios (el servicio de pruebas de FR-020 queda fuera):
  - **`db`**:
    - imagen `postgres:16-alpine`;
    - volumen nombrado persistente para los datos;
    - base inicializada con intercalación `C` (Constitución 2.6);
    - chequeo de salud con `pg_isready`;
    - puerto no publicado en el host.
  - **`api`**:
    - imagen construida con FR-015;
    - `DATABASE_URL` apuntando al servicio `db` por la red interna;
    - arranque condicionado a que `db` esté sano;
    - chequeo de salud contra `GET /health`;
    - puerto `8080` publicado solo en `127.0.0.1` del host.
- **FR-018**: La composición DEBE levantarse sin crear ni editar archivos. Las credenciales de
  la base tienen valores de desarrollo por defecto, que se pueden cambiar por variables de
  entorno sin tocar archivos versionados. Ningún secreto real se versiona.

### Requisitos no funcionales

- **RNF-001 — Paridad entre motores**:
  - Para el mismo conjunto de datos, la misma entrada y el mismo instante de referencia,
    todo cuerpo JSON de la API y de la CLI DEBE ser idéntico con SQLite y con PostgreSQL.
  - Esto incluye el orden de las listas y el orden de texto por bytes, sin distinguir
    idioma (Constitución 1.3 y 2.6).
- **RNF-002 — Sonda acotada en el tiempo**:
  - `GET /health` y `health` DEBEN responder en 3 segundos o menos, aunque la base no
    responda o la red esté colgada.
  - Con la base disponible, la sonda responde en menos de 500 ms en el 95 % de las
    consultas.
- **RNF-003 — Confidencialidad de la configuración y exposición mínima**:
  - Ninguna respuesta, salida de la CLI, registro ni mensaje de error DEBE incluir
    `DATABASE_URL` ni sus partes (usuario, contraseña, host, puerto, nombre de la base).
    Solo puede aparecer el esquema.
  - La API se publica solo en loopback del host y la base no se publica.
  - La imagen no contiene secretos y el proceso no corre como `root`.
  - La autenticación sigue fuera de alcance; esta exposición mínima es su mitigación.
- **RNF-004 — Reproducibilidad**:
  - Las versiones de las imágenes base DEBEN estar fijadas: `python:3.12-slim` y
    `postgres:16-alpine`.
  - Las dependencias de Python se instalan exclusivamente desde el archivo de bloqueo.
  - Dos construcciones desde el mismo commit producen el mismo conjunto de paquetes
    instalados.
- **RNF-005 — Desarrollo sin contenedores**:
  - La suite de pruebas, los oráculos de dominio y la CLI DEBEN ejecutarse sin Docker, sin
    PostgreSQL y sin red, con el almacén por defecto.
  - Los casos que necesitan PostgreSQL o Docker aparecen como omitidos en el informe, nunca
    como superados (Constitución 3.6).
- **RNF-006 — Observabilidad sin fugas**:
  - La sonda DEBE registrar cada cambio de estado (`connected` → `unavailable` y al revés)
    y cada consulta con resultado `unavailable`. Una consulta `connected` que no cambia el
    estado no se registra.
  - Cada línea registrada contiene solo el resultado, la duración y el código de estado.
  - El estado de partida de cada proceso es «desconocido», así que la primera consulta
    siempre se registra.
  - Los fallos de las operaciones de negocio se registran con la clase del error, nunca con
    su mensaje (comportamiento vigente del manejador genérico), porque el driver puede
    incluir credenciales o el host en él. La sonda no registra la causa: solo el resultado.
- **RNF-007 — Confinamiento hexagonal**:
  - El driver de PostgreSQL DEBE quedar confinado a los adaptadores de salida y a las
    pruebas, y la verificación estática de fronteras lo prohíbe en dominio, aplicación y
    canales (Constitución 4.2 y T4).
  - El puerto no cambia.
  - El dominio, los casos de uso y los canales existentes no se modifican para soportar el
    segundo motor. Las únicas excepciones son la sonda nueva y la raíz de composición.
- **RNF-008 — Recuperación**:
  - Tras volver la base, la siguiente consulta a la sonda DEBE informar `connected`, y las
    operaciones de negocio vuelven a funcionar sin reiniciar la aplicación.
  - En la composición, `api` DEBE pasar a «no sano» en 60 segundos o menos después de que
    la base deje de responder, y volver a «sano» en 60 segundos o menos después de que
    vuelva.
  - Una pausa de la base más corta que el intervalo de chequeo no tiene por qué cambiar el
    estado de `api`.
- **RNF-009 — Rendimiento**:
  - El resumen de incidentes activos DEBE cumplir sobre PostgreSQL el mismo objetivo que la
    spec 002 (SC-001) fija sobre SQLite para el volumen de referencia.
  - La medición se repite sobre el nuevo motor; no se infiere de la de SQLite (ADR-004).
- **RNF-010 — Durabilidad**:
  - Los datos confirmados DEBEN sobrevivir a la detención, el reinicio o la recreación de
    los contenedores mientras el volumen exista.
  - Solo eliminar el volumen borra los datos.
- **RNF-011 — Verificación automatizada de contenedores**:
  - Cada escenario E12–E17 DEBE tener una prueba automatizada en `tests/`, agrupada bajo un
    marcador propio que permita ejecutarla o excluirla por separado.
  - Estas pruebas usan un nombre de proyecto de composición aislado, nunca tocan el volumen
    del runtime y eliminan al terminar sus contenedores y volúmenes, aunque fallen.
  - Sin Docker disponible se omiten de forma visible, nunca se dan por superadas.

### Decisiones de alcance

| # | Decisión | Fuente |
|---|---|---|
| D1 | `/v1/health` se conserva como *liveness*; `/health` es la sonda de disponibilidad. | Clarificación 2026-11-24 |
| D2 | PostgreSQL vacío se siembra una vez con los datos de demostración; un archivo SQLite no. | Clarificación 2026-11-24; roadmap H004 |
| D3 | `health` sale con `4` cuando la base no responde; el cuerpo distingue la causa. | Clarificación 2026-11-24 |
| D4 | Solo `postgresql://`; `postgres://` se rechaza. | Constitución 3.5 |
| D5 | El cuerpo de `/health` no usa el sobre común de errores. | Pedido explícito del usuario; FR-003 |
| D6 | El servicio HTTP arranca degradado si la base no responde; la CLI mantiene el fallo temprano salvo en `health`. | Clarificación 2026-11-24 (reemplaza el fallo temprano de ADR-006 solo para HTTP) |

### Contrato observable

| Canal | Operación | Éxito | Base no disponible |
|---|---|---|---|
| HTTP | `GET /health` | `200 {"status": "ok", "database": "connected"}` | `503 {"status": "error", "database": "unavailable"}` |
| HTTP | `GET /v1/health` | `200 {"status": "ok"}` | `200 {"status": "ok"}` (no consulta la base) |
| CLI | `health [--format table\|json]` | código `0`; JSON = cuerpo `200` | código `4`; JSON = cuerpo `503`; diagnóstico en stderr |

Las demás rutas, subcomandos, cuerpos y códigos de las specs 001–003 no cambian.

### Fuera de alcance

- Autenticación, autorización y TLS.
- Alta disponibilidad, réplicas, escalado horizontal y pool de conexiones externo (un pool
  que traiga una dependencia exige su propio ADR, Constitución T3/T5).
- Herramienta de migraciones versionadas. El esquema se crea de forma idempotente y
  aditiva, como en SQLite.
- Copias de seguridad y restauración del volumen.
- Despliegue en producción, registros de imágenes y pipelines de integración continua.
- Migrar datos existentes de SQLite a PostgreSQL.
- Canal MCP.

### Entidades clave

- **Estado de la sonda**: resultado de comprobar si el almacén responde. Tiene dos valores
  observables, `connected` y `unavailable`. No se persiste.
- **Configuración de almacén**: el valor de `DATABASE_URL`. Determina el motor, la ubicación
  y, en PostgreSQL, las credenciales. Es confidencial salvo su esquema.
- **Conjunto de datos de referencia**: los ocho incidentes de demostración `INC-2001`…
  `INC-2008`, ya definidos por la spec 002. Se reutilizan como siembra de PostgreSQL.
- **Volumen de datos**: el almacenamiento persistente de la base dedicada. Su ciclo de vida
  es independiente de los contenedores.

---

## Criterios de éxito

### Resultados medibles

- **SC-001**: En una máquina que solo tiene el motor de contenedores, con las imágenes base ya
  descargadas, un clon limpio pasa de la orden de arranque a «servicio disponible» en menos
  de 3 minutos, sin pasos manuales.
- **SC-002**: Tras 3 ciclos consecutivos de detener y volver a levantar el servicio
  completo, el 100 % de los incidentes creados sigue disponible con los mismos valores, y
  los datos de referencia aparecen exactamente una vez.
- **SC-003**: Con la base detenida, el 100 % de las consultas a la sonda informa «no
  disponible» en 3 segundos o menos. Con la base de vuelta, la primera consulta informa
  «disponible». El estado del servicio en la composición refleja cada cambio en 60 segundos
  o menos.
- **SC-004**: El 100 % de los escenarios de paridad (E11) produce resultados idénticos con
  ambos motores.
- **SC-005**: Con el volumen de referencia, el resumen de incidentes activos responde en
  menos de 1 segundo con ambos motores.
- **SC-006**: La suite completa de desarrollo termina con 0 fallos en una máquina sin motor
  de contenedores ni base dedicada. Las comprobaciones que los necesitan aparecen como
  omitidas.
- **SC-007**: En los cuerpos, salidas y registros de todos los escenarios, la configuración
  de conexión completa aparece 0 veces.

---

## Supuestos

- El operador del runtime tiene Docker con el plugin Compose v2, que admite la condición
  «servicio sano» en las dependencias de arranque.
- `python:3.12-slim` en la imagen y CPython 3.10 en el entorno local de desarrollo comparten
  el mismo archivo de bloqueo (`requires-python >= 3.10`). El tope `pytest<9.2` solo afecta
  a las dependencias de desarrollo, que no entran en la imagen.
- `psycopg[binary]` publica ruedas precompiladas para la plataforma de la imagen, así que la
  construcción no necesita compilador ni `libpq` del sistema.
- Las credenciales por defecto de la composición son solo de desarrollo local. Su riesgo se
  acota porque la base no se publica en el host y la API solo escucha en loopback.
- El intervalo y los reintentos del chequeo de salud los fija el plan, siempre dentro del
  límite de 60 segundos de RNF-008.
- Detrás del proxy TLS local, la construcción de la imagen puede necesitar los certificados
  del sistema, igual que `uv sync --system-certs`. Es un asunto del entorno, no de la feature.
- La verificación de E9 y E11 necesita la base de pruebas de FR-020, y la de E12–E17
  necesita Docker. En la suite rápida se omiten de forma visible.

## Dependencias

### De gobernanza (bloquean la implementación)

- **D-G1 — ADR-004 aceptado.** Hoy figura como «Propuesto». La Constitución (Governance,
  punto 2) exige un ADR aceptado para la enmienda 3.1.0 que esta feature aplica.
- **D-G2 — Enmienda de la Constitución para el contrato de canales.** F3 enumera las rutas y
  los subcomandos vigentes. `GET /health` y el subcomando `health` lo amplían. F2 no
  enumera la orden de la composición. Ambos cambios requieren una enmienda (MINOR).
- **D-G3 — Alineación de `docs/constitution.md` y `AGENTS.md`.** `docs/constitution.md`
  (Art. 2.6 y 3.2) aún admite solo `sqlite3` y llama ADR-004 al ADR de stack. `AGENTS.md`
  no documenta `postgresql://`, la sonda ni la composición.
- **D-G4 — Fronteras estáticas.** Las reglas de frontera de Ruff y la prueba de arquitectura
  aún no prohíben el driver de PostgreSQL fuera de los adaptadores de salida (Constitución
  4.2).
- **D-G5 — Arranque degradado frente a ADR-006.** ADR-006 decidió que la raíz de composición
  exija `check_health()` al arrancar, y FR-019 lo invierte para el servicio HTTP. Hace falta
  registrarlo en un ADR: en ADR-004, mientras siga «Propuesto», o en un ADR nuevo que
  reemplace parcialmente a ADR-006.

### Técnicas

- `IncidentRepositoryPort.check_health()` (ADR-006), que ya existe y se reutiliza sin
  cambios.
- Los incidentes de demostración de la spec 002, que se reutilizan como siembra.
- Las specs 001–003, cuyos contratos no cambian salvo la adición de FR-001 a FR-007.

## Preguntas abiertas

- Número del ADR de stack (FastAPI/Typer/pytest), antes reservado como ADR-004. No bloquea
  esta feature, pero lo citan specs y documentos anteriores.
