from __future__ import annotations

import asyncio
import logging
import signal

from dotenv import load_dotenv

from bedtime_lights.config import load_bedtime_config, load_service_config
from bedtime_lights.ha import HomeAssistantClient
from bedtime_lights.notifier import Notifier
from bedtime_lights.runtime_state import RuntimeState
from bedtime_lights.service import BedtimeService

LOGGER = logging.getLogger(__name__)


async def run() -> None:
    load_dotenv()
    service_config = load_service_config()
    logging.basicConfig(
        level=getattr(logging, service_config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = load_bedtime_config(service_config.config_path)
    state = RuntimeState.load(service_config.state_path)
    ha = HomeAssistantClient(dry_run=service_config.dry_run)
    service = BedtimeService(
        config,
        ha=ha,
        notifier=Notifier(dry_run=service_config.dry_run),
        state=state,
        state_path=service_config.state_path,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await ha.connect()
    try:
        states = await ha.get_states()
        await service.validate_startup(states)
        service.update_states(states)
        await service.evaluate_and_notify_now()
        ha.add_event_handler(service.handle_event)
        await ha.subscribe_events("state_changed")
        await ha.subscribe_events("mobile_app_notification_action")
        LOGGER.info("Bedtime lights watcher started")

        reconcile_task = asyncio.create_task(
            _reconcile_loop(service, ha, state, service_config.state_path, service_config.reconcile_seconds),
            name="bedtime-lights-reconcile",
        )
        stop_task = asyncio.create_task(stop_event.wait(), name="bedtime-lights-stop")
        try:
            done, pending = await asyncio.wait(
                {reconcile_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if reconcile_task in done:
                reconcile_task.result()
            for task in pending:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        finally:
            state.save(service_config.state_path)
    finally:
        await ha.close()


async def _reconcile_loop(
    service: BedtimeService,
    ha: HomeAssistantClient,
    state: RuntimeState,
    state_path: str,
    reconcile_seconds: int,
) -> None:
    while True:
        await asyncio.sleep(reconcile_seconds)
        states = await ha.get_states()
        service.update_states(states)
        await service.evaluate_and_notify_now()
        state.save(state_path)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Interrupted; exiting.", flush=True)


if __name__ == "__main__":
    main()
