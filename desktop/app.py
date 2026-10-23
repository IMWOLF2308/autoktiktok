import json
import multiprocessing
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime

from PIL import Image, ImageTk
from core.content_rules import prepare_voiceover
from core.gemini_config import DEFAULT_REVIEW_MODEL, normalize_review_model
from core.process_utils import run_command
from core.tiktok_browser import load_account, tiktok_worker
from desktop.pipeline import JobConfig, cleanup_work, default_asset, validate_job, validate_style, worker_entry

from desktop.studio_ui import ACCENT, BG, GREEN, StudioUI


def resource_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def settings_path():
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AutoEditTikTok" / "settings.json"
    return resource_root() / ".appdata" / "settings.json"


class AutoEditApp(StudioUI, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AutoEdit TikTok • Studio")
        width = min(1440, self.winfo_screenwidth() - 60)
        height = min(960, self.winfo_screenheight() - 100)
        self.geometry(f"{width}x{height}+20+20")
        self.minsize(min(940, width), min(600, height))
        self.configure(bg=BG)
        self.option_add("*Font", ("Segoe UI", 10))
        self.process = None
        self.events = None
        self.cancel_thread = None
        self.cancel_result = queue.Queue()
        self.closing = False
        self.last_video = ""
        self.last_export = None
        self.tiktok_account = load_account(settings_path().parent / "tiktok")
        self.auto_post = tk.BooleanVar(value=False)
        self.pending_publish = None
        self.post_after_login = False
        self.active_work = None
        self.generated_voice_script = None
        self.generated_content_video = None
        self.source_ready = None
        self.confirmed_voice = None
        self.vars = {}
        self.actions = []
        self.inputs = []
        self.pages = {}
        self.nav = {}
        self.preview_image = None
        self._styles()
        self._variables()
        self._layout()
        self._load_settings()
        self.vars["voice_file"].trace_add("write", lambda *args: self.refresh_navigation())
        self.show_page("video")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind_all("<MouseWheel>", self._wheel)
        self.after(100, self._poll)
        self.log("Sẵn sàng. Chọn video để Gemini phân tích; thông tin bổ sung có thể để trống.")

    def _variables(self):
        root = resource_root()
        default_output = (Path.home() / "Videos" / "AutoEditTikTok") if getattr(sys, "frozen", False) else root / "output_videos"
        defaults = dict(
            video="", output_dir=str(default_output), api_key=os.environ.get("GEMINI_API_KEY", ""),
            model=DEFAULT_REVIEW_MODEL, voice_file="", engine="Gemini + Edge dự phòng",
            voice="vi-VN-HoaiMyNeural", rate="+24%",
            logo=default_asset("logo/logo.png"), bgm="",
            contact1="LH Ngay", contact2="SDT/ZALO : ", contact_duration="8", bgm_volume="16",
        )
        for name, value in defaults.items():
            self.vars[name] = tk.StringVar(value=value)
        for name, value in [("use_logo", True), ("use_bgm", True), ("use_contact", True), ("allow_model_fallback", True)]:
            self.vars[name] = tk.BooleanVar(value=value)
        self.status = tk.StringVar(value="Sẵn sàng")

    def _wheel(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        page = self.pages[self.current_page]
        if str(widget).startswith(str(page)):
            amount = -1 if event.delta > 0 else 1
            if isinstance(widget, tk.Text):
                first, last = widget.yview()
                if (amount < 0 and first > 0) or (amount > 0 and last < 1):
                    widget.yview_scroll(amount * 3, "units")
                    return "break"
            page.canvas.yview_scroll(amount * 3, "units")
            return "break"

    def pick_file(self, name, label, extensions):
        path = filedialog.askopenfilename(parent=self, title=f"Chọn {label.lower()}", filetypes=[(label, extensions), ("Tất cả", "*.*")])
        if path:
            self.vars[name].set(path)
            if name in {"logo", "bgm"}:
                self.vars[f"use_{name}"].set(True)
            if name == "voice_file":
                self.generated_voice_script = None
                self.refresh_navigation()

    def pick_output(self):
        path = filedialog.askdirectory(parent=self, title="Chọn thư mục xuất")
        if path:
            self.vars["output_dir"].set(path)

    def snapshot(self, action=None):
        values = {k: v.get() for k, v in self.vars.items()}
        values["model"] = normalize_review_model(values["model"]) or DEFAULT_REVIEW_MODEL
        try:
            style_needed = action in {None, "render", "all"}
            values["contact_duration"] = float(values["contact_duration"].replace(",", ".")) if style_needed else 8.0
            values["bgm_volume"] = float(values["bgm_volume"].replace(",", ".")) / 100 if style_needed else 0.16
        except ValueError:
            raise ValueError("Âm lượng và số giây phải là số hợp lệ.") from None
        if action in {"inspect", "draft", "voice", "check_voice"}:
            values["output_dir"] = str(settings_path().parent / "drafts")
        return JobConfig(**values, room_info=self.room_text.get("1.0", "end").strip(),
                         script=self.script_text.get("1.0", "end").strip(), caption=self.caption_text.get("1.0", "end").strip())

    def source_signature(self):
        path = self.vars["video"].get()
        try:
            file = Path(path)
            info = file.stat()
            return (str(file.resolve()), info.st_size, info.st_mtime_ns, self.room_text.get("1.0", "end").strip()) if file.is_file() else None
        except OSError:
            return None

    def voice_signature(self):
        path = Path(self.vars["voice_file"].get())
        if not path.is_file():
            raise ValueError("Hãy tạo hoặc chọn file giọng đọc trước khi tiếp tục.")
        info = path.stat()
        return (str(path.resolve()), info.st_size, info.st_mtime_ns, self.script_text.get("1.0", "end").strip())

    def check_current_voice(self):
        if not self.script_text.get("1.0", "end").strip():
            raise ValueError("Kịch bản đang trống. Hãy nhập lời bình trước khi xác nhận.")
        if self.generated_voice_script is not None and self.generated_voice_script != self.script_text.get("1.0", "end").strip():
            raise ValueError("Bạn đã sửa kịch bản sau khi tạo giọng. Hãy tạo lại giọng hoặc chọn file thu âm phù hợp.")
        return self.voice_signature()

    def previous_step(self):
        if not self.process and self.current_step > 0:
            self.show_step(self.current_step - 1)

    def next_step(self):
        if self.process:
            return
        try:
            if self.current_step == 0:
                if self.source_ready is not None and self.source_ready == self.source_signature():
                    self.show_step(1)
                elif not self.vars["api_key"].get().strip():
                    self.open_connection()
                else:
                    self.start("draft")
            elif self.current_step == 1:
                self.check_current_voice()
                self.start("check_voice")
            elif self.current_step == 2:
                if self.confirmed_voice != self.check_current_voice():
                    self.show_step(1)
                    raise ValueError("Âm thanh hoặc kịch bản đã thay đổi. Hãy xác nhận lại ở bước 2.")
                validate_style(self.snapshot())
                self.show_step(3)
            else:
                self.start("render")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Chưa thể tiếp tục", str(exc), parent=self)

    def start(self, action):
        if self.process is not None:
            return
        try:
            if action in {"voice", "all"} and self.script_text.get("1.0", "end").strip():
                self._set_text(self.script_text, prepare_voiceover(self.script_text.get("1.0", "end").strip()))
            config = self.snapshot(action)
            if action == "render":
                try:
                    current_voice = self.check_current_voice()
                except (ValueError, OSError):
                    self.show_step(1)
                    raise
                if self.confirmed_voice is None or self.confirmed_voice != current_voice:
                    self.show_step(1)
                    raise ValueError("Hãy xác nhận file âm thanh ở bước 2 trước khi xuất video.")
                if self.source_ready is None or self.source_ready != self.source_signature():
                    self.show_step(0)
                    raise ValueError("Video hoặc yêu cầu AI đã thay đổi. Hãy tạo lại kịch bản ở bước 1.")
            if action in {"voice", "check_voice"} and (self.source_ready is None or self.source_ready != self.source_signature()):
                self.show_step(0)
                raise ValueError("Video hoặc yêu cầu AI đã thay đổi. Hãy tạo lại kịch bản ở bước 1.")
            if action == "check_voice":
                self.pending_voice = self.check_current_voice()
            validate_job(config, action)
            if (action in {"all", "render"} and config.script and self.generated_content_video
                    and str(Path(config.video).resolve()) != self.generated_content_video):
                raise ValueError("Video đã thay đổi. Hãy bấm Gemini phân tích & viết để tạo nội dung cho video mới.")
            if action == "render" and self.generated_voice_script is not None and config.script != self.generated_voice_script:
                raise ValueError("Bạn đã sửa lời bình sau khi tạo giọng. Hãy tạo lại giọng đọc hoặc bấm TẠO VIDEO.")
            if action == "draft" and config.script and not messagebox.askyesno("Viết lại lời bình?", "Lời bình và caption hiện tại sẽ được thay bằng nội dung AI mới.", parent=self):
                return
            if action in {"draft", "voice"}:
                self.confirmed_voice = None
                self.vars["voice_file"].set("")
            if action == "draft":
                self.source_ready = None
                self.pending_source = self.source_signature()
            if action == "render":
                if self.auto_post.get() and not self.tiktok_account:
                    raise ValueError("Hãy bấm Đăng nhập TikTok trước, hoặc bỏ chọn đăng tự động để chỉ xuất video.")
                if self.auto_post.get() and not config.caption.strip():
                    raise ValueError("Hãy nhập caption ở bước 2 trước khi đăng TikTok.")
                self.active_export = {"caption": config.caption, "selection": self.export_selection()}
                self.pending_publish = {"username": self.tiktok_account["username"]} if self.auto_post.get() else None
            self._save_settings()
            context = multiprocessing.get_context("spawn")
            self.events = context.Queue()
            self.process = context.Process(target=worker_entry, args=(config, action, self.events), daemon=True)
            self.active_script = config.script
            self.active_video = str(Path(config.video).resolve()) if config.video else ""
            self.active_action = action
            self.process.start()
            self._busy(True)
            self.status.set("Đang khởi động tác vụ…")
            self.log(f"Bắt đầu: {action}")
        except Exception as exc:
            if self.process is not None and self.process.pid is None:
                self.process = None
                if self.events:
                    self.events.close()
                    self.events = None
            self.log(str(exc))
            messagebox.showerror("Chưa thể bắt đầu", str(exc), parent=self)

    def export_selection(self):
        """Bind a post to the exact render selection, not a stale last_video."""
        keys = ("video", "voice_file", "logo", "use_logo", "bgm", "use_bgm", "bgm_volume",
                "use_contact", "contact1", "contact2", "contact_duration")
        return ({key: self.vars[key].get() for key in keys}, self.source_signature(),
                self.voice_signature(), self.caption_text.get("1.0", "end").strip())

    def connect_tiktok(self):
        self.start_tiktok("tiktok_login")

    def auto_post_changed(self):
        if not self.auto_post.get() or self.process:
            return
        if not self.tiktok_account:
            self.connect_tiktok()
        elif self.last_export:
            self.post_latest_video()

    def post_latest_video(self):
        if self.process:
            return
        try:
            if not self.last_export or not Path(self.last_export["video"]).is_file():
                raise ValueError("Hãy xuất video trước. Nếu đã tích đăng tự động, tool sẽ đăng ngay sau khi xuất xong.")
            if self.last_export["selection"] != self.export_selection():
                raise ValueError("Nội dung hoặc lựa chọn đã thay đổi. Hãy xuất lại video để đăng đúng bản mới nhất.")
            if not self.tiktok_account:
                self.post_after_login = True
                self.connect_tiktok()
                return
            self.start_tiktok("tiktok_publish", {"video": self.last_export["video"],
                              "caption": self.last_export["caption"], "username": self.tiktok_account["username"]})
        except (ValueError, OSError) as exc:
            messagebox.showerror("Chưa thể đăng TikTok", str(exc), parent=self)

    def start_tiktok(self, action, payload=None):
        if self.process:
            return
        try:
            context = multiprocessing.get_context("spawn")
            self.events = context.Queue()
            self.process = context.Process(target=tiktok_worker,
                args=(action, str(settings_path().parent / "tiktok"), payload or {}, self.events), daemon=True)
            self.active_action = action
            self.process.start()
            self._busy(True)
            self.status.set("Đang mở TikTok…")
        except Exception as exc:
            if self.process is not None and self.process.pid is None:
                self.process = None
                self.events.close()
                self.events = None
            self._busy(False)
            messagebox.showerror("Chưa mở được TikTok", str(exc), parent=self)

    def _busy(self, busy):
        for b in self.actions:
            b.configure(state="disabled" if busy else "normal")
        for widget, state in self.inputs:
            widget.configure(state="disabled" if busy else state)
        self.stop_button.configure(state="normal" if busy else "disabled")
        if busy:
            self.status_indicator.configure(fg=ACCENT)
            self.progress.pack(fill="both", expand=True)
            self.progress.start(12)
        else:
            self.status_indicator.configure(fg=GREEN)
            self.progress.stop()
            self.progress["value"] = 0
            self.progress.pack_forget()
        self.refresh_navigation()

    def log(self, text):
        secret = self.vars["api_key"].get()
        if secret:
            text = text.replace(secret, "[API KEY]")
        self.logs.configure(state="normal")
        self.logs.insert("end", f"[{datetime.now():%H:%M:%S}] {text}\n")
        if int(self.logs.index("end-1c").split(".")[0]) > 1200:
            self.logs.delete("1.0", "200.0")
        self.logs.see("end")
        self.logs.configure(state="disabled")

    def clear_log(self):
        self.logs.configure(state="normal")
        self.logs.delete("1.0", "end")
        self.logs.configure(state="disabled")

    def _set_text(self, widget, text):
        state = widget.cget("state")
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state=state)

    def _preview(self, path):
        try:
            with Image.open(path) as img:
                img.thumbnail((170, 90))
                self.preview_image = ImageTk.PhotoImage(img.copy())
            self.preview.configure(image=self.preview_image, text="")
        except Exception as exc:
            self.log(f"Không thể xem ảnh: {exc}")

    def _handle(self, kind, value):
        if kind == "work":
            self.active_work = value
        elif kind == "log":
            self.log(value)
        elif kind == "stage":
            self.status.set(value)
            self.log(value)
        elif kind == "script":
            self._set_text(self.script_text, value["script"])
            self._set_text(self.caption_text, value["caption"])
            self.active_script = value["script"]
            self._set_text(self.analysis_text, value["room_info"])
            self.review_model_label.configure(text=f'AI đã dùng: {value.get("model", self.vars["model"].get())}')
            self.generated_content_video = self.active_video
        elif kind == "storyboard":
            self._preview(value)
        elif kind == "voice":
            self.vars["voice_file"].set(value)
            self.generated_voice_script = self.active_script
        elif kind == "music":
            self.music_status.configure(text=f'Đã chọn · {value["title"]} · CC0')
            self.log(f'Nhạc: {value["title"]}. Thông tin nguồn được lưu trong file .music.txt cạnh video.')
        elif kind == "tiktok_connected":
            self.tiktok_account = value
            self._finish()
            self.refresh_tiktok_badge(verified=True)
            name = value.get("display_name") or value["username"]
            self.status.set(f"Đã đăng nhập thành công: {name} (@{value['username']})")
            self.log(self.status.get())
            post_after_login = self.post_after_login
            self.post_after_login = False
            if (self.auto_post.get() or post_after_login) and self.last_export:
                self.post_latest_video()
        elif kind == "tiktok_published":
            self._finish()
            self.auto_post.set(False)
            message = "TikTok đã nhận video, đang xử lý" if value.get("status") == "submitted" else "Đã đăng video lên TikTok"
            self.export_result.configure(text=f"✓ {message}: @{value['username']} • {Path(value['video']).name}")
            self.status.set(f"{message}: @{value['username']}")
            self.log(self.status.get())
        elif kind == "done":
            action = getattr(self, "active_action", None)
            if value.get("storyboard"):
                self._preview(value["storyboard"])
            if value.get("video"):
                self.last_video = value["video"]
                self.log(f"Đã xuất: {self.last_video}")
            self.status.set("Hoàn tất • " + (Path(self.last_video).name if value.get("video") else "Sẵn sàng cho bước tiếp theo"))
            self.log("Tác vụ hoàn tất.")
            self._finish()
            if action == "draft":
                self.source_ready = self.pending_source
                self.show_step(1)
                self.status.set("Kịch bản đã sẵn sàng • Chỉnh lời bình và tạo giọng đọc")
            elif action == "check_voice":
                try:
                    current_voice = self.voice_signature()
                except (OSError, ValueError):
                    current_voice = None
                if self.pending_voice == current_voice:
                    self.confirmed_voice = self.pending_voice
                    self.show_step(2)
                    self.status.set("Đã xác nhận âm thanh • Chọn nhạc và logo")
                else:
                    self.status.set("File âm thanh đã thay đổi trong khi kiểm tra. Hãy xác nhận lại.")
            elif action == "voice":
                self.status.set("Đã tạo giọng • Nghe thử rồi bấm Xác nhận âm thanh")
            elif action == "render":
                self.export_result.configure(text=f"✓ Đã xuất: {Path(self.last_video).name}")
                self.last_export = dict(self.active_export, video=self.last_video)
                pending = self.pending_publish
                self.pending_publish = None
                if pending:
                    self.start_tiktok("tiktok_publish", dict(pending, video=self.last_video, caption=self.last_export["caption"]))
        elif kind == "error":
            self.pending_publish = None
            self.post_after_login = False
            self.status.set("Có lỗi • Xem nhật ký để biết chi tiết")
            self.log(value)
            self._finish()
            self.status_indicator.configure(fg="#b84659")
            if not self.terminal.winfo_manager():
                self.toggle_log()
            messagebox.showerror("Xử lý chưa hoàn tất", value[:900], parent=self)

    def _finish(self):
        if self.process:
            self.process.join(timeout=0.05)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=0.2)
            self.process.close()
        self.process = None
        if self.events:
            # Cancellation may happen before the UI consumes the workspace event.
            try:
                while True:
                    kind, value = self.events.get_nowait()
                    if kind == "work":
                        self.active_work = value
            except queue.Empty:
                pass
            self.events.close()
        self.events = None
        if self.active_work:
            try:
                cleanup_work(Path(self.active_work["path"]), Path(self.active_work["output_dir"]))
            except (OSError, ValueError) as exc:
                self.log(f"Chưa dọn được thư mục tạm: {exc}")
            self.active_work = None
        self._busy(False)

    def _poll(self):
        if self.cancel_thread:
            try:
                error = self.cancel_result.get_nowait()
            except queue.Empty:
                self.after(100, self._poll)
                return
            self.cancel_thread = None
            if error:
                self.log(error)
                self.stop_button.configure(state="normal")
                self.closing = False
            else:
                self._finish()
                self.pending_publish = None
                self.post_after_login = False
                self.status.set("Đã dừng tác vụ")
                self.log("Đã dừng tác vụ và các tiến trình con.")
                if self.closing:
                    self.destroy()
                    return
        if self.events:
            try:
                for _ in range(150):
                    if not self.events:
                        break
                    kind, value = self.events.get_nowait()
                    self._handle(kind, value)
            except queue.Empty:
                pass
            if self.process and not self.process.is_alive():
                # A final queue message may arrive just after process exit.
                try:
                    kind, value = self.events.get(timeout=0.05)
                    self._handle(kind, value)
                except queue.Empty:
                    self.log(f"Tiến trình đã thoát bất thường (mã {self.process.exitcode}).")
                    self.status.set("Tác vụ bị gián đoạn")
                    self._finish()
        self.after(100, self._poll)

    def cancel(self):
        if not self.process or self.cancel_thread:
            return
        process = self.process
        self.stop_button.configure(state="disabled")
        self.status.set("Đang dừng tác vụ…")
        def stop():
            try:
                if process.is_alive():
                    if os.name == "nt":
                        result = run_command(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                        if result.returncode and process.is_alive():
                            raise RuntimeError("Không thể dừng cây tiến trình. Hãy thử lại.")
                    else:
                        process.terminate()
                    process.join(timeout=3)
                self.cancel_result.put(None)
            except Exception as exc:
                self.cancel_result.put(str(exc))
        self.cancel_thread = threading.Thread(target=stop, daemon=True)
        self.cancel_thread.start()

    def open_path(self, path):
        if not path or not Path(path).exists():
            messagebox.showinfo("Chưa có tệp", "Hãy tạo hoặc chọn tệp/thư mục trước.", parent=self)
            return
        try:
            os.startfile(str(Path(path).resolve()))
        except OSError as exc:
            messagebox.showerror("Không mở được", str(exc), parent=self)

    def copy_caption(self):
        self.clipboard_clear()
        self.clipboard_append(self.caption_text.get("1.0", "end").strip())
        self.log("Đã sao chép caption.")

    def _load_settings(self):
        try:
            data = json.loads(settings_path().read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            for key, value in data.items():
                if key in self.vars and key != "voice_file":
                    self.vars[key].set(value)
            self.vars["model"].set(normalize_review_model(self.vars["model"].get()) or DEFAULT_REVIEW_MODEL)
            if not self.vars["logo"].get() or self.vars["logo"].get() == "@bundled":
                self.vars["logo"].set(default_asset("logo/logo.png"))
            # Migrate the old bundled default; preserve users' own music files.
            bgm = self.vars["bgm"].get()
            if bgm == "@bundled" or (bgm and Path(bgm).resolve() == Path(default_asset("bgm/upbeat_tiktok_bgm.mp3")).resolve()):
                self.vars["bgm"].set("")
            # Room notes belong to this video, not to global app settings.
            # Never re-inject legacy sample room_info on the next launch.
        except (OSError, ValueError, tk.TclError):
            pass

    def _save_settings(self):
        self.vars["model"].set(normalize_review_model(self.vars["model"].get()) or DEFAULT_REVIEW_MODEL)
        data = {k: v.get() for k, v in self.vars.items() if k != "voice_file"}
        # One-file builds extract resources to a different directory each launch.
        for key, asset in (("logo", "logo/logo.png"), ("bgm", "bgm/upbeat_tiktok_bgm.mp3")):
            if Path(data[key]).resolve() == Path(default_asset(asset)).resolve():
                data[key] = "@bundled"
        try:
            path = settings_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            self.log(f"Không lưu được cấu hình: {exc}")

    def close(self):
        if self.process:
            if not messagebox.askyesno("Đang xử lý", "Dừng tác vụ đang chạy và đóng ứng dụng?", parent=self):
                return
            self.closing = True
            self._save_settings()
            self.cancel()
            return
        self._save_settings()
        self.destroy()


def main():
    app = AutoEditApp()
    app.mainloop()
