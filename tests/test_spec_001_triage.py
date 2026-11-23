"""Pruebas de aceptación BDD de la spec 001 (§9.1): triaje por HTTP y CLI.

Cada prueba sigue Given / When / Then. Los valores esperados (severidad, componente,
equipo, acción, clave de grupo) son los que fija el dominio; la prueba los observa, no los
redefine (Constitución Art. 1.1).
"""

from __future__ import annotations

import json

import pytest

import src.application.services as services_module

CAIDA_PASARELA = (
    "URGENTE: el gateway de pagos devuelve HTTP 502 y múltiples comercios no pueden cobrar con tarjeta"
)
CUENTA_BLOQUEADA = (
    "Mi cuenta está bloqueada y necesito acceder hoy mismo para enviar un informe a gerencia"
)


def _post_triage(client, reports):
    return client.post("/v1/triage", json={"reports": reports})


# ---------------------------------------------------------------------------
# E1 — Caída crítica en la pasarela de pagos
# ---------------------------------------------------------------------------
def test_e1_caida_critica_pasarela_de_pagos(client):
    """
    Given un reporte de caída global del gateway de pagos con HTTP 502, múltiples
          comercios afectados y urgencia declarada
    When  se clasifica mediante POST /v1/triage en un lote de un solo reporte
    Then  la respuesta es 200 con P0, payment-gateway, Backend-Core y escalate_24x7,
          sin clave de grupo, y la nota léxica de "URGENTE" no altera la severidad
    """
    response = _post_triage(client, [{"raw_text": CAIDA_PASARELA}])

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    result = results[0]
    assert result["severity"] == "P0"
    assert result["component"] == "payment-gateway"
    assert result["recommended_team"] == "Backend-Core"
    assert result["action"] == "escalate_24x7"
    assert result["duplicate_type"] == "none"
    assert result["duplicate_group_key"] is None
    assert result["merge"] is False
    assert any("Nota léxica" in step and '"urgente"' in step for step in result["analysis"])


# ---------------------------------------------------------------------------
# E1b — La caída se agrupa cuando hay más de un reporte
# ---------------------------------------------------------------------------
def test_e1b_caida_se_agrupa_con_mas_de_un_reporte(client):
    """
    Given un lote con dos reportes de caída del mismo componente, sin marca de
          recurrencia y separados por 10 minutos (dentro de la ventana de fusión)
    When  se clasifican
    Then  ambos comparten la clave canónica "payment-availability", son
          "exact_duplicate" y solo el segundo tiene merge=true
    """
    response = _post_triage(
        client,
        [
            {
                "raw_text": "El gateway de pagos devuelve HTTP 502 en todas las transacciones",
                "created_at": "2026-11-05T08:15:00",
            },
            {
                "raw_text": "La pasarela de pagos está caída para todos los comercios, error 502",
                "created_at": "2026-11-05T08:25:00",
            },
        ],
    )

    assert response.status_code == 200
    first, second = response.json()["results"]
    for result in (first, second):
        assert result["duplicate_group_key"] == "payment-availability"
        assert result["duplicate_type"] == "exact_duplicate"
    assert first["merge"] is False
    assert second["merge"] is True


# ---------------------------------------------------------------------------
# E2 — Cuenta individual bloqueada que menciona "hoy"
# ---------------------------------------------------------------------------
def test_e2_cuenta_bloqueada_con_hoy_no_es_p0(client):
    """
    Given un reporte de una cuenta individual bloqueada que necesita acceso "hoy mismo"
    When  se clasifica en un lote de uno
    Then  la respuesta es 200 con P2 (no P0), auth-identity, Security-IAM y
          restore_account, y "hoy" queda registrado como trampa léxica
    """
    response = _post_triage(client, [{"raw_text": CUENTA_BLOQUEADA}])

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["severity"] == "P2"
    assert result["severity"] != "P0"
    assert result["component"] == "auth-identity"
    assert result["recommended_team"] == "Security-IAM"
    assert result["action"] == "restore_account"
    lexical = [step for step in result["analysis"] if "Nota léxica" in step]
    assert lexical and '"hoy' in lexical[0]


# ---------------------------------------------------------------------------
# E3 — Entradas vacías o con solo espacios
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw_text", ["", " ", "   \t  "])
@pytest.mark.parametrize("position", [0, 1])
def test_e3_raw_text_vacio_responde_422_sin_ejecutar_motor(client, monkeypatch, raw_text, position):
    """
    Given una petición cuyo raw_text en la posición N es vacío o solo espacios
    When  se envía a POST /v1/triage
    Then  la respuesta es 422 con code "invalid_payload" y field "reports[N].raw_text"
    And   el motor no se ejecuta y no se devuelve ningún result
    """
    calls = []
    monkeypatch.setattr(services_module, "classify_incident_batch", lambda reports: calls.append(reports))
    reports = [{"raw_text": CAIDA_PASARELA}, {"raw_text": CUENTA_BLOQUEADA}]
    reports[position] = {"raw_text": raw_text}

    response = _post_triage(client, reports)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "invalid_payload"
    assert body["error"]["field"] == f"reports[{position}].raw_text"
    assert "results" not in body
    assert calls == []


# ---------------------------------------------------------------------------
# E3b — Etiqueta vacía por CLI
# ---------------------------------------------------------------------------
def test_e3b_etiqueta_vacia_por_cli_termina_con_codigo_3(runner, cli_app):
    """
    Given una invocación triage --incident-id "" --raw-text "..."
    When  se ejecuta
    Then  termina con código 3, escribe el diagnóstico por stderr y no imprime
          resultado por stdout
    """
    result = runner.invoke(cli_app, ["triage", "--incident-id", "", "--raw-text", CUENTA_BLOQUEADA])

    assert result.exit_code == 3
    assert result.stderr.strip() != ""
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# E4 — Paridad del canal CLI
# ---------------------------------------------------------------------------
def test_e4_paridad_cli_http_para_inc_1001(runner, cli_app, client, sample_texts, fixed_now):
    """
    Given el reporte INC-1001 del fixture, invocado como
          triage --incident-id INC-1001 --raw-text "..." --format json
    When  se ejecuta
    Then  termina con código 0 y stdout es JSON {"results": [...]} con un elemento
    And   severity es P0, recommended_team es Backend-Core y no incluye incident_id
    And   el mismo lote por HTTP produce exactamente los mismos campos (Art. 2.7)
    """
    raw_text = sample_texts["INC-1001"]

    cli_result = runner.invoke(
        cli_app,
        [
            "triage",
            "--incident-id", "INC-1001",
            "--raw-text", raw_text,
            "--now", fixed_now.isoformat(),
            "--format", "json",
        ],
    )

    assert cli_result.exit_code == 0, cli_result.stderr
    cli_body = json.loads(cli_result.stdout)
    assert list(cli_body) == ["results"]
    assert len(cli_body["results"]) == 1
    cli_item = cli_body["results"][0]
    assert cli_item["severity"] == "P0"
    assert cli_item["recommended_team"] == "Backend-Core"
    assert "incident_id" not in cli_item
    assert "INC-1001" not in cli_result.stdout

    http_response = _post_triage(client, [{"raw_text": raw_text}])

    assert http_response.status_code == 200
    assert http_response.json() == cli_body


# ---------------------------------------------------------------------------
# E10 — Contrato estricto (complementario: valida el reparto 400/422 de D11)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("report", "code", "field"),
    [
        ({"raw_text": CAIDA_PASARELA, "incident_id": "INC-1"}, "reserved_field", "reports[0].incident_id"),
        ({"raw_text": CAIDA_PASARELA, "prioridad": "alta"}, "invalid_payload", "reports[0].prioridad"),
        ({"raw_text": 123}, "invalid_payload", "reports[0].raw_text"),
    ],
)
def test_e10_contrato_estricto_responde_400(client, monkeypatch, report, code, field):
    """
    Given un cuerpo con incident_id, un campo desconocido o un tipo incorrecto
    When  se envía a POST /v1/triage
    Then  se rechaza con 400 y el code correspondiente, sin clasificar nada
    """
    calls = []
    monkeypatch.setattr(services_module, "classify_incident_batch", lambda reports: calls.append(reports))

    response = _post_triage(client, [report])

    assert response.status_code == 400
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["field"] == field
    assert calls == []


def test_json_malformado_responde_400_invalid_json(client):
    """Given un cuerpo que no es JSON, When se envía, Then es 400 con code invalid_json."""
    response = client.post(
        "/v1/triage", content=b"{reports: [", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_json"


def test_health(client):
    """Given el servicio, When se consulta /v1/health, Then responde 200 {"status": "ok"}."""
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
