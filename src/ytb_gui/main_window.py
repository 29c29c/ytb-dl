from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QSettings, QStandardPaths, QThread, Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from .backend import YtDlpBackend
from .diagnostics import run_diagnostics
from .dialogs import FormatsDialog, FormatSettingsDialog
from .formatting import build_format_selector, friendly_error, human_bytes
from .history import HistoryStore
from .models import DownloadJob, DownloadProgress, FormatRule, ItemState, ScanRequest, VideoItem
from .table_model import VideoFilterProxyModel, VideoTableModel
from .workers import DownloadWorker, FormatProbeWorker, ScanWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("yt-dlp 频道 / 播放列表下载器")
        self.resize(1280, 760)

        self.settings = QSettings()
        data_override = os.environ.get("YTB_GUI_DATA_DIR")
        app_data = Path(data_override) if data_override else Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        )
        self.history = HistoryStore(app_data / "history.sqlite3")
        self.backend = YtDlpBackend()
        self.format_rule = self._load_format_rule()
        self.format_overrides: dict[str, str] = {}

        self.scan_thread: QThread | None = None
        self.scan_worker: ScanWorker | None = None
        self.probe_thread: QThread | None = None
        self.probe_worker: FormatProbeWorker | None = None
        self.download_thread: QThread | None = None
        self.download_worker: DownloadWorker | None = None
        self._download_paused = False

        self.model = VideoTableModel(self)
        self.proxy = VideoFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)

        self._build_ui()
        self._build_menu()
        self._load_settings()
        self._show_dependency_summary()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

        source_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴 YouTube 频道或播放列表网址")
        self.scan_button = QPushButton("开始扫描")
        self.cancel_scan_button = QPushButton("取消扫描")
        self.cancel_scan_button.setEnabled(False)
        source_row.addWidget(QLabel("网址"))
        source_row.addWidget(self.url_input, 1)
        source_row.addWidget(self.scan_button)
        source_row.addWidget(self.cancel_scan_button)
        root.addLayout(source_row)

        auth_row = QHBoxLayout()
        self.cookie_browser = QComboBox()
        self.cookie_browser.addItem("不使用 Cookie", None)
        self.cookie_browser.addItem("Chrome", "chrome")
        self.cookie_browser.addItem("Edge", "edge")
        self.cookie_profile = QLineEdit()
        self.cookie_profile.setPlaceholderText("可选：浏览器 Profile 名称或目录")
        self.max_items = QSpinBox()
        self.max_items.setRange(0, 1_000_000)
        self.max_items.setSpecialValueText("不限")
        self.max_items.setToolTip("0 表示扫描全部")
        auth_row.addWidget(QLabel("登录态"))
        auth_row.addWidget(self.cookie_browser)
        auth_row.addWidget(self.cookie_profile, 1)
        auth_row.addWidget(QLabel("最多扫描"))
        auth_row.addWidget(self.max_items)
        root.addLayout(auth_row)

        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setPlaceholderText("搜索标题、上传者、日期或链接")
        self.match_button = QPushButton("勾选匹配")
        self.select_all_button = QPushButton("全选当前结果")
        self.clear_selection_button = QPushButton("取消当前勾选")
        self.result_count = QLabel("0 项")
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(self.match_button)
        filter_row.addWidget(self.select_all_button)
        filter_row.addWidget(self.clear_selection_button)
        filter_row.addWidget(self.result_count)
        root.addLayout(filter_row)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        self.table.setColumnWidth(0, 54)
        self.table.setColumnWidth(1, 360)
        self.table.setColumnWidth(2, 170)
        self.table.setColumnWidth(3, 105)
        self.table.setColumnWidth(4, 105)
        self.table.setColumnWidth(5, 330)
        self.table.setColumnWidth(6, 110)
        root.addWidget(self.table, 1)

        download_options_row = QHBoxLayout()
        self.destination_input = QLineEdit()
        self.destination_button = QPushButton("选择目录")
        self.format_button = QPushButton("全局格式设置")
        self.item_format_button = QPushButton("所选视频格式")
        download_options_row.addWidget(QLabel("保存到"))
        download_options_row.addWidget(self.destination_input, 1)
        download_options_row.addWidget(self.destination_button)
        download_options_row.addWidget(self.format_button)
        download_options_row.addWidget(self.item_format_button)
        root.addLayout(download_options_row)

        queue_row = QHBoxLayout()
        self.download_button = QPushButton("下载已勾选项目")
        self.pause_button = QPushButton("暂停后续任务")
        self.pause_button.setEnabled(False)
        self.cancel_download_button = QPushButton("取消当前项")
        self.cancel_download_button.setEnabled(False)
        self.retry_button = QPushButton("重试失败项")
        self.queue_label = QLabel("队列空闲")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumWidth(260)
        queue_row.addWidget(self.download_button)
        queue_row.addWidget(self.pause_button)
        queue_row.addWidget(self.cancel_download_button)
        queue_row.addWidget(self.retry_button)
        queue_row.addWidget(self.queue_label, 1)
        queue_row.addWidget(self.progress_bar)
        root.addLayout(queue_row)

        self.setCentralWidget(central)

        self.scan_button.clicked.connect(self.start_scan)
        self.cancel_scan_button.clicked.connect(self.cancel_scan)
        self.url_input.returnPressed.connect(self.start_scan)
        self.search_input.textChanged.connect(self._filter_changed)
        self.match_button.clicked.connect(lambda: self._set_visible_checked(True))
        self.select_all_button.clicked.connect(lambda: self._set_visible_checked(True))
        self.clear_selection_button.clicked.connect(lambda: self._set_visible_checked(False))
        self.destination_button.clicked.connect(self.choose_destination)
        self.format_button.clicked.connect(self.edit_format_rule)
        self.item_format_button.clicked.connect(self.probe_selected_format)
        self.download_button.clicked.connect(self.start_downloads)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.cancel_download_button.clicked.connect(self.cancel_current_download)
        self.retry_button.clicked.connect(self.retry_failed)
        self.table.doubleClicked.connect(self.open_video)

        copy_action = QAction("复制视频链接", self)
        copy_action.triggered.connect(self.copy_current_url)
        open_action = QAction("在浏览器中打开", self)
        open_action.triggered.connect(self.open_video)
        redownload_action = QAction("允许重新下载（清除历史标记）", self)
        redownload_action.triggered.connect(self.allow_redownload)
        self.table.addAction(copy_action)
        self.table.addAction(open_action)
        self.table.addAction(redownload_action)

    def _build_menu(self) -> None:
        help_menu = self.menuBar().addMenu("帮助")
        diagnostics_action = QAction("环境诊断", self)
        diagnostics_action.triggered.connect(self.show_diagnostics)
        help_menu.addAction(diagnostics_action)

    def _load_format_rule(self) -> FormatRule:
        raw = self.settings.value("format_rule", "")
        if not raw:
            return FormatRule()
        try:
            return FormatRule.from_dict(json.loads(str(raw)))
        except (TypeError, ValueError, json.JSONDecodeError):
            return FormatRule()

    def _load_settings(self) -> None:
        default_downloads = str(Path.home() / "Downloads" / "YTB-DL")
        self.destination_input.setText(str(self.settings.value("destination", default_downloads)))
        browser = self.settings.value("cookie_browser", "") or None
        browser_index = self.cookie_browser.findData(browser)
        self.cookie_browser.setCurrentIndex(max(browser_index, 0))
        self.cookie_profile.setText(str(self.settings.value("cookie_profile", "")))
        self.max_items.setValue(int(self.settings.value("max_items", 0)))

    def _save_settings(self) -> None:
        self.settings.setValue("destination", self.destination_input.text().strip())
        self.settings.setValue("cookie_browser", self.cookie_browser.currentData() or "")
        self.settings.setValue("cookie_profile", self.cookie_profile.text().strip())
        self.settings.setValue("max_items", self.max_items.value())
        self.settings.setValue("format_rule", json.dumps(self.format_rule.to_dict(), ensure_ascii=False))

    def _show_dependency_summary(self) -> None:
        missing = [item.name for item in run_diagnostics() if not item.available]
        if missing:
            self.statusBar().showMessage(f"环境提示：未找到 {', '.join(missing)}；可在“帮助 → 环境诊断”查看详情", 15000)
        else:
            self.statusBar().showMessage("环境检查通过", 5000)

    def show_diagnostics(self) -> None:
        lines = []
        for item in run_diagnostics():
            icon = "✓" if item.available else "✗"
            lines.append(f"{icon} {item.name}：{item.detail}（用于{item.required_for}）")
        QMessageBox.information(self, "环境诊断", "\n".join(lines))

    def _valid_source_url(self, text: str) -> bool:
        try:
            parsed = urlparse(text)
        except ValueError:
            return False
        host = (parsed.hostname or "").casefold()
        return parsed.scheme in {"http", "https"} and (host == "youtu.be" or host.endswith("youtube.com"))

    def start_scan(self) -> None:
        if self.scan_thread and self.scan_thread.isRunning():
            return
        url = self.url_input.text().strip()
        if not self._valid_source_url(url):
            QMessageBox.warning(self, "网址无效", "请输入完整的 YouTube 频道或播放列表网址")
            return

        self.model.clear()
        self.format_overrides.clear()
        self._update_result_count()
        request = ScanRequest(
            url=url,
            cookie_browser=self.cookie_browser.currentData(),
            cookie_profile=self.cookie_profile.text().strip() or None,
            max_items=self.max_items.value() or None,
            format_rule=self.format_rule,
        )
        self.scan_thread = QThread(self)
        self.scan_worker = ScanWorker(self.backend, request)
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.item_added.connect(self._add_scanned_item)
        self.scan_worker.item_updated.connect(self._update_scanned_item)
        self.scan_worker.status.connect(self.statusBar().showMessage)
        self.scan_worker.failed.connect(lambda text: QMessageBox.warning(self, "扫描失败", friendly_error(text)))
        self.scan_worker.finished.connect(self._scan_finished)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_thread.finished.connect(self._cleanup_scan_thread)
        self.scan_button.setEnabled(False)
        self.cancel_scan_button.setEnabled(True)
        self.queue_label.setText("正在扫描…")
        self.scan_thread.start()
        self._save_settings()

    def cancel_scan(self) -> None:
        if self.scan_worker:
            self.scan_worker.request_cancel()
            self.cancel_scan_button.setEnabled(False)
            self.queue_label.setText("正在停止扫描…")

    def _add_scanned_item(self, item: VideoItem) -> None:
        record = self.history.get(item.extractor, item.video_id)
        if record:
            item.state = ItemState.COMPLETED
            item.downloaded_path = record.file_path
        self.model.add_item(item)
        self._update_result_count()

    def _update_scanned_item(self, item: VideoItem) -> None:
        record = self.history.get(item.extractor, item.video_id)
        if record:
            item.state = ItemState.COMPLETED
            item.downloaded_path = record.file_path
        self.model.update_item(item)

    def _scan_finished(self, cancelled: bool) -> None:
        self.scan_button.setEnabled(True)
        self.cancel_scan_button.setEnabled(False)
        self.queue_label.setText("扫描已取消" if cancelled else f"扫描完成，共 {len(self.model.items)} 项")

    def _cleanup_scan_thread(self) -> None:
        if self.scan_worker:
            self.scan_worker.deleteLater()
        if self.scan_thread:
            self.scan_thread.deleteLater()
        self.scan_worker = None
        self.scan_thread = None

    def _filter_changed(self, text: str) -> None:
        self.proxy.set_search_text(text)
        self._update_result_count()

    def _update_result_count(self) -> None:
        self.result_count.setText(f"{self.proxy.rowCount()} / {self.model.rowCount()} 项")

    def _visible_source_rows(self) -> set[int]:
        return {self.proxy.mapToSource(self.proxy.index(row, 0)).row() for row in range(self.proxy.rowCount())}

    def _set_visible_checked(self, checked: bool) -> None:
        self.model.set_checked_rows(self._visible_source_rows(), checked)

    def _current_item(self) -> VideoItem | None:
        proxy_index = self.table.currentIndex()
        if not proxy_index.isValid():
            return None
        return self.model.item_at(self.proxy.mapToSource(proxy_index).row())

    def copy_current_url(self) -> None:
        item = self._current_item()
        if item:
            QGuiApplication.clipboard().setText(item.webpage_url)
            self.statusBar().showMessage("视频链接已复制", 3000)

    def open_video(self, *_args) -> None:
        item = self._current_item()
        if item and item.webpage_url:
            QDesktopServices.openUrl(QUrl(item.webpage_url))

    def allow_redownload(self) -> None:
        item = self._current_item()
        if not item:
            return
        self.history.remove(item.extractor, item.video_id)
        item.state = ItemState.READY
        item.downloaded_path = ""
        item.error = ""
        self.model.update_item(item)
        self.statusBar().showMessage("已清除该视频的下载历史标记", 3000)

    def choose_destination(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择下载目录", self.destination_input.text())
        if chosen:
            self.destination_input.setText(chosen)
            self._save_settings()

    def edit_format_rule(self) -> None:
        dialog = FormatSettingsDialog(self.format_rule, self)
        if dialog.exec():
            self.format_rule = dialog.rule
            self._save_settings()
            self.statusBar().showMessage("全局格式规则已保存；重新扫描可刷新预期大小", 5000)

    def probe_selected_format(self) -> None:
        item = self._current_item()
        if not item:
            QMessageBox.information(self, "选择视频", "请先在表格中选择一个视频")
            return
        if self.probe_thread and self.probe_thread.isRunning():
            return
        self.item_format_button.setEnabled(False)
        self.probe_thread = QThread(self)
        self.probe_worker = FormatProbeWorker(
            self.backend,
            item.webpage_url,
            self.cookie_browser.currentData(),
            self.cookie_profile.text().strip() or None,
        )
        self.probe_worker.moveToThread(self.probe_thread)
        self.probe_thread.started.connect(self.probe_worker.run)
        self.probe_worker.status.connect(self.statusBar().showMessage)
        self.probe_worker.succeeded.connect(lambda formats, key=item.key: self._show_formats_dialog(key, formats))
        self.probe_worker.failed.connect(lambda text: QMessageBox.warning(self, "格式获取失败", friendly_error(text)))
        self.probe_worker.finished.connect(self.probe_thread.quit)
        self.probe_thread.finished.connect(self._cleanup_probe_thread)
        self.probe_thread.start()

    def _show_formats_dialog(self, key: str, formats: list) -> None:
        if not formats:
            QMessageBox.information(self, "没有格式", "该视频没有返回可用格式")
            return
        dialog = FormatsDialog(formats, self)
        if dialog.exec():
            if dialog.selector:
                self.format_overrides[key] = dialog.selector
                self.statusBar().showMessage(f"已设置单项格式：{dialog.selector}", 4000)
            else:
                self.format_overrides.pop(key, None)
                self.statusBar().showMessage("已恢复使用全局格式规则", 3000)

    def _cleanup_probe_thread(self) -> None:
        self.item_format_button.setEnabled(True)
        if self.probe_worker:
            self.probe_worker.deleteLater()
        if self.probe_thread:
            self.probe_thread.deleteLater()
        self.probe_worker = None
        self.probe_thread = None

    def start_downloads(self) -> None:
        if self.download_thread and self.download_thread.isRunning():
            return
        items = self.model.selected_items()
        if not items:
            QMessageBox.information(self, "没有下载项", "请先勾选需要下载的视频")
            return
        destination_text = self.destination_input.text().strip()
        if not destination_text:
            QMessageBox.warning(self, "下载目录", "请选择下载目录")
            return
        try:
            self.backend.validate_selector(build_format_selector(self.format_rule))
        except Exception as exc:
            QMessageBox.warning(self, "格式规则无效", friendly_error(exc))
            return

        destination = Path(destination_text)
        jobs = [
            DownloadJob(
                item=item,
                destination=destination,
                rule=self.format_rule,
                format_override=self.format_overrides.get(item.key),
                cookie_browser=self.cookie_browser.currentData(),
                cookie_profile=self.cookie_profile.text().strip() or None,
            )
            for item in items
        ]
        for item in items:
            self.model.update_state(item.key, ItemState.QUEUED.value)

        self.download_thread = QThread(self)
        self.download_worker = DownloadWorker(self.backend, jobs, self.history)
        self.download_worker.moveToThread(self.download_thread)
        self.download_thread.started.connect(self.download_worker.run)
        self.download_worker.item_state.connect(self._on_download_state)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.queue_progress.connect(self._on_queue_progress)
        self.download_worker.status.connect(self.statusBar().showMessage)
        self.download_worker.finished.connect(self.download_thread.quit)
        self.download_worker.finished.connect(self._downloads_finished)
        self.download_thread.finished.connect(self._cleanup_download_thread)
        self._download_paused = False
        self.download_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.cancel_download_button.setEnabled(True)
        self.download_thread.start()
        self._save_settings()

    def _on_download_state(self, key: str, state: str, detail: str) -> None:
        self.model.update_state(key, state, detail)

    def _on_download_progress(self, progress: DownloadProgress) -> None:
        self.progress_bar.setValue(round(progress.percent * 10))
        speed = f" · {human_bytes(progress.speed)}/s" if progress.speed else ""
        eta = f" · 剩余 {progress.eta}s" if progress.eta is not None else ""
        self.queue_label.setText(f"{progress.stage} {progress.percent:.1f}%{speed}{eta}")
        if "后处理" in progress.stage:
            self.model.update_state(progress.key, ItemState.POSTPROCESSING.value)

    def _on_queue_progress(self, current: int, total: int) -> None:
        self.queue_label.setText(f"队列 {current} / {total}")

    def toggle_pause(self) -> None:
        if not self.download_worker:
            return
        self._download_paused = not self._download_paused
        self.download_worker.set_paused(self._download_paused)
        self.pause_button.setText("继续队列" if self._download_paused else "暂停后续任务")
        if self._download_paused:
            self.statusBar().showMessage("当前项完成后暂停，不会强行挂起正在写入的文件", 5000)

    def cancel_current_download(self) -> None:
        if self.download_worker:
            self.download_worker.cancel_current()
            self.statusBar().showMessage("正在取消当前项，将保留 .part 文件", 5000)

    def retry_failed(self) -> None:
        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.information(self, "队列运行中", "请等待当前队列结束后重试")
            return
        failed_rows = {row for row, item in enumerate(self.model.items) if item.state is ItemState.FAILED}
        if not failed_rows:
            QMessageBox.information(self, "没有失败项", "当前没有可重试的失败任务")
            return
        self.model.set_checked_rows(failed_rows, True)
        self.start_downloads()

    def _downloads_finished(self) -> None:
        self.download_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("暂停后续任务")
        self.cancel_download_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.queue_label.setText("队列已结束")

    def _cleanup_download_thread(self) -> None:
        if self.download_worker:
            self.download_worker.deleteLater()
        if self.download_thread:
            self.download_thread.deleteLater()
        self.download_worker = None
        self.download_thread = None

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        active = any(
            thread and thread.isRunning()
            for thread in (self.scan_thread, self.probe_thread, self.download_thread)
        )
        if active:
            answer = QMessageBox.question(
                self,
                "任务仍在运行",
                "扫描或下载任务仍在运行。确定退出吗？当前下载会取消并保留 .part 文件。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            if self.scan_worker:
                self.scan_worker.request_cancel()
            if self.download_worker:
                self.download_worker.stop_all()
        self._save_settings()
        event.accept()
