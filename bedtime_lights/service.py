from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from homelab import NotificationActionRouter

from bedtime_lights.config import BedtimeConfig
from bedtime_lights.rules import (
    BedtimeInputs,
    NightWindow,
    PersonPresence,
    PixelPower,
    evaluate_bedtime,
)
from bedtime_lights.runtime_state import RuntimeState

LOGGER = logging.getLogger(__name__)
ACTION_PREFIX = "BEDTIME_TURN_OFF_LIGHTS"
NOTIFICATION_TAG = "bedtime-lights"


class BedtimeService:
    def __init__(
        self,
        config: BedtimeConfig,
        *,
        ha: Any,
        notifier: Any,
        state: RuntimeState,
        state_path: str | Path | None = None,
    ) -> None:
        self.config = config
        self.ha = ha
        self.notifier = notifier
        self.state = state
        self.state_path = Path(state_path) if state_path is not None else None
        self.entity_states: dict[str, str] = {}
        self.action_router = NotificationActionRouter()
        self.action_router.register(ACTION_PREFIX, self._handle_action_value_sync)

    def update_state(self, entity_id: str, state: str) -> None:
        self.entity_states[entity_id] = state

    def update_states(self, states: dict[str, Any]) -> None:
        for entity_id, state in states.items():
            self.update_state(entity_id, str(state.state))

    async def validate_startup(self, states: dict[str, Any]) -> None:
        missing = sorted(entity for entity in self.config.watched_entities if entity not in states)
        if missing:
            raise RuntimeError(f"Missing configured Home Assistant entities: {', '.join(missing)}")
        LOGGER.info("Validated %s configured Home Assistant entities", len(self.config.watched_entities))

    async def evaluate_and_notify_now(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(ZoneInfo(self.config.timezone))
        decision = evaluate_bedtime(
            self._inputs(now),
            self._night_window(),
            fresh_minutes=self.config.presence_fresh_minutes,
        )
        if not decision.should_notify or not decision.night_key:
            return False
        token = self.state.mark_notification_sent(decision.night_key)
        if token is None:
            return False
        action = NotificationActionRouter.make_action(ACTION_PREFIX, token.token)
        await self.notifier.send(
            title=self.config.notification.title,
            message=self.config.notification.message,
            tag=NOTIFICATION_TAG,
            group=NOTIFICATION_TAG,
            buttons=[{"title": "Turn off lights", "action": action}],
        )
        self._save_state()
        LOGGER.info(
            "Sent bedtime lights notification for night=%s people=%s",
            decision.night_key,
            ",".join(decision.in_bed_people),
        )
        return True

    def evaluate_and_notify_now_sync(self, now: datetime) -> bool:
        return asyncio.run(self.evaluate_and_notify_now(now))

    async def handle_action(self, action: str) -> bool:
        prefix, separator, token = action.partition("::")
        if prefix != ACTION_PREFIX or not separator:
            return False
        if not self.state.mark_action_handled(token):
            LOGGER.info("Ignoring stale bedtime lights action")
            return False
        await self.ha.call_service(
            "script",
            "turn_on",
            {"entity_id": self.config.action.script_entity},
        )
        self._save_state()
        LOGGER.info("Ran %s from bedtime lights action", self.config.action.script_entity)
        return True

    def handle_action_sync(self, action: str) -> bool:
        return asyncio.run(self.handle_action(action))

    async def handle_event(self, event: dict[str, Any]) -> None:
        if event.get("event_type") == "state_changed":
            await self._handle_state_changed(event)
            await self.evaluate_and_notify_now()
            return
        if event.get("event_type") == "mobile_app_notification_action":
            action = (event.get("data") or {}).get("action")
            if isinstance(action, str):
                await self.handle_action(action)

    async def _handle_state_changed(self, event: dict[str, Any]) -> None:
        data = event.get("data") or {}
        entity_id = data.get("entity_id")
        new_state = data.get("new_state") or {}
        state = new_state.get("state") if isinstance(new_state, dict) else None
        if isinstance(entity_id, str) and state is not None:
            self.update_state(entity_id, str(state))

    def _inputs(self, now: datetime) -> BedtimeInputs:
        people = [
            PersonPresence(
                name=person.name,
                presence_start=_parse_datetime(self.entity_states.get(person.presence_start_entity)),
                presence_end=_parse_datetime(self.entity_states.get(person.presence_end_entity)),
            )
            for person in self.config.people
        ]
        return BedtimeInputs(
            now=now,
            people=people,
            pixel=PixelPower(
                battery_state=self.entity_states.get(self.config.pixel.battery_state_entity),
                charger_type=self.entity_states.get(self.config.pixel.charger_type_entity),
            ),
        )

    def _night_window(self) -> NightWindow:
        return NightWindow(
            start=self.config.night_window.start,
            end=self.config.night_window.end,
            timezone=self.config.timezone,
        )

    def _handle_action_value_sync(self, value: str, event: dict[str, Any]) -> None:
        self.handle_action_sync(NotificationActionRouter.make_action(ACTION_PREFIX, value))

    def _save_state(self) -> None:
        if self.state_path is not None:
            self.state.save(self.state_path)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value or value in {"unknown", "unavailable"}:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
