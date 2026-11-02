# AGENTS.md

Operator notes for Bedtime Lights. The package is `bedtime_lights`. The process entry point is `bedtime-lights`, which calls `bedtime_lights.main:main`.

## How to run

Install once in a local virtualenv:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
```

For a real Home Assistant deployment, copy the example files, put secrets in `.env`, put personal entity IDs in `config.yaml`, then start the process:

```bash
cp .env.example .env
cp config.example.yaml config.yaml
./.venv/bin/bedtime-lights
```

`SERVICE_PORT` defaults to `8104`. The process binds `GET /health`, `GET /docs`, and `GET /openapi.json` on that port.

To prove the local HTTP endpoints and docs page without production secrets, follow `.cursor/skills/verify-bedtime/SKILL.md`. That path runs `python -m bedtime_lights.main` against a fake local Home Assistant WebSocket, with `DRY_RUN=true` and isolated ports and state.

`HealthServer` binds `0.0.0.0`. Local verification still calls `http://127.0.0.1` on the instance port.

## How to test

```bash
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/pytest -q
```

`[tool.pytest.ini_options]` sets `testpaths = ["tests"]` and `asyncio_mode = "auto"`. Do not add `@pytest.mark.asyncio` unless a test needs a different loop policy.

CI in `.github/workflows/container.yml` builds and pushes the image only on `main` (and `workflow_dispatch`). It does not run pytest. Local pytest is the default proof. Run a Docker build only when Docker is installed.

## Code and test conventions

Match the files that already exist.

- Python 3.11+, `from __future__ import annotations`, type hints on public functions.
- Config records are frozen dataclasses in `bedtime_lights/config.py`. Runtime mutation lives in `RuntimeState`, not in config.
- The Home Assistant client and notifier take a `dry_run` flag. Tests inject fakes (`FakeHomeAssistant`, `FakeNotifier`) and assert call lists. Do not mock private helpers to fake a send.
- HTTP tests in `tests/test_health.py` start a real `HealthServer` on port `0` and assert status, content type, and body. Keep `/health` at exactly `{"service": "bedtime", "status": "ok"}`.
- Prefer one behavior per test function. Name tests after the observable result.
- Do not add dependencies to `pyproject.toml` unless the app cannot run or test without them.

## Environment, config, and state

Runtime configuration comes from the environment. `main.run` calls `load_dotenv()`, which fills missing keys from `.env` and does not override keys already set.

| Variable | Role |
| --- | --- |
| `HA_URL` | Home Assistant base URL. The client appends `/api/websocket`. |
| `HA_LONG_LIVED_TOKEN` | Home Assistant long-lived token. |
| `HOMELAB_FUNCTIONS_URL` | Broker used by `notify_joe` when `DRY_RUN` is false. |
| `HOMELAB_FUNCTIONS_TOKEN` | Broker token. Unused while `DRY_RUN` is true. |
| `CONFIG_PATH` | YAML config. Defaults to `config.yaml`. |
| `STATE_PATH` | JSON runtime state. Defaults to `data/state.json`. |
| `SERVICE_PORT` | HTTP port. Defaults to `8104`. |
| `RECONCILE_SECONDS` | Periodic HA refresh. Defaults to `60`. |
| `DRY_RUN` | When true, skip notification sends and Home Assistant `call_service` writes. Startup still connects to Home Assistant and validates configured entities. |
| `TZ`, `LOG_LEVEL` | Process timezone and log level. |

`config.example.yaml` holds every nonsecret application setting. Copy it to `config.yaml` for a private run. Secrets stay in `.env` and private `config.yaml`, never committed. `.gitignore` already excludes `.env`, `config.yaml`, `data/`, and `logs/`.

`RuntimeState.save` writes a temp file and replaces `STATE_PATH`. Start from an empty state directory for verification. Do not point a verify run at a live `data/` directory.

## Structure

- `bedtime_lights/` is the only package. `tests/` mirrors modules as `test_<module>.py`.
- `HealthServer` in `health.py` is the HTTP UI. The browser page is static HTML at `/docs`. There is no separate frontend.
- Keep generated runtime files, virtualenvs, and verification evidence out of git. Evidence from the verify skill belongs under `/opt/cursor/artifacts/verify-bedtime/` or another path outside the repo.

## Auth

never build custom auth; this service is intentionally tailnet-open, and if auth is ever needed, reuse the homelab IdP

## pstack

Each task uses one implementer and one reviewer, with no arena, swarm, or multi-judge fan-outs unless Joe asks.
