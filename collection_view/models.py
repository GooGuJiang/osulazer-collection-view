from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from typing import Any


MODE_LABELS = {
    "osu": "osu",
    "taiko": "taiko",
    "fruits": "ctb",
    "mania": "mania",
}

VISIBLE_MODES = ("All", "osu", "taiko", "ctb", "mania")


def _display_mode(short_name: str | None, missing: bool) -> str:
    if missing:
        return "missing"
    if not short_name:
        return "unknown"
    return MODE_LABELS.get(short_name, short_name)


@dataclass(slots=True)
class BeatmapEntry:
    md5: str
    title: str = ""
    title_unicode: str = ""
    artist: str = ""
    artist_unicode: str = ""
    beatmap_id: int | None = None
    beatmap_set_id: int | None = None
    star_rating: float | None = None
    circle_size: float | None = None
    overall_difficulty: float | None = None
    approach_rate: float | None = None
    drain_rate: float | None = None
    total_object_count: int | None = None
    length_ms: float | None = None
    bpm: float | None = None
    status_int: int | None = None
    difficulty_name: str = ""
    mapper: str = ""
    ruleset_short_name: str = ""
    ruleset_name: str = ""
    background_url: str = ""
    missing: bool = False

    @property
    def mode(self) -> str:
        return _display_mode(self.ruleset_short_name, self.missing)

    @property
    def name(self) -> str:
        if self.missing:
            return f"[Missing] {self.md5}"
        text = " - ".join(part for part in (self.artist, self.title) if part)
        return text or self.title or self.artist or self.md5

    @property
    def name_original(self) -> str:
        if self.missing:
            return f"[Missing] {self.md5}"
        artist = self.artist_unicode or self.artist
        title = self.title_unicode or self.title
        text = " - ".join(part for part in (artist, title) if part)
        return text or self.name

    @property
    def bid_text(self) -> str:
        return "" if self.beatmap_id is None else str(self.beatmap_id)

    @property
    def sid_text(self) -> str:
        return "" if self.beatmap_set_id is None else str(self.beatmap_set_id)

    @property
    def star_rating_text(self) -> str:
        return "" if self.star_rating is None or self.star_rating < 0 else f"{self.star_rating:.2f}"

    @property
    def cs_text(self) -> str:
        return _format_float(self.circle_size)

    @property
    def od_text(self) -> str:
        return _format_float(self.overall_difficulty)

    @property
    def ar_text(self) -> str:
        return _format_float(self.approach_rate)

    @property
    def hp_text(self) -> str:
        return _format_float(self.drain_rate)

    @property
    def note_count_text(self) -> str:
        return "" if self.total_object_count is None or self.total_object_count < 0 else str(self.total_object_count)

    @property
    def length_text(self) -> str:
        if self.length_ms is None or self.length_ms < 0:
            return ""
        total_seconds = int(round(self.length_ms / 1000))
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def bpm_text(self) -> str:
        return _format_float(self.bpm)

    @property
    def status_text(self) -> str:
        if self.status_int is None:
            return ""
        return STATUS_LABELS.get(self.status_int, str(self.status_int))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BeatmapEntry":
        return cls(
            md5=payload.get("md5", ""),
            title=payload.get("title", ""),
            title_unicode=payload.get("titleUnicode", ""),
            artist=payload.get("artist", ""),
            artist_unicode=payload.get("artistUnicode", ""),
            beatmap_id=payload.get("beatmapId"),
            beatmap_set_id=payload.get("beatmapSetId"),
            star_rating=payload.get("starRating"),
            circle_size=payload.get("circleSize"),
            overall_difficulty=payload.get("overallDifficulty"),
            approach_rate=payload.get("approachRate"),
            drain_rate=payload.get("drainRate"),
            total_object_count=payload.get("totalObjectCount"),
            length_ms=payload.get("lengthMs"),
            bpm=payload.get("bpm"),
            status_int=payload.get("statusInt"),
            difficulty_name=payload.get("difficultyName", ""),
            mapper=payload.get("mapper", ""),
            ruleset_short_name=payload.get("rulesetShortName", ""),
            ruleset_name=payload.get("rulesetName", ""),
            background_url=payload.get("backgroundUrl", ""),
            missing=bool(payload.get("missing", False)),
        )


@dataclass(slots=True)
class CollectionInfo:
    id: str
    name: str
    last_modified: str = ""
    items: list[BeatmapEntry] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def missing_count(self) -> int:
        return sum(1 for item in self.items if item.missing)

    def items_for_mode(self, mode: str) -> list[BeatmapEntry]:
        if mode == "All":
            return list(self.items)
        return [item for item in self.items if item.mode == mode]

    def count_for_mode(self, mode: str) -> int:
        return len(self.items_for_mode(mode))

    @property
    def last_modified_text(self) -> str:
        if not self.last_modified:
            return ""
        try:
            return datetime.fromisoformat(self.last_modified.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return self.last_modified

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CollectionInfo":
        return cls(
            id=payload.get("id", ""),
            name=payload.get("name", ""),
            last_modified=payload.get("lastModified", ""),
            items=[BeatmapEntry.from_dict(item) for item in payload.get("items", [])],
        )


@dataclass(slots=True)
class ExtractedData:
    source_path: str
    generated_at: str
    collections: list[CollectionInfo]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExtractedData":
        return cls(
            source_path=payload.get("sourcePath", ""),
            generated_at=payload.get("generatedAt", ""),
            collections=[CollectionInfo.from_dict(item) for item in payload.get("collections", [])],
        )


STATUS_LABELS = {
    -2: "graveyard",
    -1: "wip",
    0: "pending",
    1: "ranked",
    2: "approved",
    3: "qualified",
    4: "loved",
}


def _format_float(value: float | None) -> str:
    if value is None or not isfinite(value):
        return ""
    return f"{value:.1f}".rstrip("0").rstrip(".")
