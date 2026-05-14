from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from homelab import NotificationActionRouter

from bedtime_lights.config import BedtimeConfig
from bedtime_lights.rules import (
    BedtimeInputs,
    NightWindow,
    PixelPower,
    evaluate_bedtime,
)
from bedtime_lights.runtime_state import RuntimeState

LOGGER = logging.getLogger(__name__)
ACTION_PREFIX = "BEDTIME_TURN_OFF_LIGHTS"
DELAY_ACTION_PREFIX = "BEDTIME_TURN_OFF_LIGHTS_DELAY"
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
        self.action_router.register(DELAY_ACTION_PREFIX, self._handle_action_value_sync)

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
        decision = evaluate_bedtime(self._inputs(now), self._night_window())
        if not decision.should_notify or not decision.night_key:
            return False
        token = self.state.mark_notification_sent(decision.night_key)
        if token is None:
            return False
        action = NotificationActionRouter.make_action(ACTION_PREFIX, token.token)
        delay_action = NotificationActionRouter.make_action(DELAY_ACTION_PREFIX, token.token)
        await self.notifier.send(
            title=self.config.notification.title,
            message=self.config.notification.message,
            tag=NOTIFICATION_TAG,
            group=NOTIFICATION_TAG,
            buttons=[
                {"title": "Turn off lights", "action": action},
                {
                    "title": f"Turn off in {self.config.delayed_action_minutes} min",
                    "action": delay_action,
                },
            ],
        )
        self._save_state()
        LOGGER.info("Sent bedtime lights notification for night=%s", decision.night_key)
        return True

    def evaluate_and_notify_now_sync(self, now: datetime) -> bool:
        return asyncio.run(self.evaluate_and_notify_now(now))

    async def handle_action(self, action: str, now: datetime | None = None) -> bool:
        now = now or datetime.now(ZoneInfo(self.config.timezone))
        prefix, separator, token = action.partition("::")
        if not separator:
            return False
        if prefix == DELAY_ACTION_PREFIX:
            due_at = now + timedelta(minutes=self.config.delayed_action_minutes)
            if not self.state.schedule_delayed_action(token, due_at=due_at):
                LOGGER.info("Ignoring stale bedtime lights delay action")
                return False
            self._save_state()
            LOGGER.info("Scheduled %s for %s", self.config.action.script_entity, due_at.isoformat())
            return True
        if prefix != ACTION_PREFIX:
            return False
        if not self.state.mark_action_handled(token):
            LOGGER.info("Ignoring stale bedtime lights action")
            return False
        await self._call_light_script()
        self._save_state()
        LOGGER.info("Ran %s from bedtime lights action", self.config.action.script_entity)
        return True

    def handle_action_sync(self, action: str, now: datetime | None = None) -> bool:
        return asyncio.run(self.handle_action(action, now=now))

    async def run_due_actions(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(ZoneInfo(self.config.timezone))
        if not self.state.pop_due_delayed_action(now):
            return False
        await self._call_light_script()
        self._save_state()
        LOGGER.info("Ran %s from delayed bedtime lights action", self.config.action.script_entity)
        return True

    def run_due_actions_sync(self, now: datetime) -> bool:
        return asyncio.run(self.run_due_actions(now))

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
        return BedtimeInputs(
            now=now,
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
        action = (event.get("data") or {}).get("action")
        if isinstance(action, str):
            self.handle_action_sync(action)

    def _save_state(self) -> None:
        if self.state_path is not None:
            self.state.save(self.state_path)

    async def _call_light_script(self) -> None:
        await self.ha.call_service(
            "script",
            "turn_on",
            {"entity_id": self.config.action.script_entity},
        )
