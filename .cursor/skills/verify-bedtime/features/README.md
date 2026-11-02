# Bedtime Lights verification map

This directory is the maintained source for verifying the user-facing HTTP and docs behavior of Bedtime Lights. Read this index before driving the app, then use the matching feature file as the recipe.

## Baseline preconditions

- Launch with `./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py launch --evidence-dir /opt/cursor/artifacts/verify-bedtime/final`.
- Concurrent runs pass distinct `--instance` and `--evidence-dir` values.
- The process is `python -m bedtime_lights.main` with `PYTHONPATH` set to this repo root, not a lone `HealthServer`.
- Config is a copy of `config.example.yaml`. State starts in an empty directory.
- `DRY_RUN=true`. Home Assistant is the local WebSocket stand-in. No production URLs or tokens.
- `./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py doctor` reports `ok: true`, the instance `base_url`, and health `{"service": "bedtime", "status": "ok"}`.
- Never drive an instance this run did not start.

## Driving conventions

- Start every recipe from the baseline state unless its preconditions say otherwise.
- Drive `/health` and `/openapi.json` with HTTP. Drive `/docs` through Chrome or Chromium. Parse `h1`, `h2`, `pre`, and `a[href="/openapi.json"]` from `bedtime_lights/health.py`. The helper does not click that link.
- Treat helper flags and quoted JSON as literal.
- Restore nothing in the live Home Assistant. This map does not click notification buttons and does not call `script.turn_off_all_lights`.
- Cleanup removes scratch state and saved PIDs. It does not remove proof artifacts.

## Proof and skip reporting

- Capture the request or browser action and the resulting body or UI, not only the final screenshot.
- HTTP proof includes URL, status, headers, and body.
- Docs proof includes the HTTP HTML, a browser DOM dump, the parser result, and a screenshot. The runner inspects the screenshot.
- Side-effect proof for a dry-run launch is in `service.log` and `standin.log`.
- `drive.json` records the feature, `run_id`, and outcome for that drive. It does not stamp every other artifact.
- Report an unreachable path with the command you ran and the unmet precondition.
- Do not report a skipped entry point as verified through a different path.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with verify-bedtime` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands, and observable proof.

## Features

- [Health status](./health-status.md) covers `GET /health` and the same payload shown on the docs page and in OpenAPI.
- [Browser API docs](./browser-api-docs.md) covers the static HTML at `GET /docs`.
- [OpenAPI document](./openapi-document.md) covers `GET /openapi.json` and the docs-page link to it.
