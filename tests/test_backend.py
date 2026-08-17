import tempfile
import unittest
from pathlib import Path

from ytb_gui.backend import BackendError, YtDlpBackend, item_from_info, needs_enrichment
from ytb_gui.models import DownloadJob, FormatRule, ScanRequest, VideoItem


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

    def test_conservative_scan_skips_size_only_enrichment(self):
        FakeYoutubeDL.root_result = {
            "entries": [
                {
                    "id": "abc",
                    "title": "Example",
                    "channel": "Uploader",
                    "extractor_key": "Youtube",
                    "url": "https://youtube.com/watch?v=abc",
                }
            ]
        }
        events = list(
            FakeBackend().scan(
                ScanRequest("https://youtube.com/playlist?list=x"),
                cancelled=lambda: False,
            )
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "add")
        self.assertFalse(events[0][1].size_pending)
        self.assertEqual(FakeYoutubeDL.last_options["sleep_interval_requests"], 2.0)
        self.assertEqual(FakeYoutubeDL.last_options["extractor_retries"], 3)

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

    def test_download_uses_conservative_delays_and_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp)
            FakeYoutubeDL.root_result = {"filepath": str(destination / "video.mp4")}
            job = DownloadJob(
                VideoItem(
                    "abc",
                    "Example",
                    "Uploader",
                    "2026-01-01",
                    "https://youtube.com/watch?v=abc",
                ),
                destination,
                FormatRule(),
            )
            FakeBackend().download(
                job,
                cancelled=lambda: False,
                on_progress=lambda _progress: None,
            )

        self.assertEqual(FakeYoutubeDL.last_options["sleep_interval_requests"], 2.0)
        self.assertEqual(FakeYoutubeDL.last_options["sleep_interval"], 5.0)
        self.assertEqual(FakeYoutubeDL.last_options["max_sleep_interval"], 10.0)
        self.assertEqual(FakeYoutubeDL.last_options["retries"], 3)
        self.assertEqual(FakeYoutubeDL.last_options["fragment_retries"], 3)


if __name__ == "__main__":
    unittest.main()
