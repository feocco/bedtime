from __future__ import annotations

from aiohttp import ClientSession

from bedtime_lights.health import HealthServer


async def test_health_server_reports_ok() -> None:
    server = HealthServer(port=0)
    await server.start()
    try:
        async with ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{server.port}/health") as response:
                payload = await response.json()

        assert response.status == 200
        assert payload == {"service": "bedtime", "status": "ok"}
    finally:
        await server.stop()
