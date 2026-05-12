from __future__ import annotations

import json

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
