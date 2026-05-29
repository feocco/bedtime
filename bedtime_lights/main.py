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
RECONNECT_DELAY_SECONDS = 10


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

    ha.add_event_handler(service.handle_event)
    while not stop_event.is_set():
        try:
            await _start_connected_service(service, ha, state, service_config.state_path)
            should_stop = await _run_until_disconnect_or_stop(
                service,
                ha,
                state,
                service_config.state_path,
                service_config.reconcile_seconds,
                stop_event,
            )
            if should_stop:
                break
        except asyncio.CancelledError:
            raise
        except Exception:
            if stop_event.is_set():
                break
            LOGGER.exception(
                "Bedtime lights watcher lost Home Assistant connection; reconnecting in %s seconds",
                RECONNECT_DELAY_SECONDS,
            )
        finally:
            state.save(service_config.state_path)
            await ha.close()
        if await _wait_for_reconnect_delay(stop_event, RECONNECT_DELAY_SECONDS):
            break


async def _start_connected_service(
    service: BedtimeService,
    ha: HomeAssistantClient,
    state: RuntimeState,
    state_path: str,
) -> None:
    await ha.connect()
    states = await ha.get_states()
    await service.validate_startup(states)
    service.update_states(states)
    await service.evaluate_and_notify_now()
    await service.run_due_actions()
    await service.evaluate_morning_prompt_now()
    service.prune_history()
    await ha.subscribe_events("state_changed")
    await ha.subscribe_events("mobile_app_notification_action")
    state.save(state_path)
    LOGGER.info("Bedtime lights watcher started")


async def _run_until_disconnect_or_stop(
    service: BedtimeService,
    ha: HomeAssistantClient,
    state: RuntimeState,
    state_path: str,
    reconcile_seconds: int,
    stop_event: asyncio.Event,
) -> bool:
    reconcile_task = asyncio.create_task(
        _reconcile_loop(service, ha, state, state_path, reconcile_seconds),
        name="bedtime-lights-reconcile",
    )
    closed_task = asyncio.create_task(ha.wait_closed(), name="bedtime-lights-ha-closed")
    stop_task = asyncio.create_task(stop_event.wait(), name="bedtime-lights-stop")
    tasks = {reconcile_task, closed_task, stop_task}
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if stop_task in done:
            return True
        for task in done:
            task.result()
        return False
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


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
        await service.run_due_actions()
        await service.evaluate_morning_prompt_now()
        service.prune_history()
        state.save(state_path)


async def _wait_for_reconnect_delay(stop_event: asyncio.Event, delay_seconds: int) -> bool:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=delay_seconds)
    except TimeoutError:
        return False
    return True


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Interrupted; exiting.", flush=True)


if __name__ == "__main__":
    main()
