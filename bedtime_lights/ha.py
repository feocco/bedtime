from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable

from homelab import HomeAssistantConfig, HomeAssistantWebSocketClient

LOGGER = logging.getLogger(__name__)
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class HomeAssistantClient:
    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._client = HomeAssistantWebSocketClient.from_env()
        self._handlers: list[EventHandler] = []
        self._client.add_event_handler(self._dispatch_event)

    @classmethod
    def from_config(cls, config: HomeAssistantConfig, *, dry_run: bool = False) -> HomeAssistantClient:
        instance = cls.__new__(cls)
        instance.dry_run = dry_run
        instance._client = HomeAssistantWebSocketClient(config)
        instance._handlers = []
        instance._client.add_event_handler(instance._dispatch_event)
        return instance

    async def connect(self) -> None:
        await self._client.connect()
        LOGGER.info("Connected to Home Assistant WebSocket")

    async def close(self) -> None:
        await self._client.close()

    async def wait_closed(self) -> None:
        await self._client.wait_closed()

    def add_event_handler(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    async def get_states(self) -> dict[str, EntityState]:
        states = await self._client.get_states()
        return {state["entity_id"]: parse_entity_state(state) for state in states}

    async def subscribe_events(self, event_type: str | None = None) -> None:
        await self._client.subscribe_events(event_type)

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.dry_run:
            LOGGER.info("DRY_RUN call_service %s.%s %s", domain, service, service_data or {})
            return {"dry_run": True}
        return await self._client.call_service(domain, service, service_data or {})

    async def _dispatch_event(self, event: dict[str, Any]) -> None:
        for handler in list(self._handlers):
            try:
                await handler(event)
            except Exception:
                LOGGER.exception("Home Assistant event handler failed")


class EntityState:
    def __init__(self, entity_id: str, state: str, last_changed: datetime | None = None) -> None:
        self.entity_id = entity_id
        self.state = state
        self.last_changed = last_changed


def parse_entity_state(raw: dict[str, Any]) -> EntityState:
    return EntityState(
        entity_id=str(raw["entity_id"]),
        state=str(raw.get("state", "")),
        last_changed=_parse_datetime(raw.get("last_changed")),
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

