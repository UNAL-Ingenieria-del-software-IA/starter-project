# Contrato CLI: subcomando `summary` (H002)

```text
uv run python -X utf8 -m src.adapters.inbound.cli summary
    [--component TEXTO]
    [--reference-time ISO-8601]
    [--format table|json]          # por defecto: table
```

| Opción | Equivalente HTTP | Regla |
|---|---|---|
| `--component` | `component` | Se normaliza (recorte + minúsculas) en el servicio. Vacío o solo espacios → `1`. |
| `--reference-time` | `reference_time` | Mismo analizador que HTTP (`parse_reference_time`). No parseable → `1`. |
| `--format` | — | `json` imprime exactamente el cuerpo de `200` de HTTP; `table` es presentación. |

## Salida

- **`--format json`**: una sola línea en `stdout` con el objeto
  `ActiveIncidentsSummaryResponse` de
  [http-incidents-summary.openapi.yaml](http-incidents-summary.openapi.yaml),
  serializado con `ensure_ascii=False`. Debe coincidir valor a valor y en orden con HTTP
  para el mismo almacén e instante (FR-014, E10).
- **`--format table`** (no es contrato, D8): una línea de cabecera con instante, filtro,
  total activo y total incumplido, seguida de una tabla con ID, severidad, estado,
  componente, minutos, incumplido (`sí`/`no`) y escalamiento (`sí`/`no`). Sin
  coincidencias, la tabla se imprime vacía y el código es `0`.

## Códigos de salida

| Código | Situación | `stderr` |
|---|---|---|
| `0` | Éxito, con o sin coincidencias | — |
| `2` | Bandera desconocida o `--format` inválido (Click/Typer) | Uso de Click |
| `1` | `--reference-time` no parseable o `--component` vacío (antes `3`; enmienda de spec 003 D8) | `error [<code>] <campo>: <mensaje>` |
| `4` | Fallo inesperado | `error [internal_error]: <TipoDeExcepción>` |
| `4` | Configuración inválida (`DATABASE_URL` no soportada); aplica también a `triage` | `error [internal_error]: <mensaje>` (nombra solo el esquema, nunca la URL) |

`stdout` lleva solo el resultado; `stderr`, solo diagnósticos. Nunca se imprimen títulos
en `stderr` (FR-015).

## Ejemplos

```text
$ ... summary --component " Payment-Gateway " --reference-time 2026-11-24T09:00:00 --format json
{"reference_time": "2026-11-24T09:00:00-05:00", "component_filter": "payment-gateway", "total_active": 2, ...}
exit 0

$ ... summary --reference-time ayer
error [invalid_timestamp] reference_time: 'ayer' no es una fecha ISO-8601 válida.
exit 1

$ ... summary --componente payment-gateway
Error: No such option: --componente
exit 2
```
