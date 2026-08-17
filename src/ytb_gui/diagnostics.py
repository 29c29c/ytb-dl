from __future__ import annotations

import importlib.util
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    name: str
    available: bool
    detail: str
    required_for: str


def run_diagnostics() -> list[DiagnosticResult]:
    python_ok = sys.version_info >= (3, 10)
    return [
        DiagnosticResult("Python", python_ok, sys.version.split()[0], "运行应用"),
        DiagnosticResult("PySide6", importlib.util.find_spec("PySide6") is not None, "Python 包", "图形界面"),
        DiagnosticResult("yt-dlp", importlib.util.find_spec("yt_dlp") is not None, "Python 包", "扫描与下载"),
        DiagnosticResult("yt-dlp-ejs", importlib.util.find_spec("yt_dlp_ejs") is not None, "Python 包", "完整 YouTube 支持"),
        DiagnosticResult("ffmpeg", shutil.which("ffmpeg") is not None, shutil.which("ffmpeg") or "未找到", "合并和转换"),
        DiagnosticResult("ffprobe", shutil.which("ffprobe") is not None, shutil.which("ffprobe") or "未找到", "媒体探测"),
        DiagnosticResult("Deno", shutil.which("deno") is not None, shutil.which("deno") or "未找到", "YouTube JS 挑战"),
    ]

