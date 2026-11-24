---
name: bdd-acceptance
description: Cómo redactar escenarios BDD Given/When/Then en el spec.md de una capacidad y cómo automatizarlos 1:1 en funciones test_bdd_* con TestClient de FastAPI y CliRunner de Typer sobre almacenamiento aislado. Úsala al especificar una capacidad, escribir o revisar pruebas de aceptación, o verificar la paridad REST/CLI.
---

# Aceptación BDD de IncidentOps

Norma para convertir una regla de negocio en un escenario legible y en **una** prueba
ejecutable. La Constitución (Art. 3.4) exige especificar en `Given / When / Then`, en
español, antes de implementar: un escenario por regla observable.

La correspondencia es estricta:

```text
un escenario del spec.md  ⇄  una función test_bdd_* en tests/
```

Si un escenario necesita dos pruebas, está mal dividido. Si una prueba cubre dos
escenarios, está mal agregada.

## 1. Dónde se escribe el escenario

En el archivo de especificación de la capacidad (`specs/NNN-...md`; el enunciado lo llama
`spec.md`), dentro de la sección de escenarios BDD. En este repo el formato vigente es el
de `specs/001-triage-endpoint-manual.md` §9:

```markdown
## 9. Escenarios BDD

### 9.1 Escenarios obligatorios del hito

**E7 — La recurrencia no fusiona incidentes**

> **Given** dos reportes de caída del mismo componente donde el segundo dice "otra vez"
> **When** se clasifican juntos
> **Then** ambos quedan marcados como recurrencia
> **And** ninguno se fusiona con el otro
```

Reglas de forma:

- Título con identificador estable (`E1`, `E3b`, `E7`…) y una frase que nombre la regla
  de negocio, no la implementación.
- `Given` describe el contexto y el estado del mundo; no es una lista de pasos de UI.
- `When` describe **un** evento o acción que dispara el comportamiento.
- `Then` describe el resultado observable; los `And` añaden observaciones del mismo
  resultado, no nuevas acciones.
- Usa ejemplos concretos y deterministas (`INC-1001`, `94 %`, `"otra vez"`) en lugar de
  abstracciones vagas.
- Un escenario no depende de otro ni de su orden de ejecución.

### Vocabulario ubicuo: qué sí y qué no

El escenario debe poder leerlo una persona de negocio. No filtres nombres de clases,
funciones, módulos ni tablas SQL.

| No escribir | Escribir |
|---|---|
| `Given un IncidentReport con raw_text que extract_signals marca como global` | `Given un reporte que describe una caída global del servicio` |
| `When se llama a IncidentService.triage_incident` | `When el reporte se clasifica` |
| `Then se inserta una fila en incidents con severity='P0'` | `Then el incidente queda registrado con severidad P0` |
| `Then el mock del repositorio devuelve...` | `Then el incidente puede consultarse de nuevo` |
| `When classify_incident_batch recibe dos elementos` | `When se clasifican dos reportes del mismo componente` |

Sí son vocabulario aceptable los términos del **contrato observable**, porque el cliente
los ve: la ruta `POST /v1/triage`, el código `422`, el `exit code 3`, los campos
`severity`, `component` o `duplicate_group_key`, y el formato `{"results": [...]}`. La
frontera es clara: contrato público sí; clase, función interna, tabla o mock no.

### Estilo Dan North

- El escenario es una conversación sobre comportamiento, no un test disfrazado.
- El título enuncia la regla; el cuerpo la ejemplifica.
- Evita "y/o", condicionales y varios `When` en el mismo escenario. Si hay dos eventos,
  hay dos escenarios.
- Describe el "qué" observable, no el "cómo" se implementa.
- Si la regla tiene varios ejemplos equivalentes, un solo escenario puede incluir una
  tabla de ejemplos; no conviertas cada ejemplo en un escenario distinto.

## 2. Cómo se mapea a `tests/`

Cada escenario produce exactamente una función:

```python
def test_bdd_e7_recurrencia_no_fusiona(client):
    """
    Given dos reportes de caída del mismo componente donde el segundo dice "otra vez"
    When  se clasifican juntos
    Then  ambos quedan marcados como recurrencia
    And   ninguno se fusiona con el otro
    """
```

Convenciones:

- Nombre: `test_bdd_<id>_<slug>`; por ejemplo `test_bdd_e1_caida_critica_pasarela`.
  Para IDs con letra, `test_bdd_e1b_caida_se_agrupa`.
- El docstring reproduce el `Given / When / Then` del spec, en español. Es la
  trazabilidad entre spec y prueba; no lo sustituyas por un comentario genérico.
- Archivo: el de aceptación de la capacidad (`tests/test_spec_001_triage.py`) o uno
  nuevo `tests/test_bdd_<capacidad>.py`. Lo obligatorio es el prefijo `test_bdd_` en la
  función.
- Una función por escenario. `pytest.mark.parametrize` solo vale para ejemplos
  equivalentes de la **misma** regla; sigue siendo una función y, por tanto, un
  escenario.
- Si el escenario exige ambos canales (paridad REST/CLI), una sola función puede usar
  `client` y `runner` y comparar sus salidas. No dupliques el escenario en dos pruebas.
- Al renombrar un escenario, renombra su prueba y actualiza cualquier tabla de
  trazabilidad. El ID no se recicla.

### Given / When / Then dentro del test

Haz que el cuerpo siga la misma estructura:

```python
def test_bdd_e2_cuenta_bloqueada_no_es_p0(client):
    """
    Given un reporte de una cuenta individual bloqueada que pide acceso "hoy mismo"
    When  se clasifica en un lote de uno
    Then  la severidad es P2 y "hoy" queda registrada como trampa léxica
    """
    # Given: el reporte existe en el contexto del test.
    report = {"raw_text": CUENTA_BLOQUEADA}

    # When: una sola acción observable.
    response = client.post("/v1/triage", json={"reports": [report]})

    # Then: resultado observable, no estado interno.
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["severity"] == "P2"
    assert result["severity"] != "P0"
```

Reglas de aserción:

- Verifica primero el resultado de la acción (estado HTTP, `exit code`, cuerpo, stdout).
- Después, los campos del contrato que el escenario menciona.
- No asserts sobre atributos privados, nombres de clases, SQL generado ni detalles de
  implementación.
- Puedes usar un espía en la frontera para demostrar que algo **no** ocurrió (por
  ejemplo, que el motor no se ejecutó), pero el escenario debe expresarlo como una
  garantía de negocio ("no se clasifica nada"), no como "el mock no fue llamado".
- Los valores esperados son los que fija el dominio; la prueba los observa, no los
  redefine (Art. 1.1).

## 3. Los dos canales en la prueba

### TestClient (REST)

`TestClient` ejecuta la app FastAPI en proceso: sin `uvicorn`, sin puerto y sin red.

```python
from fastapi.testclient import TestClient
from src.adapters.inbound.api.app import create_app

client = TestClient(create_app(service))
response = client.post("/v1/triage", json={"reports": [{"raw_text": CAIDA_PASARELA}]})
assert response.status_code == 200
assert response.json()["results"][0]["severity"] == "P0"
```

### CliRunner (CLI)

`CliRunner` invoca la app Typer en proceso: sin subprocess, sin terminal real.

```python
from typer.testing import CliRunner
from src.adapters.inbound.cli import create_cli

runner = CliRunner()
result = runner.invoke(cli_app, ["triage", "--raw-text", CAIDA_PASARELA, "--format", "json"])
assert result.exit_code == 0
assert result.stderr == ""
payload = json.loads(result.stdout)
assert payload["results"][0]["severity"] == "P0"
```

Para paridad, compara el **mismo** reporte por ambos canales:

```python
def test_bdd_e4_paridad_cli_http(client, runner, cli_app, sample_texts):
    """..."""
    raw_text = sample_texts["INC-1001"]

    cli_result = runner.invoke(cli_app, ["triage", "--raw-text", raw_text, "--format", "json"])
    http_response = client.post("/v1/triage", json={"reports": [{"raw_text": raw_text}]})

    assert cli_result.exit_code == 0
    assert http_response.status_code == 200
    assert http_response.json() == json.loads(cli_result.stdout)
```

Recuerda: los canales solo traducen. Si una prueba de aceptación necesita lógica de
triaje para pasar, la lógica está en el lugar equivocado.

## 4. Almacenamiento aislado

Cada prueba debe poseer su estado. Prohibido compartir una base de datos entre pruebas,
usar `data/sample_incidents.json` como almacén de escritura o apuntar al almacén por
defecto de la aplicación.

### Cuándo usar repositorio nulo

Si el escenario afirma que **no** hay persistencia (triaje de solo lectura), construye el
servicio con el repositorio nulo y comprueba que no se creó nada:

```python
@pytest.fixture
def service():
    # H001: sin efectos secundarios; el repositorio nulo satisface el puerto.
    return build_service(FIXED_NOW)


def test_bdd_e12_sin_efectos_secundarios(client, tmp_path):
    """..."""
    response = client.post("/v1/triage", json={"reports": [{"raw_text": CAIDA_PASARELA}]})
    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []
```

### Cuándo usar SQLite desechable

Si el escenario escribe o lee estado persistente, usa una base por prueba con `tmp_path`
y cablea el adaptador real. No uses un mock del repositorio en una prueba de aceptación:
lo que se quiere verificar es justamente el adaptador.

```python
@pytest.fixture
def repository(tmp_path):
    repo = build_incident_repository(database_path=tmp_path / "incidents.db")
    try:
        yield repo
    finally:
        repo.close()  # En Windows, un archivo abierto impide limpiar tmp_path.


@pytest.fixture
def service(repository):
    # La firma exacta de build_service depende del corte; lo importante es inyectar
    # el repositorio aislado, no construirlo dentro del caso de uso.
    return build_service(FIXED_NOW, repository)
```

Puntos finos:

- `tmp_path` es único por prueba y pytest lo limpia; no uses `tests/test.db`, ni una
  ruta relativa al repo, ni `scope="session"` para el almacén.
- `sqlite3` con `:memory:` solo conserva datos si la **misma** conexión sigue viva. Si el
  adaptador abre una conexión por operación, `:memory:` pierde el estado; usa `tmp_path`.
- `TestClient` puede ejecutar endpoints síncronos en un hilo del pool. Una conexión
  SQLite creada en el hilo del test y usada en otro falla con `check_same_thread`. Abre
  la conexión por operación o crea la conexión dentro del contexto que la usa; si
  compartes una, usa `check_same_thread=False` con un lock y justifícalo.
- Cierra conexiones en el finalizador del fixture. En Windows, una conexión abierta deja
  el archivo bloqueado y `tmp_path` no se puede borrar.
- Si un escenario hace varias invocaciones CLI que comparten estado, la fábrica del CLI
  debe devolver servicios contra el **mismo** almacén desechable:

```python
@pytest.fixture
def cli_app(repository):
    return create_cli(lambda now: build_service(now or FIXED_NOW, repository))
```

- Para paridad con escritura, no compartas el mismo estado entre canales: usa dos
  almacenes desechables equivalentes, o reinicia el almacén entre las dos ejecuciones.
  Así la comparación no se contamina.
- Fija el reloj (`FixedClock` o `build_service(FIXED_NOW)`) en toda prueba con fechas.
  Sin reloj fijo, el escenario deja de ser determinista.

### Fixtures compartidas

Las fixtures de `tests/conftest.py` deben ser de alcance por función (el valor por
defecto) cuando toquen almacenamiento. `client`, `cli_app`, `runner` y `service` se
construyen con la misma fábrica y el mismo instante fijo; el almacén se decide por
prueba. Una fixture de solo lectura, como el fixture graduado `sample_texts`, sí puede
ser de sesión.

## 5. Ejemplo completo

**En el spec:**

```markdown
**E1 — Caída crítica en la pasarela de pagos**

> **Given** un reporte que describe una caída global de la pasarela de pagos con
> múltiples comercios afectados y urgencia declarada
> **When** se clasifica en un lote de un solo reporte
> **Then** la respuesta es 200
> **And** la severidad es P0
> **And** el componente es payment-gateway y el equipo recomendado es Backend-Core
```

**En `tests/test_bdd_triage.py`:**

```python
def test_bdd_e1_caida_critica_pasarela(client):
    """
    Given un reporte que describe una caída global de la pasarela de pagos con
          múltiples comercios afectados y urgencia declarada
    When  se clasifica en un lote de un solo reporte
    Then  la respuesta es 200
    And   la severidad es P0
    And   el componente es payment-gateway y el equipo recomendado es Backend-Core
    """
    response = client.post("/v1/triage", json={"reports": [{"raw_text": CAIDA_PASARELA}]})

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["severity"] == "P0"
    assert result["component"] == "payment-gateway"
    assert result["recommended_team"] == "Backend-Core"
```

La prueba no menciona `IncidentService`, `TriageResult`, `classify_incident_batch` ni la
tabla `incidents`: solo el contrato que el escenario promete.

## 6. Checklist antes de cerrar

- [ ] El escenario está en el spec **antes** del código, con ID y título de negocio.
- [ ] Tiene un solo `Given`, un solo `When` y un `Then` observable (con `And` si hace
      falta).
- [ ] No filtra clases, funciones, módulos, mocks ni tablas SQL; solo vocabulario de
      negocio y contrato público.
- [ ] Existe **una** función `test_bdd_<id>_<slug>` por escenario, con el docstring
      `Given / When / Then` copiado del spec.
- [ ] La prueba usa `TestClient` y/o `CliRunner`, nunca red, puerto ni subprocess.
- [ ] El almacenamiento es aislado: repositorio nulo o `tmp_path` por prueba, sin bases
      compartidas ni escrituras en `data/`.
- [ ] El reloj está fijo y las conexiones se cierran.
- [ ] Las aserciones miran estado HTTP, `exit code`, cuerpo, stdout/stderr y estado
      persistido observable; no atributos privados.
- [ ] `uv run python -X utf8 -m pytest -v -k test_bdd` pasa.
- [ ] La paridad REST/CLI se verifica con el mismo caso de uso y la misma proyección de
      contrato (Art. 2.7).
