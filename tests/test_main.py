from __future__ import annotations

import asyncio

import pytest

from bedtime_lights.main import _run_until_disconnect_or_stop


class FakeService:
    def __init__(self) -> None:
        self.updated = False

    def update_states(self, _states) -> None:
        self.updated = True

    async def evaluate_and_notify_now(self) -> bool:
        return False

    async def run_due_actions(self) -> bool:
        return False

    async def evaluate_morning_prompt_now(self) -> bool:
        return False

    def prune_history(self) -> None:
        return None


class TimeoutHomeAssistant:
    async def get_states(self):
        raise TimeoutError

    async def wait_closed(self) -> None:
        await asyncio.Event().wait()


class IdleHomeAssistant:
    async def get_states(self):
        return {}

    async def wait_closed(self) -> None:
        await asyncio.Event().wait()


async def test_run_until_disconnect_propagates_reconcile_timeout() -> None:
    with pytest.raises(TimeoutError):
        await _run_until_disconnect_or_stop(
            FakeService(),
            TimeoutHomeAssistant(),
            state=FakeState(),
            state_path="/tmp/state.json",
            reconcile_seconds=0,
            stop_event=asyncio.Event(),
        )


async def test_run_until_disconnect_returns_true_when_stop_requested() -> None:
    stop_event = asyncio.Event()
    stop_event.set()

    should_stop = await _run_until_disconnect_or_stop(
        FakeService(),
        IdleHomeAssistant(),
        state=FakeState(),
        state_path="/tmp/state.json",
        reconcile_seconds=60,
        stop_event=stop_event,
    )

    assert should_stop is True


class FakeState:
    def save(self, _path: str) -> None:
        return None
