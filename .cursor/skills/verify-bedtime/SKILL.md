---
name: verify-bedtime
description: >-
  Launch an isolated local bedtime-lights process, doctor it, and drive GET
  /health, GET /docs, and GET /openapi.json over HTTP plus the browser docs UI.
  Use when verifying Bedtime Lights without production secrets, proving those
  endpoints, or capturing local run evidence.
---

# Verify Bedtime Lights

Drive the real `python -m bedtime_lights.main` process from this checkout. Do not import `HealthServer` as a substitute. Read `features/README.md`, then the feature file for the journey.

Python is `./.venv/bin/python`. Install with `./.venv/bin/python -m pip install -e '.[dev]'` if that binary is missing. Helper:

```bash
./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py
```

The live instance record is JSON at `/tmp/verify-bedtime/instance.json` unless you pass `--instance`. That default path is one named slot. Launch replaces only the run recorded in that slot, after a safe cleanup of that slot. Concurrent runs require distinct `--instance` files and distinct `--evidence-dir` directories.

Instance fields: `run_id`, `repo_root`, `python`, `scratch_dir`, `evidence_dir`, `instance_path`, `base_url`, `service_port`, `ha_url`, `ha_port`, `config_path`, `state_path`, `state_dir`, `service_pid`, `standin_pid`, `service_log`, `standin_log`, `started_at`. Evidence defaults to `/opt/cursor/artifacts/verify-bedtime/`. A recorded proof run may use `/opt/cursor/artifacts/verify-bedtime/final/`.

Never pass production `HA_URL`, `HA_LONG_LIVED_TOKEN`, or `HOMELAB_FUNCTIONS_TOKEN`. The helper overwrites those with fake local values. Do not add auth.

## Launch

```bash
./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py launch \
  --evidence-dir /opt/cursor/artifacts/verify-bedtime/final
```

Launch copies `config.example.yaml` into a new directory from `tempfile.mkdtemp` under `/tmp/verify-bedtime/`. It starts a local Home Assistant WebSocket stand-in on `127.0.0.1`, then runs `python -m bedtime_lights.main` with `PYTHONPATH` set to this repo root and with:

- `DRY_RUN=true`
- `CONFIG_PATH` and `STATE_PATH` under that scratch dir
- `SERVICE_PORT` and `HA_URL` on unused localhost ports
- `HA_LONG_LIVED_TOKEN=verify-bedtime-token`
- `RECONCILE_SECONDS=3600`

The process listens on `0.0.0.0` because production `HealthServer` binds that address. Verification HTTP calls use `http://127.0.0.1:$SERVICE_PORT`.

Ready is both of these, not `/health` alone (`HealthServer` starts before the HA connect loop in `bedtime_lights/main.py`):

1. `GET $base_url/health` returns JSON equal to `{"service": "bedtime", "status": "ok"}`
2. `service.log` contains `Bedtime lights watcher started`

Launch writes only the new instance JSON to stdout. If that slot already has an instance file, launch cleans that recorded run first and stays silent during that cleanup. On failure, launch still cleans the slot it started.

## Doctor

```bash
./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py doctor
```

Doctor checks the recorded instance and writes `doctor.json` plus log copies into the evidence dir. It is not read-only. Exit `0` only when all of these hold:

- `service_pid` is running `python -m bedtime_lights.main` for this checkout, with `CONFIG_PATH`, `STATE_PATH`, and `SERVICE_PORT` equal to the instance record
- that pid owns `service_port`
- `standin_pid` is this run's stand-in, matching the instance config path and HA port
- `GET $base_url/health` is `200` `application/json` with body exactly `{"service": "bedtime", "status": "ok"}`
- `service.log` contains `Bedtime lights watcher started`
- `standin.log` contains `type=get_states`

`doctor.json` also records `run_id`, `repo_root`, `python`, `service_cmdline`, `service_cwd`, and the live `CONFIG_PATH` and `SERVICE_PORT` from the process environment. Run doctor before the first drive, after any surprise, and after a failed drive. Do not drive a process this run did not launch.

## Drive

HTTP for `/health` and `/openapi.json`. HTTP plus Chrome or Chromium for `/docs`. The helper parses the rendered DOM with `html.parser` and checks `h1`, `h2`, `pre`, and `a[href="/openapi.json"]` text from `bedtime_lights/health.py`. It does not click the OpenAPI link. `GET $base_url/openapi.json` is the resolved target of that href. Do not use coordinates. The screenshot is visual evidence for the runner to inspect.

```bash
./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py drive --feature all
```

`--feature` is `health`, `docs`, `openapi`, or `all`. Drive runs doctor first and refuses a bad instance. It deletes this run's drive proof files first, then writes new ones, including `drive.json` with the current `run_id` for every outcome. Exit `0` is a full pass. Exit `1` is an HTTP or doctor failure. Exit `2` means HTTP passed and the browser capture did not.

| Feature | User action | Command | Observable result |
| --- | --- | --- | --- |
| Health | `GET /health` | `drive --feature health` | `200`, `{"service": "bedtime", "status": "ok"}` |
| Docs | Open `/docs` in a browser | `drive --feature docs` | Parsed `h1` `Bedtime Lights API Docs`, `h2` `GET /health`, `pre` JSON, `a[href="/openapi.json"]` text `/openapi.json`, plus a screenshot |
| OpenAPI | `GET /openapi.json` | `drive --feature openapi` | `openapi` `3.1.0`, `info.title` `Bedtime Lights API`, path `/health` |

Chrome lookup order, first match:

1. `/opt/google/chrome/google-chrome`
2. `/usr/bin/google-chrome-stable`
3. `/usr/bin/chromium-browser`
4. `/usr/bin/chromium`
5. `PATH` lookup for `chromium`, then `chromium-browser`

The helper does not use a PATH `google-chrome` wrapper.

`DRY_RUN=true` skips `notify_joe` and HA `call_service` writes. Confirm by reading `service.log` and `standin.log`, not by the flag name. Idle stand-in states are `discharging` / `none` / `off`, so a successful launch should not log `DRY_RUN notification`. `standin.log` must show `get_states` and `subscribe_events`.

## Evidence

Proof lives in the `--evidence-dir` you pass. Keep it outside the git work tree.

Minimum for a passing run:

- `health.request.txt`, `health.response.txt`, `health.headers.txt`
- `docs.request.txt`, `docs.response.txt`, `docs.dom.html`, `docs.ui.txt`, `docs.screenshot.png`
- `openapi.request.txt`, `openapi.response.txt`
- `service.log`, `standin.log`
- `doctor.json`, `drive.json`, `instance.json`

`drive.json` summarizes that drive. It does not stamp every other file. Exercise the real process endpoints. Do not call `HealthServer` from a one-off Python snippet and call that a proof. Capture the request and the resulting body or parsed DOM, not only the final screenshot. If Chrome is missing, HTTP evidence still ships and `docs.screenshot.blocked.txt` must name the exact Chrome command and the blocker.

## Cleanup

```bash
./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py cleanup
```

Signals `SIGTERM` then `SIGKILL` only after the pid matches this run. Service match is `bedtime_lights.main` plus this run's `CONFIG_PATH`, `STATE_PATH`, and `SERVICE_PORT`. Stand-in match is the `standin` command plus this run's config path and HA port. Copies logs into the evidence dir. Deletes `scratch_dir` only when that path is a strict child of `/tmp/verify-bedtime/`, never that root. Removes the live instance file after this run's processes are gone or proven not to be this run's processes. Leaves the evidence copy of `instance.json` in place. Safe if the instance file is missing. Never `pkill bedtime-lights`. Run cleanup after every failed iteration.

## Helpers

`scripts/verify_bedtime.py` is the only helper. Invoke it with `./.venv/bin/python`.

```bash
./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py launch --evidence-dir /opt/cursor/artifacts/verify-bedtime/final
./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py doctor
./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py drive --feature all
./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py cleanup
```

`standin` is internal to `launch`. Entity IDs come from the copied `config.example.yaml`. The fake token is `verify-bedtime-token`.

After the map or the HTTP HTML changes, run `/maintain-verification-skill`.
