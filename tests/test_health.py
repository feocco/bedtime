from __future__ import annotations

import json

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


async def test_docs_endpoint_serves_browser_friendly_html() -> None:
    server = HealthServer(port=0)
    await server.start()
    try:
        async with ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{server.port}/docs") as response:
                body = await response.text()

        assert response.status == 200
        assert response.content_type == "text/html"
        assert "Bedtime Lights API Docs" in body
        assert "GET /health" in body
        assert "/openapi.json" in body
        assert "https://unpkg.com" not in body
    finally:
        await server.stop()


async def test_openapi_endpoint_serves_valid_openapi_31_json() -> None:
    server = HealthServer(port=0)
    await server.start()
    try:
        async with ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{server.port}/openapi.json") as response:
                raw = await response.text()

        document = json.loads(raw)
        assert response.status == 200
        assert response.content_type == "application/json"
        assert document["openapi"] == "3.1.0"
        assert document["info"]["title"] == "Bedtime Lights API"
        assert document["paths"]["/health"]["get"]["responses"]["200"]["description"] == "Service is healthy"
        assert document["paths"]["/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "service": {"type": "string", "const": "bedtime"},
                "status": {"type": "string", "const": "ok"},
            },
            "required": ["service", "status"],
        }
    finally:
        await server.stop()
