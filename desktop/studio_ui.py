"""Native studio presentation. Processing and persistence live in app/pipeline."""
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

BG = "#101219"
CARD = "#1b1e29"
TEXT = "#edf0f7"
MUTED = "#a0a9bc"
LINE = "#303646"
ACCENT = "#a99bff"
TINT = "#29263f"
GREEN = "#64d9b4"


class RoundedCard(tk.Canvas):
    """A responsive card with a real frame for keyboard-accessible controls."""
    def __init__(self, parent):
        super().__init__(parent, bg=BG, highlightthickness=0, height=80, width=1)
        self.body = tk.Frame(self, bg=CARD)
        self.window = self.create_window(16, 16, window=self.body, anchor="nw")
        self.bind("<Configure>", self._resize)
        self.body.bind("<Configure>", self._measure)

    def _resize(self, event):
        self.itemconfigure(self.window, width=max(1, event.width - 32))
        self._draw(event.width, self.winfo_height())

    def _measure(self, event):
        height = self.body.winfo_reqheight() + 32
        if int(self.cget("height")) != height:
            self.configure(height=height)
        self._draw(self.winfo_width(), height)

    def _draw(self, width, height):
        self.delete("surface")
        r, w, h = 14, width - 1, height - 1
        self.create_polygon(r, 1, w-r, 1, w, 1, w, r, w, h-r, w, h,
                            w-r, h, r, h, 1, h, 1, h-r, 1, r, 1, 1,
                            smooth=True, splinesteps=24, fill=CARD, outline=LINE,
                            tags="surface")
        self.tag_lower("surface")


class ScrollPage(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, yscrollincrement=20)
        self.body = tk.Frame(self.canvas, bg=BG)
        window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        def resize(event):
            width = min(1100, event.width)
            self.canvas.itemconfigure(window, width=width)
            self.canvas.coords(window, max(0, (event.width - width) // 2), 0)
        self.canvas.bind("<Configure>", resize)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(10, 0))
        self.canvas.pack(side="left", fill="both", expand=True)


class StudioUI:
    def _styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TEntry", fieldbackground="#131620", foreground=TEXT,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=(9, 8))
        style.map("TEntry", bordercolor=[("focus", ACCENT)],
                  fieldbackground=[("disabled", "#20232d")], foreground=[("disabled", MUTED)])
        style.configure("TCombobox", fieldbackground="#131620", background="#131620",
                        foreground=TEXT, arrowcolor=MUTED, bordercolor=LINE,
                        lightcolor=LINE, darkcolor=LINE, padding=(8, 7), arrowsize=12)
        style.map("TCombobox", fieldbackground=[("disabled", "#20232d"), ("readonly", "#131620")],
                  foreground=[("disabled", MUTED), ("readonly", TEXT)],
                  selectbackground=[("readonly", TINT)], selectforeground=[("readonly", TEXT)])
        style.map("TCombobox", background=[("active", TINT), ("disabled", CARD)])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=BG,
                        borderwidth=0, thickness=3, lightcolor=ACCENT, darkcolor=ACCENT)
        style.configure("Vertical.TScrollbar", background="#3a4153", troughcolor=BG,
                        borderwidth=0, arrowsize=11, arrowcolor=MUTED)
        style.map("Vertical.TScrollbar", background=[("active", "#505b74"), ("pressed", ACCENT)])
        self.option_add("*TCombobox*Listbox.background", CARD)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", TINT)
        self.option_add("*TCombobox*Listbox.selectForeground", ACCENT)

    def label(self, parent, text, size=10, color=TEXT, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kwargs)

    def paragraph(self, parent, text, color=MUTED, size=9):
        label = self.label(parent, text, size, color, justify="left", anchor="w", wraplength=250)
        label.pack(fill="x", pady=(4, 0))
        label.bind("<Configure>", lambda e: label.configure(wraplength=max(100, e.width)))
        return label

    def button(self, parent, text, command, primary=False, danger=False, tracked=True):
        background = "#35232e" if danger else "#7057db" if primary else TINT
        foreground = "#ff9bb0" if danger else "#ffffff" if primary else ACCENT
        hover = "#4a2b3b" if danger else "#7963ee" if primary else "#37314f"
        button = tk.Button(parent, text=text, command=command, bg=background, fg=foreground,
                           activebackground=hover, activeforeground=foreground,
                           font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                           padx=13, pady=9, cursor="hand2", disabledforeground="#778196",
                           highlightthickness=1, highlightbackground=background, highlightcolor=ACCENT)
        button.bind("<Enter>", lambda e: button.configure(bg=hover) if button.cget("state") != "disabled" else None)
        button.bind("<Leave>", lambda e: button.configure(bg=background))
        if tracked:
            self.actions.append(button)
        return button

    def card(self, parent, title, subtitle=""):
        panel = RoundedCard(parent)
        panel.pack(fill="x", pady=(0, 14))
        body = panel.body
        if title:
            self.label(body, title, 11, bold=True).pack(anchor="w")
        if subtitle:
            self.paragraph(body, subtitle)
        return body

    def field(self, parent, name, title, browse=None, secret=False):
        self.label(parent, title, 9, MUTED).pack(anchor="w", pady=(12, 5))
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x")
        entry = ttk.Entry(row, width=1, textvariable=self.vars[name], show="•" if secret else "")
        entry.pack(side="left", fill="x", expand=True)
        self.inputs.append((entry, "normal"))
        if browse:
            self.button(row, "Chọn", browse).pack(side="right", padx=(6, 0))
        return entry

    def text_box(self, parent, height=5):
        text = tk.Text(parent, height=height, width=1, wrap="word", bg="#131620", fg=TEXT,
                       insertbackground=ACCENT, selectbackground="#443c6b", selectforeground=TEXT,
                       relief="flat", padx=11, pady=10, undo=True, spacing1=2, spacing3=2,
                       highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
                       font=("Segoe UI", 10))
        text.pack(fill="both", expand=True, pady=(10, 0))
        text.bind("<MouseWheel>", self._wheel)
        self.inputs.append((text, "normal"))
        return text

    def check(self, parent, name, label):
        check = tk.Checkbutton(parent, text=label, variable=self.vars[name], bg=CARD, fg=TEXT,
                               activebackground=CARD, activeforeground=ACCENT,
                               selectcolor=TINT, disabledforeground=MUTED, bd=0, highlightthickness=0, cursor="hand2",
                               font=("Segoe UI", 10), anchor="w")
        check.pack(fill="x", pady=(10, 0))
        self.inputs.append((check, "normal"))

    def _layout(self):
        sidebar = tk.Frame(self, bg="#0b0d13", width=86)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        logo = tk.Canvas(sidebar, width=46, height=46, bg="#0b0d13", highlightthickness=0)
        logo.pack(pady=(24, 6))
        logo.create_oval(2, 2, 44, 44, fill=ACCENT, outline="")
        logo.create_polygon(19, 14, 19, 32, 32, 23, fill="white")
        self.label(sidebar, "AUTOEDIT", 8, "#c7c5dd", True).pack()
        nav = tk.Button(sidebar, text="▣\nVideo", command=lambda: self.show_page("video"),
                        bg="#29253e", fg="#e6e0ff", activebackground="#393250", activeforeground="white",
                        font=("Segoe UI", 10), bd=0, relief="flat", pady=13, cursor="hand2")
        nav.pack(fill="x", padx=9, pady=(38, 0))
        self.nav["video"] = nav
        self.label(sidebar, "STUDIO", 8, "#9291aa").pack(side="bottom", pady=22)

        shell = tk.Frame(self, bg=BG)
        shell.pack(side="left", fill="both", expand=True)
        header = tk.Frame(shell, bg=CARD, padx=26, pady=13)
        header.pack(fill="x")
        self.label(header, "Video studio", 10, TEXT, True).pack(side="left")
        self.button(header, "Hướng dẫn", self.toggle_help, tracked=False).pack(side="right")
        self.tiktok_button = self.button(header, "Đăng nhập TikTok", self.connect_tiktok)
        self.tiktok_button.configure(wraplength=185)
        self.tiktok_button.pack(side="right", padx=(8, 10))
        self.key_badge = self.label(header, "●  Chưa nhập API Key", 9, MUTED)
        self.key_badge.pack(side="right", padx=8)
        self.key_badge.configure(cursor="hand2")
        self.key_badge.bind("<Button-1>", lambda e: self.open_connection())
        tk.Frame(shell, bg=LINE, height=1).pack(fill="x")

        hero = tk.Frame(shell, bg=BG, padx=26, pady=18)
        hero.pack(fill="x")
        self.step_eyebrow = self.label(hero, "TOOL 01  /  VIDEO STUDIO", 8, ACCENT, True)
        self.step_eyebrow.pack(anchor="w", pady=(0, 6))
        self.step_title = self.label(hero, "", 23, TEXT, True)
        self.step_title.pack(anchor="w")
        self.step_subtitle = self.label(hero, "", 10, MUTED)
        self.step_subtitle.pack(anchor="w", pady=(5, 0))
        steps_bar = tk.Frame(hero, bg=BG)
        steps_bar.pack(fill="x", pady=(18, 0))
        self.step_labels = []
        for i, title in enumerate(("Video & yêu cầu", "Kịch bản & giọng", "Nhạc & logo", "Xuất video")):
            steps_bar.columnconfigure(i, weight=1, uniform="steps")
            label = self.label(steps_bar, f"{i + 1:02}   {title}", 10, MUTED, True, anchor="w", padx=12, pady=9)
            label.grid(row=0, column=i, sticky="ew", padx=(0, 6))
            self.step_labels.append(label)

        self.footer = tk.Frame(shell, bg=CARD, padx=24, pady=14)
        self.footer.pack(side="bottom", fill="x")
        self.run_button = self.button(self.footer, "", self.next_step, primary=True)
        self.run_button.pack(side="right")
        self.back_button = self.button(self.footer, "← Quay lại", self.previous_step)
        self.back_button.pack(side="right", padx=(8, 8))
        self.stop_button = self.button(self.footer, "Dừng", self.cancel, danger=True, tracked=False)
        self.stop_button.pack(side="right", padx=9)
        self.stop_button.configure(state="disabled")
        self.log_toggle = self.button(self.footer, "Nhật ký  ↑", self.toggle_log, tracked=False)
        self.log_toggle.pack(side="right", padx=(8, 4))
        self.status_indicator = self.label(self.footer, "●", 12, GREEN)
        self.status_indicator.pack(side="left", padx=(0, 9))
        self.status_label = tk.Label(self.footer, textvariable=self.status, bg=CARD, fg=TEXT,
                                     font=("Segoe UI", 9), anchor="w", justify="left", wraplength=300)
        self.status_label.pack(side="left", fill="x", expand=True)
        self.footer.bind("<Configure>", lambda e: self.status_label.configure(wraplength=max(100, e.width - 400)))

        self.terminal = tk.Frame(shell, bg="#0c0f16", padx=22, pady=10)
        bar = tk.Frame(self.terminal, bg="#0c0f16")
        bar.pack(fill="x")
        self.label(bar, "NHẬT KÝ HOẠT ĐỘNG", 8, MUTED, True).pack(side="left")
        self.button(bar, "Xóa", self.clear_log, tracked=False).pack(side="right")
        self.logs = tk.Text(self.terminal, height=4, bg="#0c0f16", fg="#b0bacd", font=("Consolas", 9),
                            relief="flat", state="disabled", wrap="word")
        self.logs.pack(fill="x", pady=(7, 0))
        self.progress_track = tk.Frame(shell, bg=LINE, height=3)
        self.progress_track.pack(side="bottom", fill="x")
        self.progress_track.pack_propagate(False)
        self.progress = ttk.Progressbar(self.progress_track, mode="indeterminate", maximum=100)

        self.page_host = tk.Frame(shell, bg=BG)
        self.page_host.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        page = ScrollPage(self.page_host)
        self.pages["video"] = page
        self.steps = [tk.Frame(page.body, bg=BG) for _ in range(4)]
        self._project_page(self.steps[0])
        self._script_page(self.steps[1])
        self._style_page(self.steps[2])
        self._export_page(self.steps[3])
        self.vars["api_key"].trace_add("write", self._refresh_key_badge)
        self.vars["video"].trace_add("write", self._refresh_media)
        self._refresh_key_badge()
        self.refresh_tiktok_badge()
        self._refresh_media()
        self.show_step(0)

    def two_columns(self, parent):
        columns = [tk.Frame(parent, bg=BG) for _ in range(2)]
        def resize(event):
            wide = event.width >= 880
            parent.columnconfigure(0, weight=3, uniform="pair")
            parent.columnconfigure(1, weight=2 if wide else 0, uniform="pair" if wide else "")
            columns[0].grid(row=0, column=0, sticky="nsew", padx=(0, 14 if wide else 0))
            columns[1].grid(row=0 if wide else 1, column=1 if wide else 0, sticky="nsew")
        parent.bind("<Configure>", resize)
        return columns

    def _project_page(self, parent):
        c = self.card(parent, "Video của bạn")
        media = tk.Frame(c, bg=CARD)
        media.pack(fill="x", pady=(14, 0))
        stage = tk.Frame(media, bg=TINT, width=180, height=100)
        stage.pack(side="left", padx=(0, 18))
        stage.pack_propagate(False)
        self.preview = self.label(stage, "▷\nVideo của bạn", 11, "#b4a7f2", justify="center")
        self.preview.pack(fill="both", expand=True)
        details = tk.Frame(media, bg=CARD)
        details.pack(side="left", fill="both", expand=True)
        self.media_label = self.paragraph(details, "Chưa chọn video", TEXT)
        self.media_detail = self.paragraph(details, "MP4, MOV, MKV, AVI hoặc WEBM", size=8)
        row = tk.Frame(details, bg=CARD)
        row.pack(fill="x", pady=(12, 0))
        self.button(row, "＋ Chọn video", lambda: self.pick_file("video", "Video", "*.mp4 *.mov *.mkv *.avi *.webm")).pack(side="left")
        self.button(row, "Xem khung hình", lambda: self.start("inspect")).pack(side="right")

        self.label(c, "Nội dung gửi cho AI", 11, bold=True).pack(anchor="w", pady=(18, 0))
        self.paragraph(c, "Nhập tư liệu, giá, địa chỉ hoặc điều cần nhấn mạnh. AI sẽ kết hợp với video để biên tập lời bình, không chép nguyên đoạn.")
        self.room_text = self.text_box(c, 4)
        self.room_text.bind("<<Modified>>", self._source_edited)

    def _script_page(self, parent):
        left, right = self.two_columns(parent)
        c = self.card(left, "Chỉnh kịch bản", "Đọc lại và sửa lời bình trước khi tạo giọng.")
        self.review_model_label = self.paragraph(c, "Chưa có kịch bản AI", ACCENT)
        self.label(c, "Lời bình", 10, TEXT, True).pack(anchor="w", pady=(12, 0))
        self.script_text = self.text_box(c, 8)
        self.word_count = self.label(c, "0 từ  ·  Nội dung sẽ được đọc thành lời", 8, MUTED)
        self.word_count.pack(anchor="w", pady=(6, 0))
        self.script_text.bind("<<Modified>>", self._update_word_count)
        self.label(c, "Caption TikTok", 10, TEXT, True).pack(anchor="w", pady=(16, 0))
        self.caption_text = self.text_box(c, 3)
        self.button(c, "Sao chép caption", self.copy_caption).pack(anchor="e", pady=(8, 0))

        c = self.card(right, "Giọng đọc", "Tạo giọng, nghe thử rồi xác nhận để tiếp tục.")
        for name, title, values in (
            ("engine", "Bộ tạo giọng", ["Gemini + Edge dự phòng", "Edge-TTS"]),
            ("voice", "Giọng Edge", ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]),
            ("rate", "Tốc độ Edge", ["+0%", "+12%", "+24%", "+35%"]),
        ):
            row = tk.Frame(c, bg=CARD)
            row.pack(fill="x", pady=(10, 0))
            self.label(row, title, 9, MUTED, width=12, anchor="w").pack(side="left")
            combo = ttk.Combobox(row, textvariable=self.vars[name], values=values, state="readonly", width=1)
            combo.pack(side="left", fill="x", expand=True)
            combo.bind("<MouseWheel>", self._wheel)
            self.inputs.append((combo, "readonly"))
        self.field(c, "voice_file", "File giọng đọc", lambda: self.pick_file("voice_file", "Âm thanh", "*.mp3 *.wav *.m4a *.aac"))
        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x", pady=(12, 0))
        self.button(row, "♫  Tạo giọng", lambda: self.start("voice")).pack(side="left")
        self.button(row, "Nghe thử", lambda: self.open_path(self.vars["voice_file"].get())).pack(side="right")

        self.voice_hint = self.paragraph(c, "Chưa có file âm thanh để xác nhận.", ACCENT)
        c = self.card(right, "Gemini quan sát được", "Mô tả từ video sau khi phân tích.")
        self.analysis_text = self.text_box(c, 4)
        self.inputs[-1] = (self.analysis_text, "disabled")
        self.analysis_text.configure(state="disabled")

    def _style_page(self, parent):
        left, right = self.two_columns(parent)
        c = self.card(right, "Logo thương hiệu")
        self.check(c, "use_logo", "Hiển thị logo")
        self.field(c, "logo", "Logo thương hiệu", lambda: self.pick_file("logo", "Hình ảnh", "*.png *.webp *.jpg *.jpeg"))
        c = self.card(left, "♫   Nhạc nền", "Tự tải nhạc miễn phí khi không chọn file.")
        self.check(c, "use_bgm", "Chèn nhạc vào video")
        self.music_status = self.paragraph(c, "", ACCENT)
        self.button(c, "↓  Tự tải nhạc miễn phí", self.use_auto_music).pack(fill="x", pady=(10, 0))
        self.paragraph(c, "Nguồn: OpenGameArt · Tuyển chọn nhạc CC0. Miễn phí sử dụng, không bắt buộc ghi công.", size=8)
        self.field(c, "bgm", "Hoặc chọn file của bạn", lambda: self.pick_file("bgm", "Âm thanh", "*.mp3 *.wav *.m4a *.aac *.mp4"))
        self.field(c, "bgm_volume", "Âm lượng nhạc (%)")
        self.vars["bgm"].trace_add("write", self._refresh_music)
        self.vars["use_bgm"].trace_add("write", self._refresh_music)
        self._refresh_music()

        c = self.card(right, "Thông tin liên hệ")
        self.check(c, "use_contact", "Hiện ở cuối video")
        self.field(c, "contact1", "Tiêu đề")
        self.field(c, "contact2", "Số điện thoại / Zalo")
        self.field(c, "contact_duration", "Thời gian hiển thị (giây)")

    def _export_page(self, parent):
        c = self.card(parent, "Sẵn sàng xuất video", "MP4 · Giữ tỷ lệ nguồn · 30 fps")
        self.export_summary = self.paragraph(c, "", TEXT, 10)
        self.field(c, "output_dir", "Lưu video vào", self.pick_output)
        self.export_result = self.paragraph(c, "Video sẽ dùng đúng file giọng đọc đã xác nhận.", ACCENT)
        self.tiktok_status = self.paragraph(c, "Chưa kết nối TikTok", MUTED)
        auto_post = tk.Checkbutton(c, text="Tự động đăng lên TikTok sau khi xuất video", variable=self.auto_post,
            command=self.auto_post_changed, bg=CARD, fg=TEXT, selectcolor=TINT,
            activebackground=CARD, activeforeground=ACCENT, disabledforeground=MUTED,
            bd=0, highlightthickness=0, anchor="w", cursor="hand2", font=("Segoe UI", 10))
        auto_post.pack(fill="x", pady=(10, 0))
        self.inputs.append((auto_post, "normal"))
        self.paragraph(c, "Tool mở TikTok Studio, điền caption ở bước 2 và bấm Đăng. Quyền xem dùng theo lựa chọn trên TikTok Studio.", size=8)
        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        self.button(row, "Thư mục", lambda: self.open_path(self.vars["output_dir"].get())).pack(side="left")
        self.button(row, "Video mới nhất", lambda: self.open_path(self.last_video)).pack(side="right")
        self.post_button = self.button(row, "Đăng video vừa tạo", self.post_latest_video)
        self.post_button.pack(side="right", padx=8)

    def refresh_tiktok_badge(self, verified=False):
        account = self.tiktok_account
        self.tiktok_button.configure(text=f"TikTok · @{account['username']}" if account else "Đăng nhập TikTok")
        if account:
            name = account.get("display_name") or account["username"]
            text = f"Đã đăng nhập thành công: {name} (@{account['username']})" if verified else f"Phiên đã lưu: @{account['username']} • Sẽ kiểm tra lại trước khi đăng"
        else:
            text = "Bấm Đăng nhập TikTok cạnh Gemini để kết nối tài khoản."
        self.tiktok_status.configure(text=text, fg=GREEN if verified else MUTED)

    def show_page(self, key):
        self.current_page = key
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)

    def toggle_help(self):
        messagebox.showinfo("Quy trình tạo video", "1. Chọn video, nhập yêu cầu và bấm Tạo kịch bản.\n\n2. Sửa lời bình, tạo hoặc chọn giọng đọc, nghe thử rồi bấm Xác nhận âm thanh.\n\n3. Chọn nhạc, logo và thông tin liên hệ.\n\n4. Chọn thư mục và xuất video.\n\nQuay lại để sửa từng bước; dữ liệu đã nhập được giữ nguyên.", parent=self)

    def open_connection(self):
        if self.process:
            return
        if getattr(self, "connection_dialog", None) and self.connection_dialog.winfo_exists():
            self.connection_dialog.lift()
            return
        dialog = tk.Toplevel(self)
        self.connection_dialog = dialog
        dialog.title("Kết nối Gemini")
        dialog.configure(bg=CARD, padx=24, pady=20)
        dialog.geometry("600x360")
        dialog.resizable(False, False)
        dialog.transient(self)
        self.label(dialog, "Kết nối Gemini", 16, bold=True).pack(anchor="w")
        self.paragraph(dialog, "API Key và model được nhớ trên máy của bạn.")
        # Dialog widgets are short-lived, unlike the tracked wizard controls.
        start = len(self.inputs)
        entry = self.field(dialog, "api_key", "API Key")
        self.field(dialog, "model", "Model phân tích")
        self.check(dialog, "allow_model_fallback", "Dùng Gemini 3.5 Flash Lite dự phòng khi model chính tạm lỗi")
        del self.inputs[start:]
        def close():
            self._save_settings()
            dialog.destroy()
        self.button(dialog, "Lưu & đóng", close, primary=True, tracked=False).pack(anchor="e", pady=(18, 0))
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.grab_set()
        entry.focus_set()

    def show_step(self, step):
        if self.process:
            return
        self.current_step = step
        for frame in self.steps:
            frame.pack_forget()
        self.steps[step].pack(fill="x")
        titles = ("Bắt đầu với video của bạn", "Kể theo cách của bạn", "Hoàn thiện dấu ấn riêng", "Xuất thành phẩm")
        subtitles = ("Chọn video và gửi yêu cầu. AI sẽ chuẩn bị kịch bản ở bước tiếp theo.",
                     "Chỉnh kịch bản, tạo giọng và xác nhận âm thanh trước khi đi tiếp.",
                     "Chọn nhạc nền, logo và thông tin hiển thị trên video.",
                     "Kiểm tra lựa chọn của bạn, rồi bắt đầu xuất video.")
        self.step_eyebrow.configure(text=f"TOOL 01  /  BƯỚC {step + 1} CỦA 4")
        self.step_title.configure(text=titles[step])
        self.step_subtitle.configure(text=subtitles[step])
        for i, label in enumerate(self.step_labels):
            label.configure(bg=TINT if i == step else BG, fg=ACCENT if i == step else GREEN if i < step else MUTED)
        if step == 3:
            music = (Path(self.vars["bgm"].get()).name or "Tự tải nhạc CC0") if self.vars["use_bgm"].get() else "Tắt"
            logo = Path(self.vars["logo"].get()).name if self.vars["use_logo"].get() else "Tắt"
            self.export_summary.configure(text=f'Video: {Path(self.vars["video"].get()).name}\nGiọng đọc: {Path(self.vars["voice_file"].get()).name}\nNhạc nền: {music}\nLogo: {logo}')
        self.refresh_navigation()
        self.update_idletasks()
        self.pages["video"].canvas.yview_moveto(0)

    def refresh_navigation(self):
        if not hasattr(self, "current_step"):
            return
        busy = self.process is not None
        labels = ("Tiếp tục →" if self.source_ready is not None and self.source_ready == self.source_signature() else "✦  Tạo kịch bản", "Xác nhận âm thanh →", "Tiếp theo →", "▶  Xuất video")
        self.run_button.configure(text=labels[self.current_step], state="disabled" if busy else "normal")
        self.back_button.configure(state="disabled" if busy or self.current_step == 0 else "normal")
        if hasattr(self, "voice_hint"):
            path = self.vars["voice_file"].get()
            stale = self.generated_voice_script is not None and self.generated_voice_script != self.script_text.get("1.0", "end").strip()
            self.voice_hint.configure(text="Kịch bản đã đổi. Hãy tạo lại giọng đọc." if stale else f"Sẵn sàng xác nhận: {Path(path).name}" if path else "Chưa có file âm thanh để xác nhận.")

    def toggle_log(self):
        if self.terminal.winfo_manager():
            self.terminal.pack_forget()
            self.log_toggle.configure(text="Nhật ký  ↑")
        else:
            self.terminal.pack(side="bottom", fill="x", after=self.footer)
            self.log_toggle.configure(text="Nhật ký  ↓")

    def scroll_to(self, widget):
        self.update_idletasks()
        page = self.pages["video"]
        y = widget.winfo_rooty() - page.body.winfo_rooty() - 16
        page.canvas.yview_moveto(max(0, y) / max(1, page.body.winfo_height()))

    def use_auto_music(self):
        self.vars["use_bgm"].set(True)
        self.vars["bgm"].set("")

    def _refresh_music(self, *args):
        path = self.vars["bgm"].get().strip()
        text = "Tự động tải khi render / dùng lại nhạc đã tải" if not path else f"File riêng · {Path(path).name}"
        self.music_status.configure(text=text if self.vars["use_bgm"].get() else "Đã tắt nhạc nền")

    def _refresh_key_badge(self, *args):
        present = bool(self.vars["api_key"].get().strip())
        self.key_badge.configure(text="⚙  Gemini · Đã nhập Key" if present else "⚙  Cài đặt Gemini · Chưa có Key",
                                 fg=GREEN if present else MUTED)

    def _refresh_media(self, *args):
        self.source_ready = None
        self.confirmed_voice = None
        path = self.vars["video"].get()
        self.media_label.configure(text=Path(path).name if path else "Chưa chọn video")
        detail = "MP4, MOV, MKV, AVI hoặc WEBM"
        if path:
            try:
                detail = f"{Path(path).suffix.lstrip('.').upper()}  ·  {Path(path).stat().st_size / 1024**2:.1f} MB"
            except OSError:
                detail = "Không tìm thấy file. Hãy chọn lại video."
        self.media_detail.configure(text=detail)
        self.preview.configure(image="", text="▷\nXem khung hình" if path else "▷\nVideo của bạn")
        self.preview_image = None
        self.refresh_navigation()

    def _source_edited(self, event=None):
        if self.room_text.edit_modified():
            self.refresh_navigation()
            self.room_text.edit_modified(False)

    def _update_word_count(self, event=None):
        if self.script_text.edit_modified():
            words = len(self.script_text.get("1.0", "end").split())
            self.word_count.configure(text=f"{words} từ  ·  Nội dung sẽ được đọc thành lời")
            self.script_text.edit_modified(False)
            self.refresh_navigation()
