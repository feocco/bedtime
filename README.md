# Bedtime Lights

Small Home Assistant service that sends one bedtime notification per night when:

- the local time is inside the configured night window
- the configured phone battery state is charging or full on a real charger

The notification includes mobile action buttons to turn lights off immediately,
schedule the same action after 1 minute, or schedule it after the configured
delay. When an action fires, the service calls the configured Home Assistant script, usually
`script.turn_off_all_lights`.

The service also keeps a local per-night usage history. If a bedtime notification
was sent and no action was used, it sends one morning follow-up notification
with an inline text reply action for recording why it was skipped.

The Home Assistant WebSocket is treated as a long-running connection. If a
periodic reconcile or event stream fails, the service closes the client,
reconnects, validates state, and re-subscribes instead of exiting the process.

The process also serves `GET /health` on `SERVICE_PORT` for homelab health
checks and dashboard status dots.

## Configuration

Runtime secrets come from environment variables. Personal Home Assistant entity
IDs belong in a private `config.yaml`, not in this public repo.

```bash
cp .env.example .env
cp config.example.yaml config.yaml
```

Then run:

```bash
bedtime-lights
```

For local development:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/pytest -q
```
