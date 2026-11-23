# Roadmap — IncidentOps

Roadmap de producto y operaciones. Cada hito indica **qué capacidad gana el producto**, no cómo se implementa.
Los detalles técnicos (interfaces, contratos, esquemas, dependencias) se definen por ADR cuando el hito se prioriza.

Los hitos son incrementales: H001 → H002 → H003 → H004.

| Hito | Tema | Persistencia | Canales |
|------|------|--------------|---------|
| H001 | Triaje multi-interfaz | No | Web y terminal |
| H002 | Resumen de incidentes activos | Lectura | Web y terminal |
| H003 | Ciclo de vida, duplicados y SLA | Sí | Web y terminal |
| H004 | Persistencia dedicada y contenedores | Relacional dedicada | Servicio |

---

## H001 — Triaje multi-interfaz

**Objetivo.** Poner la clasificación y el enrutamiento determinista de reportes al alcance de quien reporta, sin guardar nada.

**Capacidades**
- Recibir un reporte y devolver de inmediato severidad y componente responsable.
- Mantener la decisión basada en impacto, no en urgencia declarada; la urgencia se expone como señal y nunca cambia la severidad.
- Resultado idéntico por web y por terminal para el mismo reporte.
- Sin efectos secundarios: el reporte no queda registrado.

**Terminado cuando**
- El mismo reporte produce la misma clasificación en ambos canales.
- El set de reportes de referencia clasifica según lo esperado, incluidos los casos de urgencia declarada.
- No se escribe ni se conserva ningún reporte.

---

## H002 — Resumen de incidentes activos

**Objetivo.** Dar visibilidad operativa inmediata del estado actual del servicio.

**Capacidades**
- Consultar los incidentes actualmente activos.
- Identificar cuáles incumplen su SLA y cuáles están en riesgo de incumplir.
- Filtrar el resumen por componente.
- Evaluar el estado a un instante de referencia dado, no solo «ahora».
- Vista consistente entre web y terminal.

**Terminado cuando**
- El resumen coincide con la fuente de verdad para cualquier instante de referencia consultado.
- El filtro por componente no altera las cifras de los componentes restantes.
- Los volúmenes de referencia se consultan sin esperas perceptibles para el operador.

---

## H003 — Ciclo de vida, duplicados y SLA

**Objetivo.** Dejar de mirar incidentes y empezar a administrarlos.

**Capacidades**
- Registrar incidentes entrantes de forma persistente.
- Alertar cuando ya existe otro incidente equivalente abierto, antes de crear el duplicado.
- Acompañar el ciclo de vida del incidente desde su apertura hasta su cierre, dejando rastro de cada cambio.
- Auditar el cumplimiento de SLA en cualquier instante de referencia, incluido el caso de un cierre posterior al plazo.

**Terminado cuando**
- Un incidente registrado sobrevive al reinicio del servicio.
- Un duplicado equivalente abierto se señala antes de generar un segundo registro.
- La situación de SLA de un incidente es reconstruible a cualquier instante de referencia.

---

## H004 — Persistencia relacional dedicada y runtime en contenedores

**Objetivo.** Operar el servicio de forma reproducible, con los datos fuera del proceso.

**Capacidades**
- Levantar el servicio en contenedores de forma reproducible, incluido un entorno nuevo desde cero.
- Separar la base de datos relacional del proceso de aplicación, con almacenamiento propio y persistente.
- Verificar conectividad operativa real contra la base, distinguiendo «no hay base» de «la aplicación falla».
- Repetir la puesta en marcha con datos de referencia en un entorno limpio.

**Terminado cuando**
- Un entorno nuevo queda operativo sin pasos manuales.
- El chequeo de conectividad falla de forma explícita cuando la base no responde.
- Los datos sobreviven al reinicio del runtime.

---

## Fuera de alcance de este documento

Rutas o contratos de interfaz, esquemas de datos, librerías y tecnologías concretas, autenticación y autorización, multi-equipo o multi-cliente, alta disponibilidad y escalado horizontal. Se definirán cuando cada hito se priorice.

## Decisiones pendientes

- Si H002 lee datos persistidos o solo el estado en memoria de la demostración.
- Qué se considera «equivalente» para efectos de duplicados.
- Si el cierre de un incidente fuera de plazo genera una alerta propia.
- Si lo desplegado en H004 reemplaza al entorno de demostración o convive con él.