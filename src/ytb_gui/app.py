from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


STYLE = """
QMainWindow { background: #f7f8fb; }
QLineEdit, QComboBox, QSpinBox {
    min-height: 30px; border: 1px solid #cbd5e1; border-radius: 6px;
    padding: 0 8px; background: white;
}
QPushButton {
    min-height: 30px; padding: 0 12px; border: 1px solid #cbd5e1;
    border-radius: 6px; background: white;
}
QPushButton:hover { background: #eff6ff; border-color: #60a5fa; }
QPushButton:disabled { color: #94a3b8; background: #f1f5f9; }
QTableView {
    background: white; alternate-background-color: #f8fafc;
    border: 1px solid #dbe2ea; border-radius: 7px; gridline-color: #e5e7eb;
}
QHeaderView::section { background: #eef2f7; padding: 7px; border: none; border-right: 1px solid #dbe2ea; }
QProgressBar { border: 1px solid #cbd5e1; border-radius: 5px; text-align: center; background: white; }
QProgressBar::chunk { background: #3b82f6; border-radius: 4px; }
"""


def main() -> int:
    QCoreApplication.setOrganizationName("YTBChannelDownloader")
    QCoreApplication.setApplicationName("YTBChannelDownloader")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()

