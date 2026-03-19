"""Application entry point.

Wires together:
  - AppConfig (YAML + env vars)
  - EventQueue (async + SQLite persistence)
  - MQTTListener (aiomqtt, auto-reconnect)
  - N × EventWorker (parallel uploads)
  - RetentionCleaner (periodic GDrive cleanup)
  - HealthServer (aiohttp, /health endpoint)
"""
from __future__ import annotations

import asyncio
import logging
import signal

import structlog

from config import AppConfig
from event_queue import EventQueue
from health import HealthServer
from mqtt_listener import MQTTListener
from retention import RetentionCleaner
from rclone_uploader import RcloneUploader
from remote_logger import RemoteLogger
from worker import EventWorker


def _setup_logging(config: AppConfig) -> None:
    level = getattr(logging, config.logging.level.upper(), logging.INFO)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]
    if config.logging.format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


async def _stats_reporter(queue: EventQueue, health: HealthServer, remote_log: "RemoteLogger", interval: float = 15.0) -> None:
    log = structlog.get_logger()
    _was_busy = False

    while True:
        try:
            stats = await queue.stats()
            health.set_queue_stats(stats)

            is_busy = (stats.get("queued", 0) + stats.get("processing", 0) + stats.get("pending", 0)) > 0

            if _was_busy and not is_busy:
                log.info(
                    "all_workers_idle",
                    done=stats.get("done", 0),
                    failed=stats.get("failed", 0),
                )
                # Sync log to GDrive immediately when all workers go idle
                await remote_log.sync_now()
            _was_busy = is_busy
        except Exception:
            pass
        await asyncio.sleep(interval)


async def main() -> None:
    config = AppConfig.load()
    _setup_logging(config)

    log = structlog.get_logger()
    frigate_host = config.frigate.resolved_host()
    mqtt_host = config.mqtt.resolved_host()

    log.info(
        "frigate_gdrive_sync_starting",
        frigate=f"{frigate_host}:{config.frigate.port}",
        mqtt=f"{mqtt_host}:{config.mqtt.port}",
        workers=config.sync.workers,
        dry_run=config.sync.dry_run,
    )
    if frigate_host != config.frigate.host:
        log.warning("frigate_host_fallback_used", configured=config.frigate.host, using=frigate_host)
    if mqtt_host != config.mqtt.host:
        log.warning("mqtt_host_fallback_used", configured=config.mqtt.host, using=mqtt_host)

    queue = EventQueue(db_path="/data/events.db")
    await queue.setup()

    health = HealthServer(port=config.health.port)

    listener = MQTTListener(config=config, on_event=queue.put)

    _orig_connect = listener._connect_and_listen  # noqa: SLF001

    async def _patched_connect(topic: str) -> None:
        try:
            await _orig_connect(topic)
        finally:
            health.set_mqtt_connected(listener.connected)
            if listener.connected:
                remote_log.info(f"MQTT connecté → {mqtt_host}:{config.mqtt.port} | topic:{config.mqtt.topic_prefix}/events")
            else:
                remote_log.info(f"MQTT déconnecté de {mqtt_host}:{config.mqtt.port}")

    listener._connect_and_listen = _patched_connect  # noqa: SLF001

    # Single shared uploader so dir-locks are effective across all workers
    shared_uploader = RcloneUploader(
        remote=config.rclone.remote,
        config_path=config.rclone.config_path,
        extra_flags=config.rclone.flags,
        bwlimit=config.rclone.bwlimit,
        dry_run=config.sync.dry_run,
    )

    remote_log = RemoteLogger(
        remote=config.rclone.remote,
        config_path=config.rclone.config_path,
        dry_run=config.sync.dry_run,
    )
    remote_log.info(
        f"Démarrage — frigate:{frigate_host}:{config.frigate.port} "
        f"mqtt:{mqtt_host}:{config.mqtt.port} "
        f"workers:{config.sync.workers} retention:{config.sync.retention_days}j"
    )

    workers = [
        EventWorker(worker_id=i, queue=queue, config=config, uploader=shared_uploader, remote_logger=remote_log)
        for i in range(config.sync.workers)
    ]

    cleaner = RetentionCleaner(config=config)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_signal(sig: signal.Signals) -> None:
        log.info("shutdown_requested", signal=sig.name)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: _on_signal(s))

    if config.health.enabled:
        await health.start()

    tasks = [
        asyncio.create_task(listener.run(), name="mqtt_listener"),
        asyncio.create_task(_stats_reporter(queue, health, remote_log), name="stats_reporter"),
        asyncio.create_task(cleaner.run(), name="retention_cleaner"),
        asyncio.create_task(remote_log.run(), name="remote_log_sync"),
        *[
            asyncio.create_task(w.run(), name=f"worker_{i}")
            for i, w in enumerate(workers)
        ],
    ]

    try:
        await stop_event.wait()
    finally:
        log.info("shutting_down", pending_tasks=len(tasks))
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await queue.close()
        await health.stop()
        await remote_log.sync_now()
        log.info("shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())