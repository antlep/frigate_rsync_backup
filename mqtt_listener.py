"""MQTT listener for Frigate events.

Subscribes to ``{topic_prefix}/events`` and forwards completed events
(``type == "end"``) to the queue callback, applying camera / label /
score filters defined in the configuration.

Handles connection drops with an automatic reconnect loop.
"""
from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable

import aiomqtt
import structlog

from config import AppConfig
from models import FrigateEvent

logger = structlog.get_logger(__name__)

EventCallback = Callable[[FrigateEvent], Awaitable[None]]


class MQTTListener:
    def __init__(self, config: AppConfig, on_event: EventCallback) -> None:
        self._cfg = config.mqtt
        self._sync = config.sync
        self._on_event = on_event
        self.connected = False            # exposed to the health server

    # ------------------------------------------------------------------ #
    # Main loop                                                            #
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        topic = f"{self._cfg.topic_prefix}/events"

        while True:
            try:
                await self._connect_and_listen(topic)
            except asyncio.CancelledError:
                raise
            except aiomqtt.MqttError as exc:
                self.connected = False
                logger.warning("mqtt_disconnected", error=str(exc))
                await asyncio.sleep(5)
            except Exception as exc:
                self.connected = False
                logger.error("mqtt_unexpected_error", error=str(exc))
                await asyncio.sleep(5)

    # ------------------------------------------------------------------ #
    # Connection handler                                                   #
    # ------------------------------------------------------------------ #

    async def _connect_and_listen(self, topic: str) -> None:
        logger.info("mqtt_connecting", host=self._cfg.host, port=self._cfg.port)

        client_kwargs: dict = dict(
            hostname=self._cfg.host,
            port=self._cfg.port,
            identifier=self._cfg.client_id,
            keepalive=self._cfg.keepalive,
        )
        if self._cfg.username:
            client_kwargs["username"] = self._cfg.username
        if self._cfg.password:
            client_kwargs["password"] = self._cfg.password

        async with aiomqtt.Client(**client_kwargs) as client:
            self.connected = True
            logger.info("mqtt_connected", topic=topic)
            await client.subscribe(topic)

            async for message in client.messages:
                await self._handle(bytes(message.payload))

    # ------------------------------------------------------------------ #
    # Message handler                                                      #
    # ------------------------------------------------------------------ #

    async def _handle(self, payload: bytes) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.warning("mqtt_invalid_json", error=str(exc))
            return

        if data.get("type") != "end":
            return  # ignore "new" / "update" events

        try:
            event = FrigateEvent.from_mqtt_payload(data)
        except (KeyError, TypeError) as exc:
            logger.warning("mqtt_parse_error", error=str(exc))
            return

        # ---- Filters -------------------------------------------------- #
        if self._sync.cameras and event.camera not in self._sync.cameras:
            logger.debug("filtered_camera", camera=event.camera)
            return

        if self._sync.labels and event.label not in self._sync.labels:
            logger.debug("filtered_label", label=event.label)
            return

        if event.score < self._sync.min_score:
            logger.debug(
                "filtered_score",
                score=event.score,
                min_score=self._sync.min_score,
            )
            return

        logger.info(
            "event_accepted",
            event_id=event.id,
            camera=event.camera,
            label=event.label,
            score=round(event.score, 2),
            has_clip=event.has_clip,
            has_snapshot=event.has_snapshot,
        )

        await self._on_event(event)
