# Contrato CLI: subcomandos `create` y `sla` (spec 003)

Invocación: `uv run python -X utf8 -m src.adapters.inbound.cli <subcomando> …`

`stdout` lleva solo el resultado; `stderr`, solo diagnósticos. `--format json` emite el
mismo cuerpo que HTTP, campo a campo (FR-020): lo producen `creation_to_contract` y
`sla_audit_to_contract`. `--format table` (valor por defecto) es presentación y no forma
parte del contrato.

## `create`

| Opción | Obligatoria | Equivale a |
|---|---|---|
| `--title TEXTO` | sí | `title` |
| `--raw-text TEXTO` | sí | `raw_text` |
| `--incident-id ID` | no | `incident_id` |
| `--created-at ISO` | no | `created_at` |
| `--status ESTADO` | no (por defecto `OPEN`) | `status` |
| `--resolved-at ISO` | no | `resolved_at` |
| `--format table\|json` | no | — |

No existen `--severity`, `--component`, `--recommended-team`, `--action` ni
`--duplicate-group-key`. Typer los rechaza como opciones desconocidas (código `2`), que es
el equivalente CLI del `400` por campo reservado.

A diferencia de `triage`, en `create` el `--incident-id` **es** el identificador del
incidente y aparece en `--format json`.

La tabla muestra el identificador, la severidad, el componente, el equipo y la clave. Si
hay duplicados, añade la línea `AVISO: duplica incidentes abiertos: INC-…, INC-…`
(también en `stdout`, porque es resultado).

## `sla <INCIDENT_ID>`

| Argumento u opción | Obligatorio | Equivale a |
|---|---|---|
| `INCIDENT_ID` (posicional) | sí | `{incident_id}` de la ruta |
| `--reference-time ISO` | no | `reference_time` |
| `--format table\|json` | no | — |

## Códigos de salida (todo el CLI, tras la enmienda D8)

| Código | Significado | Casos de `create`/`sla` |
|---|---|---|
| `0` | Éxito | Creación (duplicado o no), auditoría válida |
| `1` | Entrada inválida | Título o texto vacío o largo, identificador mal formado, estado o resolución inválidos, instante ilegible, `reference_time` anterior a la creación, incidente inexistente, identificador ya existente |
| `2` | Error de uso | Opción desconocida o reservada, falta `--title`/`--raw-text`/`INCIDENT_ID`, `--format` inválido |
| `4` | Fallo interno | Almacén caído, `DATABASE_URL` no soportada, error inesperado |

El código `3` deja de usarse en todo el CLI (`triage` y `summary` incluidos).

Formato del diagnóstico en `stderr`, igual que H001/H002:
`error [<code>] <campo|->: <mensaje>`. Nunca incluye el título ni el texto del reporte.

## Persistencia entre invocaciones

Cada invocación es un proceso nuevo. Con el `DATABASE_URL` por defecto
(`sqlite:///:memory:`), un `create` desaparece al terminar. Para crear y auditar después,
configura un archivo:

```powershell
$env:DATABASE_URL = "sqlite:///incidentops.db"
```
