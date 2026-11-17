# Bitácora de Ingeniería de Prompts y Contexto — Semana 1 (`CONTEXT_LOG.md`)

**Estudiante(s)**: `Edgar Fernando Vega Morales`  
**Fecha**: `2026-11-16`  
**Modelos / Asistentes Utilizados**: `GPT-6, Claude Opus 5.5`

---

## 1. De Prompts Pobres a Técnicas Clásicas de *Prompt Engineering* (Reto 1: `src/triage_rules.py`)

### 1.1 Diagnóstico de un Prompt Pobre y Ambiguo
Analiza el siguiente prompt deficiente para el Reto 1:
> *"El archivo `triage_rules.py` funciona mal con algunos tickets del JSON. Agrégale el equipo recomendado y una clave para duplicados, y no pongas P0 cuando no sea urgente."*

Documenta al menos **3 modos de fallo o ambigüedades** de este prompt (p. ej., ausencia de contexto de dominio, restricciones negativas difusas, falta de enumeración de equipos válidos o ausencia de ejemplos canónicos):
1. `Se es ambiguo en la frase "funciona mal con algunos tickets del JSON" para que el LLM entienda cuales están mal se necesita mayor contexto habría que explicar cuales tickets son ambiguos y el porqué.`
2. `La frase “no pongas P0 cuando no sea urgente” no describe los niveles de severidad de las incidencias. El LLM podría llegar a intuir que el nivel P0 es uno de los niveles más graves, pero no podría llegar a inferir cuantos niveles de severidad están definidos y cuál es su código especifico.`
3. ` Falta la enumeración de cuáles son los equipos de trabajo válidos.`
4. ` Ausencia de ejemplos canónicos representativos, para que el modelo sepa cómo podría ser la entrada del sistema y cuáles son los niveles y las reglas para clasificarlos .`

### 1.2 Uso de *Self-Consistency*, *Chain-of-Thought* y *Few-Shot Prompting*
- ¿Cómo utilizaste *Chain-of-Thought* (`<analysis>`) y *Self-Consistency* (múltiples consultas independientes) para definir las reglas de clasificación de los casos ambiguos (`INC-1002`, `INC-1007`, `INC-1009`) y la agrupación de duplicados (`INC-1001`/`INC-1006` e `INC-1003`/`INC-1008`)?
- Copia el prompt mejorado que empleaste aplicando las técnicas clásicas (`<role>`, `<domain_rules>` con justificación del *porqué*, `<examples>` *Few-Shot* y `<task>`):

```xml
<!-- Pega aquí tu prompt estructurado con <role>, <domain_rules>, <examples>, <task> -->
<role>
Actúa como Ingeniero Principal de Confiabilidad (SRE) y Seguridad en IncidentOps.
</role>
<context>
	<lsp_context symbol="classify_incident_report">
	  <!-- 1. Definiciones de Tipos y Políticas (LSP Hover / Type Definition) -->
	# [LSP textDocument/hover type] src\models.py:12
	class SLARule:
		"""Define el acuerdo de nivel de servicio (SLA) para un nivel de severidad."""

		severity: SeverityLevel
		max_resolution_minutes: int
		operates_24x7: bool
		escalation_threshold_ratio: float = 0.75

	# [LSP textDocument/hover type] src\models.py:22
	class Incident:
		"""Representa un incidente registrado en la plataforma IncidentOps."""

		incident_id: str
		title: str
		component: str
		severity: SeverityLevel
		status: IncidentStatus
		created_at: datetime
		resolved_at: Optional[datetime] = None

	# [LSP textDocument/hover type] src\models.py:35
	class SLAEvaluation:
		"""Resultado determinista de la evaluación de SLA de un incidente."""

		incident_id: str
		severity: SeverityLevel
		elapsed_minutes: int
		allowed_minutes: int
		remaining_minutes: int
		is_breached: bool
		requires_escalation: bool

	# [LSP textDocument/hover type] src\models.py:48
	class TriageResult:
		"""Resultado estructurado producido por el clasificador de triaje con IA."""

		incident_id: str
		severity: SeverityLevel
		component: str
		rationale: str
		consistency_ratio: float = 1.0

	# [LSP textDocument/hover symbol] src\sla_calculator.py:17
	SLA_POLICY_TABLE: Dict[SeverityLevel, SLARule] = {
		"P0": SLARule(severity="P0", max_resolution_minutes=60, operates_24x7=True),
		"P1": SLARule(severity="P1", max_resolution_minutes=240, operates_24x7=True),
		"P2": SLARule(severity="P2", max_resolution_minutes=480, operates_24x7=False),
		"P3": SLARule(severity="P3", max_resolution_minutes=1440, operates_24x7=False),
	}

	  <!-- 2. Definición Exacta del Símbolo (LSP GoToDefinition) -->
	# [LSP textDocument/definition] src\triage_rules.py:27
	def classify_incident_report(incident_id: str, raw_text: str) -> TriageResult:
		"""Clasifica un reporte de incidente aplicando reglas heurísticas iniciales.

		DEUDA TÉCNICA INTENCIONAL:
		- Evalúa palabras sueltas ("hoy", "urgente") antes de analizar el impacto real
		  (caída global vs. cuenta individual vs. entorno de staging).
		- No normaliza componentes ni identifica el equipo de guardia correspondiente.
		"""
		text_lower = raw_text.lower()

		# Bug de diseño: si un usuario dice "necesito acceder hoy" por su cuenta bloqueada,
		# se dispara como P0 antes de verificar si es una caída global o un caso individual.
		if "urgente" in text_lower or "hoy" in text_lower or "502" in text_lower:
			severity: SeverityLevel = "P0"
		elif "94%" in text_lower or "timeout" in text_lower:
			severity = "P1"
		elif "lenta" in text_lower or "segundos" in text_lower:
			severity = "P2"
		else:
			severity = "P3"

		if "pago" in text_lower or "cobro" in text_lower or "tarjeta" in text_lower:
			component = "payments-gateway"
		elif "cuenta" in text_lower or "ingresar" in text_lower:
			component = "auth-identity"
		elif "postgresql" in text_lower or "conexiones" in text_lower:
			component = "database-cluster"
		elif "certificado" in text_lower or "tls" in text_lower:
			component = "infra-certificates"
		elif "botón" in text_lower or "color" in text_lower:
			component = "frontend-ui"
		else:
			component = "reporting-api"

		return TriageResult(
			incident_id=incident_id,
			severity=severity,
			component=component,
			rationale=f"Clasificación heurística legacy asignada a {component} ({severity}).",
		)

	  <!-- 3. Referencias de Invocación en el Proyecto (LSP FindReferences) -->
	# [LSP textDocument/references] src\triage_rules.py:77
	  L76:     for item in incidents:
	  L77:         result = classify_incident_report(item["id"], item["raw_text"])
	  L78:         snippet = item["raw_text"][:45] + "..." if len(item["raw_text"]) > 45 else item["raw_text"]
	</lsp_context>
</context>
<domain_rules>
Debemos clasificar reportes de incidentes en cuatro niveles de severidad:
- P0 (SLA 60 min, guardia 24/7): Indisponibilidad global de un servicio crítico
(ej. pagos HTTP 502) o brecha activa de seguridad / fuga de datos entre
organizaciones (multi-tenant).
- P1 (SLA 240 min, guardia 24/7): Degradación severa de infraestructura compartida
con riesgo inminente de caída (ej. pool de conexiones de base de datos >90%).
- P2 (SLA 480 min, horario hábil L-V 08:00-18:00): Degradación moderada de
rendimiento sin caída del servicio (ej. reportes lentos >3s) o bloqueo operativo
que afecta únicamente a un usuario individual.
- P3 (SLA 1440 min, horario hábil): Solicitudes cosméticas de UI o tareas
preventivas de mantenimiento en entornos no productivos (staging).
Importante (Por qué): La prioridad depende del impacto real sobre la
disponibilidad, la integridad de datos multi-tenant y el radio de afectación, nunca
de palabras emocionales o de prisa subjetiva del usuario como "urgente" u "hoy".
</domain_rules>

<examples>

    <!-- CASO 1: INCIDENTES DUPLICADOS O RECURRENTES -->

    <example>
        <input>
            El gateway de pagos devuelve HTTP 502 en todas las transacciones con tarjeta de crédito. Ningún comercio puede cobrar.

            Otra vez cayó la pasarela de cobros con tarjeta. Los clientes reciben error 502 al intentar pagar.
        </input>

        <analysis>
            1. Radio de afectación: Potencialmente global. Los reportes describen afectación de la pasarela de pagos y múltiples comercios.

            2. Impacto funcional: El procesamiento de pagos con tarjeta está indisponible. Se compromete una operación crítica del negocio.

            3. Riesgo financiero: Pérdida potencial de ingresos, transacciones fallidas y afectación comercial de múltiples organizaciones.

            4. Coincidencia entre reportes: Ambos identifican el mismo componente, el mismo código HTTP 502 y el mismo comportamiento funcional.

            5. Detección de duplicidad: Existe una relación fuerte entre ambos reportes. Sin embargo, INC-1001 fue creado a las 08:15 e INC-1006 a las 13:00. La expresión "Otra vez" sugiere recurrencia, pero no demuestra que sea una interrupción continua ni que ambos episodios tengan la misma causa raíz.

            6. Decisión de agrupación: Relacionar ambos reportes bajo un mismo problema de disponibilidad de pagos. Mantener los eventos independientes hasta verificar si hubo recuperación del servicio entre ellos.

            7. Severidad: P0 por indisponibilidad global reportada de un servicio crítico de pagos.
        </analysis>

        <output>
            severity=P0 | component=payment-gateway | duplicate_group=payment-availability | duplicate_type=recurrence | merge=false | action=escalate_24x7
        </output>
    </example>


    <!-- CASO 2: INCIDENTE INDIVIDUAL DE AUTENTICACIÓN -->

    <example>
        <input>
            He intentado ingresar a mi cuenta tres veces y ahora aparece bloqueada. Necesito acceder hoy mismo porque debo enviar un informe a la junta directiva.
        </input>

        <analysis>
            1. Radio de afectación: Una cuenta individual. No existe evidencia de afectación a otros usuarios ni de indisponibilidad global del servicio de autenticación.

            2. Impacto funcional: La usuaria no puede acceder a su cuenta y realizar una actividad empresarial.

            3. Riesgo de seguridad: No hay evidencia suficiente para determinar que existe una vulnerabilidad. El bloqueo puede corresponder a una política de autenticación.

            4. Nota léxica: La expresión "hoy mismo" representa urgencia individual, pero no justifica activar una guardia P0.

            5. Detección de duplicidad: No se identifican reportes que describan el mismo evento o una causa raíz compartida.

            6. Decisión de agrupación: Mantener como incidente independiente.

            7. Severidad: P2 por afectación individual con impacto empresarial.
        </analysis>

        <output>
            severity=P2 | component=auth-identity | duplicate_group=none | duplicate_type=none | merge=false | action=restore_account
        </output>
    </example>


    <!-- CASO 3: INCIDENTES RELACIONADOS POR RENDIMIENTO -->

    <example>
        <input>
            El dashboard de reportes históricos tarda cerca de 4.5 segundos en cargar cuando un cliente tiene más de 10,000 órdenes registradas.

            El listado de planes e historial tarda más de 3 segundos cuando se abre la pestaña de clientes corporativos con más de 10,000 registros.

            El nodo primario de PostgreSQL muestra un uso de conexiones del 94% y timeouts intermitentes en el pool de conexiones del servicio de facturación.
        </input>

        <analysis>
            1. Radio de afectación: Los problemas de rendimiento afectan funcionalidades utilizadas por clientes con grandes volúmenes de información.

            2. Impacto funcional: Los módulos siguen respondiendo, pero presentan tiempos de carga elevados. INC-1005 reporta presión sobre las conexiones de PostgreSQL.

            3. Patrón común: INC-1003 e INC-1008 presentan degradación de rendimiento bajo condiciones similares de volumen de datos.

            4. Relación técnica: INC-1005 podría representar una señal de presión sobre la infraestructura de base de datos. No existe evidencia suficiente para demostrar que sea la causa de los otros dos problemas.

            5. Detección de duplicidad: INC-1003 e INC-1008 no son duplicados exactos porque afectan módulos diferentes. INC-1005 es un incidente de infraestructura distinto.

            6. Decisión de agrupación: Relacionar los tres reportes bajo una investigación común de rendimiento y capacidad. Mantener cada incidente independiente para conservar su trazabilidad y resolución.

            7. Severidad: P2 provisional para los problemas de rendimiento. INC-1005 requiere evaluación independiente de su impacto sobre facturación y los SLA.
        </analysis>

        <output>
            severity=P2 | component=application-performance | duplicate_group=database-performance-investigation | duplicate_type=related_incidents | merge=false | action=investigate_shared_root_cause
        </output>
    </example>


    <!-- CASO 4: VULNERABILIDAD DE SEGURIDAD MULTI-TENANT -->

    <example>
        <input>
            Detectamos que al cambiar el parámetro company_id en la URL del reporte PDF se pueden visualizar facturas pertenecientes a otra organización.
        </input>

        <analysis>
            1. Radio de afectación: Potencialmente múltiples organizaciones. Se compromete el aislamiento de información entre tenants.

            2. Impacto funcional: Un usuario puede consultar facturas que pertenecen a otra organización.

            3. Riesgo de seguridad: Crítico. Existe una vulnerabilidad de autorización a nivel de objeto, conocida como IDOR o BOLA.

            4. Confidencialidad: Se encuentra comprometida porque el backend permite visualizar información financiera ajena.

            5. Alcance potencial: No se conoce el número de organizaciones ni de documentos afectados. Sin embargo, la vulnerabilidad demuestra que el aislamiento multi-tenant no funciona correctamente.

            6. Detección de duplicidad: No existe otro reporte que describa esta misma vulnerabilidad. No debe agruparse con problemas de autenticación individual.

            7. Decisión de agrupación: Mantener como incidente de seguridad independiente.

            8. Severidad: P0 por exposición de información entre organizaciones. Requiere contención inmediata, investigación forense y validación de autorizaciones en backend.
        </analysis>

        <output>
            severity=P0 | component=security-tenant-isolation | duplicate_group=none | duplicate_type=none | merge=false | action=contain_security_breach
        </output>
    </example>


    <!-- CASO 5: DEGRADACIÓN DE RENDIMIENTO SIN FALLA FUNCIONAL -->

    <example>
        <input>
            La exportación mensual a Excel se queda pensando unos 20 segundos, pero al final sí descarga el archivo completo. Hoy tenemos cierre contable.
        </input>

        <analysis>
            1. Radio de afectación: Se identifica un proceso de exportación lento. No existe evidencia de afectación global ni de múltiples organizaciones.

            2. Impacto funcional: La exportación continúa funcionando y genera el archivo completo.

            3. Integridad de datos: No se reportan pérdidas, archivos incompletos ni errores de generación.

            4. Riesgo empresarial: La demora puede afectar la productividad durante el cierre contable.

            5. Nota léxica: La expresión "hoy tenemos cierre contable" representa urgencia empresarial, pero no convierte una funcionalidad operativa en una indisponibilidad crítica.

            6. Detección de duplicidad: No existe evidencia suficiente para relacionar este proceso con los problemas del dashboard o del listado de planes.

            7. Decisión de agrupación: Mantener como incidente independiente de rendimiento.

            8. Severidad: P3 provisional. Puede elevarse a P2 si incumple el SLA o bloquea efectivamente el cierre contable.
        </analysis>

        <output>
            severity=P3 | component=reporting-export | duplicate_group=none | duplicate_type=none | merge=false | action=optimize_export_performance
        </output>
    </example>


    <!-- CASO 6: SOLICITUD COSMÉTICA SIN IMPACTO FUNCIONAL -->

    <example>
        <input>
            Sería excelente si pudieran cambiar el color del botón de exportar CSV a verde oscuro porque el gris actual casi no resalta en mi monitor secundario.
        </input>

        <analysis>
            1. Radio de afectación: Visual y cosmético. No existe evidencia de afectación funcional.

            2. Riesgo operativo: Ninguno demostrado. El botón continúa disponible y no se reportan errores de exportación.

            3. Riesgo de seguridad: No existe.

            4. Detección de duplicidad: No hay evidencia de relación con otros incidentes.

            5. Decisión de clasificación: Es una solicitud de mejora visual, no un incidente crítico de producción.

            6. Severidad: P3.
        </analysis>

        <output>
            severity=P3 | component=frontend-ui | duplicate_group=none | duplicate_type=none | merge=false | action=register_enhancement
        </output>
    </example>


    <!-- CASO 7: ALERTA PREVENTIVA DE INFRAESTRUCTURA -->

    <example>
        <input>
            El certificado TLS del entorno de staging vencerá en 14 días. Requiere rotación programada antes del próximo sprint.
        </input>

        <analysis>
            1. Radio de afectación: Limitado al entorno de staging.

            2. Impacto funcional: No existe indisponibilidad actual. El certificado todavía está vigente.

            3. Riesgo de seguridad y disponibilidad: Existe riesgo futuro si el certificado expira sin renovación.

            4. Detección de duplicidad: No hay evidencia de otros reportes que describan el mismo certificado o vencimiento.

            5. Decisión de clasificación: Es una actividad preventiva de mantenimiento, no una caída activa de producción.

            6. Severidad: P3.
        </analysis>

        <output>
            severity=P3 | component=infrastructure-tls | duplicate_group=none | duplicate_type=none | merge=false | action=schedule_certificate_rotation
        </output>
    </example>

</examples>


<incidents>

    INC-1001: URGENTE: El gateway de pagos devuelve HTTP 502 Bad Gateway en todas las transacciones con tarjeta de crédito desde hace 12 minutos. Ningún comercio puede cobrar.

    INC-1002: He intentado ingresar a mi cuenta tres veces y ahora aparece bloqueada. Necesito acceder hoy mismo porque debo enviar el informe de cierre a la junta directiva.

    INC-1003: El dashboard de reportes históricos tarda cerca de 4.5 segundos en cargar cuando un cliente tiene más de 10,000 órdenes registradas. No da error, pero la experiencia es muy lenta.

    INC-1004: Sería excelente si pudieran cambiar el color del botón de exportar CSV a verde oscuro porque el gris actual casi no resalta en mi monitor secundario.

    INC-1005: El nodo primario de PostgreSQL muestra un uso de conexiones del 94% y timeouts intermitentes en el pool de conexiones del servicio de facturación.

    INC-1006: Otra vez cayó la pasarela de cobros con tarjeta, a nuestros clientes les sale error 502 al intentar pagar el carrito de compras.

    INC-1007: Detectamos que al cambiar el parámetro company_id en la URL del reporte PDF se pueden visualizar facturas pertenecientes a otra organización.

    INC-1008: El listado de planes e historial tarda más de 3 segundos en responder cada vez que abrimos la pestaña de clientes corporativos con más de 10,000 registros.

    INC-1009: La exportación mensual a Excel se queda pensando unos 20 segundos pero al final sí descarga el archivo completo. Hoy tenemos cierre contable y nos preocupa que falle más tarde.

    INC-1010: El certificado TLS del entorno de staging vencerá en 14 días. Requiere rotación programada antes del próximo sprint.

</incidents>

<task>
tengo un software que analiza incidentes de un equipo de ingenieria del software y los clasifica segun su severidad,
Quiero refactorizar los archivos adjuntos Para que cuando se evalue cada uno de los  incidentes en `<incidents>`, 
razone y clasifique los incidentes en el formato esperados de salida agrupandolos cuando sea necesario y confirmado,
evalua y estudia los ejemplos dentro de las etiquetas <example> sigue el razonamiento dentro de la
etiqueta `<analysis>` evaluando el radio de afectación, el impacto en
seguridad/disponibilidad y las trampas léxicas, y luego emite la clasificación
final en `<output>`.
</task>
```
---

## 2. Flujo Explorar $\rightarrow$ Destilar $\rightarrow$ Ejecutar en Contexto Limpio (Reto 2: Cálculo de SLA en Horario Hábil y ADR-002)

### 2.1 Exploración de Diseño (Sin Generar Código Aún) y Destilación
- **Objetivo explorado**: Diseño del algoritmo de cálculo de SLA en horario hábil (`P2`/`P3`, Lunes–Viernes 08:00–18:00) vs. 24/7 (`P0`/`P1`) y regla de escalamiento preventivo al 75%.
- **Síntesis de tu exploración de alternativas y resumen destilado (máx. 10 líneas)**:
  > `[Describe qué dudas e hipótesis iniciales exploraste, qué casos borde descubriste junto con el modelo (creación en fin de semana, fuera de horario, cruces de varios días) y pega el bloque destilado que llevaste al nuevo chat limpio]`

  ```
  Resumen de decisiones – Cálculo de SLA IncidentOps
  1. P0/P1: conservar cálculo de tiempo calendario 24x7, sin cambios.
  2. P2/P3: contabilizar únicamente lunes a viernes, de 08:00 a 18:00, excluyendo festivos colombianos.
  3. Festivos: aplicar las reglas de la Ley 51 de 1983 (Ley Emiliani), incluyendo festivos trasladables y religiosos.
  4. Decisión: implementar un calendario colombiano calculado dinámicamente, sin librerías externas.
  5. Descartado: mantener festivos en archivos o listas anuales manuales, por riesgo de desactualización.
  6. Descartado: utilizar Pandas, NumPy o dependencias especializadas para el cálculo.
  7. Algoritmo: recorrer diariamente el intervalo y calcular la intersección con el horario laboral: O(D) en tiempo.
  8. Arquitectura: separar políticas SLA, calendario colombiano, generador de festivos y calculador de tiempo hábil.
  9. Zona horaria: utilizar America/Bogota; inicialmente solo festivos nacionales, sin festivos municipales.
  10. Validación: pruebas unitarias para fines de semana, festivos, Semana Santa, años diferentes, escalamiento al 75 % y límites de incumplimiento.
  ```

### 2.2 Ejecución con Contexto Curado en Nuevo Chat Limpio (*Context Engineering*)
Copia el prompt estructurado con etiquetas XML que utilizaste en un nuevo chat limpio para generar el **ADR (`docs/adr/002-calculo-sla-horario-habil.md`)** y la refactorización de `src/sla_calculator.py`:

```xml
<!-- Pega aquí tu prompt estructurado con <context>, <decision_summary>, <constraints>, <task> -->
<context>
Estamos optimizando el módulo de Cálculo de SLA de IncidentOps.
A continuación se incluye la definición actual de `evaluate_sla_status`
extraída vía LSP y la plantilla oficial de ADR del equipo.
<lsp_context symbol="evaluate_sla_status">
  <!-- 1. Definiciones de Tipos y Políticas (LSP Hover / Type Definition) -->
# [LSP textDocument/hover type] src\models.py:34
class SLARule:
    """Define el acuerdo de nivel de servicio (SLA) para un nivel de severidad."""

    severity: SeverityLevel
    max_resolution_minutes: int
    operates_24x7: bool
    escalation_threshold_ratio: float = 0.75

# [LSP textDocument/hover type] src\models.py:44
class Incident:
    """Representa un incidente registrado en la plataforma IncidentOps."""

    incident_id: str
    title: str
    component: str
    severity: SeverityLevel
    status: IncidentStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None

# [LSP textDocument/hover type] src\models.py:57
class SLAEvaluation:
    """Resultado determinista de la evaluación de SLA de un incidente."""

    incident_id: str
    severity: SeverityLevel
    elapsed_minutes: int
    allowed_minutes: int
    remaining_minutes: int
    is_breached: bool
    requires_escalation: bool

# [LSP textDocument/hover type] src\models.py:79
class TriageResult:
    """Resultado estructurado producido por el clasificador de triaje.

    Los campos nuevos tienen valores por defecto para mantener compatibilidad con
    los consumidores existentes que solo usan severity/component/rationale.
    """

    incident_id: str
    severity: SeverityLevel
    component: str
    rationale: str
    consistency_ratio: float = 1.0
    recommended_team: Optional[TeamName] = None
    duplicate_group_key: Optional[str] = None
    duplicate_type: DuplicateType = "none"
    merge: bool = False
    action: TriageAction = "manual_review"
    analysis: Tuple[str, ...] = ()

    def to_output_line(self) -> str:
        """Serializa en el formato `<output>` acordado."""
        return (
            f"severity={self.severity} | component={self.component} | "
            f"duplicate_group={self.duplicate_group_key or 'none'} | "
            f"duplicate_type={self.duplicate_type} | "
            f"merge={'true' if self.merge else 'false'} | action={self.action}"
        )

# [LSP textDocument/hover symbol] src\sla_calculator.py:17
SLA_POLICY_TABLE: Dict[SeverityLevel, SLARule] = {
    "P0": SLARule(severity="P0", max_resolution_minutes=60, operates_24x7=True),
    "P1": SLARule(severity="P1", max_resolution_minutes=240, operates_24x7=True),
    "P2": SLARule(severity="P2", max_resolution_minutes=480, operates_24x7=False),
    "P3": SLARule(severity="P3", max_resolution_minutes=1440, operates_24x7=False),
}

  <!-- 2. Definición Exacta del Símbolo (LSP GoToDefinition) -->
# [LSP textDocument/definition] src\sla_calculator.py:25
def get_sla_rule_for_severity(severity: SeverityLevel) -> SLARule:
    """Obtiene la regla de SLA aplicable a una severidad validada contra la tabla."""
    if severity not in SLA_POLICY_TABLE:
        raise ValueError(f"Severidad no válida: {severity}")
    return SLA_POLICY_TABLE[severity]

# [LSP textDocument/definition] src\sla_calculator.py:32
def evaluate_sla_status(incident: Incident, reference_time: datetime) -> SLAEvaluation:
    """Evalúa si un incidente ha incumplido su SLA o requiere escalamiento preventivo.

    Args:
        incident: Entidad del incidente a evaluar.
        reference_time: Marca de tiempo actual o de cierre contra la cual medir.

    Returns:
        SLAEvaluation con los minutos transcurridos, restantes y banderas de estado.
    """
    rule = get_sla_rule_for_severity(incident.severity)
    end_time = incident.resolved_at or reference_time

    if end_time < incident.created_at:
        raise ValueError("El tiempo de referencia no puede ser anterior a la creación.")

    # TODO(week-1-taller): Cuando rule.operates_24x7 es False (P2 y P3), solo deben
    # contabilizarse los minutos dentro del horario hábil (Lunes-Viernes 08:00-18:00).
    delta_seconds = (end_time - incident.created_at).total_seconds()
    elapsed_minutes = int(delta_seconds // 60)

    remaining_minutes = rule.max_resolution_minutes - elapsed_minutes
    is_breached = elapsed_minutes > rule.max_resolution_minutes

    escalation_limit = int(rule.max_resolution_minutes * rule.escalation_threshold_ratio)
    requires_escalation = (
        incident.status != "RESOLVED"
        and not is_breached
        and elapsed_minutes >= escalation_limit
    )

    return SLAEvaluation(
        incident_id=incident.incident_id,
        severity=incident.severity,
        elapsed_minutes=elapsed_minutes,
        allowed_minutes=rule.max_resolution_minutes,
        remaining_minutes=remaining_minutes,
        is_breached=is_breached,
        requires_escalation=requires_escalation,
    )

  <!-- 3. Referencias de Invocación en el Proyecto (LSP FindReferences) -->
# [LSP textDocument/references] src\incident_repository.py:145
  L144:             )
  L145:             sla_eval = evaluate_sla_status(incident, reference_time=reference_time)
  L146:             results.append(

# [LSP textDocument/references] src\sla_calculator.py:87
  L86:     monday_morning = datetime(2026, 11, 9, 9, 0, 0)
  L87:     evaluation = evaluate_sla_status(sample_incident, reference_time=monday_morning)
  L88:
</lsp_context>
# ADR-000: [Título Corto de la Decisión Arquitectónica]

- **Estado**: Propuesto | Aceptado | Reemplazado
- **Fecha**: YYYY-MM-DD
- **Autor(es)**: [Nombre del Ingeniero / Equipo]
- **Componentes Afectados**: [`src/...`]

---

## 1. Contexto y Problema

Describe el problema técnico o de negocio actual, las limitaciones del código existente (por ejemplo, latencia, consultas N+1, errores de cálculo de SLA o limitaciones de escalabilidad) y las restricciones del sistema (p. ej., mantener cero dependencias externas, seguridad contra inyección SQL, determinismo).

---

## 2. Opciones Consideradas

1. **Opción A — [Nombre de la opción]**:
   - *Ventajas*: ...
   - *Desventajas*: ...
2. **Opción B — [Nombre de la opción]**:
   - *Ventajas*: ...
   - *Desventajas*: ...
3. **Opción C — [Nombre de la opción]**:
   - *Ventajas*: ...
   - *Desventajas*: ...

---

## 3. Decisión Arquitectónica

Explica claramente cuál opción fue elegida y **por qué**. Incluye un diagrama **Mermaid** (`flowchart TD`, `flowchart LR`, `sequenceDiagram` o `stateDiagram-v2`) que ilustre el diseño aprobado.

    ```mermaid
    flowchart LR
        A["Solicitud / Evento"] --> B["Componente Refactorizado"]
        B --> C["Resultado Validado"]
    ```

---

## 4. Consecuencias e Impacto

- **Positivas**: Mejoras en rendimiento, mantenibilidad, precisión o consumo de recursos.
- **Negativas / Trade-offs**: Complejidad adicional asumida o límites conocidos de la solución.
- **Verificación**: Cómo se comprobará empíricamente que la implementación cumple esta decisión.
</context>

<decision_summary>
P0/P1: conservar cálculo de tiempo calendario 24x7, sin cambios.
P2/P3: contabilizar únicamente lunes a viernes, de 08:00 a 18:00, excluyendo festivos colombianos.
Festivos: aplicar las reglas de la Ley 51 de 1983 (Ley Emiliani), incluyendo festivos trasladables y religiosos.
Decisión: implementar un calendario colombiano calculado dinámicamente, sin librerías externas.
Descartado: mantener festivos en archivos o listas anuales manuales, por riesgo de desactualización.
Descartado: utilizar Pandas, NumPy o dependencias especializadas para el cálculo.
Algoritmo: recorrer diariamente el intervalo y calcular la intersección con el horario laboral: O(D) en tiempo.
Arquitectura: separar políticas SLA, calendario colombiano, generador de festivos y calculador de tiempo hábil.
Zona horaria: utilizar America/Bogota; inicialmente solo festivos nacionales, sin festivos municipales.
Validación: pruebas unitarias para fines de semana, festivos, Semana Santa, años diferentes, escalamiento al 75 % y límites de incumplimiento.
</decision_summary>

<constraints>
- No introduzcas dependencias externas adicionales.
- Escribe el código coincidiendo con la densidad de comentarios e modismos del código circundante.
</constraints>

<task>
Redacta el documento `docs/adr/002-calculo-sla-horario-habil.md` siguiendo
las secciones de la plantilla e incluye un diagrama Mermaid ( flowchart
 TD o stateDiagram-v2 ) que explique el cálculo y la transición a escalamiento.
</task>
```
---

## 3. Tipos de Modelos y Matriz de Decisión Arquitectónica

### 3.1 Comparación de Tipos de Modelos
Compara el comportamiento que observaste al interactuar con:
1. **Modelo Rápido / Estándar (ej. Flash, Mini, Haiku o modo estándar)**:
2. **Modelo de Razonamiento Extendido (*Thinking Model*)**:
- ¿En cuál de las tareas de la semana fue indispensable el modelo de razonamiento y en cuál bastó el modelo rápido?
  
  **Respuesta:** en todas las tareas se utilizo Modelo de Razonamiento Extendido para tener ya que estas eran las daban mejores justificaciones.

### 3.2 Matriz de Decisión Arquitectónica
Para la plataforma *IncidentOps* y su evolución futura, justifica qué paradigma es el adecuado en cada escenario:

| Escenario / Requerimiento | Paradigma Elegido (Código Determinista / ML Clásico / Asistente GenAI en Chat / LLM en Tiempo de Ejecución) | Justificación Técnica (Determinismo, Costo, Latencia, Riesgo de Alucinación) |
| :--- | :--- | :--- |
| 1. Contabilizar minutos hábiles transcurridos y verificar si un ticket superó el 75% de su SLA | Código determinista | Es una operación aplicando una formula relativamente sencilla de calcular no se necesita tecnicas muy sofisticadas para hacerla|
| 2. Explorar casos borde y redactar un ADR antes de modificar la arquitectura de consultas SQL | Asistente GenAI en Chat | Fue practicamente lo que hicimos en este taller y funciona bien |
| 3. Detectar anomalías numéricas en millones de métricas de CPU/RAM por minuto | ML clásico | Son datos numéricos y estructurados que llegan por millones, la latencia y el costo por inferencia tienen que ser mínimos.|
| 4. Clasificar reportes de incidentes redactados en lenguaje natural abierto cuando las reglas deterministas no cubren nuevos patrones | LLM en tiempo de ejecución | Entender e interpretar lenguaje natural es uno de los fuertes actuales de los LLM por lo que nuestro código determinista enfrentaría un límite que no puede superar. |

---

## 4. Economía de Tokens y Curaduría de Contexto con `tiktoken` (LSP vs. `grep`/`read` vs. `glob`/`read`)

### 4.1 Medición Empírica en *IncidentOps*
Completa la tabla con los resultados obtenidos al auditar los símbolos con `uv run python -m src.context_audit --symbol evaluate_sla_status` (y `classify_incident_report`):

| Estrategia de Recolección de Contexto `classify_incident_report`| Alcance (Archivos / Nodos) | Caracteres Totales | Tokens (`tiktoken o200k_base`) | % de Reducción vs. Fuerza Bruta |
| :--- | :--- | :---: | :---: | :---: |
| **1. Fuerza Bruta (`glob` + `read` todo)** | 12 archivos        | 82828      | 20325 tokens| 96.1% (Línea base) |
| **2. Búsqueda Textual (`grep` + `read` `.py`)** | 2 archivos .py     | 28475      | 6836 tokens|88.4% menos tokens |
| **3. Semántica vía LSP (`definition` + `references` + `hover`)** | Definición+Refs    | 3026       | 791 tokens| |

| Estrategia de Recolección de Contexto `evaluate_sla_status` | Alcance (Archivos / Nodos) | Caracteres Totales | Tokens (`tiktoken o200k_base`) | % de Reducción vs. Fuerza Bruta |
| :--- | :--- | :---: | :---: | :---: |
| **1. Fuerza Bruta (`glob` + `read` todo)** | 12 archivos        | 82828      | 20325 tokens | 93.4% menos tokens |
| **2. Búsqueda Textual (`grep` + `read` `.py`)** | 4 archivos .py     | 29127      | 7073 tokens| 81.1% menos tokens|
| **3. Semántica vía LSP (`definition` + `references` + `hover`)** | Definición+Refs    | 5388       | 1334 tokens| |

### 4.2 Comparación de Formatos de Serialización (`--compare-formats`)
Registra los tokens medidos con `tiktoken` para los 10 incidentes en JSON indentado, JSON compacto, YAML y CSV, y explica qué formato elegirías al inyectar datos tabulares o logs largos en la ventana de contexto.

|Formato de Serialización       | Caracteres   | Tokens|
|----|-----|-------|
|JSON Indentado (indent=2)      | 2942         | 878 tokens|
|JSON Compacto (minified)       | 2641         | 728 tokens|
|YAML Equivalente               | 2579         | 755 tokens|
|CSV Delimitado por '\|'         | 2171         | 617 tokens|

**Respuesta** Datos tabulares delimitados por '|' representan la mejor opción, ya que es la opción que implica menos caracteres y por lo tanto menos tokens que es el sistema de medida de cobro del uso en los LLM's.