from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .formatting import build_download_options, estimate_expected_size, friendly_error, normalize_upload_date
from .models import DownloadJob, DownloadProgress, FormatInfo, ItemState, ScanRequest, VideoItem


StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[DownloadProgress], None]


class BackendError(RuntimeError):
    pass


class _Logger:
    def __init__(self, callback: StatusCallback | None = None):
        self.callback = callback

    def debug(self, message: str) -> None:
        if self.callback and message and not message.startswith("[debug] "):
            self.callback(message)

    info = debug

    def warning(self, message: str) -> None:
        if self.callback:
            self.callback(f"警告：{message}")

    def error(self, message: str) -> None:
        if self.callback:
            self.callback(f"错误：{message}")


def _cookie_options(browser: str | None, profile: str | None) -> dict[str, Any]:
    if not browser:
        return {}
    return {"cookiesfrombrowser": (browser, profile or None, None, None)}


def _video_url(info: dict[str, Any]) -> str:
    url = info.get("webpage_url") or info.get("original_url") or info.get("url") or ""
    video_id = str(info.get("id") or "")
    if url and str(url).startswith(("http://", "https://")):
        return str(url)
    extractor = str(info.get("extractor_key") or info.get("extractor") or "").casefold()
    if video_id and "youtube" in extractor:
        return f"https://www.youtube.com/watch?v={video_id}"
    return str(url)


def item_from_info(
    info: dict[str, Any],
    *,
    enriching: bool = False,
    full: bool = False,
    format_rule=None,
) -> VideoItem:
    video_id = str(info.get("id") or "").strip()
    title = str(info.get("title") or info.get("fulltitle") or "未知标题").strip()
    uploader = str(
        info.get("uploader")
        or info.get("channel")
        or info.get("uploader_id")
        or info.get("channel_id")
        or "未知"
    ).strip()
    upload_date = normalize_upload_date(info.get("upload_date"))
    extractor = str(info.get("extractor_key") or info.get("extractor") or "youtube").casefold()
    if "youtube" in extractor:
        extractor = "youtube"
    availability = str(info.get("availability") or "").casefold()
    error = ""
    state = ItemState.ENRICHING if enriching else ItemState.READY
    if availability in {"private", "premium_only", "subscriber_only", "needs_auth"}:
        state = ItemState.UNAVAILABLE
        error = f"视频访问状态：{availability}"
    expected_size = estimate_expected_size(info, format_rule) if format_rule else None
    return VideoItem(
        video_id=video_id,
        title=title,
        uploader=uploader,
        upload_date=upload_date,
        webpage_url=_video_url(info),
        extractor=extractor,
        state=state,
        error=error,
        expected_size=expected_size,
        size_pending=not full and expected_size is None,
    )


def needs_enrichment(item: VideoItem) -> bool:
    return (
        item.title == "未知标题"
        or item.uploader == "未知"
        or item.upload_date == "未知"
        or item.size_pending
    )


class YtDlpBackend:
    """Thin, structured wrapper around yt-dlp's Python API."""

    def _ydl_class(self):
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise BackendError("未安装 yt-dlp，请先运行 setup.ps1") from exc
        return YoutubeDL

    def validate_selector(self, selector: str) -> None:
        """Ask yt-dlp itself to parse a selector without performing network I/O."""
        YoutubeDL = self._ydl_class()
        try:
            with YoutubeDL({"format": selector, "quiet": True, "no_warnings": True}):
                pass
        except Exception as exc:
            raise BackendError(f"格式选择表达式无效：{exc}") from exc

    def scan(
        self,
        request: ScanRequest,
        *,
        cancelled: Callable[[], bool],
        on_status: StatusCallback | None = None,
    ) -> Iterator[tuple[str, VideoItem]]:
        YoutubeDL = self._ydl_class()
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "lazy_playlist": True,
            "ignoreerrors": True,
            "logger": _Logger(on_status),
        }
        options.update(_cookie_options(request.cookie_browser, request.cookie_profile))

        try:
            with YoutubeDL(options) as ydl:
                result = ydl.extract_info(request.url, download=False)
                if not result or "entries" not in result:
                    raise BackendError("请输入 YouTube 频道或播放列表网址，首版不接受单视频网址")
                entries = result.get("entries") or []
                seen: set[str] = set()
                count = 0
                for raw in entries:
                    if cancelled():
                        return
                    if request.max_items and count >= request.max_items:
                        return
                    if not raw:
                        continue
                    flat = dict(raw)
                    item = item_from_info(flat, enriching=False, format_rule=request.format_rule)
                    if not item.video_id or item.key in seen:
                        continue
                    seen.add(item.key)
                    count += 1
                    if needs_enrichment(item) and item.webpage_url:
                        item.state = ItemState.ENRICHING
                    yield "add", item

                    if item.state is ItemState.ENRICHING and not cancelled():
                        try:
                            full_options = {
                                "quiet": True,
                                "no_warnings": True,
                                "skip_download": True,
                                "noplaylist": True,
                                "logger": _Logger(on_status),
                            }
                            full_options.update(_cookie_options(request.cookie_browser, request.cookie_profile))
                            with YoutubeDL(full_options) as detail_ydl:
                                full = detail_ydl.extract_info(item.webpage_url, download=False)
                            if full:
                                enriched = item_from_info(
                                    dict(full),
                                    full=True,
                                    format_rule=request.format_rule,
                                )
                                enriched.selected = item.selected
                                yield "update", enriched
                        except Exception as exc:  # one bad item must not abort a large scan
                            item.state = ItemState.READY
                            item.error = friendly_error(exc)
                            yield "update", item
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(friendly_error(exc)) from exc

    def probe_formats(
        self,
        url: str,
        *,
        cookie_browser: str | None = None,
        cookie_profile: str | None = None,
        on_status: StatusCallback | None = None,
    ) -> list[FormatInfo]:
        YoutubeDL = self._ydl_class()
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "logger": _Logger(on_status),
        }
        options.update(_cookie_options(cookie_browser, cookie_profile))
        try:
            with YoutubeDL(options) as ydl:
                result = ydl.extract_info(url, download=False)
        except Exception as exc:
            raise BackendError(friendly_error(exc)) from exc

        formats: list[FormatInfo] = []
        for raw in (result or {}).get("formats") or []:
            video_codec = str(raw.get("vcodec") or "none")
            audio_codec = str(raw.get("acodec") or "none")
            if video_codec == "none" and audio_codec == "none":
                continue
            width, height = raw.get("width"), raw.get("height")
            resolution = raw.get("resolution") or (f"{width}x{height}" if width and height else "仅音频")
            formats.append(
                FormatInfo(
                    format_id=str(raw.get("format_id") or ""),
                    extension=str(raw.get("ext") or ""),
                    resolution=str(resolution),
                    fps=raw.get("fps"),
                    video_codec=video_codec,
                    audio_codec=audio_codec,
                    bitrate=raw.get("tbr") or raw.get("abr") or raw.get("vbr"),
                    filesize=raw.get("filesize") or raw.get("filesize_approx"),
                )
            )
        return formats

    def download(
        self,
        job: DownloadJob,
        *,
        cancelled: Callable[[], bool],
        on_progress: ProgressCallback,
        on_status: StatusCallback | None = None,
    ) -> str:
        YoutubeDL = self._ydl_class()
        actual_path = ""

        def progress_hook(data: dict[str, Any]) -> None:
            if cancelled():
                raise RuntimeError("用户取消下载")
            status = data.get("status")
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = int(data.get("downloaded_bytes") or 0)
            percent = (downloaded / total * 100.0) if total else 0.0
            on_progress(
                DownloadProgress(
                    key=job.item.key,
                    percent=max(0.0, min(percent, 100.0)),
                    speed=data.get("speed"),
                    eta=data.get("eta"),
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                    stage="下载完成，等待后处理" if status == "finished" else "下载中",
                    filename=str(data.get("filename") or ""),
                )
            )

        def postprocessor_hook(data: dict[str, Any]) -> None:
            if cancelled():
                raise RuntimeError("用户取消下载")
            on_progress(
                DownloadProgress(
                    key=job.item.key,
                    percent=100.0,
                    stage=f"后处理中：{data.get('postprocessor', '')}",
                )
            )

        def after_move_hook(data: Any) -> None:
            nonlocal actual_path
            if isinstance(data, dict):
                info = data.get("info_dict") or data
                actual_path = str(info.get("filepath") or info.get("_filename") or "")
            else:
                actual_path = str(data or "")

        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": False,
            "logger": _Logger(on_status),
            "noplaylist": True,
            "paths": {"home": str(job.destination)},
            "outtmpl": "%(uploader,channel,uploader_id|Unknown)s/%(upload_date|Unknown)s - %(title)s [%(id)s].%(ext)s",
            "windowsfilenames": True,
            "overwrites": False,
            "continuedl": True,
            "nopart": False,
            "retries": 10,
            "fragment_retries": 10,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "post_hooks": [after_move_hook],
        }
        options.update(build_download_options(job.rule))
        if job.format_override:
            options["format"] = job.format_override
        options.update(_cookie_options(job.cookie_browser, job.cookie_profile))

        try:
            Path(job.destination).mkdir(parents=True, exist_ok=True)
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(job.item.webpage_url, download=True)
                if not actual_path and info:
                    actual_path = str(info.get("filepath") or ydl.prepare_filename(info))
        except Exception as exc:
            if cancelled():
                raise BackendError("用户取消下载") from exc
            raise BackendError(friendly_error(exc)) from exc
        return actual_path
