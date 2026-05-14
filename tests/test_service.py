from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bedtime_lights.config import (
    ActionConfig,
    BedtimeConfig,
    NightWindowConfig,
    NotificationConfig,
    PixelConfig,
)
from bedtime_lights.runtime_state import RuntimeState
from bedtime_lights.service import BedtimeService


NY = ZoneInfo("America/New_York")


@dataclass
class FakeHomeAssistant:
    calls: list[tuple[str, str, dict]] = field(default_factory=list)

    async def call_service(self, domain: str, service: str, service_data: dict | None = None) -> dict:
        self.calls.append((domain, service, service_data or {}))
        return {"ok": True}


@dataclass
class FakeNotifier:
    sends: list[dict] = field(default_factory=list)

    async def send(self, *, title: str, message: str, tag: str, group: str, buttons: list[dict]) -> None:
        self.sends.append(
            {
                "title": title,
                "message": message,
                "tag": tag,
                "group": group,
                "buttons": buttons,
            }
        )


def config() -> BedtimeConfig:
    return BedtimeConfig(
        timezone="America/New_York",
        night_window=NightWindowConfig(start="21:45", end="04:00"),
        pixel=PixelConfig(
            battery_state_entity="sensor.pixel_battery_state",
            charger_type_entity="sensor.pixel_charger_type",
        ),
        action=ActionConfig(script_entity="script.turn_off_all_lights"),
        delayed_action_minutes=30,
        notification=NotificationConfig(
            title="Bedtime lights",
            message="Turn off the lights?",
        ),
    )


def test_evaluate_and_notify_sends_once_with_action_button() -> None:
    ha = FakeHomeAssistant()
    notifier = FakeNotifier()
    state = RuntimeState()
    service = BedtimeService(config(), ha=ha, notifier=notifier, state=state)
    service.update_state("sensor.pixel_battery_state", "charging")
    service.update_state("sensor.pixel_charger_type", "ac")

    now = datetime.fromisoformat("2026-05-12T00:15:00").replace(tzinfo=NY)
    sent = service.evaluate_and_notify_now_sync(now)
    sent_again = service.evaluate_and_notify_now_sync(now)

    assert sent is True
    assert sent_again is False
    assert len(notifier.sends) == 1
    assert notifier.sends[0]["tag"] == "bedtime-lights"
    assert notifier.sends[0]["group"] == "bedtime-lights"
    assert notifier.sends[0]["buttons"][0]["title"] == "Turn off lights"
    assert notifier.sends[0]["buttons"][0]["action"].startswith("BEDTIME_TURN_OFF_LIGHTS::")
    assert notifier.sends[0]["buttons"][1]["title"] == "Turn off in 30 min"
    assert notifier.sends[0]["buttons"][1]["action"].startswith("BEDTIME_TURN_OFF_LIGHTS_DELAY::")


def test_evaluate_and_notify_persists_sent_state(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    service = BedtimeService(
        config(),
        ha=FakeHomeAssistant(),
        notifier=FakeNotifier(),
        state=RuntimeState(),
        state_path=state_path,
    )
    service.update_state("sensor.pixel_battery_state", "charging")
    service.update_state("sensor.pixel_charger_type", "ac")

    now = datetime.fromisoformat("2026-05-12T00:15:00").replace(tzinfo=NY)
    assert service.evaluate_and_notify_now_sync(now)

    assert RuntimeState.load(state_path).last_notification_night_key == "2026-05-11"


def test_handle_action_calls_turn_on_for_configured_script() -> None:
    ha = FakeHomeAssistant()
    notifier = FakeNotifier()
    state = RuntimeState()
    token = state.mark_notification_sent("2026-05-11")
    assert token is not None
    service = BedtimeService(config(), ha=ha, notifier=notifier, state=state)

    handled = service.handle_action_sync(f"BEDTIME_TURN_OFF_LIGHTS::{token.token}")

    assert handled is True
    assert ha.calls == [
        ("script", "turn_on", {"entity_id": "script.turn_off_all_lights"})
    ]
    assert state.pending_action_token is None


def test_handle_delayed_action_schedules_turn_off() -> None:
    ha = FakeHomeAssistant()
    state = RuntimeState()
    token = state.mark_notification_sent("2026-05-11")
    assert token is not None
    service = BedtimeService(config(), ha=ha, notifier=FakeNotifier(), state=state)
    now = datetime.fromisoformat("2026-05-11T22:00:00").replace(tzinfo=NY)

    handled = service.handle_action_sync(f"BEDTIME_TURN_OFF_LIGHTS_DELAY::{token.token}", now=now)

    assert handled is True
    assert ha.calls == []
    assert state.pending_action_token is None
    assert state.delayed_action_due_at == now + timedelta(minutes=30)


def test_run_due_actions_calls_configured_script_once() -> None:
    ha = FakeHomeAssistant()
    state = RuntimeState()
    token = state.mark_notification_sent("2026-05-11")
    assert token is not None
    service = BedtimeService(config(), ha=ha, notifier=FakeNotifier(), state=state)
    now = datetime.fromisoformat("2026-05-11T22:00:00").replace(tzinfo=NY)
    assert service.handle_action_sync(f"BEDTIME_TURN_OFF_LIGHTS_DELAY::{token.token}", now=now)

    assert service.run_due_actions_sync(now + timedelta(minutes=30))
    assert not service.run_due_actions_sync(now + timedelta(minutes=31))

    assert ha.calls == [
        ("script", "turn_on", {"entity_id": "script.turn_off_all_lights"})
    ]


def test_handle_action_persists_handled_state(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    state = RuntimeState()
    token = state.mark_notification_sent("2026-05-11")
    assert token is not None
    service = BedtimeService(
        config(),
        ha=FakeHomeAssistant(),
        notifier=FakeNotifier(),
        state=state,
        state_path=state_path,
    )

    assert service.handle_action_sync(f"BEDTIME_TURN_OFF_LIGHTS::{token.token}")

    loaded = RuntimeState.load(state_path)
    assert loaded.pending_action_token is None
    assert loaded.last_action_night_key == "2026-05-11"


def test_handle_action_ignores_stale_token() -> None:
    ha = FakeHomeAssistant()
    service = BedtimeService(config(), ha=ha, notifier=FakeNotifier(), state=RuntimeState())

    handled = service.handle_action_sync("BEDTIME_TURN_OFF_LIGHTS::stale")

    assert handled is False
    assert ha.calls == []
