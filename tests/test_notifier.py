from __future__ import annotations

from bedtime_lights.notifier import Notifier


def test_dry_run_notifier_does_not_call_client() -> None:
    calls = []

    async def fake_notify(**kwargs):
        calls.append(kwargs)

    notifier = Notifier(dry_run=True, notify=fake_notify)
    notifier.send_sync(
        title="Title",
        message="Message",
        tag="tag",
        group="group",
        buttons=[{"title": "Action", "action": "PREFIX::token"}],
    )

    assert calls == []
