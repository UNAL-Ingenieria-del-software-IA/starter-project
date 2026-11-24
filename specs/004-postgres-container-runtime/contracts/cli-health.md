# Contrato CLI: subcomando `health` (spec 004)

```text
uv run python -X utf8 -m src.adapters.inbound.cli health [--format table|json]
```

| Opción | Valores | Por defecto |
|---|---|---|
| `--format` | `table`, `json` | `table` |

Una opción desconocida o reservada sale con código `2` (error de uso, vigente).

## Resultado

| Situación | stdout (`--format json`) | stdout (`--format table`) | stderr | Código |
|---|---|---|---|---|
| El almacén responde | `{"status": "ok", "database": "connected"}` | `estado         ok`<br>`base de datos  connected` | vacío | `0` |
| El almacén no responde, ya sea al construir el servicio o al consultar | `{"status": "error", "database": "unavailable"}` | `estado         error`<br>`base de datos  unavailable` | `error [database_unavailable]: el almacén de incidentes no responde.` | `4` |
| `DATABASE_URL` con un esquema no soportado o mal formada | vacío | vacío | `error [internal_error]: DATABASE_URL no soportada (esquema '<s>'): …` | `4` |

## Reglas

- El JSON es exactamente el de `health_to_contract`, la misma proyección que usa
  `GET /health` (Art. 2.7).
- El cuerpo `unavailable` es un **resultado**, por eso va a stdout. Solo el diagnóstico va a
  stderr (convención F3).
- Ninguna salida contiene `DATABASE_URL` ni sus partes: usuario, contraseña, host, puerto ni
  nombre de la base (RNF-003).
- La respuesta llega en 3 s o menos aunque la base no responda (RNF-002).
- Los demás subcomandos (`triage`, `summary`, `create`, `sla`) conservan el fallo temprano:
  sin almacén salen con `4` y `error [internal_error]: …` (FR-019).
