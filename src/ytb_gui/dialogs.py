from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .formatting import InvalidFormatSelector, build_format_selector, human_bytes
from .models import FormatInfo, FormatRule, MediaMode


class FormatSettingsDialog(QDialog):
    def __init__(self, rule: FormatRule, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局格式规则")
        self.setMinimumWidth(520)
        self._initial_rule = rule

        self.mode = QComboBox()
        for text, value in (
            ("最佳视频 + 音频", MediaMode.BEST),
            ("视频（可限制质量）", MediaMode.VIDEO),
            ("仅音频", MediaMode.AUDIO),
            ("高级格式表达式", MediaMode.CUSTOM),
        ):
            self.mode.addItem(text, value.value)

        self.height = QComboBox()
        for text, value in (("不限", None), ("2160p", 2160), ("1440p", 1440), ("1080p", 1080), ("720p", 720), ("480p", 480), ("360p", 360)):
            self.height.addItem(text, value)
        self.container = QComboBox()
        for value in ("auto", "mp4", "mkv", "webm"):
            self.container.addItem(value.upper() if value != "auto" else "自动", value)
        self.video_codec = QComboBox()
        for text, value in (("自动", "auto"), ("H.264 优先", "h264"), ("VP9 优先", "vp9"), ("AV1 优先", "av1")):
            self.video_codec.addItem(text, value)
        self.audio_codec = QComboBox()
        for text, value in (("自动", "auto"), ("M4A/AAC 优先", "m4a"), ("Opus 优先", "opus")):
            self.audio_codec.addItem(text, value)
        self.audio_format = QComboBox()
        for value in ("m4a", "mp3", "opus", "flac", "wav"):
            self.audio_format.addItem(value.upper(), value)
        self.audio_quality = QComboBox()
        for text, value in (("最高质量", "0"), ("320 kbps", "320"), ("256 kbps", "256"), ("192 kbps", "192"), ("128 kbps", "128")):
            self.audio_quality.addItem(text, value)

        self.manual_subs = QCheckBox("下载人工字幕")
        self.auto_subs = QCheckBox("下载自动字幕")
        self.embed_subs = QCheckBox("嵌入媒体文件（需要 ffmpeg）")
        self.subtitle_languages = QLineEdit()
        self.subtitle_languages.setPlaceholderText("例如 zh-Hans,zh,en；留空表示全部（排除直播聊天）")
        self.custom_selector = QLineEdit()
        self.custom_selector.setPlaceholderText("例如 bv*[height<=1080]+ba/b")

        form = QFormLayout()
        form.addRow("下载模式", self.mode)
        form.addRow("最高分辨率", self.height)
        form.addRow("输出容器", self.container)
        form.addRow("视频编码", self.video_codec)
        form.addRow("音频编码", self.audio_codec)
        form.addRow("纯音频格式", self.audio_format)
        form.addRow("音频质量", self.audio_quality)
        form.addRow("高级表达式", self.custom_selector)

        subtitle_widget = QWidget()
        subtitle_layout = QVBoxLayout(subtitle_widget)
        subtitle_layout.setContentsMargins(0, 0, 0, 0)
        subtitle_layout.addWidget(self.manual_subs)
        subtitle_layout.addWidget(self.auto_subs)
        subtitle_layout.addWidget(self.embed_subs)
        subtitle_layout.addWidget(self.subtitle_languages)
        form.addRow("字幕", subtitle_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._load_rule(rule)
        self.mode.currentIndexChanged.connect(self._update_enabled)
        self.manual_subs.toggled.connect(self._update_enabled)
        self.auto_subs.toggled.connect(self._update_enabled)
        self._update_enabled()

    @staticmethod
    def _set_combo(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _load_rule(self, rule: FormatRule) -> None:
        self._set_combo(self.mode, rule.mode.value)
        self._set_combo(self.height, rule.max_height)
        self._set_combo(self.container, rule.container)
        self._set_combo(self.video_codec, rule.video_codec)
        self._set_combo(self.audio_codec, rule.audio_codec)
        self._set_combo(self.audio_format, rule.audio_format)
        self._set_combo(self.audio_quality, rule.audio_quality)
        self.manual_subs.setChecked(rule.include_manual_subtitles)
        self.auto_subs.setChecked(rule.include_auto_subtitles)
        self.embed_subs.setChecked(rule.embed_subtitles)
        self.subtitle_languages.setText(",".join(rule.subtitle_languages))
        self.custom_selector.setText(rule.custom_selector)

    def _update_enabled(self) -> None:
        mode = MediaMode(self.mode.currentData())
        self.height.setEnabled(mode is MediaMode.VIDEO)
        self.video_codec.setEnabled(mode is MediaMode.VIDEO)
        self.audio_codec.setEnabled(mode is MediaMode.VIDEO)
        self.audio_format.setEnabled(mode is MediaMode.AUDIO)
        self.audio_quality.setEnabled(mode is MediaMode.AUDIO)
        self.container.setEnabled(mode in (MediaMode.BEST, MediaMode.VIDEO))
        self.custom_selector.setEnabled(mode is MediaMode.CUSTOM)
        have_subs = self.manual_subs.isChecked() or self.auto_subs.isChecked()
        self.embed_subs.setEnabled(have_subs and mode is not MediaMode.AUDIO)
        self.subtitle_languages.setEnabled(have_subs)

    @property
    def rule(self) -> FormatRule:
        languages = [part.strip() for part in self.subtitle_languages.text().split(",") if part.strip()]
        return FormatRule(
            mode=MediaMode(self.mode.currentData()),
            max_height=self.height.currentData(),
            container=self.container.currentData(),
            video_codec=self.video_codec.currentData(),
            audio_codec=self.audio_codec.currentData(),
            audio_format=self.audio_format.currentData(),
            audio_quality=self.audio_quality.currentData(),
            subtitle_languages=languages,
            include_manual_subtitles=self.manual_subs.isChecked(),
            include_auto_subtitles=self.auto_subs.isChecked(),
            embed_subtitles=self.embed_subs.isChecked() and self.embed_subs.isEnabled(),
            custom_selector=self.custom_selector.text().strip(),
        )

    def accept(self) -> None:
        try:
            build_format_selector(self.rule)
        except InvalidFormatSelector as exc:
            QMessageBox.warning(self, "格式表达式无效", str(exc))
            return
        super().accept()


class FormatsDialog(QDialog):
    def __init__(self, formats: list[FormatInfo], parent=None):
        super().__init__(parent)
        self.formats = formats
        self._selector: str | None = None
        self.setWindowTitle("单项格式覆盖")
        self.resize(1000, 560)

        label = QLabel("选择一个复合格式，或同时选择一个视频格式和一个纯音频格式。按住 Ctrl 可多选。")
        label.setWordWrap(True)
        self.table = QTableWidget(len(formats), 8)
        self.table.setHorizontalHeaderLabels(("格式 ID", "容器", "分辨率", "FPS", "视频编码", "音频编码", "码率", "估算大小"))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        for row, info in enumerate(formats):
            values = (
                info.format_id,
                info.extension,
                info.resolution,
                "" if info.fps is None else f"{info.fps:g}",
                info.video_codec,
                info.audio_codec,
                "" if info.bitrate is None else f"{info.bitrate:g} kbps",
                human_bytes(info.filesize),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(row, column, cell)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        clear_button = buttons.addButton("使用全局规则", QDialogButtonBox.ButtonRole.ResetRole)
        clear_button.clicked.connect(self._clear_override)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    @property
    def selector(self) -> str | None:
        return self._selector

    def _clear_override(self) -> None:
        self._selector = None
        super().accept()

    def accept(self) -> None:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        if not rows or len(rows) > 2:
            QMessageBox.warning(self, "选择格式", "请选择一个格式，或一个视频格式加一个纯音频格式")
            return
        selected = [self.formats[row] for row in rows]
        if len(selected) == 1:
            self._selector = selected[0].format_id
        else:
            video = [item for item in selected if item.has_video]
            audio_only = [item for item in selected if item.has_audio and not item.has_video]
            if len(video) != 1 or len(audio_only) != 1:
                QMessageBox.warning(self, "格式组合无效", "双选时必须选择一个视频格式和一个纯音频格式")
                return
            self._selector = f"{video[0].format_id}+{audio_only[0].format_id}"
        super().accept()
