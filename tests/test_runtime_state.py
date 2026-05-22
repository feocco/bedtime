from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from bedtime_lights.runtime_state import RuntimeState


def test_once_nightly_notification_creates_pending_token() -> None:
    state = RuntimeState()
    now = datetime(2026, 5, 11, 22, 0, tzinfo=timezone.utc)

    first = state.mark_notification_sent("2026-05-11", sent_at=now)
    second = state.mark_notification_sent("2026-05-11", sent_at=now)

    assert first is not None
    assert second is None
    assert state.pending_action_token == first.token
    assert state.history["2026-05-11"].notification_sent_at == now


def test_matching_action_token_marks_action_handled() -> None:
    state = RuntimeState()
    token = state.mark_notification_sent("2026-05-11")
    assert token is not None

    clicked_at = datetime(2026, 5, 11, 22, 5, tzinfo=timezone.utc)
    assert state.mark_action_handled(token.token, clicked_at=clicked_at)
    assert state.pending_action_token is None
    assert state.last_action_night_key == "2026-05-11"
    assert state.history["2026-05-11"].action_used
    assert state.history["2026-05-11"].action_type == "immediate"
    assert state.history["2026-05-11"].action_clicked_at == clicked_at


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
    assert state.history["2026-05-11"].delayed_action_ran_at == now + timedelta(minutes=30)


def test_morning_prompt_and_feedback_round_trip() -> None:
    state = RuntimeState()
    sent_at = datetime(2026, 5, 11, 22, 0, tzinfo=timezone.utc)
    prompt_at = datetime(2026, 5, 12, 12, 30, tzinfo=timezone.utc)
    reply_at = datetime(2026, 5, 12, 12, 35, tzinfo=timezone.utc)
    state.mark_notification_sent("2026-05-11", sent_at=sent_at)

    prompt = state.mark_morning_prompt_sent("2026-05-11", sent_at=prompt_at)
    assert prompt is not None
    assert state.mark_morning_prompt_sent("2026-05-11", sent_at=prompt_at) is None

    assert state.record_feedback(prompt.token, "Already off", replied_at=reply_at)
    record = state.history["2026-05-11"]
    assert record.morning_prompt_sent_at == prompt_at
    assert record.feedback_reply_at == reply_at
    assert record.feedback_text == "Already off"
    assert record.feedback_token is None


def test_morning_prompt_not_sent_when_action_was_used() -> None:
    state = RuntimeState()
    token = state.mark_notification_sent("2026-05-11")
    assert token is not None
    assert state.mark_action_handled(token.token)

    assert state.mark_morning_prompt_sent(
        "2026-05-11",
        sent_at=datetime(2026, 5, 12, 12, 30, tzinfo=timezone.utc),
    ) is None


def test_prune_history_removes_old_nights() -> None:
    state = RuntimeState()
    state.mark_notification_sent("2026-01-01")
    state.mark_notification_sent("2026-05-11")

    state.prune_history(now=datetime(2026, 7, 1, tzinfo=timezone.utc), retention_days=180)

    assert "2026-01-01" not in state.history
    assert "2026-05-11" in state.history


def test_old_state_shape_loads_without_history(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "last_notification_night_key": "2026-05-11",
                "pending_action_night_key": "2026-05-11",
                "pending_action_token": "token",
                "last_action_night_key": None,
            }
        ),
        encoding="utf-8",
    )

    state = RuntimeState.load(path)

    assert state.last_notification_night_key == "2026-05-11"
    assert state.pending_action_token == "token"
    assert state.history == {}
