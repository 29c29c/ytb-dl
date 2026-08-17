from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ItemState(str, Enum):
    READY = "就绪"
    ENRICHING = "获取中"
    UNAVAILABLE = "不可用"
    QUEUED = "等待下载"
    DOWNLOADING = "下载中"
    POSTPROCESSING = "后处理中"
    PAUSED = "已暂停"
    COMPLETED = "已下载"
    FAILED = "失败"
    CANCELLED = "已取消"


class MediaMode(str, Enum):
    BEST = "best"
    VIDEO = "video"
    AUDIO = "audio"
    CUSTOM = "custom"


@dataclass(slots=True)
class VideoItem:
    video_id: str
    title: str
    uploader: str
    upload_date: str
    webpage_url: str
    extractor: str = "youtube"
    selected: bool = False
    state: ItemState = ItemState.READY
    error: str = ""
    downloaded_path: str = ""
    expected_size: int | None = None
    size_pending: bool = False

    @property
    def key(self) -> str:
        return f"{self.extractor}:{self.video_id}"

    @property
    def searchable_text(self) -> str:
        return "\n".join((self.title, self.uploader, self.upload_date, self.webpage_url)).casefold()


@dataclass(slots=True)
class ScanRequest:
    url: str
    cookie_browser: str | None = None
    cookie_profile: str | None = None
    max_items: int | None = None
    format_rule: FormatRule = field(default_factory=lambda: FormatRule())


@dataclass(slots=True)
class FormatRule:
    mode: MediaMode = MediaMode.BEST
    max_height: int | None = None
    container: str = "auto"
    video_codec: str = "auto"
    audio_codec: str = "auto"
    audio_format: str = "m4a"
    audio_quality: str = "0"
    subtitle_languages: list[str] = field(default_factory=list)
    include_manual_subtitles: bool = False
    include_auto_subtitles: bool = False
    embed_subtitles: bool = False
    custom_selector: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = {name: getattr(self, name) for name in self.__dataclass_fields__}
        result["mode"] = self.mode.value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FormatRule":
        allowed = set(cls.__dataclass_fields__)
        clean = {key: value for key, value in data.items() if key in allowed}
        try:
            clean["mode"] = MediaMode(clean.get("mode", MediaMode.BEST.value))
        except ValueError:
            clean["mode"] = MediaMode.BEST
        return cls(**clean)


@dataclass(slots=True)
class FormatInfo:
    format_id: str
    extension: str
    resolution: str
    fps: float | None
    video_codec: str
    audio_codec: str
    bitrate: float | None
    filesize: int | None

    @property
    def has_video(self) -> bool:
        return bool(self.video_codec and self.video_codec != "none")

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_codec and self.audio_codec != "none")


@dataclass(slots=True)
class DownloadJob:
    item: VideoItem
    destination: Path
    rule: FormatRule
    format_override: str | None = None
    cookie_browser: str | None = None
    cookie_profile: str | None = None


@dataclass(slots=True)
class DownloadProgress:
    key: str
    percent: float = 0.0
    speed: float | None = None
    eta: int | None = None
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    stage: str = "下载中"
    filename: str = ""
