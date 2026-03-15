"""Async wrapper around the rclone CLI."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class RcloneUploader:
    """Calls ``rclone copyto`` via asyncio subprocess.

    Each :meth:`upload_file` is fully non-blocking: it spawns rclone as a
    child process and awaits its completion without touching the event loop.

    A per-directory asyncio.Lock prevents two workers from uploading to the
    same Google Drive folder simultaneously, which would cause duplicate
    folder entries (GDrive allows duplicate names unlike a real filesystem).
    """

    def __init__(
        self,
        remote: str,
        config_path: str,
        extra_flags: Optional[list[str]] = None,
        bwlimit: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        self.remote = remote
        self.config_path = config_path
        self.extra_flags = extra_flags or []
        self.bwlimit = bwlimit
        self.dry_run = dry_run
        self._dir_locks: dict[str, asyncio.Lock] = {}

    def _get_dir_lock(self, remote_subpath: str) -> asyncio.Lock:
        """Return (creating if needed) a lock for the destination directory."""
        directory = remote_subpath.rsplit("/", 1)[0] if "/" in remote_subpath else remote_subpath
        if directory not in self._dir_locks:
            self._dir_locks[directory] = asyncio.Lock()
        return self._dir_locks[directory]

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def upload_file(self, local_path: Path, remote_subpath: str) -> bool:
        """Upload *local_path* to ``{remote}/{remote_subpath}``.

        Returns True on success, False on failure.
        """
        dest = f"{self.remote}/{remote_subpath}"

        if self.dry_run:
            logger.info(
                "rclone_dry_run",
                src=str(local_path),
                dest=dest,
            )
            return True

        cmd = self._build_cmd(str(local_path), dest)
        async with self._get_dir_lock(remote_subpath):
            return await self._run(cmd)

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _build_cmd(self, src: str, dest: str) -> list[str]:
        cmd: list[str] = [
            "rclone",
            "copyto",
            "--config", self.config_path,
            "--log-level", "ERROR",   # rclone stderr → only errors
            "--retries", "1",         # retry logic is handled by EventWorker
        ]
        if self.bwlimit:
            cmd += ["--bwlimit", self.bwlimit]
        cmd += self.extra_flags
        cmd += [src, dest]
        return cmd

    async def _run(self, cmd: list[str]) -> bool:
        log = logger.bind(dest=cmd[-1])
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0:
                log.info("rclone_ok")
                return True

            log.error(
                "rclone_failed",
                returncode=proc.returncode,
                stderr=stderr.decode(errors="replace").strip(),
            )
            return False

        except FileNotFoundError:
            log.error("rclone_not_found", hint="Is rclone installed in the container?")
            return False
        except OSError as exc:
            log.error("rclone_os_error", error=str(exc))
            return False