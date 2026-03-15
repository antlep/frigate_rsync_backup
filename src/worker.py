"""Event processing worker.

Each worker runs as an independent asyncio coroutine.  Workers pull events
from the shared :class:`EventQueue`, download the media via the Frigate API,
then upload everything through rclone.

Retry strategy: exponential back-off capped at *retry_attempts*.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import structlog

from config import AppConfig
from event_queue import EventQueue
from frigate_client import FrigateClient
from models import FrigateEvent
from rclone_uploader import RcloneUploader

logger = structlog.get_logger(__name__)


class EventWorker:
    def __init__(self, worker_id: int, queue: EventQueue, config: AppConfig) -> None:
        self.worker_id = worker_id
        self.queue = queue
        self.config = config
        self._uploader = RcloneUploader(
            remote=config.rclone.remote,
            config_path=config.rclone.config_path,
            extra_flags=config.rclone.flags,
            bwlimit=config.rclone.bwlimit,
            dry_run=config.sync.dry_run,
        )
        self._log = logger.bind(worker=worker_id)

    # ------------------------------------------------------------------ #
    # Main loop                                                            #
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        self._log.info("worker_started")
        async with FrigateClient(
            host=self.config.frigate.resolved_host(),
            port=self.config.frigate.port,
            timeout=self.config.frigate.api_timeout,
        ) as frigate:
            while True:
                event = await self.queue.get()
                try:
                    await self._process_with_retry(event, frigate)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._log.exception("worker_unhandled_error", event_id=event.id, error=str(exc))
                finally:
                    self.queue.task_done()

    # ------------------------------------------------------------------ #
    # Retry wrapper                                                        #
    # ------------------------------------------------------------------ #

    async def _process_with_retry(self, event: FrigateEvent, frigate: FrigateClient) -> None:
        cfg = self.config.sync
        log = self._log.bind(event_id=event.id, camera=event.camera, label=event.label)

        for attempt in range(1, cfg.retry_attempts + 1):
            log = log.bind(attempt=attempt)
            try:
                ok = await self._process(event, frigate)
                if ok:
                    await self.queue.mark_done(event.id)
                    log.info("event_done")
                    return
                log.warning("process_returned_false")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("attempt_error", error=str(exc))

            await self.queue.increment_attempts(event.id)

            if attempt < cfg.retry_attempts:
                wait = cfg.retry_delay * (cfg.retry_backoff ** (attempt - 1))
                log.info("retry_wait", seconds=round(wait, 1))
                await asyncio.sleep(wait)

        await self.queue.mark_failed(event.id)
        log.error("event_permanently_failed")

    # ------------------------------------------------------------------ #
    # Core processing                                                      #
    # ------------------------------------------------------------------ #

    async def _process(self, event: FrigateEvent, frigate: FrigateClient) -> bool:
        cfg = self.config.sync
        tmp = Path(cfg.tmp_dir) / event.id
        tmp.mkdir(parents=True, exist_ok=True)

        # Remote path built from config path_template
        remote_dir = event.render_path(cfg.path_template)
        stem = event.filename_stem

        files: list[tuple[Path, str]] = []
        all_ok = True

        try:
            # ---- clip ------------------------------------------------- #
            if cfg.download_clip and event.has_clip:
                dest = tmp / f"{stem}.mp4"
                if await frigate.download_clip(event.id, dest):
                    files.append((dest, f"{remote_dir}/{stem}.mp4"))
                else:
                    # Clip not ready yet — abort so retry uploads nothing twice
                    return False

            # ---- snapshot --------------------------------------------- #
            if cfg.download_snapshot and event.has_snapshot:
                dest = tmp / f"{stem}.jpg"
                if await frigate.download_snapshot(event.id, dest):
                    files.append((dest, f"{remote_dir}/{stem}.jpg"))
                else:
                    return False

            # ---- metadata JSON ---------------------------------------- #
            if cfg.export_json:
                meta = await frigate.get_event(event.id) or event.raw
                dest = tmp / f"{stem}.json"
                dest.write_text(json.dumps(meta, indent=2, default=str))
                files.append((dest, f"{remote_dir}/{stem}.json"))

            if not files:
                self._log.warning(
                    "nothing_to_upload",
                    event_id=event.id,
                    has_clip=event.has_clip,
                    has_snapshot=event.has_snapshot,
                )
                # No media yet (Frigate sometimes fires end before clip is ready).
                # Return False to trigger a retry.
                return False

            # ---- upload all files in parallel ------------------------- #
            results = await asyncio.gather(
                *[self._uploader.upload_file(local, remote) for local, remote in files],
                return_exceptions=True,
            )

            for (local, remote), result in zip(files, results):
                if isinstance(result, Exception):
                    self._log.error("upload_exception", file=local.name, error=str(result))
                    all_ok = False
                elif not result:
                    self._log.error("upload_failed", file=local.name, remote=remote)
                    all_ok = False
                else:
                    self._log.info(
                        "uploaded",
                        file=local.name,
                        remote=remote,
                        camera=event.camera,
                        label=event.label,
                        score=round(event.score, 2),
                    )

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        return all_ok