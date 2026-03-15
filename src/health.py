"""Minimal HTTP health-check server.

GET /health  →  200 OK  {"status": "ok", ...stats...}
              →  503     {"status": "degraded"} when MQTT is disconnected

Used by Docker HEALTHCHECK and monitoring tools.
"""
from __future__ import annotations

from aiohttp import web
import structlog

logger = structlog.get_logger(__name__)


class HealthServer:
    def __init__(self, port: int = 8080) -> None:
        self.port = port
        self._mqtt_connected: bool = False
        self._queue_stats: dict = {}
        self._app = web.Application()
        self._app.router.add_get("/health", self._handle_health)
        self._runner: web.AppRunner | None = None

    # ------------------------------------------------------------------ #
    # State setters (called by main coroutines)                           #
    # ------------------------------------------------------------------ #

    def set_mqtt_connected(self, value: bool) -> None:
        self._mqtt_connected = value

    def set_queue_stats(self, stats: dict) -> None:
        self._queue_stats = stats

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        logger.info("health_server_started", port=self.port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    # ------------------------------------------------------------------ #
    # Handler                                                              #
    # ------------------------------------------------------------------ #

    async def _handle_health(self, _request: web.Request) -> web.Response:
        body = {
            "status": "ok" if self._mqtt_connected else "degraded",
            "mqtt_connected": self._mqtt_connected,
            **self._queue_stats,
        }
        status_code = 200 if self._mqtt_connected else 503
        return web.json_response(body, status=status_code)
