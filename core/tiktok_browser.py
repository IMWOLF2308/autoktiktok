"""TikTok Studio automation using a dedicated, local browser profile.

Authentication remains interactive. No password collection, CAPTCHA handling,
private API calls, or changes to the user's normal browser profile.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse


HOME_URL = "https://www.tiktok.com/"
LOGIN_URL = "https://www.tiktok.com/login?redirect_url=https%3A%2F%2Fwww.tiktok.com%2F"
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?lang=en"
PROFILE_LABEL = re.compile(r"^(Profile|View profile|Your profile|Hồ sơ|Xem hồ sơ|Trang cá nhân)$", re.I)
POST_LABEL = re.compile(r"^(Post|Đăng)$", re.I)
SUCCESS_TEXT = re.compile(r"^(Video posted|Posted successfully|Your video has been posted|Đã đăng video|Đăng thành công)[.!\s]*$", re.I)
ACCEPTED_TEXT = re.compile(r"^(Your video (is being|has been) uploaded to TikTok|Video của bạn (đang|đã) được tải lên TikTok)[.!\s]*$", re.I)


def _save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_account(folder):
    try:
        data = json.loads((Path(folder) / "account.json").read_text(encoding="utf-8"))
        if isinstance(data, dict) and re.fullmatch(r"[A-Za-z0-9._]{1,24}", data.get("username", "")):
            return {"username": data["username"], "display_name": str(data.get("display_name") or data["username"])}
    except (OSError, ValueError, TypeError):
        pass
    return None


def profile_username(href):
    """Only accept a canonical TikTok profile, never a video/foreign link."""
    parsed = urlparse(urljoin(HOME_URL, href or ""))
    if parsed.scheme != "https" or parsed.hostname not in {"www.tiktok.com", "tiktok.com"}:
        return None
    match = re.fullmatch(r"/@([A-Za-z0-9._]{1,24})/?", parsed.path)
    return match.group(1) if match else None


def _own_account(page):
    if urlparse(page.url).hostname not in {"www.tiktok.com", "tiktok.com"}:
        return None
    # Never use arbitrary /@ links: those identify creators in the video feed.
    candidates = page.get_by_role("link", name=PROFILE_LABEL)
    candidates = candidates.or_(page.locator('a[data-e2e="nav-profile"], a[data-e2e="profile-icon"]'))
    usernames = set()
    for i in range(candidates.count()):
        link = candidates.nth(i)
        if link.is_visible():
            username = profile_username(link.get_attribute("href"))
            if username:
                usernames.add(username)
    if len(usernames) != 1:
        return None
    return {"username": usernames.pop()}


@contextmanager
def _browser(folder, *, headless=False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Thiếu thư viện đăng TikTok. Chạy: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt") from None
    browsers = [
        ("msedge", Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe"),
        ("msedge", Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe"),
        ("chrome", Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"),
        ("chrome", Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Google/Chrome/Application/chrome.exe"),
    ]
    channel = next((channel for channel, path in browsers if path.is_file()), None)
    if not channel:
        raise RuntimeError("Cần Microsoft Edge hoặc Google Chrome để đăng nhập TikTok.")
    profile = Path(folder) / "browser"
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile), channel=channel, headless=headless, viewport=None,
            args=["--start-maximized"], accept_downloads=False,
        )
        context.set_default_timeout(15000)
        context.set_default_navigation_timeout(60000)
        try:
            yield context
        finally:
            context.close()


def _wait_account(context, page, timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.is_closed():
            raise RuntimeError("Bạn đã đóng cửa sổ TikTok trước khi xác nhận đăng nhập.")
        # A session cookie alone is insufficient: also require the account's own
        # Profile navigation link rendered by the logged-in website.
        authenticated = any(cookie["name"] in {"sessionid", "sessionid_ss"} and cookie["value"]
                            for cookie in context.cookies(HOME_URL))
        account = _own_account(page) if authenticated else None
        if account:
            return account
        page.wait_for_timeout(750)
    raise RuntimeError("Chưa xác nhận được tài khoản TikTok. Hãy đăng nhập bằng QR/điện thoại, hoàn tất xác minh rồi mở trang chủ TikTok trong cửa sổ đó. Bấm Đăng nhập TikTok để thử lại.")


def login(folder, progress):
    progress("Đang mở TikTok • Bạn đăng nhập trong cửa sổ trình duyệt")
    with _browser(folder) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        account = _wait_account(context, page)
        account["display_name"] = account["username"]
        # Username is always sufficient; display name is optional decoration.
        try:
            page.goto(HOME_URL + "@" + account["username"], wait_until="domcontentloaded")
            subtitle = page.locator('[data-e2e="user-subtitle"]')
            subtitle.wait_for(state="visible", timeout=5000)
            account["display_name"] = subtitle.inner_text().strip() or account["username"]
        except Exception:
            pass
    _save_json(Path(folder) / "account.json", account)
    return account


def video_digest(video):
    with Path(video).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class PublishJournal:
    """Write BEFORE clicking Post; interrupted submissions must not auto-retry."""
    def __init__(self, folder, username, digest):
        self.username = username
        key = hashlib.sha256(f"{username.casefold()}:{digest}".encode()).hexdigest()
        self.path = Path(folder) / "posts" / f"{key}.json"

    def check(self):
        if not self.path.exists():
            return
        try:
            previous = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RuntimeError("Không đọc được nhật ký đăng TikTok. Chưa đăng lại để tránh trùng video.") from None
        if previous.get("status") in {"posted", "submitted"}:
            raise RuntimeError("Video này đã được gửi lên tài khoản TikTok đã chọn. Không đăng trùng lần nữa.")
        raise RuntimeError("Lần đăng video này chưa có kết quả chắc chắn. Hãy kiểm tra kênh TikTok trước khi thử lại; tool đã chặn đăng lặp. Nhật ký: " + str(self.path))

    def record(self, status, video, caption):
        _save_json(self.path, {"status": status, "username": self.username,
                              "video": str(video), "caption": caption,
                              "time": datetime.now(timezone.utc).isoformat()})


def _unique_visible(locator):
    visible = [locator.nth(i) for i in range(locator.count()) if locator.nth(i).is_visible()]
    return visible[0] if len(visible) == 1 else None


def _upload_surface(page, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for frame in page.frames:
            # File inputs are normally hidden behind the Select video button.
            inputs = frame.locator('input[type="file"]')
            if inputs.count() == 1:
                return frame, inputs
        page.wait_for_timeout(500)
    raise RuntimeError("Không tìm thấy ô tải video của TikTok Studio. Hãy kiểm tra phiên đăng nhập hoặc màn hình xác minh TikTok.")


def _caption_editor(surface, timeout=120):
    deadline = time.monotonic() + timeout
    selectors = ('[contenteditable="true"][role="textbox"]',
                 '.public-DraftEditor-content[contenteditable="true"]',
                 '[contenteditable="true"][data-placeholder]',
                 'textarea[name="caption"]')
    while time.monotonic() < deadline:
        for selector in selectors:
            editor = _unique_visible(surface.locator(selector))
            if editor is not None:
                return editor
        surface.page.wait_for_timeout(500)
    raise RuntimeError("TikTok chưa hiển thị ô caption. Video chưa được đăng; hãy thử lại sau khi kiểm tra TikTok Studio.")


def _same_text(left, right):
    return " ".join(left.split()) == " ".join(right.split())


def _editor_text(editor):
    return editor.input_value() if editor.evaluate("el => /^(INPUT|TEXTAREA)$/.test(el.tagName)") else editor.inner_text()


def upload_and_post(page, video, caption, journal, progress, timeout=300, before_post=None):
    """Operate the Studio form. Also exercised against an offline browser fixture."""
    surface, file_input = _upload_surface(page)
    file_input.set_input_files(str(video))
    progress("Đang tải video lên TikTok Studio…")
    editor = _caption_editor(surface)
    editor.fill(caption)
    # Give controlled editors time to apply their state before checking it.
    page.wait_for_timeout(750)
    if not _same_text(_editor_text(editor), caption):
        raise RuntimeError("Caption trên TikTok không khớp nội dung đã chọn. Chưa bấm Đăng.")
    deadline = time.monotonic() + timeout
    post = None
    while time.monotonic() < deadline:
        post = _unique_visible(surface.get_by_role("button", name=POST_LABEL))
        if post is not None and post.is_enabled():
            break
        page.wait_for_timeout(750)
    else:
        raise RuntimeError("TikTok chưa cho phép đăng video. Hãy kiểm tra xử lý video, bản quyền hoặc yêu cầu xác minh trên TikTok Studio.")
    if not _same_text(_editor_text(editor), caption):
        raise RuntimeError("Caption đã thay đổi trong khi tải video. Chưa bấm Đăng.")
    if before_post:
        before_post()
    if not _same_text(_editor_text(editor), caption):
        raise RuntimeError("Caption đã thay đổi trước khi đăng. Chưa bấm Đăng.")
    # Upload completion before Post is not evidence that a post was created.
    if any(_unique_visible(frame.get_by_text(pattern)) is not None
           for frame in page.frames for pattern in (SUCCESS_TEXT, ACCEPTED_TEXT)):
        raise RuntimeError("TikTok đang hiển thị kết quả của bài đăng khác. Chưa bấm Đăng video hiện tại.")
    journal.check()
    journal.record("submitting", video, caption)
    progress("Đang đăng video • Chờ TikTok xác nhận; không đóng cửa sổ")
    try:
        post.click()
        deadline = time.monotonic() + timeout
        prompted = False
        while time.monotonic() < deadline:
            for frame in page.frames:
                success = _unique_visible(frame.get_by_text(SUCCESS_TEXT))
                if success is not None:
                    journal.record("posted", video, caption)
                    return "posted"
                accepted = _unique_visible(frame.get_by_text(ACCEPTED_TEXT))
                if accepted is not None:
                    journal.record("submitted", video, caption)
                    return "submitted"
            # TikTok may require extra interactive copyright/account checks.
            # Do not click unrelated confirmation/consent dialogs blindly.
            if not prompted and page.get_by_role("dialog").count():
                progress("TikTok cần xác nhận thêm • Hãy kiểm tra hộp thoại trong trình duyệt để hoàn tất đăng")
                prompted = True
            page.wait_for_timeout(750)
    except Exception as exc:
        journal.record("unknown", video, caption)
        raise RuntimeError("Đã gửi lệnh Đăng nhưng chưa nhận được xác nhận. Hãy kiểm tra kênh TikTok; tool sẽ không tự đăng lặp.") from exc
    journal.record("unknown", video, caption)
    raise RuntimeError("TikTok chưa xác nhận đăng thành công. Hãy kiểm tra kênh; video vẫn được lưu trên máy và tool đã chặn đăng lặp.")


def publish(folder, video, caption, expected_username, progress):
    video = Path(video).resolve()
    if not video.is_file() or video.suffix.lower() != ".mp4":
        raise ValueError("Không tìm thấy video MP4 đã xuất để đăng TikTok.")
    caption = caption.strip()
    if not caption or len(caption) > 2200:
        raise ValueError("Caption đăng TikTok cần có nội dung và tối đa 2.200 ký tự.")
    if not re.fullmatch(r"[A-Za-z0-9._]{1,24}", expected_username or ""):
        raise ValueError("Hãy đăng nhập TikTok trước khi đăng video.")
    digest = video_digest(video)
    journal = PublishJournal(folder, expected_username, digest)
    journal.check()
    progress("Đang mở TikTok • Kiểm tra tài khoản trước khi đăng")
    with _browser(folder) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(HOME_URL, wait_until="domcontentloaded")
        account = _wait_account(context, page, timeout=90)
        if account["username"].casefold() != expected_username.casefold():
            raise RuntimeError(f'Tài khoản trình duyệt là @{account["username"]}, khác @{expected_username}. Hãy đăng nhập lại trên tool để chọn đúng tài khoản.')
        progress(f"Đúng tài khoản @{expected_username} • Đang mở TikTok Studio")
        page.goto(UPLOAD_URL, wait_until="domcontentloaded")
        def recheck():
            if video_digest(video) != digest:
                raise RuntimeError("File video đã thay đổi trong khi tải lên. Chưa bấm Đăng.")
            check_page = context.new_page()
            try:
                check_page.goto(HOME_URL, wait_until="domcontentloaded")
                current = _wait_account(context, check_page, timeout=20)
                if current["username"].casefold() != expected_username.casefold():
                    raise RuntimeError("Tài khoản TikTok đã thay đổi trong khi tải video. Chưa bấm Đăng.")
            finally:
                check_page.close()
                page.bring_to_front()
        status = upload_and_post(page, video, caption, journal, progress, before_post=recheck)
    return {"username": expected_username, "video": str(video), "profile_url": HOME_URL + "@" + expected_username, "status": status}


def tiktok_worker(action, folder, payload, events):
    def progress(text):
        events.put(("stage", text))
    try:
        if action == "tiktok_login":
            result = login(folder, progress)
            events.put(("tiktok_connected", result))
        elif action == "tiktok_publish":
            result = publish(folder, payload["video"], payload["caption"], payload["username"], progress)
            events.put(("tiktok_published", result))
        else:
            raise ValueError("Tác vụ TikTok không hợp lệ.")
    except Exception as exc:
        message = str(exc)
        if type(exc).__module__.startswith("playwright"):
            message = "Không thao tác được cửa sổ TikTok. Hãy kiểm tra mạng, đóng cửa sổ TikTok do tool mở còn sót lại rồi thử lại. Nếu vừa bấm Đăng, kiểm tra kênh trước để tránh đăng trùng."
        events.put(("error", message))
