# Bitácora de Desarrollo Guiado por Especificaciones — Semana 2 (`SDD_LOG.md`)
**Estudiante(s)**: `Edgar Fernando Vega Morales`

**Fecha**: `[2026-11-24]`

**Modelos Utilizados en OpenCode (Plan/Razonamiento vs. Build/Implementación)**: `[
Modelo gratuito OpenCode DeepSeek V4.1 Flash Free / Modelo Claude Opus 5.5 / Modelo de Razonamiento para Clarify y Plan / Modelo
Razonamiento para Implement]`
---
## 1. Elicitación con `/speckit.clarify` y Auditoría con `/speckit.analyze`
### 1.1 Feature `003-incident-lifecycle-sla`
- **Ambigüedades y casos borde detectados con `/speckit.clarify`**: `[
1. Pediste código de salida 1 en el CLI para los rechazos 422 y 404, pero la Constitución (F3) fija 0/2/3/4: entrada inválida = 3, y triage y summary ya usan 3. ¿Qué código usan create y sla para entrada inválida e incidente inexistente?
2. En create, incident_id es opcional y lo puede enviar el cliente. Si envía uno que ya existe (por ejemplo INC-2001 de la demo), ¿qué hace el sistema? Hoy el almacén reemplaza silenciosamente un incidente con el mismo identificador.
3. En create, status es opcional (por defecto OPEN). La Constitución (Art. 1.10) exige que un incidente RESOLVED tenga instante de resolución, y create no recibe ese campo. ¿Qué estados se aceptan al crear?
]`
- **Hallazgos o validaciones de `/speckit.analyze` antes de implementar**: `[Informe de análisis de la especificación (H003)

El análisis encontró 13 hallazgos: 1 crítico, 3 altos, 5 medios y 4 bajos. El crítico es la enmienda constitucional sin ADR. Los altos son una contradicción con la spec, un orden de tareas imposible y campos sin cita al modelo de datos. Los 29 requisitos medibles tienen al menos una tarea, pero varios casos que piden la spec o los criterios de éxito no tienen prueba. No modifiqué ningún archivo.]`
### 1.2 Feature `004-postgres-container-runtime`
- **Ambigüedades y RNF aclarados antes de diseñar PostgreSQL/Compose**: `[
* Enmienda 3.0.0 sin ADR. Choca con cuatro normas:
• Gobernanza (2): toda enmienda exige un ADR aceptado.
• Art. 4.1 de docs/constitution.md: dice lo mismo.
• F4 (f): exige ADR actualizado para dar un cambio por terminado.
• F5: los ADR se reemplazan, no se reescriben. Sin ADR nuevo, ADR-006 sigue vigente aunque contradice el puerto nuevo.
* D8 sigue diciendo que la enmienda va con un «ADR nuevo». plan.md y tasks.md ya dicen que no hay ADR.
* E2 verifica el reinicio auditando el SLA (spec.md:172), y eso solo existe tras T045–T049 (US3). El punto de control de US1 exige E2 en verde, lo que es imposible antes de US3.
* En las tareas, la traza registra el «estado». Puede leerse como el código HTTP o como el estado del incidente; FR-021 dice «código de resultado».]`
---
## 2. Comparación Crítica: SDD Manual (Iteración 1) vs. GitHub Spec Kit (Iteración 2 y
Retos)
| Dimensión Comparada | SDD Manual (Iteración 1: `001`) | GitHub Spec Kit (Iteración 2 y
Retos: `002`–`004`) |
| :--- | :--- | :--- |
| **Separación *QUÉ* vs. *CÓMO* vs. *TAREAS*** | | |
| **Gestión de ambigüedades (`/speckit.clarify`)** | | |
| **Consistencia contra la Constitución (`/speckit.analyze`)** | | |
| **Riesgo de verbosidad / exceso de Markdown** | | |
- **Análisis basado en MartinFowler.com (Birgitta Böckeler)**:
1. De los tres niveles descritos por Böckeler (**Spec-first**, **Spec-anchored**,
**Spec-as-source**), ¿en cuál ubicas este proyecto de *IncidentOps* y por qué? **Respuesta:** creeria que en **Spec-anchored** nunca se borro la especificación queda como bitacora, y el codigo lo hizo el agente.
2. Böckeler advierte que los *toolkits* SDD pueden generar "montañas de Markdown"
difíciles de revisar para un humano. ¿Qué técnicas aplicaste (concisión en
`docs/ROADMAP.md`, curaduría en `clarify`/`plan`/`tasks` y pruebas deterministas en
`pytest`) para evitar aprobar especificaciones verbosas a ciegas? **REspuesta:**Me centre en la curaduria `clarify`/`plan`/`tasks` para detectar y solucionar inconsistencias que pudieran haber.
---
## 3. *Commands* vs. *Agent Skills*, Arquitectura Hexagonal, ADRs y Uso de *Reasoning*
- **Diferencia entre *Commands* (`/speckit.*`) y *Agent Skills* (`hexagonal-
architecture`, `bdd-acceptance`, `adr-writer`)**: Explica cómo OpenCode carga las
*skills* bajo demanda y por qué fue necesario seguir el orden causal ADR $\rightarrow$
Constitución $\rightarrow$ Hito tanto en clase (`ADR-003` antes de
`docs/constitution.md`) como en el Reto 2 (`ADR-004` y actualización de
`.specify/memory/constitution.md` antes de especificar e implementar el Hito `004`). **Respuesta:** Los commandos /speckit.* se invocan en cada uno de los pasos del flujo SDD (specify → plan → tasks → implement) y genera un artefacto. Las skills son normas reutilizables que el agente activa por su cuenta: al iniciar solo carga su name/description, y carga el SKILL.md completo cuando la tarea coincide con esa descripción. El orden ADR → Constitución → Hito existe porque la Constitución es la norma superior y toda enmienda exige un ADR aceptado. Así el ADR justifica, la Constitución norma y el hito aplica. Invertir el orden deja deuda de gobernanza en H003. 
- **Valor de la Arquitectura Hexagonal**: Explica cómo compartir `IncidentService` e
`IncidentRepositoryPort` facilitó exponer FastAPI, Typer y el adaptador PostgreSQL sin
tocar el dominio (y cómo prepara la incorporación de futuros adaptadores). **Respuesta:** La idea central es que el dominio no sabe quién lo llama ni dónde se guardan los datos. IncidentService es la única puerta de entrada y IncidentRepositoryPort la única de salida. H004 añadió un canal nuevo (la sonda), un motor nuevo (PostgreSQL) y un runtime nuevo (contenedores), y lo único que cambió dentro de src/domain/ fue una línea en su ruff.toml para prohibir psycopg. 
- **Uso intencional de *Reasoning / Extended Thinking* en OpenCode**: ¿En qué comandos
(`/speckit.clarify`, `/speckit.plan`, `/speckit.analyze`) aportó mayor valor el
razonamiento extendido y en cuáles (`/speckit.implement`) resultó más eficiente un
modelo rápido? **Respuesta:** en todos estos pasos se utilizo modelos de razonamiento extendido "High" se usaron dos por que a la mitad del taller se quedo sin tokens.

---
## 4. Evidencia de Verificación Determinista
- **Análisis estático de fronteras hexagonales (`uv run ruff check src/`)**:
```
uv run ruff check src/
warning: `VIRTUAL_ENV=C:/Users/Usuario/Downloads/starter-project/.venv` does not match the project environment path `.venv` and will be ignored; use `--active` to target the active environment instead
All checks passed!
(incidentops-starter)
```
- **Salida completa de `uv run pytest -v`**:
```
$ uv run pytest -v
warning: `VIRTUAL_ENV=C:/Users/Usuario/Downloads/starter-project/.venv` does not match the project environment path `.venv` and will be ignored; use `--active` to target the active environment instead
========================================================================= test session starts =========================================================================
platform win32 -- Python 3.10.0, pytest-9.1.1, pluggy-1.7.0 -- C:\Users\Usuario\GIT\starter-project-taller-autonomo\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\Usuario\GIT\starter-project-taller-autonomo
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.16.0
collected 227 items                                                                                                                                                    

tests/test_arquitectura.py::test_capa_interna_sin_dependencias_prohibidas[domain] PASSED                                                                         [  0%] 
tests/test_arquitectura.py::test_capa_interna_sin_dependencias_prohibidas[application] PASSED                                                                    [  0%]
tests/test_arquitectura.py::test_canales_de_entrada_no_conocen_persistencia PASSED                                                                               [  1%]
tests/test_arquitectura.py::test_dominio_no_lee_el_reloj PASSED                                                                                                  [  1%]
tests/test_spec_001_triage.py::test_e1_caida_critica_pasarela_de_pagos PASSED                                                                                    [  2%]
tests/test_spec_001_triage.py::test_e1b_caida_se_agrupa_con_mas_de_un_reporte PASSED                                                                             [  2%]
tests/test_spec_001_triage.py::test_e2_cuenta_bloqueada_con_hoy_no_es_p0 PASSED                                                                                  [  3%]
tests/test_spec_001_triage.py::test_e3_raw_text_vacio_responde_422_sin_ejecutar_motor[0-] PASSED                                                                 [  3%]
tests/test_spec_001_triage.py::test_e3_raw_text_vacio_responde_422_sin_ejecutar_motor[0- ] PASSED                                                                [  3%] 
tests/test_spec_001_triage.py::test_e3_raw_text_vacio_responde_422_sin_ejecutar_motor[0-   \t  ] PASSED                                                          [  4%]
tests/test_spec_001_triage.py::test_e3_raw_text_vacio_responde_422_sin_ejecutar_motor[1-] PASSED                                                                 [  4%]
tests/test_spec_001_triage.py::test_e3_raw_text_vacio_responde_422_sin_ejecutar_motor[1- ] PASSED                                                                [  5%]
tests/test_spec_001_triage.py::test_e3_raw_text_vacio_responde_422_sin_ejecutar_motor[1-   \t  ] PASSED                                                          [  5%]
tests/test_spec_001_triage.py::test_e3b_etiqueta_vacia_por_cli_termina_con_codigo_3 PASSED                                                                       [  6%]
tests/test_spec_001_triage.py::test_e4_paridad_cli_http_para_inc_1001 PASSED                                                                                     [  6%]
tests/test_spec_001_triage.py::test_e10_contrato_estricto_responde_400[report0-reserved_field-reports[0].incident_id] PASSED                                     [  7%]
tests/test_spec_001_triage.py::test_e10_contrato_estricto_responde_400[report1-invalid_payload-reports[0].prioridad] PASSED                                      [  7%]
tests/test_spec_001_triage.py::test_e10_contrato_estricto_responde_400[report2-invalid_payload-reports[0].raw_text] PASSED                                       [  7%]
tests/test_spec_001_triage.py::test_json_malformado_responde_400_invalid_json PASSED                                                                             [  8%]
tests/test_spec_001_triage.py::test_health PASSED                                                                                                                [  8%]
tests/test_spec_002_summary.py::test_el_puerto_declara_los_seis_metodos_del_hito PASSED                                                                          [  9%]
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[add_incident-SQLiteIncidentRepository] PASSED                           [  9%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[add_incident-NullIncidentRepository] PASSED                             [ 10%]
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[add_incident-InMemoryIncidentRepository] PASSED                         [ 10%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[check_health-SQLiteIncidentRepository] PASSED                           [ 11%]
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[check_health-NullIncidentRepository] PASSED                             [ 11%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[check_health-InMemoryIncidentRepository] PASSED                         [ 11%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[find_open_duplicates-SQLiteIncidentRepository] PASSED                   [ 12%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[find_open_duplicates-NullIncidentRepository] PASSED                     [ 12%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[find_open_duplicates-InMemoryIncidentRepository] PASSED                 [ 13%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[get_incident-SQLiteIncidentRepository] PASSED                           [ 13%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[get_incident-NullIncidentRepository] PASSED                             [ 14%]
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[get_incident-InMemoryIncidentRepository] PASSED                         [ 14%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[list_active_incidents-SQLiteIncidentRepository] PASSED                  [ 14%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[list_active_incidents-NullIncidentRepository] PASSED                    [ 15%]
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[list_active_incidents-InMemoryIncidentRepository] PASSED                [ 15%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[save_incident-SQLiteIncidentRepository] PASSED                          [ 16%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[save_incident-NullIncidentRepository] PASSED                            [ 16%] 
tests/test_spec_002_summary.py::test_forma_de_cada_implementacion_coincide_con_el_puerto[save_incident-InMemoryIncidentRepository] PASSED                        [ 17%] 
tests/test_spec_002_summary.py::test_guardar_y_recuperar_normaliza_a_bogota[memoria] PASSED                                                                      [ 17%] 
tests/test_spec_002_summary.py::test_guardar_y_recuperar_normaliza_a_bogota[sqlite] PASSED                                                                       [ 18%] 
tests/test_spec_002_summary.py::test_guardar_reemplaza_por_identificador[memoria] PASSED                                                                         [ 18%]
tests/test_spec_002_summary.py::test_guardar_reemplaza_por_identificador[sqlite] PASSED                                                                          [ 18%] 
tests/test_spec_002_summary.py::test_identificador_inexistente_devuelve_none[memoria] PASSED                                                                     [ 19%] 
tests/test_spec_002_summary.py::test_identificador_inexistente_devuelve_none[sqlite] PASSED                                                                      [ 19%] 
tests/test_spec_002_summary.py::test_severidad_sin_politica_se_rechaza[memoria] PASSED                                                                           [ 20%] 
tests/test_spec_002_summary.py::test_severidad_sin_politica_se_rechaza[sqlite] PASSED                                                                            [ 20%] 
tests/test_spec_002_summary.py::test_activos_coinciden_exactamente_con_la_definicion_del_dominio[memoria] PASSED                                                 [ 21%] 
tests/test_spec_002_summary.py::test_activos_coinciden_exactamente_con_la_definicion_del_dominio[sqlite] PASSED                                                  [ 21%] 
tests/test_spec_002_summary.py::test_activos_filtrados_por_componente[memoria] PASSED                                                                            [ 22%] 
tests/test_spec_002_summary.py::test_activos_filtrados_por_componente[sqlite] PASSED                                                                             [ 22%] 
tests/test_spec_002_summary.py::test_duplicados_abiertos_por_clave_de_grupo_y_ordenados[memoria] PASSED                                                          [ 22%] 
tests/test_spec_002_summary.py::test_duplicados_abiertos_por_clave_de_grupo_y_ordenados[sqlite] PASSED                                                           [ 23%] 
tests/test_spec_002_summary.py::test_el_almacen_responde[memoria] PASSED                                                                                         [ 23%] 
tests/test_spec_002_summary.py::test_el_almacen_responde[sqlite] PASSED                                                                                          [ 24%]
tests/test_spec_002_summary.py::test_sqlite_y_doble_devuelven_lo_mismo_para_los_mismos_datos PASSED                                                              [ 24%] 
tests/test_spec_002_summary.py::test_sla_policies_es_espejo_de_la_politica_del_dominio PASSED                                                                    [ 25%] 
tests/test_spec_002_summary.py::test_la_consulta_de_activos_usa_el_indice_parcial[global] PASSED                                                                 [ 25%] 
tests/test_spec_002_summary.py::test_la_consulta_de_activos_usa_el_indice_parcial[por-componente] PASSED                                                         [ 25%]
tests/test_spec_002_summary.py::test_repositorio_nulo_no_tiene_efectos PASSED                                                                                    [ 26%] 
tests/test_spec_002_summary.py::test_e1_resumen_global_excluye_resueltos PASSED                                                                                  [ 26%]
tests/test_spec_002_summary.py::test_e1_por_la_web_devuelve_el_contrato_completo PASSED                                                                          [ 27%]
tests/test_spec_002_summary.py::test_metodo_distinto_de_get_responde_405 PASSED                                                                                  [ 27%]
tests/test_spec_002_summary.py::test_e4_solo_resolved_queda_fuera PASSED                                                                                         [ 28%] 
tests/test_spec_002_summary.py::test_e7_minutos_segun_la_politica_de_la_severidad PASSED                                                                         [ 28%] 
tests/test_spec_002_summary.py::test_e8_incumplimiento_y_escalamiento_son_excluyentes PASSED                                                                     [ 29%] 
tests/test_spec_002_summary.py::test_e9_orden_determinista_del_detalle PASSED                                                                                    [ 29%] 
tests/test_spec_002_summary.py::test_e12_la_consulta_no_modifica_los_datos[memoria] PASSED                                                                       [ 29%]
tests/test_spec_002_summary.py::test_e12_la_consulta_no_modifica_los_datos[sqlite] PASSED                                                                        [ 30%]
tests/test_spec_002_summary.py::test_e2_filtro_por_componente PASSED                                                                                             [ 30%]
tests/test_spec_002_summary.py::test_e3_caso_vacio_es_exitoso[E3.1-sin-activos] PASSED                                                                           [ 31%]
tests/test_spec_002_summary.py::test_e3_caso_vacio_es_exitoso[E3.2-sin-coincidencias] PASSED                                                                     [ 31%]
tests/test_spec_002_summary.py::test_filtro_con_mayusculas_y_espacios_se_normaliza PASSED                                                                        [ 32%]
tests/test_spec_002_summary.py::test_sc004_el_filtro_no_altera_las_cifras_de_otros_componentes PASSED                                                            [ 32%] 
tests/test_spec_002_summary.py::test_filtro_vacio_se_rechaza_con_422[] PASSED                                                                                    [ 33%]
tests/test_spec_002_summary.py::test_filtro_vacio_se_rechaza_con_422[   ] PASSED                                                                                 [ 33%]
tests/test_spec_002_summary.py::test_e5_instante_anterior_a_la_creacion_excluye_el_incidente PASSED                                                              [ 33%]
tests/test_spec_002_summary.py::test_incidente_creado_en_el_instante_exacto_cuenta_con_cero_minutos PASSED                                                       [ 34%]
tests/test_spec_002_summary.py::test_e6_el_estado_sla_se_recalcula_al_instante_consultado PASSED                                                                 [ 34%]
tests/test_spec_002_summary.py::test_instante_futuro_se_admite PASSED                                                                                            [ 35%] 
tests/test_spec_002_summary.py::test_parse_reference_time_acepta_iso_8601[naive] PASSED                                                                          [ 35%] 
tests/test_spec_002_summary.py::test_parse_reference_time_acepta_iso_8601[sufijo-Z] PASSED                                                                       [ 36%] 
tests/test_spec_002_summary.py::test_parse_reference_time_acepta_iso_8601[utc] PASSED                                                                            [ 36%] 
tests/test_spec_002_summary.py::test_parse_reference_time_acepta_iso_8601[bogota] PASSED                                                                         [ 37%] 
tests/test_spec_002_summary.py::test_parse_reference_time_rechaza_texto_no_iso PASSED                                                                            [ 37%] 
tests/test_spec_002_summary.py::test_e10_consulta_equivalente_por_terminal[global] PASSED                                                                        [ 37%]
tests/test_spec_002_summary.py::test_e10_consulta_equivalente_por_terminal[filtrado] PASSED                                                                      [ 38%]
tests/test_spec_002_summary.py::test_cli_tabla_muestra_totales_y_detalle PASSED                                                                                  [ 38%]
tests/test_spec_002_summary.py::test_e11a_invalidez_semantica_del_instante_y_del_filtro PASSED                                                                   [ 39%]
tests/test_spec_002_summary.py::test_e11b_parametro_desconocido[bandera] PASSED                                                                                  [ 39%]
tests/test_spec_002_summary.py::test_e11b_parametro_desconocido[formato] PASSED                                                                                  [ 40%]
tests/test_spec_002_summary.py::test_fallo_interno_responde_500_y_codigo_4_sin_titulos PASSED                                                                    [ 40%]
tests/test_spec_002_summary.py::test_configuracion_invalida_termina_con_codigo_4_sin_traceback[command0] PASSED                                                  [ 40%]
tests/test_spec_002_summary.py::test_configuracion_invalida_termina_con_codigo_4_sin_traceback[command1] PASSED                                                  [ 41%]
tests/test_spec_002_summary.py::test_sc001_diez_mil_activos_por_canal_en_menos_de_un_segundo PASSED                                                              [ 41%]
tests/test_spec_003_lifecycle_sla.py::test_forma_de_los_metodos_nuevos_del_puerto[add_incident-SQLiteIncidentRepository] PASSED                                  [ 42%] 
tests/test_spec_003_lifecycle_sla.py::test_forma_de_los_metodos_nuevos_del_puerto[add_incident-NullIncidentRepository] PASSED                                    [ 42%] 
tests/test_spec_003_lifecycle_sla.py::test_forma_de_los_metodos_nuevos_del_puerto[add_incident-InMemoryIncidentRepository] PASSED                                [ 43%] 
tests/test_spec_003_lifecycle_sla.py::test_forma_de_los_metodos_nuevos_del_puerto[find_open_duplicates-SQLiteIncidentRepository] PASSED                          [ 43%]
tests/test_spec_003_lifecycle_sla.py::test_forma_de_los_metodos_nuevos_del_puerto[find_open_duplicates-NullIncidentRepository] PASSED                            [ 44%] 
tests/test_spec_003_lifecycle_sla.py::test_forma_de_los_metodos_nuevos_del_puerto[find_open_duplicates-InMemoryIncidentRepository] PASSED                        [ 44%] 
tests/test_spec_003_lifecycle_sla.py::test_forma_del_generador_de_identificadores[RandomHexIdGenerator] PASSED                                                   [ 44%] 
tests/test_spec_003_lifecycle_sla.py::test_forma_del_generador_de_identificadores[SequenceIdGenerator] PASSED                                                    [ 45%]
tests/test_spec_003_lifecycle_sla.py::test_el_generador_aleatorio_produce_la_forma_publica PASSED                                                                [ 45%] 
tests/test_spec_003_lifecycle_sla.py::test_insertar_un_identificador_existente_es_conflicto_sin_tocar_el_original[memoria] PASSED                                [ 46%] 
tests/test_spec_003_lifecycle_sla.py::test_insertar_un_identificador_existente_es_conflicto_sin_tocar_el_original[sqlite] PASSED                                 [ 46%]
tests/test_spec_003_lifecycle_sla.py::test_insertar_con_severidad_sin_politica_se_rechaza[memoria] PASSED                                                        [ 47%] 
tests/test_spec_003_lifecycle_sla.py::test_insertar_con_severidad_sin_politica_se_rechaza[sqlite] PASSED                                                         [ 47%]
tests/test_spec_003_lifecycle_sla.py::test_duplicados_abiertos_filtran_por_clave_estado_y_excluido[memoria] PASSED                                               [ 48%] 
tests/test_spec_003_lifecycle_sla.py::test_duplicados_abiertos_filtran_por_clave_estado_y_excluido[sqlite] PASSED                                                [ 48%]
tests/test_spec_003_lifecycle_sla.py::test_ida_y_vuelta_de_los_nueve_campos[memoria] PASSED                                                                      [ 48%] 
tests/test_spec_003_lifecycle_sla.py::test_ida_y_vuelta_de_los_nueve_campos[sqlite] PASSED                                                                       [ 49%]
tests/test_spec_003_lifecycle_sla.py::test_un_archivo_de_h002_se_migra_sin_perder_filas PASSED                                                                   [ 49%]
tests/test_spec_003_lifecycle_sla.py::test_la_busqueda_de_duplicados_usa_su_indice_parcial PASSED                                                                [ 50%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e1_registro_inicial_sin_duplicados PASSED                                                                         [ 50%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e3_la_urgencia_no_cambia_la_severidad PASSED                                                                      [ 51%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e4_el_creado_aparece_en_el_resumen_de_activos PASSED                                                              [ 51%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e19_se_respeta_el_identificador_del_cliente PASSED                                                                [ 51%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e20_identificador_repetido_se_rechaza_sin_tocar_el_existente PASSED                                               [ 52%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e21_el_estado_inicial_puede_informarse[E21.1-en-curso] PASSED                                                     [ 52%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e21_el_estado_inicial_puede_informarse[E21.2-escalado] PASSED                                                     [ 53%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e21_el_estado_inicial_puede_informarse[E21.3-resuelto-completo] PASSED                                            [ 53%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e21_el_estado_inicial_puede_informarse[E21.4-resuelto-incompleto] PASSED                                          [ 54%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e21_el_estado_inicial_puede_informarse[E21.5-resolucion-en-abierto] PASSED                                        [ 54%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e21_el_estado_inicial_puede_informarse[E21.6-resolucion-previa] PASSED                                            [ 55%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e21_el_estado_inicial_puede_informarse[E21.7-estado-inexistente] PASSED                                           [ 55%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15a_contenido_inaceptable_no_guarda_nada[E15a.1-titulo-vacio] PASSED                                             [ 55%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15a_contenido_inaceptable_no_guarda_nada[E15a.2-texto-vacio] PASSED                                              [ 56%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15a_contenido_inaceptable_no_guarda_nada[E15a.3-texto-largo] PASSED                                              [ 56%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15a_contenido_inaceptable_no_guarda_nada[E15a.4-titulo-largo] PASSED                                             [ 57%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15a_contenido_inaceptable_no_guarda_nada[E15a.5-identificador-mal-formado] PASSED                                [ 57%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15a_contenido_inaceptable_no_guarda_nada[E15a.6-instante-ilegible] PASSED                                        [ 58%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15b_fuera_de_contrato_no_guarda_nada[E15b.1-desconocido] PASSED                                                  [ 58%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15b_fuera_de_contrato_no_guarda_nada[E15b.2-reservado-severity] PASSED                                           [ 59%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15b_fuera_de_contrato_no_guarda_nada[E15b.2-reservado-component] PASSED                                          [ 59%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15b_fuera_de_contrato_no_guarda_nada[E15b.2-reservado-recommended_team] PASSED                                   [ 59%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15b_fuera_de_contrato_no_guarda_nada[E15b.2-reservado-action] PASSED                                             [ 60%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e15b_fuera_de_contrato_no_guarda_nada[E15b.2-reservado-duplicate_group_key] PASSED                                [ 60%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e17_fallo_del_almacen_al_crear PASSED                                                                             [ 61%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e18_la_creacion_no_expone_el_contenido_en_las_trazas PASSED                                                       [ 61%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e5_duplicado_abierto_ignora_resueltos PASSED                                                                      [ 62%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e6_sin_aviso_cuando_no_hay_abierto_con_la_misma_clave[E6.1-otra-clave] PASSED                                     [ 62%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e6_sin_aviso_cuando_no_hay_abierto_con_la_misma_clave[E6.2-coincidente-resuelto] PASSED                           [ 62%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e6_sin_aviso_cuando_no_hay_abierto_con_la_misma_clave[E6.3-sin-clave] PASSED                                      [ 63%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e6_sin_aviso_cuando_no_hay_abierto_con_la_misma_clave[E6.4-sin-clasificar] PASSED                                 [ 63%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e8_creaciones_simultaneas_del_mismo_problema PASSED                                                               [ 64%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e22_ni_la_antiguedad_ni_la_recurrencia_impiden_el_aviso PASSED                                                    [ 64%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e23_un_creado_ya_resuelto_no_genera_avisos_en_otros PASSED                                                        [ 65%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e2_el_incidente_sobrevive_al_reinicio PASSED                                                                      [ 65%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e9_sla_de_un_incidente_activo PASSED                                                                              [ 66%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e10_reconstruccion_del_sla_a_un_instante_pasado[E10.1-antes-del-cierre] PASSED                                    [ 66%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e10_reconstruccion_del_sla_a_un_instante_pasado[E10.2-despues-del-cierre] PASSED                                  [ 66%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e11_paridad_cli_create_y_sla[E11.1-registrar] PASSED                                                              [ 67%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e11_paridad_cli_create_y_sla[E11.2-auditar] PASSED                                                                [ 67%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e12_sla_habil_determinista PASSED                                                                                 [ 68%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e13_auditoria_incidente_inexistente PASSED                                                                        [ 68%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e14_auditoria_antes_de_la_creacion PASSED                                                                         [ 69%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_e16_la_auditoria_no_modifica_datos_ni_expone_contenido PASSED                                                     [ 69%]
tests/test_spec_003_lifecycle_sla.py::test_sc006_crear_y_auditar_con_diez_mil_abiertos_en_menos_de_un_segundo PASSED                                             [ 70%]
tests/test_spec_004_runtime_health.py::test_bdd_e1_health_200 PASSED                                                                                             [ 70%]
tests/test_spec_004_runtime_health.py::test_bdd_e1_health_200_con_el_almacen_por_defecto PASSED                                                                  [ 70%]
tests/test_spec_004_runtime_health.py::test_bdd_e2_cli_health_ok PASSED                                                                                          [ 71%]
tests/test_spec_004_runtime_health.py::test_bdd_e3_health_503_con_doble PASSED                                                                                   [ 71%]
tests/test_spec_004_runtime_health.py::test_bdd_e4_cli_health_unavailable_con_doble PASSED                                                                       [ 72%]
tests/test_spec_004_runtime_health.py::test_bdd_e4_cli_health_unavailable_al_consultar PASSED                                                                    [ 72%]
tests/test_spec_004_runtime_health.py::test_bdd_e5_recuperacion_sin_reinicio PASSED                                                                              [ 73%]
tests/test_spec_004_runtime_health.py::test_bdd_e6_liveness_sin_cambios PASSED                                                                                   [ 73%]
tests/test_spec_004_runtime_health.py::test_health_metodo_no_permitido PASSED                                                                                    [ 74%]
tests/test_spec_004_runtime_health.py::test_rnf006_registro_solo_cambios_de_estado PASSED                                                                        [ 74%]
tests/test_spec_004_runtime_health.py::test_fr004_check_health_que_lanza_es_unavailable PASSED                                                                   [ 74%]
tests/test_spec_004_runtime_health.py::test_bdd_e7_sin_database_url_usa_memoria[sin_variable] PASSED                                                             [ 75%]
tests/test_spec_004_runtime_health.py::test_bdd_e7_sin_database_url_usa_memoria[vacia] PASSED                                                                    [ 75%]
tests/test_spec_004_runtime_health.py::test_bdd_e8_sqlite_archivo PASSED                                                                                         [ 76%]
tests/test_spec_004_runtime_health.py::test_bdd_e10_esquema_no_soportado[summary-mysql://u:secreto@h/db-mysql] PASSED                                            [ 76%] 
tests/test_spec_004_runtime_health.py::test_bdd_e10_esquema_no_soportado[summary-postgres://u:secreto@h/db-postgres] PASSED                                      [ 77%]
tests/test_spec_004_runtime_health.py::test_bdd_e10_esquema_no_soportado[summary-texto-desconocido] PASSED                                                       [ 77%]
tests/test_spec_004_runtime_health.py::test_bdd_e10_esquema_no_soportado[health-mysql://u:secreto@h/db-mysql] PASSED                                             [ 77%]
tests/test_spec_004_runtime_health.py::test_bdd_e10_esquema_no_soportado[health-postgres://u:secreto@h/db-postgres] PASSED                                       [ 78%]
tests/test_spec_004_runtime_health.py::test_bdd_e10_esquema_no_soportado[health-texto-desconocido] PASSED                                                        [ 78%]
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[save_incident-sqlite] PASSED                                               [ 79%] 
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[save_incident-postgresql] PASSED                                           [ 79%]
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[add_incident-sqlite] PASSED                                                [ 80%] 
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[add_incident-postgresql] PASSED                                            [ 80%] 
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[get_incident-sqlite] PASSED                                                [ 81%] 
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[get_incident-postgresql] PASSED                                            [ 81%]
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[find_open_duplicates-sqlite] PASSED                                        [ 81%]
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[find_open_duplicates-postgresql] PASSED                                    [ 82%] 
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[list_active_incidents-sqlite] PASSED                                       [ 82%]
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[list_active_incidents-postgresql] PASSED                                   [ 83%]
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[check_health-sqlite] PASSED                                                [ 83%] 
tests/test_spec_004_runtime_health.py::test_create_repository_conformidad_estructural[check_health-postgresql] PASSED                                            [ 84%]
tests/test_spec_004_runtime_health.py::test_bdd_e4_camino_real_puerto_muerto PASSED                                                                              [ 84%]
tests/test_spec_004_runtime_health.py::test_bdd_e17_arranque_degradado_rapido PASSED                                                                             [ 85%]
tests/test_spec_004_runtime_health.py::test_url_postgres_mal_formada PASSED                                                                                      [ 85%] 
tests/test_spec_004_runtime_health.py::test_c9_check_health_con_el_almacen_caido PASSED                                                                          [ 85%]
tests/test_spec_004_runtime_health.py::test_c11_error_del_driver_no_cruza_el_puerto PASSED                                                                       [ 86%]
tests/test_spec_004_runtime_health.py::test_c1_save_incident_reemplaza[sqlite] PASSED                                                                            [ 86%]
tests/test_spec_004_runtime_health.py::test_c1_save_incident_reemplaza[postgresql] SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: casos PostgreSQL...) [ 87%] 
tests/test_spec_004_runtime_health.py::test_c2_add_incident_con_id_existente[sqlite] PASSED                                                                      [ 87%]
tests/test_spec_004_runtime_health.py::test_c2_add_incident_con_id_existente[postgresql] SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: casos Post...) [ 88%] 
tests/test_spec_004_runtime_health.py::test_c3_severidad_sin_politica[sqlite-save_incident] PASSED                                                               [ 88%]
tests/test_spec_004_runtime_health.py::test_c3_severidad_sin_politica[sqlite-add_incident] PASSED                                                                [ 88%]
tests/test_spec_004_runtime_health.py::test_c3_severidad_sin_politica[postgresql-save_incident] SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: cas...) [ 89%] 
tests/test_spec_004_runtime_health.py::test_c3_severidad_sin_politica[postgresql-add_incident] SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: caso...) [ 89%]
tests/test_spec_004_runtime_health.py::test_c4_get_incident_inexistente[sqlite] PASSED                                                                           [ 90%]
tests/test_spec_004_runtime_health.py::test_c4_get_incident_inexistente[postgresql] SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: casos PostgreSQ...) [ 90%] 
tests/test_spec_004_runtime_health.py::test_c5_ida_y_vuelta_de_instantes[sqlite] PASSED                                                                          [ 91%]
tests/test_spec_004_runtime_health.py::test_c5_ida_y_vuelta_de_instantes[postgresql] SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: casos PostgreS...) [ 91%] 
tests/test_spec_004_runtime_health.py::test_c6_activos_por_estado_y_componente[sqlite] PASSED                                                                    [ 92%]
tests/test_spec_004_runtime_health.py::test_c6_activos_por_estado_y_componente[postgresql] SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: casos Po...) [ 92%] 
tests/test_spec_004_runtime_health.py::test_c7_duplicados_abiertos_en_orden_por_bytes[sqlite] PASSED                                                             [ 92%]
tests/test_spec_004_runtime_health.py::test_c7_duplicados_abiertos_en_orden_por_bytes[postgresql] SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: c...) [ 93%] 
tests/test_spec_004_runtime_health.py::test_c8_check_health_disponible[sqlite] PASSED                                                                            [ 93%]
tests/test_spec_004_runtime_health.py::test_c8_check_health_disponible[postgresql] SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: casos PostgreSQL...) [ 94%]
tests/test_spec_004_runtime_health.py::test_c10_siembra_unica SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: casos PostgreSQL omitidos (Constituci...) [ 94%] 
tests/test_spec_004_runtime_health.py::test_bdd_e9_postgresql_persiste_entre_procesos SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: casos Postgre...) [ 95%] 
tests/test_spec_004_runtime_health.py::test_bdd_e11_paridad_byte_a_byte SKIPPED (INCIDENTOPS_TEST_POSTGRES_URL no está definida: casos PostgreSQL omitidos (...) [ 95%] 
tests/test_spec_004_runtime_health.py::test_dockerfile_estructura PASSED                                                                                         [ 96%] 
tests/test_spec_004_runtime_health.py::test_dockerignore_entradas_del_contrato PASSED                                                                            [ 96%] 
tests/test_spec_004_runtime_health.py::test_compose_estructura PASSED                                                                                            [ 96%]
tests/test_spec_004_runtime_health.py::test_compose_config_valida PASSED                                                                                         [ 97%]
tests/test_spec_004_runtime_health.py::test_bdd_e12_entorno_nuevo PASSED                                                                                         [ 97%]
tests/test_spec_004_runtime_health.py::test_bdd_e13_persistencia_tras_reinicio PASSED                                                                            [ 98%]
tests/test_spec_004_runtime_health.py::test_bdd_e14_caida_de_la_base PASSED                                                                                      [ 98%]
tests/test_spec_004_runtime_health.py::test_bdd_e15_exposicion_minima PASSED                                                                                     [ 99%]
tests/test_spec_004_runtime_health.py::test_bdd_e16_imagen_limpia PASSED                                                                                         [ 99%]
tests/test_spec_004_runtime_health.py::test_bdd_e17_arranque_degradado PASSED                                                                                    [100%]

========================================================================== warnings summary =========================================================================== 
.venv\lib\site-packages\fastapi\testclient.py:1
  C:\Users\Usuario\GIT\starter-project-taller-autonomo\.venv\lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================================================= 215 passed, 12 skipped, 1 warning in 204.12s (0:03:24) ======================================================== 
```
- **Evidencia de CLI Typer y containerización (`docker compose config` / `docker compose up --build`)**:
```
$ docker compose config
name: incidentops
services:
  api:
    build:
      context: C:\Users\Usuario\GIT\starter-project-taller-autonomo
      dockerfile: Dockerfile
    depends_on:
      db:
        condition: service_healthy
        required: true
    environment:
      DATABASE_URL: postgresql://incidentops:incidentops@db:5432/incidentops
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',
          timeout=4).status == 200 else 1)
      timeout: 5s
      interval: 10s
      retries: 3
      start_period: 15s
    networks:
      default: null
    ports:
      - mode: ingress
        host_ip: 127.0.0.1
        target: 8080
        published: "8080"
        protocol: tcp
    restart: unless-stopped
  db:
    environment:
      POSTGRES_DB: incidentops
      POSTGRES_INITDB_ARGS: --locale=C --encoding=UTF8
      POSTGRES_PASSWORD: incidentops
      POSTGRES_USER: incidentops
    healthcheck:
      test:
        - CMD-SHELL
        - pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"
      timeout: 3s
      interval: 5s
      retries: 10
      start_period: 10s
    image: postgres:16-alpine
    networks:
      default: null
    restart: unless-stopped
    volumes:
      - type: volume
        source: pgdata
        target: /var/lib/postgresql/data
        volume: {}
networks:
  default:
    name: incidentops_default
volumes:
  pgdata:
    name: incidentops_pgdata

```