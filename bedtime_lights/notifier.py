from __future__ import annotations

import asyncio
import logging
from typing import Any

from homelab import notify_joe

LOGGER = logging.getLogger(__name__)


class Notifier:
    def __init__(self, *, dry_run: bool = False, notify: Any = None) -> None:
        self.dry_run = dry_run
        self._notify = notify

    async def send(
        self,
        *,
        title: str,
        message: str,
        tag: str,
        group: str,
        buttons: list[dict[str, Any]],
    ) -> None:
        if self.dry_run:
            LOGGER.info("DRY_RUN notification title=%s tag=%s group=%s", title, tag, group)
            return
        if self._notify is not None:
            await self._notify(
                title=title,
                message=message,
                tag=tag,
                group=group,
                buttons=buttons,
            )
            return
        await asyncio.to_thread(
            notify_joe,
            title,
            message,
            tag=tag,
            group=group,
            buttons=buttons,
        )

    def send_sync(
        self,
        *,
        title: str,
        message: str,
        tag: str,
        group: str,
        buttons: list[dict[str, Any]],
    ) -> None:
        asyncio.run(
            self.send(
                title=title,
                message=message,
                tag=tag,
                group=group,
                buttons=buttons,
            )
        )
