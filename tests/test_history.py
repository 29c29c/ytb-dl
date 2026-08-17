import tempfile
import unittest
from pathlib import Path

from ytb_gui.history import HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def test_record_update_lookup_and_remove(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.sqlite3")
            self.assertFalse(store.contains("youtube", "abc"))
            store.record("youtube", "abc", "Title", "C:/one.mp4")
            self.assertTrue(store.contains("youtube", "abc"))
            record = store.get("youtube", "abc")
            self.assertIsNotNone(record)
            self.assertEqual(record.title, "Title")
            store.record("youtube", "abc", "New title", "C:/two.mp4")
            self.assertEqual(store.get("youtube", "abc").file_path, "C:/two.mp4")
            store.remove("youtube", "abc")
            self.assertFalse(store.contains("youtube", "abc"))


if __name__ == "__main__":
    unittest.main()

