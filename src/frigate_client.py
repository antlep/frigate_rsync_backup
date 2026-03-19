"""Async HTTP client for the Frigate REST API."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

import aiohttp
import structlog

logger = structlog.get_logger(__name__)


class FrigateClient:
    """Thin async wrapper around the Frigate HTTP API.

    Use as an async context manager::

        async with FrigateClient("192.168.1.10", 5000) as client:
            await client.download_clip(event_id, dest_path)
    """

    def __init__(self, host: str, port: int, timeout: int = 30) -> None:
        self.base_url = f"http://{host}:{port}"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> FrigateClient:
        self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._session:
            await self._session.close()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def probe_clip(self, event_id: str) -> bool:
        """Return True if the clip URL responds with HTTP 200 (non-blocking HEAD)."""
        url = f"{self.base_url}/api/events/{event_id}/clip.mp4"
        try:
            async with self._session.head(url) as resp:  # type: ignore[union-attr]
                return resp.status == 200
        except aiohttp.ClientError:
            return False

    async def download_clip(self, event_id: str, dest: Path) -> bool:
        url = f"{self.base_url}/api/events/{event_id}/clip.mp4"
        return await self._stream_to_file(url, dest)

    async def download_snapshot(self, event_id: str, dest: Path) -> bool:
        url = f"{self.base_url}/api/events/{event_id}/snapshot.jpg"
        return await self._stream_to_file(url, dest)

    async def get_event(self, event_id: str) -> Optional[dict[str, Any]]:
        url = f"{self.base_url}/api/events/{event_id}"
        try:
            async with self._session.get(url) as resp:  # type: ignore[union-attr]
                if resp.status == 200:
                    return await resp.json()
                logger.warning(
                    "frigate_event_not_found",
                    event_id=event_id,
                    status=resp.status,
                )
        except aiohttp.ClientError as exc:
            logger.error("frigate_get_event_error", event_id=event_id, error=str(exc))
        return None

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    async def _stream_to_file(self, url: str, dest: Path) -> bool:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with self._session.get(url) as resp:  # type: ignore[union-attr]
                if resp.status != 200:
                    logger.warning(
                        "frigate_download_failed", url=url, status=resp.status
                    )
                    return False
                with open(dest, "wb") as fh:
                    async for chunk in resp.content.iter_chunked(65_536):
                        fh.write(chunk)
            logger.debug("frigate_downloaded", dest=str(dest))
            return True
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as exc:
            logger.error("frigate_stream_error", url=url, error=str(exc))
            return False