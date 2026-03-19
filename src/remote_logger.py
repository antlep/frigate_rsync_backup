"""Remote log file synced to Google Drive.

Writes human-readable log entries to a local file (/data/frigate-sync.log)
and syncs it to the rclone remote periodically and after every ERROR.

Three levels:
  INFO    — connectivity events, startup, retention cleanup
  SUCCESS — event successfully backed up (camera, label, duration, files)
  ERROR   — event failed or discarded (camera, label, reason)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

_LOCAL_LOG = "/data/frigate-sync.log"
_REMOTE_LOG = "frigate-sync.log"   # relative to rclone remote root
_SYNC_INTERVAL = 300               # sync to GDrive every 5 minutes


class RemoteLogger:
    def __init__(
        self,
        remote: str,
        config_path: str,
        local_path: str = _LOCAL_LOG,
        dry_run: bool = False,
    ) -> None:
        self._remote = remote
        self._config_path = config_path
        self._local = Path(local_path)
        self._dry_run = dry_run
        self._lock = asyncio.Lock()
        self._dirty = False   # True when local file has unsynced entries

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def info(self, message: str) -> None:
        self._write("INFO   ", message)

    def success(
        self,
        camera: str,
        label: str,
        event_id: str,
        score: float,
        duration_s: float,
        files: list[str],
    ) -> None:
        files_str = "+".join(files) if files else "—"
        self._write(
            "SUCCESS",
            f"{camera} | {label} | score:{round(score, 2)} "
            f"| {round(duration_s, 1)}s | {files_str} | id:{event_id}",
        )

    def error(
        self,
        camera: str,
        label: str,
        event_id: str,
        reason: str,
    ) -> None:
        self._write(
            "ERROR  ",
            f"{camera} | {label} | id:{event_id} | {reason}",
        )
        # Schedule immediate sync on error (best-effort, non-blocking)
        asyncio.create_task(self._sync())

    # ------------------------------------------------------------------ #
    # Background sync loop                                                 #
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        """Periodic sync task — call as asyncio.create_task."""
        while True:
            await asyncio.sleep(_SYNC_INTERVAL)
            if self._dirty:
                await self._sync()

    async def sync_now(self) -> None:
        """Force an immediate sync (e.g. at shutdown)."""
        await self._sync()

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _write(self, level: str, message: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{level}] {message}\n"
        try:
            self._local.parent.mkdir(parents=True, exist_ok=True)
            with open(self._local, "a", encoding="utf-8") as f:
                f.write(line)
            self._dirty = True
        except OSError as exc:
            logger.error("remote_logger_write_error", error=str(exc))

    async def _sync(self) -> None:
        if self._dry_run:
            logger.debug("remote_logger_dry_run_sync")
            return

        async with self._lock:
            dest = f"{self._remote}/{_REMOTE_LOG}"
            cmd = [
                "rclone", "copyto",
                "--config", self._config_path,
                "--log-level", "ERROR",
                str(self._local),
                dest,
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode == 0:
                    self._dirty = False
                    logger.debug("remote_log_synced", dest=dest)
                else:
                    logger.warning(
                        "remote_log_sync_failed",
                        returncode=proc.returncode,
                        stderr=stderr.decode(errors="replace").strip(),
                    )
            except OSError as exc:
                logger.error("remote_log_sync_error", error=str(exc))