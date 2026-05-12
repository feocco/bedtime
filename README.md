# Bedtime Lights

Small Home Assistant service that sends one bedtime notification per night when:

- the local time is inside the configured night window
- a configured bed-side presence timestamp indicates someone is currently in bed
- the configured phone battery state is charging or full on a real charger

The notification includes a mobile action button. When tapped, the service calls
the configured Home Assistant script, usually `script.turn_off_all_lights`.

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
