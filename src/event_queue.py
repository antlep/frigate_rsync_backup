"""Persistent event queue backed by SQLite.

On startup, any events left in ``pending`` or ``processing`` state from a
previous run are automatically re-enqueued so no events are lost across
container restarts.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import structlog

from models import EventStatus, FrigateEvent

logger = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    camera      TEXT NOT NULL,
    data        TEXT NOT NULL,          -- JSON blob
    status      TEXT NOT NULL DEFAULT 'pending',
    attempts    INTEGER DEFAULT 0,
    created_at  TEXT,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_status ON events (status);
CREATE INDEX IF NOT EXISTS idx_events_camera ON events (camera);
"""


class EventQueue:
    """Thread-safe async queue with SQLite persistence.

    The in-memory :class:`asyncio.Queue` is the hot path; SQLite is the
    persistence layer for durability across restarts.
    """

    def __init__(self, db_path: str = "/data/events.db", max_in_memory: int = 2_000) -> None:
        self._db_path = db_path
        self._queue: asyncio.Queue[FrigateEvent] = asyncio.Queue(maxsize=max_in_memory)
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def setup(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_DDL)
        await self._db.commit()
        await self._recover()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def put(self, event: FrigateEvent) -> None:
        """Persist the event then enqueue it for processing."""
        now = _now()
        await self._db.execute(  # type: ignore[union-attr]
            """
            INSERT OR IGNORE INTO events
                (id, camera, data, status, attempts, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', 0, ?, ?)
            """,
            (event.id, event.camera, json.dumps(event.to_dict()), now, now),
        )
        await self._db.commit()  # type: ignore[union-attr]
        await self._queue.put(event)
        logger.debug("event_queued", event_id=event.id, camera=event.camera, qsize=self._queue.qsize())

    async def get(self) -> FrigateEvent:
        """Dequeue the next event (blocks until one is available)."""
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def mark_done(self, event_id: str) -> None:
        await self._set_status(event_id, EventStatus.DONE)

    async def mark_failed(self, event_id: str) -> None:
        await self._set_status(event_id, EventStatus.FAILED)

    async def increment_attempts(self, event_id: str) -> int:
        """Increment attempt counter and return the new value."""
        await self._db.execute(  # type: ignore[union-attr]
            "UPDATE events SET attempts = attempts + 1, updated_at = ? WHERE id = ?",
            (_now(), event_id),
        )
        await self._db.commit()  # type: ignore[union-attr]
        async with self._db.execute(  # type: ignore[union-attr]
            "SELECT attempts FROM events WHERE id = ?", (event_id,)
        ) as cur:
            row = await cur.fetchone()
        return row["attempts"] if row else 1

    async def purge_old_events(self, retention_days: int) -> None:
        """Delete done/failed events older than retention_days from SQLite."""
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).timestamp()
        async with self._db.execute(  # type: ignore[union-attr]
            """DELETE FROM events
               WHERE status IN ('done', 'failed')
               AND CAST(json_extract(data, '$.start_time') AS REAL) < ?"""
            , (cutoff,)
        ) as cur:
            deleted = cur.rowcount
        await self._db.commit()  # type: ignore[union-attr]
        if deleted:
            import structlog
            structlog.get_logger().info("events_purged", deleted=deleted, retention_days=retention_days)

    async def stats(self) -> dict[str, int]:
        """Return per-status counts (useful for the health endpoint)."""
        result: dict[str, int] = {s.value: 0 for s in EventStatus}
        async with self._db.execute(  # type: ignore[union-attr]
            "SELECT status, COUNT(*) AS cnt FROM events GROUP BY status"
        ) as cur:
            async for row in cur:
                result[row["status"]] = row["cnt"]
        result["queued"] = self._queue.qsize()
        return result

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    async def _recover(self) -> None:
        async with self._db.execute(  # type: ignore[union-attr]
            "SELECT id, data FROM events WHERE status IN ('pending', 'processing')"
        ) as cur:
            rows = await cur.fetchall()

        if not rows:
            return

        for row in rows:
            try:
                event = FrigateEvent.from_dict(json.loads(row["data"]))
                await self._queue.put(event)
            except Exception as exc:
                logger.warning("recovery_skip", event_id=row["id"], error=str(exc))

        logger.info("events_recovered", count=len(rows))

    async def _set_status(self, event_id: str, status: EventStatus) -> None:
        await self._db.execute(  # type: ignore[union-attr]
            "UPDATE events SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, _now(), event_id),
        )
        await self._db.commit()  # type: ignore[union-attr]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()