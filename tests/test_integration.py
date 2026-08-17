import os
import tempfile
import unittest
from pathlib import Path

from ytb_gui.backend import YtDlpBackend
from ytb_gui.models import DownloadJob, FormatRule, ScanRequest


class NetworkIntegrationTests(unittest.TestCase):
    def _scan_source(self, environment_name):
        url = os.environ.get(environment_name)
        if not url:
            self.skipTest(f"set {environment_name} to enable this network test")
        events = list(
            YtDlpBackend().scan(
                ScanRequest(url, max_items=2),
                cancelled=lambda: False,
            )
        )
        added = [item for event, item in events if event == "add"]
        self.assertTrue(added)
        self.assertTrue(all(item.title and item.uploader and item.upload_date and item.webpage_url for item in added))

    def test_public_channel_scan(self):
        self._scan_source("YTB_TEST_CHANNEL_URL")

    def test_public_playlist_scan(self):
        self._scan_source("YTB_TEST_PLAYLIST_URL")

    def test_short_video_download(self):
        url = os.environ.get("YTB_TEST_VIDEO_URL")
        if not url:
            self.skipTest("set YTB_TEST_VIDEO_URL to enable the download test")
        backend = YtDlpBackend()
        with tempfile.TemporaryDirectory() as temp:
            info = backend.probe_formats(url)
            self.assertTrue(info)
            from ytb_gui.models import VideoItem

            item = VideoItem("integration", "Integration", "Test", "2026-01-01", url)
            output = backend.download(
                DownloadJob(item, Path(temp), FormatRule()),
                cancelled=lambda: False,
                on_progress=lambda _progress: None,
            )
            self.assertTrue(output)


if __name__ == "__main__":
    unittest.main()

