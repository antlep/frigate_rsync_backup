"""Periodic retention cleaner.

Deletes files older than ``retention_days`` from the rclone remote.
Runs once at startup, then every 24h.

Strategy: rclone uses ``--min-age`` to filter old files, then
``rclone delete`` + ``rclone rmdirs`` to remove empty folders.
This respects the path_template structure whatever it is.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from config import AppConfig

logger = structlog.get_logger(__name__)

_24H = 60 * 60 * 24


class RetentionCleaner:
    def __init__(self, config: AppConfig, queue=None, remote_log=None) -> None:
        self._config = config
        self._retention_days = config.sync.retention_days
        self._queue = queue
        self._remote_log = remote_log

    # ------------------------------------------------------------------ #
    # Main loop                                                            #
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        if self._retention_days <= 0:
            logger.info("retention_disabled")
            return

        logger.info("retention_cleaner_started", retention_days=self._retention_days)

        while True:
            await self._clean()
            await asyncio.sleep(_24H)

    # ------------------------------------------------------------------ #
    # Cleanup                                                              #
    # ------------------------------------------------------------------ #

    async def _clean(self) -> None:
        cfg = self._config
        remote = cfg.rclone.remote
        min_age = f"{self._retention_days}d"
        log = logger.bind(remote=remote, min_age=min_age)

        if cfg.sync.dry_run:
            log.info("retention_dry_run")
            return

        log.info("retention_cleanup_start")

        # Step 1 — delete files older than retention_days
        delete_cmd = [
            "rclone", "delete",
            "--config", cfg.rclone.config_path,
            "--min-age", min_age,
            "--log-level", "ERROR",
            remote,
        ]
        ok = await self._run(delete_cmd, "retention_delete")
        if not ok:
            return

        # Step 2 — remove empty directories left behind
        rmdirs_cmd = [
            "rclone", "rmdirs",
            "--config", cfg.rclone.config_path,
            "--log-level", "ERROR",
            "--leave-root",   # never delete the root remote folder itself
            remote,
        ]
        await self._run(rmdirs_cmd, "retention_rmdirs")

        log.info("retention_cleanup_done", next_run="in 24h")

        # Daily: purge old SQLite events and rotate remote log
        if self._queue:
            await self._queue.purge_old_events(self._retention_days)
        if self._remote_log:
            self._remote_log.rotate(self._retention_days)
            await self._remote_log.sync_now()

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    async def _run(self, cmd: list[str], event: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0:
                logger.debug(f"{event}_ok")
                return True

            logger.error(
                f"{event}_failed",
                returncode=proc.returncode,
                stderr=stderr.decode(errors="replace").strip(),
            )
            return False

        except FileNotFoundError:
            logger.error(f"{event}_rclone_not_found")
            return False
        except OSError as exc:
            logger.error(f"{event}_os_error", error=str(exc))
            return False