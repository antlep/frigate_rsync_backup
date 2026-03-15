from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EventStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class FrigateEvent:
    id: str
    camera: str
    label: str
    start_time: float
    end_time: Optional[float]
    has_clip: bool
    has_snapshot: bool
    score: float = 0.0
    zones: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Factory                                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_mqtt_payload(cls, payload: dict[str, Any]) -> FrigateEvent:
        after = payload.get("after", {})
        return cls(
            id=after["id"],
            camera=after["camera"],
            label=after.get("label", "unknown"),
            start_time=after.get("start_time", 0.0),
            end_time=after.get("end_time"),
            has_clip=after.get("has_clip", False),
            has_snapshot=after.get("has_snapshot", False),
            score=after.get("score") or 0.0,
            zones=after.get("entered_zones", []),
            raw=payload,
        )

    # ------------------------------------------------------------------ #
    # Serialisation (used for SQLite persistence)                         #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "camera": self.camera,
            "label": self.label,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "has_clip": self.has_clip,
            "has_snapshot": self.has_snapshot,
            "score": self.score,
            "zones": self.zones,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FrigateEvent:
        return cls(**d)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.start_time)

    @property
    def date_str(self) -> str:
        """e.g.  2026-03-15"""
        return self.dt.strftime('%Y-%m-%d')

    def render_path(self, template: str) -> str:
        """Resolve a path template using event data.

        Available variables:
          {date}   → 2026-03-15
          {year}   → 2026
          {month}  → 2026-03
          {hour}   → 14
          {camera} → annke_02
          {label}  → person
          {id}     → 1773575581.33434-f8r7fs
          {stem}   → 2026-03-15_14-32-07_person_1773575581.33434-f8r7fs
        """
        return template.format(
            date=self.dt.strftime("%Y-%m-%d"),
            year=self.dt.strftime("%Y"),
            month=self.dt.strftime("%Y-%m"),
            hour=self.dt.strftime("%H"),
            camera=self.camera,
            label=self.label,
            id=self.id,
            stem=self.filename_stem,
        )

    @property
    def filename_stem(self) -> str:
        """e.g.  2024-12-25_14-32-07_person_abc123"""
        return f"{self.dt.strftime('%Y-%m-%d_%H-%M-%S')}_{self.label}_{self.id}"