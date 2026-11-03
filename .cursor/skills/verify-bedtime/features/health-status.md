# Health status

Health status tells an operator the Bedtime Lights process is accepting HTTP. `GET /health` returns JSON `{"service": "bedtime", "status": "ok"}`.

## Sub-features

- `health-get` returns that JSON from `GET /health`.
- `health-docs-example` shows the same JSON in the docs page `pre` block.
- `health-openapi` describes `GET /health` in `/openapi.json`.

## How to get to it (user POV)

- Request `GET /health` on the service port, default `8104` in production and `$base_url` in a verify run.
- Open `GET /docs` and read the `GET /health` example body.
- Open `GET /openapi.json` and read `paths./health`.

## Driving it with verify-bedtime

Preconditions:

- Doctor reports `ok: true` for this run's instance.
- `$base_url` is the `base_url` field from the live instance file.

- **Direct GET.** Request health. Run `./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py drive --feature health`. Exit `0`, `health.status` is `200`, and `health.payload` equals `{"service": "bedtime", "status": "ok"}`. Artifacts `health.request.txt` and `health.response.txt` show that URL and body.
- **Docs example.** Open the docs page and read the example payload. Run `./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py drive --feature docs`. The parser result includes `pre` text `{"service": "bedtime", "status": "ok"}`.
- **OpenAPI path.** Fetch the schema. Run `./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py drive --feature openapi`. The document contains `paths./health` and `info.title` `Bedtime Lights API`. That request is `GET $base_url/openapi.json`, the resolved docs href, not a click.
- **Proof.** Keep `health.response.txt`, `docs.response.txt`, and `openapi.response.txt`. The health body is exactly the JSON above. The docs `pre` and the OpenAPI schema describe that same object.

## Gotchas

- `HealthServer` starts before Home Assistant connects. A `200` from `/health` is not proof the watcher started. Doctor also requires the log line `Bedtime lights watcher started`.
- Compare parsed JSON to `{"service": "bedtime", "status": "ok"}`. Do not accept another service name or a wrapping envelope.
- Production `HealthServer` binds `0.0.0.0` on `SERVICE_PORT` (default `8104`). A verify run still calls `127.0.0.1` on the instance port. Do not curl `8104` unless doctor says this instance owns it.
- Driving only `/docs` or only `/openapi.json` does not verify `GET /health`. Hit the health URL.
