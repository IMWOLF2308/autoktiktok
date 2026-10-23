"""Opt-in Edge integration fixture. All web requests are fulfilled locally.

Run: python -m unittest discover -s tests -p browser_tiktok_check.py -v
This never contacts TikTok or publishes any actual social-media content.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from core.tiktok_browser import (
    HOME_URL, UPLOAD_URL, PublishJournal, _browser, _own_account, _wait_account,
    load_account, login, publish, upload_and_post, video_digest,
)


FORM = """<!doctype html><html><body>
<input id="video" type="file" accept="video/*">
<div role="textbox" contenteditable="true">filename.mp4</div>
<button id="post" disabled>Post</button><div id="result"></div>
<script>
window.posts = 0;
document.querySelector('#video').onchange = () => setTimeout(() => document.querySelector('#post').disabled = false, 50);
document.querySelector('#post').onclick = () => {
  window.posts++;
  document.querySelector('#result').textContent = 'Video posted';
};
</script></body></html>"""


class PersistentBrowserCheck(unittest.TestCase):
    def test_dedicated_profile_remembers_session_and_closes_only_its_context(self):
        with tempfile.TemporaryDirectory() as folder:
            with _browser(folder, headless=True) as context:
                context.route("**/*", lambda route: route.fulfill(status=200, body="Local fixture"))
                page = context.pages[0]
                page.goto(HOME_URL)
                context.add_cookies([{"name": "sessionid", "value": "local-test-only", "url": HOME_URL,
                                      "expires": time.time() + 3600}])
            self.assertTrue(page.is_closed())
            with _browser(folder, headless=True) as context:
                self.assertTrue(any(cookie["name"] == "sessionid" and cookie["value"] == "local-test-only"
                                    for cookie in context.cookies(HOME_URL)))
            self.assertTrue((Path(folder) / "browser").is_dir())


class TikTokBrowserChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel="msedge", headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.video = self.folder / "fixture.mp4"
        self.video.write_bytes(b"local fixture video - never sent to a server")
        self.context = self.browser.new_context()
        self.username = "owner.test"
        self.form = FORM
        def route(request):
            url = request.request.url
            if "tiktokstudio/upload" in url:
                body = '<iframe src="/local-form"></iframe>'
            elif "/local-form" in url:
                body = self.form
            else:
                body = f'<a href="/@feed.creator">A feed creator</a><nav><a href="/@{self.username}">Profile</a></nav><h2 data-e2e="user-subtitle">Test Owner</h2>'
            request.fulfill(status=200, content_type="text/html", body=body)
        self.context.route("**/*", route)
        self.context.add_cookies([{"name": "sessionid", "value": "local-test-session", "url": HOME_URL}])
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()
        self.temp.cleanup()

    @contextmanager
    def local_browser(self, folder):
        try:
            yield self.context
        finally:
            self.context.close()

    def test_login_uses_own_profile_and_closes_browser_before_success(self):
        with patch("core.tiktok_browser._browser", self.local_browser):
            account = login(self.folder, lambda _: None)
        self.assertEqual(account, {"username": "owner.test", "display_name": "Test Owner"})
        self.assertEqual(load_account(self.folder), account)
        self.assertTrue(self.page.is_closed())

    def test_feed_profile_and_cookie_alone_do_not_identify_account(self):
        self.page.goto(HOME_URL)
        self.page.locator("nav").evaluate("el => el.remove()")
        self.assertIsNone(_own_account(self.page))
        with self.assertRaises(RuntimeError):
            _wait_account(self.context, self.page, timeout=0.1)

    def test_upload_file_caption_and_click_only_once_then_confirm(self):
        self.page.goto(UPLOAD_URL)
        journal = PublishJournal(self.folder, self.username, video_digest(self.video))
        caption = "5,7 triệu: phòng có cửa sổ ở Gò Vấp! #phongtro #govap"
        upload_and_post(self.page, self.video, caption, journal, lambda _: None, timeout=2)
        form = self.page.frames[1]
        self.assertEqual(form.locator('[role="textbox"]').inner_text(), caption)
        self.assertEqual(form.locator('input[type="file"]').evaluate("el => el.files[0].name"), self.video.name)
        self.assertEqual(form.evaluate("window.posts"), 1)
        self.assertEqual(json.loads(journal.path.read_text(encoding="utf-8"))["status"], "posted")
        with self.assertRaises(RuntimeError):
            journal.check()

    def test_ambiguous_result_blocks_repeat_and_keeps_local_video(self):
        self.form = FORM.replace("'Video posted'", "'Processing upload'")
        self.page.goto(UPLOAD_URL)
        journal = PublishJournal(self.folder, self.username, video_digest(self.video))
        with self.assertRaises(RuntimeError):
            upload_and_post(self.page, self.video, "Independent caption", journal, lambda _: None, timeout=0.2)
        self.assertEqual(json.loads(journal.path.read_text(encoding="utf-8"))["status"], "unknown")
        self.assertTrue(self.video.is_file())
        with self.assertRaises(RuntimeError):
            journal.check()

    def test_tiktok_acceptance_is_not_reported_as_published(self):
        self.form = FORM.replace("'Video posted'", "'Your video is being uploaded to TikTok!'")
        self.page.goto(UPLOAD_URL)
        journal = PublishJournal(self.folder, self.username, video_digest(self.video))
        status = upload_and_post(self.page, self.video, "Caption", journal, lambda _: None, timeout=2)
        self.assertEqual(status, "submitted")
        with self.assertRaises(RuntimeError):
            journal.check()

    def test_upload_completion_before_post_is_not_publish_success(self):
        self.form = FORM.replace('<div id="result"></div>', '<div id="result">Video uploaded</div>').replace("'Video posted'", "'Processing upload'")
        self.page.goto(UPLOAD_URL)
        journal = PublishJournal(self.folder, self.username, video_digest(self.video))
        with self.assertRaises(RuntimeError):
            upload_and_post(self.page, self.video, "Caption", journal, lambda _: None, timeout=0.2)
        self.assertEqual(json.loads(journal.path.read_text(encoding="utf-8"))["status"], "unknown")

    def test_wrong_account_stops_before_upload(self):
        with patch("core.tiktok_browser._browser", self.local_browser), patch("core.tiktok_browser.upload_and_post") as upload:
            with self.assertRaisesRegex(RuntimeError, "khác"):
                publish(self.folder, self.video, "Caption", "different.user", lambda _: None)
            upload.assert_not_called()

    def test_account_switch_while_uploading_stops_before_post(self):
        def switch_account(stage):
            if "Đang tải video" in stage:
                self.username = "changed.user"
        with patch("core.tiktok_browser._browser", self.local_browser):
            with self.assertRaisesRegex(RuntimeError, "đã thay đổi"):
                publish(self.folder, self.video, "Caption", "owner.test", switch_account)
        self.assertFalse((self.folder / "posts").exists())
