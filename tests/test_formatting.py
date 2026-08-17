import unittest

from ytb_gui.formatting import (
    InvalidFormatSelector,
    build_download_options,
    build_format_selector,
    estimate_expected_size,
    friendly_error,
    normalize_upload_date,
    sanitize_windows_component,
    validate_format_selector,
)
from ytb_gui.models import FormatRule, MediaMode


class FormattingTests(unittest.TestCase):
    def test_normalize_upload_date(self):
        self.assertEqual(normalize_upload_date("20260102"), "2026-01-02")
        self.assertEqual(normalize_upload_date(None), "未知")
        self.assertEqual(normalize_upload_date("bad"), "未知")

    def test_best_and_capped_video_selectors(self):
        self.assertEqual(build_format_selector(FormatRule()), "bv*+ba/b")
        rule = FormatRule(mode=MediaMode.VIDEO, max_height=1080, video_codec="h264", audio_codec="m4a")
        selector = build_format_selector(rule)
        self.assertIn("height<=1080", selector)
        self.assertIn("vcodec", selector)
        self.assertIn("ext=m4a", selector)

    def test_custom_selector_validation(self):
        self.assertEqual(validate_format_selector("bv*+ba/b"), "bv*+ba/b")
        with self.assertRaises(InvalidFormatSelector):
            validate_format_selector("bv*[height<=720")
        with self.assertRaises(InvalidFormatSelector):
            validate_format_selector("best\n--exec bad")

    def test_audio_and_subtitle_options(self):
        rule = FormatRule(
            mode=MediaMode.AUDIO,
            audio_format="mp3",
            audio_quality="192",
            include_manual_subtitles=True,
            include_auto_subtitles=True,
            embed_subtitles=True,
            subtitle_languages=["zh-Hans", "en"],
        )
        options = build_download_options(rule)
        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(options["subtitleslangs"], ["zh-Hans", "en"])
        self.assertTrue(any(pp["key"] == "FFmpegExtractAudio" for pp in options["postprocessors"]))
        self.assertFalse(any(pp["key"] == "FFmpegEmbedSubtitle" for pp in options["postprocessors"]))

    def test_windows_filename_component(self):
        self.assertEqual(sanitize_windows_component('a<b>:c?.'), "a_b__c_")
        self.assertEqual(sanitize_windows_component("CON"), "_CON")
        self.assertEqual(sanitize_windows_component("   "), "Unknown")

    def test_error_mapping(self):
        self.assertIn("Cookie", friendly_error("Please sign in to confirm your age"))
        self.assertIn("ffmpeg", friendly_error("ffmpeg not found"))
        self.assertIn("格式", friendly_error("requested format is not available"))

    def test_expected_size_for_video_and_audio(self):
        info = {
            "duration": 100,
            "formats": [
                {"format_id": "140", "vcodec": "none", "acodec": "mp4a", "filesize": 2_000_000},
                {"format_id": "137", "vcodec": "avc1", "acodec": "none", "height": 1080, "filesize": 10_000_000},
            ],
        }
        video_rule = FormatRule(mode=MediaMode.VIDEO, max_height=1080)
        self.assertEqual(estimate_expected_size(info, video_rule), 12_000_000)
        audio_rule = FormatRule(mode=MediaMode.AUDIO, audio_format="mp3", audio_quality="192")
        self.assertEqual(estimate_expected_size(info, audio_rule), 2_400_000)


if __name__ == "__main__":
    unittest.main()
