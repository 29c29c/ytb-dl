from __future__ import annotations

import re
from typing import Any

from .models import FormatRule, MediaMode


class InvalidFormatSelector(ValueError):
    pass


def validate_format_selector(selector: str) -> str:
    selector = selector.strip()
    if not selector:
        raise InvalidFormatSelector("格式选择表达式不能为空")
    if any(char in selector for char in ("\n", "\r", "\x00")):
        raise InvalidFormatSelector("格式选择表达式不能包含换行或空字符")
    pairs = {"[": "]", "(": ")"}
    stack: list[str] = []
    for char in selector:
        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                raise InvalidFormatSelector("格式选择表达式括号不匹配")
    if stack:
        raise InvalidFormatSelector("格式选择表达式括号不匹配")
    return selector


def build_format_selector(rule: FormatRule) -> str:
    if rule.mode is MediaMode.CUSTOM:
        return validate_format_selector(rule.custom_selector)
    if rule.mode is MediaMode.AUDIO:
        return "bestaudio/best"
    if rule.mode is MediaMode.BEST:
        return "bv*+ba/b"

    height = f"[height<={int(rule.max_height)}]" if rule.max_height else ""
    codec_filter = {
        "h264": "[vcodec~='^(avc|h264)']",
        "vp9": "[vcodec^=vp9]",
        "av1": "[vcodec^=av01]",
    }.get(rule.video_codec, "")
    audio_filter = {
        "m4a": "[ext=m4a]",
        "opus": "[acodec^=opus]",
    }.get(rule.audio_codec, "")
    preferred = f"bv*{height}{codec_filter}+ba{audio_filter}"
    fallback = f"bv*{height}+ba/b{height}"
    return f"{preferred}/{fallback}"


def build_download_options(rule: FormatRule) -> dict[str, Any]:
    options: dict[str, Any] = {"format": build_format_selector(rule)}
    if rule.container != "auto" and rule.mode is not MediaMode.AUDIO:
        options["merge_output_format"] = rule.container

    postprocessors: list[dict[str, Any]] = []
    if rule.mode is MediaMode.AUDIO:
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": rule.audio_format,
                "preferredquality": rule.audio_quality,
            }
        )

    if rule.include_manual_subtitles or rule.include_auto_subtitles:
        options["writesubtitles"] = rule.include_manual_subtitles
        options["writeautomaticsub"] = rule.include_auto_subtitles
        options["subtitleslangs"] = rule.subtitle_languages or ["all", "-live_chat"]
        options["subtitlesformat"] = "srt/ass/best"
        if rule.embed_subtitles and rule.mode is not MediaMode.AUDIO:
            postprocessors.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})

    if postprocessors:
        options["postprocessors"] = postprocessors
    return options


def normalize_upload_date(value: Any) -> str:
    if value is None:
        return "未知"
    text = str(value).strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    return "未知"


def human_bytes(value: int | float | None) -> str:
    if value is None:
        return "未知"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return "未知"


def _stream_size(format_data: dict[str, Any], duration: float | None) -> int | None:
    direct = format_data.get("filesize") or format_data.get("filesize_approx")
    if direct:
        return int(direct)
    bitrate = format_data.get("tbr") or (
        (format_data.get("vbr") or 0) + (format_data.get("abr") or 0)
    )
    if duration and bitrate:
        return round(float(duration) * float(bitrate) * 1000 / 8)
    return None


def estimate_expected_size(info: dict[str, Any], rule: FormatRule) -> int | None:
    """Estimate the selected output size from yt-dlp metadata and format rows."""
    duration_value = info.get("duration")
    try:
        duration = float(duration_value) if duration_value else None
    except (TypeError, ValueError):
        duration = None

    if rule.mode is MediaMode.AUDIO and duration:
        if rule.audio_format == "wav":
            bitrate = 1411
        elif rule.audio_format == "flac":
            bitrate = 900
        elif rule.audio_quality.isdigit() and rule.audio_quality != "0":
            bitrate = int(rule.audio_quality)
        elif rule.audio_format == "opus":
            bitrate = 160
        else:
            bitrate = 256
        return round(duration * bitrate * 1000 / 8)

    formats = [
        row for row in (info.get("formats") or [])
        if (row.get("vcodec") not in (None, "none") or row.get("acodec") not in (None, "none"))
    ]
    if not formats:
        direct = info.get("filesize") or info.get("filesize_approx")
        return int(direct) if direct else None

    if rule.mode is MediaMode.AUDIO:
        audio = [row for row in formats if row.get("acodec") not in (None, "none")]
        return _stream_size(audio[-1], duration) if audio else None

    videos = [row for row in formats if row.get("vcodec") not in (None, "none")]
    if rule.mode is MediaMode.VIDEO and rule.max_height:
        capped = [row for row in videos if row.get("height") and row.get("height") <= rule.max_height]
        videos = capped
    if not videos:
        return None

    codec_matches: list[dict[str, Any]] = []
    if rule.mode is MediaMode.VIDEO and rule.video_codec != "auto":
        patterns = {
            "h264": ("avc", "h264"),
            "vp9": ("vp9",),
            "av1": ("av01", "av1"),
        }.get(rule.video_codec, ())
        codec_matches = [
            row for row in videos
            if str(row.get("vcodec") or "").casefold().startswith(patterns)
        ]
    selected_video = (codec_matches or videos)[-1]
    video_size = _stream_size(selected_video, duration)
    if selected_video.get("acodec") not in (None, "none"):
        return video_size

    audio_only = [
        row for row in formats
        if row.get("vcodec") in (None, "none") and row.get("acodec") not in (None, "none")
    ]
    if not audio_only:
        return video_size
    audio_size = _stream_size(audio_only[-1], duration)
    if video_size is None or audio_size is None:
        return video_size or audio_size
    return video_size + audio_size


def sanitize_windows_component(value: str) -> str:
    """Sanitize one path component for previews/tests; yt-dlp does final sanitization."""
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).rstrip(" .")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if sanitized.upper() in reserved:
        sanitized = f"_{sanitized}"
    return sanitized or "Unknown"


def friendly_error(error: BaseException | str) -> str:
    message = str(error).strip()
    lowered = message.casefold()
    mappings = (
        (("sign in", "login", "cookie"), "需要登录或 Cookie 已失效，请检查 Chrome/Edge Cookie 设置"),
        (("ffmpeg", "ffprobe"), "缺少 ffmpeg/ffprobe，无法合并或后处理媒体"),
        (("deno", "javascript runtime", "ejs"), "缺少 Deno 或 yt-dlp-ejs，YouTube 完整解析不可用"),
        (("private video", "video unavailable", "unavailable"), "视频不可用、私密或已删除"),
        (("geo", "country", "region"), "视频受到地区限制"),
        (("requested format", "format is not available"), "所选格式不可用，请调整格式规则"),
        (("unsupported url",), "不支持该网址，请输入 YouTube 频道或播放列表网址"),
    )
    for needles, friendly in mappings:
        if any(needle in lowered for needle in needles):
            return friendly
    return message or "未知错误"
