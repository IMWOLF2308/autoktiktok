import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.tiktok_browser import PublishJournal, load_account, profile_username, publish, tiktok_worker, video_digest


class TikTokTests(unittest.TestCase):
    def test_profile_links_do_not_accept_foreign_hosts_or_video_creators(self):
        self.assertEqual(profile_username("/@test.user"), "test.user")
        self.assertEqual(profile_username("https://www.tiktok.com/@test.user?lang=en"), "test.user")
        for link in ("https://example.com/@test", "https://www.tiktok.com.evil.test/@test",
                     "/@test/video/123", "/login", "/@", "javascript:alert(1)"):
            self.assertIsNone(profile_username(link), link)

    def test_account_cache_handles_missing_and_invalid_data(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(load_account(folder))
            path = Path(folder) / "account.json"
            for value in ([], {"username": "../other"}, {"username": 4}, "invalid"):
                path.write_text(json.dumps(value), encoding="utf-8")
                self.assertIsNone(load_account(folder))
            path.write_text('{"username":"test.user","display_name":"Test"}', encoding="utf-8")
            self.assertEqual(load_account(folder)["username"], "test.user")

    def test_journal_blocks_repeat_after_success_crash_or_ambiguous_result(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "a.mp4"
            video.write_bytes(b"synthetic video")
            copy = Path(folder) / "renamed.mp4"
            copy.write_bytes(video.read_bytes())
            digest = video_digest(video)
            for status in ("submitting", "unknown", "posted", "submitted"):
                journal = PublishJournal(folder, "test.user", digest)
                journal.record(status, video, "Caption")
                duplicate = PublishJournal(folder, "TEST.USER", video_digest(copy))
                with self.assertRaises(RuntimeError):
                    duplicate.check()
                PublishJournal(folder, "other.user", digest).check()

    def test_validation_happens_before_opening_browser(self):
        with tempfile.TemporaryDirectory() as folder, patch("core.tiktok_browser._browser") as browser:
            file = Path(folder) / "test.mp4"
            file.write_bytes(b"synthetic")
            for video, caption, username in ((str(file), "", "user"), (str(file), "x" * 2201, "user"),
                                              (str(file), "caption", ""), ("missing.mp4", "caption", "user")):
                with self.assertRaises(ValueError):
                    publish(folder, video, caption, username, lambda _: None)
            browser.assert_not_called()

    def test_worker_delivers_success_and_failure_without_marking_failed_post_as_done(self):
        import queue
        events = queue.Queue()
        account = {"username": "test.user", "display_name": "Test"}
        with patch("core.tiktok_browser.login", return_value=account):
            tiktok_worker("tiktok_login", "unused", {}, events)
        self.assertEqual(events.get_nowait(), ("tiktok_connected", account))
        with patch("core.tiktok_browser.publish", side_effect=RuntimeError("Upload failed")):
            tiktok_worker("tiktok_publish", "unused", {"video": "x", "caption": "y", "username": "z"}, events)
        self.assertEqual(events.get_nowait(), ("error", "Upload failed"))
        self.assertTrue(events.empty())
