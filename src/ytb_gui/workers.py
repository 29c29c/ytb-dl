from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Signal, Slot

from .backend import YtDlpBackend
from .history import HistoryStore
from .models import DownloadJob, DownloadProgress, ItemState, ScanRequest, VideoItem


class ScanWorker(QObject):
    item_added = Signal(object)
    item_updated = Signal(object)
    status = Signal(str)
    failed = Signal(str)
    finished = Signal(bool)

    def __init__(self, backend: YtDlpBackend, request: ScanRequest):
        super().__init__()
        self.backend = backend
        self.request = request
        self._cancelled = threading.Event()

    def request_cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        was_cancelled = False
        try:
            for event, item in self.backend.scan(
                self.request,
                cancelled=self._cancelled.is_set,
                on_status=self.status.emit,
            ):
                if event == "add":
                    self.item_added.emit(item)
                else:
                    self.item_updated.emit(item)
            was_cancelled = self._cancelled.is_set()
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit(was_cancelled)


class FormatProbeWorker(QObject):
    status = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, backend: YtDlpBackend, url: str, browser: str | None, profile: str | None):
        super().__init__()
        self.backend = backend
        self.url = url
        self.browser = browser
        self.profile = profile

    @Slot()
    def run(self) -> None:
        try:
            formats = self.backend.probe_formats(
                self.url,
                cookie_browser=self.browser,
                cookie_profile=self.profile,
                on_status=self.status.emit,
            )
            self.succeeded.emit(formats)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class DownloadWorker(QObject):
    item_state = Signal(str, str, str)
    progress = Signal(object)
    queue_progress = Signal(int, int)
    status = Signal(str)
    finished = Signal()

    def __init__(self, backend: YtDlpBackend, jobs: list[DownloadJob], history: HistoryStore):
        super().__init__()
        self.backend = backend
        self.jobs = jobs
        self.history = history
        self._paused = threading.Event()
        self._cancel_current = threading.Event()
        self._stop_all = threading.Event()

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._paused.set()
        else:
            self._paused.clear()

    def cancel_current(self) -> None:
        self._cancel_current.set()

    def stop_all(self) -> None:
        self._stop_all.set()
        self._cancel_current.set()
        self._paused.clear()

    @Slot()
    def run(self) -> None:
        total = len(self.jobs)
        try:
            for index, job in enumerate(self.jobs, start=1):
                if self._stop_all.is_set():
                    break
                while self._paused.is_set() and not self._stop_all.is_set():
                    self.item_state.emit(job.item.key, ItemState.PAUSED.value, "")
                    time.sleep(0.1)
                if self._stop_all.is_set():
                    break
                self._cancel_current.clear()
                self.queue_progress.emit(index, total)
                self.item_state.emit(job.item.key, ItemState.DOWNLOADING.value, "")
                try:
                    path = self.backend.download(
                        job,
                        cancelled=lambda: self._cancel_current.is_set() or self._stop_all.is_set(),
                        on_progress=self.progress.emit,
                        on_status=self.status.emit,
                    )
                    if self._cancel_current.is_set() or self._stop_all.is_set():
                        self.item_state.emit(job.item.key, ItemState.CANCELLED.value, "用户取消下载")
                    else:
                        self.history.record(
                            job.item.extractor,
                            job.item.video_id,
                            job.item.title,
                            path,
                        )
                        self.item_state.emit(job.item.key, ItemState.COMPLETED.value, path)
                except Exception as exc:
                    state = ItemState.CANCELLED if self._cancel_current.is_set() else ItemState.FAILED
                    self.item_state.emit(job.item.key, state.value, str(exc))
        finally:
            self.finished.emit()

