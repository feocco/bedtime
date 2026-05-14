from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from bedtime_lights.runtime_state import RuntimeState


def test_once_nightly_notification_creates_pending_token() -> None:
    state = RuntimeState()

    first = state.mark_notification_sent("2026-05-11")
    second = state.mark_notification_sent("2026-05-11")

    assert first is not None
    assert second is None
    assert state.pending_action_token == first.token


def test_matching_action_token_marks_action_handled() -> None:
    state = RuntimeState()
    token = state.mark_notification_sent("2026-05-11")
    assert token is not None

    assert state.mark_action_handled(token.token)
    assert state.pending_action_token is None
    assert state.last_action_night_key == "2026-05-11"


def test_stale_action_token_is_ignored() -> None:
    state = RuntimeState()
    state.mark_notification_sent("2026-05-11")

    assert not state.mark_action_handled("wrong-token")
    assert state.pending_action_token is not None


def test_state_round_trip(tmp_path) -> None:
    path = tmp_path / "state.json"
    state = RuntimeState()
    token = state.mark_notification_sent("2026-05-11")
    assert token is not None
    state.save(path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    loaded = RuntimeState.load(path)

    assert raw["last_notification_night_key"] == "2026-05-11"
    assert loaded.pending_action_token == token.token


def test_schedule_delayed_action_records_due_time() -> None:
    state = RuntimeState()
    token = state.mark_notification_sent("2026-05-11")
    assert token is not None
    now = datetime(2026, 5, 11, 22, 0, tzinfo=timezone.utc)

    assert state.schedule_delayed_action(token.token, due_at=now + timedelta(minutes=30))

    assert state.pending_action_token is None
    assert state.delayed_action_due_at == now + timedelta(minutes=30)
    assert state.delayed_action_night_key == "2026-05-11"


def test_pop_due_delayed_action_only_when_due() -> None:
    state = RuntimeState()
    token = state.mark_notification_sent("2026-05-11")
    assert token is not None
    now = datetime(2026, 5, 11, 22, 0, tzinfo=timezone.utc)
    state.schedule_delayed_action(token.token, due_at=now + timedelta(minutes=30))

    assert state.pop_due_delayed_action(now + timedelta(minutes=29)) is False
    assert state.pop_due_delayed_action(now + timedelta(minutes=30)) is True
    assert state.delayed_action_due_at is None
    assert state.last_action_night_key == "2026-05-11"
