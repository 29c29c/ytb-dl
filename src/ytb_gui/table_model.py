from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from .formatting import human_bytes
from .models import ItemState, VideoItem


class VideoTableModel(QAbstractTableModel):
    HEADERS = ("选择", "视频名称", "上传者", "上传日期", "预期大小", "视频链接", "状态")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[VideoItem] = []
        self._rows_by_key: dict[str, int] = {}

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.items)):
            return None
        item = self.items[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.CheckStateRole and column == 0:
            return Qt.CheckState.Checked if item.selected else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                "",
                item.title,
                item.uploader,
                item.upload_date,
                "计算中…" if item.size_pending else human_bytes(item.expected_size),
                item.webpage_url,
                item.state.value,
            )[column]
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 6 and item.error:
                return item.error
            if column == 4:
                return "根据扫描时的全局格式规则估算；转码、字幕和网站变化可能造成差异"
            if column == 5:
                return item.webpage_url
            if item.downloaded_path:
                return f"文件：{item.downloaded_path}"
        if role == Qt.ItemDataRole.ForegroundRole and column == 5:
            return QColor("#2563eb")
        if role == Qt.ItemDataRole.UserRole:
            return item
        return None

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0 and self.items[index.row()].state is not ItemState.UNAVAILABLE:
            flags |= Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole):  # noqa: N802
        if (
            index.isValid()
            and index.column() == 0
            and role == Qt.ItemDataRole.CheckStateRole
            and self.items[index.row()].state is not ItemState.UNAVAILABLE
        ):
            self.items[index.row()].selected = value == Qt.CheckState.Checked.value or value == Qt.CheckState.Checked
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            return True
        return False

    def clear(self) -> None:
        self.beginResetModel()
        self.items.clear()
        self._rows_by_key.clear()
        self.endResetModel()

    def add_item(self, item: VideoItem) -> bool:
        if item.key in self._rows_by_key:
            return False
        row = len(self.items)
        self.beginInsertRows(QModelIndex(), row, row)
        self.items.append(item)
        self._rows_by_key[item.key] = row
        self.endInsertRows()
        return True

    def update_item(self, item: VideoItem) -> None:
        row = self._rows_by_key.get(item.key)
        if row is None:
            self.add_item(item)
            return
        previous = self.items[row]
        item.selected = previous.selected
        if previous.downloaded_path and not item.downloaded_path:
            item.downloaded_path = previous.downloaded_path
            item.state = ItemState.COMPLETED
        self.items[row] = item
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))

    def item_for_key(self, key: str) -> VideoItem | None:
        row = self._rows_by_key.get(key)
        return self.items[row] if row is not None else None

    def item_at(self, row: int) -> VideoItem | None:
        return self.items[row] if 0 <= row < len(self.items) else None

    def set_checked_rows(self, rows: set[int], checked: bool) -> None:
        changed: list[int] = []
        for row in rows:
            if 0 <= row < len(self.items):
                item = self.items[row]
                if item.state is ItemState.UNAVAILABLE:
                    continue
                if checked and item.state is ItemState.COMPLETED:
                    continue
                if item.selected != checked:
                    item.selected = checked
                    changed.append(row)
        for row in changed:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])

    def selected_items(self) -> list[VideoItem]:
        return [item for item in self.items if item.selected and item.state is not ItemState.UNAVAILABLE]

    def update_state(self, key: str, state_value: str, detail: str = "") -> None:
        row = self._rows_by_key.get(key)
        if row is None:
            return
        item = self.items[row]
        item.state = ItemState(state_value)
        if item.state is ItemState.COMPLETED:
            item.downloaded_path = detail
            item.error = ""
            item.selected = False
        elif detail:
            item.error = detail
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))


class VideoFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._needle = ""
        self.setDynamicSortFilter(True)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_search_text(self, text: str) -> None:
        self._needle = text.strip().casefold()
        if hasattr(self, "beginFilterChange") and hasattr(self, "endFilterChange"):
            self.beginFilterChange()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:  # Qt 6.8 compatibility
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):  # noqa: N802
        if not self._needle:
            return True
        model = self.sourceModel()
        item = model.item_at(source_row) if model else None
        return bool(item and self._needle in item.searchable_text)
