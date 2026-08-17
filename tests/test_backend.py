import unittest

from ytb_gui.backend import BackendError, YtDlpBackend, item_from_info, needs_enrichment
from ytb_gui.models import FormatRule, ScanRequest


class FakeYoutubeDL:
    root_result = None
    last_options = None

    def __init__(self, options=None):
        self.options = options or {}
        type(self).last_options = self.options

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def extract_info(self, url, download=False):
        return self.root_result


class FakeBackend(YtDlpBackend):
    def _ydl_class(self):
        return FakeYoutubeDL


class BackendTests(unittest.TestCase):
    def test_item_normalization(self):
        item = item_from_info(
            {
                "id": "abc",
                "title": "Example",
                "channel": "Uploader",
                "upload_date": "20260102",
                "extractor_key": "YoutubeTab",
                "url": "abc",
                "filesize": 1024,
            },
            format_rule=FormatRule(),
        )
        self.assertEqual(item.extractor, "youtube")
        self.assertEqual(item.upload_date, "2026-01-02")
        self.assertEqual(item.webpage_url, "https://www.youtube.com/watch?v=abc")
        self.assertFalse(needs_enrichment(item))

    def test_scan_deduplicates_entries(self):
        entry = {
            "id": "abc",
            "title": "Example",
            "channel": "Uploader",
            "upload_date": "20260102",
            "extractor_key": "Youtube",
            "url": "https://www.youtube.com/watch?v=abc",
            "filesize": 1024,
        }
        FakeYoutubeDL.root_result = {"_type": "playlist", "entries": [entry, dict(entry)]}
        events = list(FakeBackend().scan(ScanRequest("https://youtube.com/playlist?list=x"), cancelled=lambda: False))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "add")

    def test_scan_rejects_single_video(self):
        FakeYoutubeDL.root_result = {"id": "abc", "title": "single"}
        with self.assertRaises(BackendError):
            list(FakeBackend().scan(ScanRequest("https://youtube.com/watch?v=abc"), cancelled=lambda: False))

    def test_scan_obeys_max_items(self):
        FakeYoutubeDL.root_result = {
            "entries": [
                {
                    "id": str(index),
                    "title": f"Video {index}",
                    "channel": "Uploader",
                    "upload_date": "20260102",
                    "extractor_key": "Youtube",
                    "url": f"https://youtube.com/watch?v={index}",
                    "filesize": 1024,
                }
                for index in range(5)
            ]
        }
        events = list(FakeBackend().scan(ScanRequest("https://youtube.com/@x", max_items=2), cancelled=lambda: False))
        self.assertEqual(len(events), 2)

    def test_scan_passes_firefox_profile_to_yt_dlp(self):
        FakeYoutubeDL.root_result = {"entries": []}
        list(
            FakeBackend().scan(
                ScanRequest(
                    "https://youtube.com/playlist?list=x",
                    cookie_browser="firefox",
                    cookie_profile="default-release",
                ),
                cancelled=lambda: False,
            )
        )
        self.assertEqual(
            FakeYoutubeDL.last_options["cookiesfrombrowser"],
            ("firefox", "default-release", None, None),
        )


if __name__ == "__main__":
    unittest.main()
