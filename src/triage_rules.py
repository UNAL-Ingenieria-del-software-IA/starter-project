"""Motor determinista de clasificación, enrutamiento y correlación de incidentes (IncidentOps).

Arquitectura (pipeline en 4 etapas, cada una pura y testeable por separado):

    texto crudo ──► 1. extract_signals()    Señales de IMPACTO (no palabras sueltas)
                ──► 2. decide_severity()     Reglas de dominio ordenadas por impacto
                ──► 3. route_component()     Componente normalizado + equipo de guardia
                ──► 4. correlate_batch()     Duplicados / recurrencias / incidentes relacionados

Principio rector (domain_rules): la severidad depende del radio de afectación, de la
disponibilidad y de la integridad multi-tenant, NUNCA de urgencia subjetiva ("urgente",
"hoy"). Esas expresiones se detectan como *trampas léxicas*, se documentan en el análisis
y no participan en la decisión.

Cada resultado incluye un `analysis` paso a paso (radio, impacto, riesgo, nota léxica,
duplicidad, decisión, severidad) y se serializa con `TriageResult.to_output_line()`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from src.models import (
    DuplicateType,
    IncidentReport,
    SeverityLevel,
    TeamName,
    TriageAction,
    TriageResult,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample_incidents.json"

# ---------------------------------------------------------------------------
# Umbrales de dominio (centralizados para no dispersar "números mágicos")
# ---------------------------------------------------------------------------
SATURATION_THRESHOLD_PCT = 90.0         # P1: infraestructura compartida > 90 %
INTERACTIVE_LATENCY_THRESHOLD_S = 3.0   # P2: respuesta interactiva > 3 s
HIGH_VOLUME_THRESHOLD = 10_000          # Firma de correlación por volumen de datos
DUPLICATE_MERGE_WINDOW = timedelta(minutes=30)  # Ventana para confirmar mismo evento


# ---------------------------------------------------------------------------
# Utilidades de normalización
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados (robusto ante 'cayó' vs 'cayo')."""
    decomposed = unicodedata.normalize("NFKD", text)
    no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", no_accents.lower()).strip()


def _matches(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "."))


# ---------------------------------------------------------------------------
# Etapa 1: extracción de señales de impacto
# ---------------------------------------------------------------------------
_P_CROSS_TENANT_TARGET = r"\b(otras?|otros?) (organizacion|empresa|compania|tenant|cliente)"
_P_DATA_ACCESS = r"visualiz|\bver\b|acced|consult|descarg|expon|filtr"
_P_OUTAGE = r"\bcay[oe]\b|\bcaid[ao]\b|indisponib|fuera de servicio|bad gateway|no (puede|pueden|podemos) (cobrar|pagar|operar)"
_P_GLOBAL = r"\btodas las\b|\btodos los\b|\bningun[oa]?\b|\bnuestros clientes\b|\bmultiples (comercios|clientes|organizaciones)\b"
_P_CRITICAL_SERVICE = r"\bpago|\bpagar\b|\bcobr|tarjeta|pasarela|checkout|carrito"
_P_SATURATION = r"(\d{1,3}(?:[.,]\d+)?)\s*%"
_P_SHARED_INFRA = r"conexion|\bpool\b|\bnodo\b|cluster|\bcpu\b|memoria|\bdisco\b"
_P_TIMEOUT = r"timeout|time-out|tiempo de espera agotado"
_P_LATENCY = r"(mas de |cerca de |unos |aprox\.? )?(\d+(?:[.,]\d+)?)\s*seg"
_P_PERFORMANCE = r"\blent[oa]\b|\btarda\b|\bdemora\b|se queda pensando|latencia"
_P_COMPLETES = r"no da error|si descarga|al final si|termina correctamente|se completa"
_P_BATCH = r"exportaci|\bbatch\b|\bjob\b|\blote\b"
_P_INDIVIDUAL = r"\bmi (cuenta|usuario|perfil|acceso)\b"
_P_ACCESS_BLOCKED = r"bloquead|no (puedo|logro) (ingresar|acceder|entrar)"
_P_NON_PROD = r"\bstaging\b|\bqa\b|sandbox|entorno de pruebas"
_P_COSMETIC = r"\bcolor\b|\bboton\b|resalta|tipografia|\bicono\b|seria excelente|estetic"
_P_PREVENTIVE = r"vencera|expira en|rotacion programada|en \d+ dias|mantenimiento (preventivo|programado)"
_P_RECURRENCE = r"otra vez|de nuevo|nuevamente|volvio a|se repite|una vez mas"
_P_HIGH_VOLUME = r"(\d{1,3}(?:[.,]\d{3})+|\d{5,})\s+(registros|ordenes|filas|transacciones)"
_P_ERROR_CODE = r"\b(5\d\d)\b"

# Expresiones de urgencia subjetiva: se registran, nunca deciden la severidad.
_LEXICAL_TRAPS: Tuple[Tuple[str, str], ...] = (
    (r"\burgente\b", "urgente"),
    (r"\bhoy mismo\b", "hoy mismo"),
    (r"\bhoy\b(?! mismo)", "hoy"),
    (r"\bya mismo\b", "ya mismo"),
    (r"\basap\b", "ASAP"),
    (r"\bnos preocupa\b", "nos preocupa"),
)


@dataclass(frozen=True)
class IncidentSignals:
    """Señales de impacto extraídas del texto. Son la única entrada de las reglas."""

    cross_tenant_exposure: bool
    service_outage: bool
    global_scope: bool
    critical_service: bool
    saturation_pct: Optional[float]
    shared_infra_timeouts: bool
    latency_seconds: Optional[float]
    latency_exceeds_threshold: bool
    performance_complaint: bool
    completes_successfully: bool
    batch_operation: bool
    individual_scope: bool
    access_blocked: bool
    non_production: bool
    cosmetic_request: bool
    preventive_maintenance: bool
    recurrence_marker: bool
    high_data_volume: bool
    error_codes: Tuple[str, ...]
    lexical_traps: Tuple[str, ...]

    @property
    def infra_saturated(self) -> bool:
        return (self.saturation_pct is not None and self.saturation_pct >= SATURATION_THRESHOLD_PCT) or (
            self.shared_infra_timeouts and self.saturation_pct is None
        )


def extract_signals(raw_text: str) -> IncidentSignals:
    t = _normalize(raw_text)

    shared_infra = _matches(_P_SHARED_INFRA, t)
    saturation_pct: Optional[float] = None
    if shared_infra:
        pcts = [_to_float(m) for m in re.findall(_P_SATURATION, t)]
        saturation_pct = max(pcts) if pcts else None

    latency_seconds: Optional[float] = None
    latency_exceeds = False
    latency_match = re.search(_P_LATENCY, t)
    if latency_match:
        qualifier, value = latency_match.group(1) or "", _to_float(latency_match.group(2))
        latency_seconds = value
        latency_exceeds = value > INTERACTIVE_LATENCY_THRESHOLD_S or (
            qualifier.startswith("mas de") and value >= INTERACTIVE_LATENCY_THRESHOLD_S
        )

    high_volume = any(
        int(re.sub(r"[.,]", "", qty)) >= HIGH_VOLUME_THRESHOLD for qty, _ in re.findall(_P_HIGH_VOLUME, t)
    )
    error_codes = tuple(sorted(set(re.findall(_P_ERROR_CODE, t))))

    return IncidentSignals(
        cross_tenant_exposure=_matches(_P_CROSS_TENANT_TARGET, t) and _matches(_P_DATA_ACCESS, t),
        service_outage=bool(error_codes) or _matches(_P_OUTAGE, t),
        global_scope=_matches(_P_GLOBAL, t),
        critical_service=_matches(_P_CRITICAL_SERVICE, t),
        saturation_pct=saturation_pct,
        shared_infra_timeouts=shared_infra and _matches(_P_TIMEOUT, t),
        latency_seconds=latency_seconds,
        latency_exceeds_threshold=latency_exceeds,
        performance_complaint=_matches(_P_PERFORMANCE, t) or latency_seconds is not None,
        completes_successfully=_matches(_P_COMPLETES, t),
        batch_operation=_matches(_P_BATCH, t),
        individual_scope=_matches(_P_INDIVIDUAL, t),
        access_blocked=_matches(_P_ACCESS_BLOCKED, t),
        non_production=_matches(_P_NON_PROD, t),
        cosmetic_request=_matches(_P_COSMETIC, t),
        preventive_maintenance=_matches(_P_PREVENTIVE, t),
        recurrence_marker=_matches(_P_RECURRENCE, t),
        high_data_volume=high_volume,
        error_codes=error_codes,
        lexical_traps=tuple(label for pattern, label in _LEXICAL_TRAPS if _matches(pattern, t)),
    )


# ---------------------------------------------------------------------------
# Etapa 2: decisión de severidad (reglas ordenadas de mayor a menor impacto)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SeverityDecision:
    severity: SeverityLevel
    reason: str
    provisional: bool = False


def decide_severity(s: IncidentSignals) -> SeverityDecision:
    # P0: integridad multi-tenant comprometida (confidencialidad > disponibilidad).
    if s.cross_tenant_exposure:
        return SeverityDecision("P0", "exposición de información entre organizaciones (aislamiento multi-tenant roto).")

    # P0: indisponibilidad global de un servicio crítico.
    if s.service_outage and s.global_scope and s.critical_service:
        return SeverityDecision("P0", "indisponibilidad global reportada de un servicio crítico.")

    # P1: saturación de infraestructura compartida con riesgo inminente de caída.
    if s.infra_saturated and not s.non_production:
        pct = f" ({s.saturation_pct:g} %)" if s.saturation_pct is not None else ""
        return SeverityDecision("P1", f"degradación severa de infraestructura compartida{pct} con riesgo inminente de caída.")

    # P1: caída global de un servicio no crítico.
    if s.service_outage and s.global_scope:
        return SeverityDecision("P1", "indisponibilidad global de un servicio no catalogado como crítico.")

    # P2: bloqueo operativo de un único usuario.
    if s.access_blocked and s.individual_scope:
        return SeverityDecision("P2", "bloqueo operativo que afecta únicamente a un usuario individual.")

    if s.performance_complaint:
        # Proceso batch que termina correctamente: degradación sin falla funcional (ver CASO 5).
        if s.batch_operation and s.completes_successfully:
            return SeverityDecision(
                "P3",
                "proceso batch lento que completa correctamente; puede elevarse a P2 si incumple el SLA "
                "o bloquea efectivamente la operación.",
                provisional=True,
            )
        if s.latency_exceeds_threshold:
            return SeverityDecision(
                "P2",
                f"degradación moderada de rendimiento (> {INTERACTIVE_LATENCY_THRESHOLD_S:g} s) sin caída del servicio.",
                provisional=True,
            )
        return SeverityDecision("P3", "percepción de lentitud sin métrica que supere el umbral.", provisional=True)

    if s.service_outage:
        return SeverityDecision("P2", "falla reportada sin evidencia de alcance global; requiere confirmación.", provisional=True)

    if s.preventive_maintenance or s.non_production:
        return SeverityDecision("P3", "tarea preventiva / entorno no productivo sin indisponibilidad actual.")

    if s.cosmetic_request:
        return SeverityDecision("P3", "solicitud de mejora visual sin impacto funcional.")

    return SeverityDecision("P3", "sin señales de impacto suficientes; requiere revisión manual.", provisional=True)


# ---------------------------------------------------------------------------
# Etapa 3: componente normalizado, equipo de guardia y acción
# ---------------------------------------------------------------------------
# (patrón, componente, equipo). El orden importa: lo más específico/crítico primero.
_COMPONENT_ROUTES: Tuple[Tuple[str, str, TeamName], ...] = (
    (r"pasarela|gateway de pagos|\bpago|\bcobr|tarjeta", "payment-gateway", "Backend-Core"),
    (r"postgres|mysql|base de datos|pool de conexiones|nodo primario|replica", "database-cluster", "Data-DBA"),
    (r"\bcuenta\b|ingresar|\blogin\b|contrasena|autentic|\bmfa\b", "auth-identity", "Security-IAM"),
    (r"certificado|\btls\b|\bssl\b", "infrastructure-tls", "Platform-SRE"),
)


def route_component(raw_text: str, s: IncidentSignals) -> Tuple[str, TeamName]:
    t = _normalize(raw_text)
    if s.cross_tenant_exposure:
        return "security-tenant-isolation", "Security-IAM"
    for pattern, component, team in _COMPONENT_ROUTES:
        if _matches(pattern, t):
            return component, team
    if s.cosmetic_request:
        return "frontend-ui", "Backend-Core"
    if s.batch_operation and s.performance_complaint:
        return "reporting-export", "Backend-Core"
    if s.performance_complaint:
        return "application-performance", "Backend-Core"
    return "unclassified", "Backend-Core"


def decide_action(severity: SeverityLevel, component: str, s: IncidentSignals) -> TriageAction:
    if component == "security-tenant-isolation":
        return "contain_security_breach"
    if severity == "P0":
        return "escalate_24x7"
    if severity == "P1":
        return "mitigate_capacity_risk"
    by_component: Dict[str, TriageAction] = {
        "reporting-export": "optimize_export_performance",
        "application-performance": "optimize_query_performance",
        "frontend-ui": "register_enhancement",
        "infrastructure-tls": "schedule_certificate_rotation",
    }
    if component == "auth-identity" and s.access_blocked:
        return "restore_account"
    return by_component.get(component, "manual_review")


# ---------------------------------------------------------------------------
# Construcción del análisis (Chain-of-Thought determinista y auditable)
# ---------------------------------------------------------------------------
def _blast_radius(s: IncidentSignals) -> str:
    if s.cross_tenant_exposure:
        return "Potencialmente múltiples organizaciones; se compromete el aislamiento entre tenants."
    if s.service_outage and s.global_scope:
        return "Potencialmente global: el reporte describe afectación de múltiples clientes/comercios."
    if s.infra_saturated:
        return "Infraestructura compartida: cualquier servicio dependiente puede verse afectado."
    if s.individual_scope:
        return "Una cuenta individual; sin evidencia de afectación a otros usuarios."
    if s.non_production:
        return "Limitado a un entorno no productivo."
    if s.cosmetic_request:
        return "Visual y cosmético; sin evidencia de afectación funcional."
    if s.performance_complaint:
        return "Funcionalidad específica con degradación; sin evidencia de afectación global."
    return "Indeterminado con la información disponible."


def _functional_impact(s: IncidentSignals) -> str:
    if s.cross_tenant_exposure:
        return "Un usuario puede consultar información que pertenece a otra organización."
    if s.service_outage:
        codes = f" (HTTP {', '.join(s.error_codes)})" if s.error_codes else ""
        return f"Servicio reportado como indisponible{codes}."
    if s.infra_saturated:
        return "El servicio responde, pero con timeouts/saturación que anticipan una caída."
    if s.access_blocked:
        return "El usuario no puede acceder a su cuenta ni completar su actividad."
    if s.performance_complaint:
        lat = f" (~{s.latency_seconds:g} s)" if s.latency_seconds is not None else ""
        done = " y el proceso completa correctamente" if s.completes_successfully else ""
        return f"La funcionalidad sigue operando con tiempos elevados{lat}{done}."
    if s.preventive_maintenance:
        return "No existe indisponibilidad actual; riesgo futuro si no se actúa a tiempo."
    if s.cosmetic_request:
        return "Ninguno: la funcionalidad sigue disponible."
    return "No determinado."


def _security_availability_risk(s: IncidentSignals) -> str:
    if s.cross_tenant_exposure:
        return "Crítico: vulnerabilidad de autorización a nivel de objeto (IDOR/BOLA); confidencialidad comprometida."
    if s.service_outage and s.critical_service:
        return "Alto: operación crítica de negocio detenida; pérdida potencial de ingresos."
    if s.infra_saturated:
        return "Alto para disponibilidad: riesgo inminente de caída en cascada."
    if s.access_blocked:
        return "Sin evidencia de vulnerabilidad; el bloqueo puede responder a la política de autenticación."
    if s.preventive_maintenance:
        return "Bajo y futuro: expiración si no se renueva a tiempo."
    return "Sin riesgo de seguridad ni de disponibilidad demostrado."


def _lexical_note(s: IncidentSignals) -> Optional[str]:
    if not s.lexical_traps:
        return None
    terms = ", ".join(f'"{x}"' for x in s.lexical_traps)
    verb, alter = ("expresan", "alteran") if len(s.lexical_traps) > 1 else ("expresa", "altera")
    return f"Nota léxica: {terms} {verb} urgencia subjetiva; no {alter} la severidad, que se decide por impacto."


# ---------------------------------------------------------------------------
# Etapa 4: correlación de lote (duplicados, recurrencias, relacionados)
# ---------------------------------------------------------------------------
@dataclass
class _Draft:
    """Estado intermedio mutable de un incidente durante el pipeline."""

    report: IncidentReport
    signals: IncidentSignals
    decision: SeverityDecision
    component: str
    team: TeamName
    action: TriageAction
    group_key: Optional[str] = None
    duplicate_type: DuplicateType = "none"
    merge: bool = False
    correlation_notes: List[str] = field(default_factory=list)


def _classify_single(report: IncidentReport) -> _Draft:
    signals = extract_signals(report.raw_text)
    decision = decide_severity(signals)
    component, team = route_component(report.raw_text, signals)
    action = decide_action(decision.severity, component, signals)
    return _Draft(report, signals, decision, component, team, action)


def _correlate_availability(drafts: Sequence[_Draft]) -> None:
    """Agrupa caídas del mismo componente y decide duplicado exacto vs. recurrencia."""
    by_component: Dict[str, List[_Draft]] = {}
    for d in drafts:
        if d.signals.service_outage and d.component != "unclassified":
            by_component.setdefault(d.component, []).append(d)

    for component, members in by_component.items():
        if len(members) < 2:
            continue
        ids = ", ".join(m.report.incident_id for m in members)
        group_key = f"{component.split('-')[0]}-availability"
        timestamps = [m.report.created_at for m in members]
        has_marker = any(m.signals.recurrence_marker for m in members)

        if all(timestamps):
            ordered = sorted(members, key=lambda m: m.report.created_at)  # type: ignore[arg-type, return-value]
            span = ordered[-1].report.created_at - ordered[0].report.created_at  # type: ignore[operator]
            within_window = span <= DUPLICATE_MERGE_WINDOW
        else:
            ordered, span, within_window = list(members), None, False

        if within_window and not has_marker:
            dup_type: DuplicateType = "exact_duplicate"
            note = (
                f"Mismo componente y síntoma en {ids} dentro de la ventana de "
                f"{int(DUPLICATE_MERGE_WINDOW.total_seconds() // 60)} min: mismo evento confirmado."
            )
            decision = "Fusionar en el incidente más antiguo para evitar trabajo duplicado de la guardia."
        elif has_marker or (span is not None and span > DUPLICATE_MERGE_WINDOW):
            dup_type = "recurrence"
            gap = f" separados por {int(span.total_seconds() // 60)} min" if span is not None else ""
            marker = ' y el texto indica reaparición ("otra vez")' if has_marker else ""
            note = (
                f"{ids} comparten componente y síntoma{gap}{marker}. Sugiere recurrencia, pero no demuestra "
                "interrupción continua ni causa raíz única."
            )
            decision = "Relacionar bajo un mismo problema; mantener eventos independientes hasta verificar recuperación entre ellos."
        else:
            dup_type = "related_incidents"
            note = f"{ids} comparten componente y síntoma, pero sin marcas de tiempo no se puede confirmar si es el mismo evento."
            decision = "Relacionar sin fusionar hasta confirmar la línea de tiempo."

        for m in ordered:
            m.group_key, m.duplicate_type = group_key, dup_type
            m.merge = dup_type == "exact_duplicate" and m is not ordered[0]
            m.correlation_notes = [note, f"Decisión de agrupación: {decision}"]


def _correlate_performance(drafts: Sequence[_Draft]) -> None:
    """Relaciona degradaciones con la misma firma de volumen y señales de presión en BD."""
    perf = [
        d for d in drafts
        if d.component == "application-performance" and d.signals.high_data_volume and d.group_key is None
    ]
    if len(perf) < 2:
        return
    db_pressure = [d for d in drafts if d.component == "database-cluster" and d.signals.infra_saturated]
    members = perf + db_pressure
    ids = ", ".join(m.report.incident_id for m in members)
    perf_ids = " y ".join(p.report.incident_id for p in perf)

    for m in members:
        m.group_key, m.duplicate_type, m.merge = "database-performance-investigation", "related_incidents", False
        if m in perf:
            m.action = "investigate_shared_root_cause"
            note = (
                f"{perf_ids} degradan bajo la misma firma (> {HIGH_VOLUME_THRESHOLD:,} registros) en módulos "
                "diferentes: no son duplicados exactos."
            )
        else:
            note = (
                "Señal de presión sobre la BD que podría explicar la degradación de rendimiento, sin evidencia "
                "suficiente de causalidad; conserva su severidad y evaluación independiente."
            )
        m.correlation_notes = [
            note,
            f"Decisión de agrupación: investigar {ids} en conjunto (rendimiento y capacidad); "
            "mantener cada incidente independiente para conservar trazabilidad.",
        ]


def _build_result(d: _Draft) -> TriageResult:
    s = d.signals
    steps: List[str] = [
        f"Radio de afectación: {_blast_radius(s)}",
        f"Impacto funcional: {_functional_impact(s)}",
        f"Riesgo de seguridad/disponibilidad: {_security_availability_risk(s)}",
    ]
    lexical = _lexical_note(s)
    if lexical:
        steps.append(lexical)
    if d.correlation_notes:
        steps.append(f"Detección de duplicidad: {d.correlation_notes[0]}")
        steps.extend(d.correlation_notes[1:])
    else:
        steps.append("Detección de duplicidad: no hay reportes que describan el mismo evento ni una causa raíz compartida.")
        steps.append("Decisión de agrupación: mantener como incidente independiente.")
    provisional = " provisional" if d.decision.provisional else ""
    steps.append(f"Severidad: {d.decision.severity}{provisional} por {d.decision.reason}")
    steps.append(f"Enrutamiento: {d.component} → guardia {d.team}.")

    numbered = tuple(f"{i}. {step}" for i, step in enumerate(steps, start=1))
    return TriageResult(
        incident_id=d.report.incident_id,
        severity=d.decision.severity,
        component=d.component,
        rationale=f"{d.decision.severity}{provisional}: {d.decision.reason}",
        recommended_team=d.team,
        duplicate_group_key=d.group_key,
        duplicate_type=d.duplicate_type,
        merge=d.merge,
        action=d.action,
        analysis=numbered,
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def classify_incident_batch(reports: Sequence[IncidentReport]) -> List[TriageResult]:
    """Clasifica un lote completo y correlaciona duplicados/recurrencias entre reportes."""
    drafts = [_classify_single(r) for r in reports]
    _correlate_availability(drafts)
    _correlate_performance(drafts)
    return [_build_result(d) for d in drafts]


def classify_incident_report(incident_id: str, raw_text: str) -> TriageResult:
    """Compatibilidad hacia atrás: clasifica un único reporte (sin correlación de lote)."""
    return classify_incident_batch([IncidentReport(incident_id, raw_text)])[0]


def load_reports(path: Path = SAMPLE_DATA_PATH) -> List[IncidentReport]:
    items = json.loads(path.read_text(encoding="utf-8"))
    return [
        IncidentReport(
            incident_id=item["id"],
            raw_text=item["raw_text"],
            created_at=datetime.fromisoformat(item["created_at"]) if item.get("created_at") else None,
        )
        for item in items
    ]


def _run_triage_audit() -> None:
    """Ejecuta el motor sobre los incidentes de prueba e imprime análisis + salida."""
    results = classify_incident_batch(load_reports())

    print("=== Auditoría del Motor de Triaje (`src/triage_rules.py`) ===\n")
    print(f"{'ID':<9} | {'Sev':<3} | {'Componente':<26} | {'Equipo':<12} | {'Grupo':<34} | Acción")
    print("-" * 125)
    for r in results:
        print(
            f"{r.incident_id:<9} | {r.severity:<3} | {r.component:<26} | {r.recommended_team or '-':<12} | "
            f"{(r.duplicate_group_key or 'none'):<34} | {r.action}"
        )
    print("-" * 125)
    for r in results:
        print(f"\n<incident id=\"{r.incident_id}\">\n  <analysis>")
        for step in r.analysis:
            print(f"    {step}")
        print(f"  </analysis>\n  <output>\n    {r.to_output_line()}\n  </output>\n</incident>")


if __name__ == "__main__":
    _run_triage_audit()