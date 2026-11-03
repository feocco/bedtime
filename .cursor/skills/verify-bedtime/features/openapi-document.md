# OpenAPI document

The OpenAPI document is the machine-readable contract at `GET /openapi.json`. It names the Bedtime Lights API and documents `GET /health`.

## Sub-features

- `openapi-get` returns JSON with `openapi` `3.1.0` and `info.title` `Bedtime Lights API`.
- `openapi-health-path` includes `paths./health` for `get`.
- `openapi-from-docs` is the URL named by the `/openapi.json` link on `/docs`.

## How to get to it (user POV)

- Request `GET /openapi.json`.
- Open `$base_url/docs` and follow the `/openapi.json` link.
- Read `paths./health` inside that document.

## Driving it with verify-bedtime

Preconditions:

- Doctor reports `ok: true` for this run's instance.

- **Direct GET.** Fetch the document. Run `./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py drive --feature openapi`. Exit `0`. Status `200`, content type `application/json`, `openapi` is `3.1.0`, `info.title` is `Bedtime Lights API`. Artifact `openapi.response.txt` holds the body.
- **Health path.** In that same body, `paths./health.get` exists. The documented `200` JSON schema has `service` const `bedtime` and `status` const `ok`.
- **Docs href.** Prove the docs page names that URL. Run `./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py drive --feature docs`. The parsed DOM contains `href="/openapi.json"`. Then `GET $base_url/openapi.json`, which is that href resolved against `$base_url`. The helper does not click the link. The document must match the direct GET.
- **Proof.** Keep `openapi.response.txt` and the docs artifact that shows the href. A schema fragment copied from `health.py` is not a substitute for `GET /openapi.json`.

## Gotchas

- The document currently describes `/health` only. Do not fail the journey because `/docs` is missing from `paths`.
- Compare `info.title` to `Bedtime Lights API`. Do not accept a different service title from another homelab process.
- The docs link is relative (`/openapi.json`). Resolve it against `$base_url`, not against a production host.
