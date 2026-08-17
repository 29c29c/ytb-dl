import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QEventLoop, QThread, QTimer
    from PySide6.QtWidgets import QApplication

    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class QtModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_filter_and_visible_selection(self):
        from ytb_gui.models import ItemState, VideoItem
        from ytb_gui.table_model import VideoFilterProxyModel, VideoTableModel

        model = VideoTableModel()
        model.add_item(VideoItem("1", "Python tutorial", "Alice", "2026-01-01", "https://x/1", expected_size=1_048_576))
        model.add_item(VideoItem("2", "Rust tutorial", "Bob", "2026-01-02", "https://x/2"))
        model.add_item(VideoItem("3", "Python private", "Alice", "未知", "https://x/3", state=ItemState.UNAVAILABLE))
        proxy = VideoFilterProxyModel()
        proxy.setSourceModel(model)
        proxy.set_search_text("python")
        self.assertEqual(proxy.rowCount(), 2)
        self.assertEqual(model.data(model.index(0, 4)), "1.0 MB")
        visible = {proxy.mapToSource(proxy.index(row, 0)).row() for row in range(proxy.rowCount())}
        model.set_checked_rows(visible, True)
        self.assertTrue(model.items[0].selected)
        self.assertFalse(model.items[1].selected)
        self.assertFalse(model.items[2].selected)

    def test_download_worker_continues_after_failure(self):
        from ytb_gui.history import HistoryStore
        from ytb_gui.models import DownloadJob, FormatRule, ItemState, VideoItem
        from ytb_gui.workers import DownloadWorker

        class FakeDownloadBackend:
            def download(self, job, **_kwargs):
                if job.item.video_id == "bad":
                    raise RuntimeError("boom")
                return f"C:/{job.item.video_id}.mp4"

        with tempfile.TemporaryDirectory() as temp:
            items = [
                VideoItem("bad", "Bad", "U", "2026-01-01", "https://x/bad"),
                VideoItem("good", "Good", "U", "2026-01-01", "https://x/good"),
            ]
            jobs = [DownloadJob(item, Path(temp), FormatRule()) for item in items]
            history = HistoryStore(Path(temp) / "history.sqlite3")
            worker = DownloadWorker(FakeDownloadBackend(), jobs, history)
            states = []
            worker.item_state.connect(lambda key, state, detail: states.append((key, state, detail)))
            worker.run()
            self.assertTrue(any(key.endswith(":bad") and state == ItemState.FAILED.value for key, state, _ in states))
            self.assertTrue(any(key.endswith(":good") and state == ItemState.COMPLETED.value for key, state, _ in states))
            self.assertTrue(history.contains("youtube", "good"))

    def test_scan_failure_dialog_runs_on_main_thread(self):
        from PySide6.QtWidgets import QMessageBox

        from ytb_gui.main_window import MainWindow

        class FailingBackend:
            def scan(self, *_args, **_kwargs):
                raise RuntimeError("scan failed")

        callback_threads = []

        def record_warning(*_args, **_kwargs):
            callback_threads.append(QThread.currentThread())
            return QMessageBox.StandardButton.Ok

        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"YTB_GUI_DATA_DIR": temp}
        ), patch.object(QMessageBox, "warning", side_effect=record_warning):
            window = MainWindow()
            window.backend = FailingBackend()
            window.url_input.setText("https://www.youtube.com/playlist?list=test")
            window.start_scan()

            thread = window.scan_thread
            self.assertIsNotNone(thread)
            loop = QEventLoop()
            thread.finished.connect(loop.quit)
            QTimer.singleShot(3000, loop.quit)
            loop.exec()
            self.app.processEvents()
            window.close()

        self.assertEqual(len(callback_threads), 1)
        self.assertIs(callback_threads[0], self.app.thread())


if __name__ == "__main__":
    unittest.main()
