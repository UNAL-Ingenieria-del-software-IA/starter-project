# Guía de validación (Fase 1): Registro, duplicado abierto y auditoría de SLA (H003)

Guía para comprobar de punta a punta que la funcionalidad cumple la spec. No contiene
implementación. Contratos: [HTTP](contracts/http-incidents.openapi.yaml),
[CLI](contracts/cli-create-sla.md), [puerto](contracts/incident-repository-port.md).
Modelo: [data-model.md](data-model.md).

Todos los comandos se ejecutan desde la raíz del repositorio, en PowerShell.

## 1. Requisitos previos

```powershell
uv sync
```

Si estás detrás del proxy TLS local, usa `uv sync --system-certs`. No se agregan
dependencias.

## 2. Verificación obligatoria (F4), en este orden

```powershell
uv run ruff check src/
```

```powershell
uv run python -X utf8 -m pytest -v
```

```powershell
uv run python -X utf8 -m src.sla_calculator
```

```powershell
uv run python -X utf8 -m src.triage_rules
```

Resultado esperado:

- **Ruff**: 0 hallazgos y ningún `# noqa` nuevo.
- **pytest**: todo en verde, incluidas `test_arquitectura.py`, las suites de spec 001 y
  spec 002 (con el código de salida `1` ya enmendado) y `test_spec_003_lifecycle_sla.py`.
- **`_run_demo`**: 12 aserciones (10 previas más E10.1 y E10.2); sale con `0`.
- **Auditoría de triaje**: salida **idéntica** a la de `main` antes del cambio. Para
  compararla, guarda la salida previa y usa `Compare-Object` (sección 6).

## 3. Escenarios obligatorios con pytest

```powershell
uv run python -X utf8 -m pytest -v tests/test_spec_003_lifecycle_sla.py -k "e1_ or e5_ or e11_ or e12_ or e13_ or e14_"
```

Debe mostrar en verde las seis funciones de los cinco comportamientos pedidos: E1, E5,
E11 (dos ejemplos), E12, E13 y E14.

## 4. Recorrido manual por HTTP

```powershell
uv run uvicorn src.main:app --host 127.0.0.1 --port 8080
```

Con el almacén de demostración por defecto, en otra terminal:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/v1/incidents -ContentType "application/json; charset=utf-8" -Body '{"title":"Caída de la pasarela de pagos","raw_text":"La pasarela de pagos está caída, ningún cliente puede pagar"}'
```

Se espera `201`, un identificador `INC-` más 8 dígitos hexadecimales, `"is_duplicate": true`
y `"duplicate_of": ["INC-2001"]`. El demo `INC-2001` está abierto con clave
`payment-availability`; `INC-2008` es de pagos pero está `RESOLVED` y no tiene esa clave.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/incidents/INC-2001/sla?reference_time=2026-11-24T08:15:00"
```

Se espera `200` con `elapsed_minutes` = `45`, `allowed_minutes` = `60` y
`requires_escalation` = `true` (P0 creado a las 07:30).

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/v1/incidents/INC-FFFFFFFF/sla" -SkipHttpErrorCheck
```

Se espera `404` con `incident_not_found`. `-SkipHttpErrorCheck` requiere PowerShell 7; en
Windows PowerShell 5.1, captura la excepción y lee `$_.Exception.Response.StatusCode`.

## 5. Recorrido manual por CLI con almacén persistente

```powershell
$env:DATABASE_URL = "sqlite:///$env:TEMP\incidentops-h003.db"
```

```powershell
uv run python -X utf8 -m src.adapters.inbound.cli create --title "Caída de la pasarela de pagos" --raw-text "La pasarela de pagos está caída" --incident-id INC-DEMO-01 --created-at 2026-11-06T17:00:00 --format json
```

```powershell
uv run python -X utf8 -m src.adapters.inbound.cli sla INC-DEMO-01 --reference-time 2026-11-09T09:00:00 --format json
```

El segundo comando corre en otro proceso y aun así encuentra el incidente (E2). El triaje
asigna `P2` a ese texto (sin alcance global), así que el resultado reproduce E12:
`elapsed_minutes` = `120`, `allowed_minutes` = `480`, `remaining_minutes` = `360`,
`is_breached` = `false` y `requires_escalation` = `false`.

```powershell
uv run python -X utf8 -m src.adapters.inbound.cli create --title "Repetido" --raw-text "La pasarela de pagos está caída" --incident-id INC-DEMO-01
```

```powershell
$LASTEXITCODE
```

Se espera `1`, con `error [incident_id_conflict]` en `stderr`.

```powershell
Remove-Item Env:DATABASE_URL
```

## 6. Invariancia de la auditoría de triaje

Antes del cambio, en `main`:

```powershell
uv run python -X utf8 -m src.triage_rules > $env:TEMP\audit-antes.txt
```

Después del cambio:

```powershell
uv run python -X utf8 -m src.triage_rules > $env:TEMP\audit-despues.txt
```

```powershell
Compare-Object (Get-Content $env:TEMP\audit-antes.txt) (Get-Content $env:TEMP\audit-despues.txt)
```

Se espera que no haya diferencias (Art. 1.12: `group_key_for` no altera el lote).

## 7. Rendimiento (SC-006)

Lo cubre una prueba gruesa por canal en `test_spec_003_lifecycle_sla.py`: siembra 10 000
abiertos en `tmp_path`, mide un `create` con búsqueda de duplicados y una auditoría, y
exige < 1 s cada uno en proceso.

## 8. Riesgo residual conocido

Si la búsqueda de duplicados falla después de guardar, el incidente queda guardado y la
respuesta es `500` / `4` ([research §R5](research.md#r5-orden-guardar-y-luego-buscar-atomicidad-de-fr-011)).
Reintentar con el mismo `incident_id` devuelve `409`, lo que confirma que existe.
