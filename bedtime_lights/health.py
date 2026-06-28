from __future__ import annotations

from aiohttp import web


class HealthServer:
    def __init__(self, *, port: int) -> None:
        self._requested_port = port
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self.port = port

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._requested_port)
        await self._site.start()
        sockets = getattr(self._site._server, "sockets", None)
        if sockets:
            self.port = int(sockets[0].getsockname()[1])

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None

    async def _handle_health(self, _request: web.Request) -> web.Response:
        return web.json_response({"service": "bedtime", "status": "ok"})
