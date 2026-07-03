from __future__ import annotations

from aiohttp import web


OPENAPI_SCHEMA = {
    "openapi": "3.1.0",
    "info": {
        "title": "Bedtime Lights API",
        "version": "0.1.0",
        "description": "HTTP endpoints exposed by the Bedtime Lights service.",
    },
    "paths": {
        "/health": {
            "get": {
                "operationId": "getHealth",
                "summary": "Health check",
                "responses": {
                    "200": {
                        "description": "Service is healthy",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "service": {
                                            "type": "string",
                                            "const": "bedtime",
                                        },
                                        "status": {
                                            "type": "string",
                                            "const": "ok",
                                        },
                                    },
                                    "required": ["service", "status"],
                                }
                            }
                        },
                    }
                },
            }
        }
    },
}


class HealthServer:
    def __init__(self, *, port: int) -> None:
        self._requested_port = port
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self.port = port

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/docs", self._handle_docs)
        app.router.add_get("/openapi.json", self._handle_openapi)
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

    async def _handle_docs(self, _request: web.Request) -> web.Response:
        html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Bedtime Lights API Docs</title>
    <style>
      :root {
        color-scheme: light dark;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      body {
        margin: 0;
        background: #f6f7fb;
        color: #172033;
      }
      main {
        max-width: 880px;
        margin: 0 auto;
        padding: 32px 20px 48px;
      }
      h1, h2 {
        margin-bottom: 0.4rem;
      }
      p, li {
        line-height: 1.5;
      }
      code, pre {
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .endpoint {
        background: #ffffff;
        border: 1px solid #d8deeb;
        border-radius: 8px;
        padding: 16px;
        margin: 16px 0;
      }
      pre {
        overflow-x: auto;
        background: #101827;
        color: #f8fafc;
        border-radius: 8px;
        padding: 12px;
      }
      a {
        color: #0b6bcb;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>Bedtime Lights API Docs</h1>
      <p>Operational HTTP surface for the Bedtime Lights homelab service.</p>

      <section class="endpoint">
        <h2>GET /health</h2>
        <p>Readiness endpoint used by homelab health checks and dashboard status dots.</p>
        <pre>{"service": "bedtime", "status": "ok"}</pre>
      </section>

      <section>
        <p>Machine-readable contract: <a href="/openapi.json">/openapi.json</a></p>
      </section>
    </main>
  </body>
</html>
"""
        return web.Response(text=html, content_type="text/html")

    async def _handle_openapi(self, _request: web.Request) -> web.Response:
        return web.json_response(OPENAPI_SCHEMA)
