"""Native studio presentation. Processing and persistence live in app/pipeline."""
import tkinter as tk
from tkinter import ttk
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
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width))
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
        self.label(header, "Không gian làm việc", 9, MUTED).pack(side="left")
        self.label(header, "  /  Video studio", 9, TEXT, True).pack(side="left")
        self.button(header, "Hướng dẫn", self.toggle_help, tracked=False).pack(side="right")
        self.key_badge = self.label(header, "●  Chưa nhập API Key", 9, MUTED)
        self.key_badge.pack(side="right", padx=18)
        self.key_badge.configure(cursor="hand2")
        self.key_badge.bind("<Button-1>", lambda e: self.scroll_to(self.connection_card))
        tk.Frame(shell, bg=LINE, height=1).pack(fill="x")

        hero = tk.Frame(shell, bg=BG, padx=26, pady=18)
        hero.pack(fill="x")
        self.label(hero, "VIDEO WORKSPACE  /  AI POWERED", 8, ACCENT, True).pack(anchor="w", pady=(0, 6))
        self.label(hero, "Tạo nội dung. Kể câu chuyện.", 23, TEXT, True).pack(anchor="w")
        self.label(hero, "Từ video căn phòng đến một bài đăng hoàn chỉnh — trong một không gian.", 10, MUTED).pack(anchor="w", pady=(5, 0))

        self.footer = tk.Frame(shell, bg=CARD, padx=24, pady=14)
        self.footer.pack(side="bottom", fill="x")
        self.run_button = self.button(self.footer, "▶  Tạo video", lambda: self.start("all"), primary=True)
        self.run_button.pack(side="right")
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
        self.help_panel = tk.Frame(page.body, bg=BG)
        self._help_page(self.help_panel)
        self.editor_columns = tk.Frame(page.body, bg=BG)
        self.editor_columns.pack(fill="x")
        self.project_section = tk.Frame(self.editor_columns, bg=BG)
        self.script_section = tk.Frame(self.editor_columns, bg=BG)
        self.export_section = tk.Frame(self.editor_columns, bg=BG)
        self._project_page(self.project_section)
        self._script_page(self.script_section)
        self._export_page(self.export_section)
        self._layout_mode = None
        self._wide_layout = False
        self.editor_columns.bind("<Configure>", self._resize_editor)
        self.vars["api_key"].trace_add("write", self._refresh_key_badge)
        self.vars["video"].trace_add("write", self._refresh_media)
        self._refresh_key_badge()
        self._refresh_media()

    def _resize_editor(self, event):
        mode = 3 if event.width >= 1160 else 2 if event.width >= 850 else 1
        if mode == self._layout_mode:
            return
        self._layout_mode = mode
        self._wide_layout = mode == 3
        for section in (self.project_section, self.script_section, self.export_section):
            section.grid_forget()
        for column in range(3):
            self.editor_columns.columnconfigure(column, weight=0, minsize=0, uniform="")
        if mode == 3:
            for column, (section, weight) in enumerate(((self.project_section, 10), (self.script_section, 14), (self.export_section, 10))):
                self.editor_columns.columnconfigure(column, weight=weight, uniform="studio")
                section.grid(row=0, column=column, sticky="nsew", padx=(0, 14 if column < 2 else 0))
        elif mode == 2:
            for column in range(2):
                self.editor_columns.columnconfigure(column, weight=1, uniform="studio")
            self.project_section.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
            self.script_section.grid(row=0, column=1, sticky="nsew")
            self.export_section.grid(row=1, column=0, columnspan=2, sticky="nsew")
        else:
            self.editor_columns.columnconfigure(0, weight=1)
            for row, section in enumerate((self.project_section, self.script_section, self.export_section)):
                section.grid(row=row, column=0, sticky="nsew")

    def _project_page(self, parent):
        c = self.card(parent, "01   Nguồn video", "Bắt đầu từ một góc nhìn của bạn.")
        stage = tk.Frame(c, bg=TINT, height=178)
        stage.pack(fill="x", pady=(14, 9))
        stage.pack_propagate(False)
        self.preview = self.label(stage, "▷\n\nKhung hình của bạn", 13, "#b4a7f2", justify="center")
        self.preview.pack(fill="both", expand=True)
        self.media_label = self.paragraph(c, "Chưa chọn video", TEXT)
        self.media_detail = self.paragraph(c, "MP4, MOV, MKV, AVI hoặc WEBM", size=8)
        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x", pady=(12, 0))
        self.button(row, "＋ Chọn video", lambda: self.pick_file("video", "Video", "*.mp4 *.mov *.mkv *.avi *.webm")).pack(side="left")
        self.button(row, "Xem khung hình", lambda: self.start("inspect")).pack(side="right")

        c = self.card(parent, "Thông tin bổ sung", "Giá, địa chỉ hoặc điểm nổi bật bạn muốn nhấn mạnh. Có thể để trống.")
        self.room_text = self.text_box(c, 4)

        c = self.card(parent, "Kết nối Gemini", "Khóa được nhớ trên máy của bạn.")
        self.connection_card = c
        self.field(c, "api_key", "API Key", secret=True)
        self.field(c, "model", "Model phân tích")

    def _script_page(self, parent):
        c = self.card(parent, "02   Nội dung & giọng đọc", "Để Gemini quan sát, rồi kể theo cách của bạn.")
        self.button(c, "✦  Phân tích & viết kịch bản", lambda: self.start("draft"), primary=True).pack(fill="x", pady=(14, 4))
        self.label(c, "Lời bình", 10, TEXT, True).pack(anchor="w", pady=(12, 0))
        self.script_text = self.text_box(c, 8)
        self.word_count = self.label(c, "0 từ  ·  Nội dung sẽ được đọc thành lời", 8, MUTED)
        self.word_count.pack(anchor="w", pady=(6, 0))
        self.script_text.bind("<<Modified>>", self._update_word_count)
        self.label(c, "Caption TikTok", 10, TEXT, True).pack(anchor="w", pady=(16, 0))
        self.caption_text = self.text_box(c, 3)
        self.button(c, "Sao chép caption", self.copy_caption).pack(anchor="e", pady=(8, 0))

        c = self.card(parent, "Giọng đọc", "Tạo giọng mới hoặc chọn file thu âm của bạn.")
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

        c = self.card(parent, "Gemini quan sát được", "Mô tả từ video sau khi phân tích.")
        self.analysis_text = self.text_box(c, 4)
        self.inputs[-1] = (self.analysis_text, "disabled")
        self.analysis_text.configure(state="disabled")

    def _export_page(self, parent):
        c = self.card(parent, "03   Dấu ấn riêng", "Hoàn thiện hình ảnh và âm thanh.")
        self.check(c, "use_logo", "Hiển thị logo")
        self.field(c, "logo", "Logo thương hiệu", lambda: self.pick_file("logo", "Hình ảnh", "*.png *.webp *.jpg *.jpeg"))
        c = self.card(parent, "♫   Nhạc nền", "Tự tải nhạc miễn phí khi không chọn file.")
        self.check(c, "use_bgm", "Chèn nhạc vào video")
        self.music_status = self.paragraph(c, "", ACCENT)
        self.button(c, "↓  Tự tải nhạc miễn phí", self.use_auto_music).pack(fill="x", pady=(10, 0))
        self.paragraph(c, "Nguồn: OpenGameArt · Tuyển chọn nhạc CC0. Miễn phí sử dụng, không bắt buộc ghi công.", size=8)
        self.field(c, "bgm", "Hoặc chọn file của bạn", lambda: self.pick_file("bgm", "Âm thanh", "*.mp3 *.wav *.m4a *.aac *.mp4"))
        self.field(c, "bgm_volume", "Âm lượng nhạc (%)")
        self.vars["bgm"].trace_add("write", self._refresh_music)
        self.vars["use_bgm"].trace_add("write", self._refresh_music)
        self._refresh_music()

        c = self.card(parent, "Thông tin liên hệ")
        self.check(c, "use_contact", "Hiện ở cuối video")
        self.field(c, "contact1", "Tiêu đề")
        self.field(c, "contact2", "Số điện thoại / Zalo")
        self.field(c, "contact_duration", "Thời gian hiển thị (giây)")

        c = self.card(parent, "Xuất thành phẩm", "MP4 · Giữ tỷ lệ nguồn · 30 fps")
        self.field(c, "output_dir", "Lưu video vào", self.pick_output)
        self.button(c, "Render với giọng đã chọn", lambda: self.start("render")).pack(fill="x", pady=(12, 0))
        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        self.button(row, "Thư mục", lambda: self.open_path(self.vars["output_dir"].get())).pack(side="left")
        self.button(row, "Video mới nhất", lambda: self.open_path(self.last_video)).pack(side="right")

    def _help_page(self, parent):
        c = self.card(parent, "Bắt đầu trong ba bước")
        self.paragraph(c, "1. Chọn video và nhập API Key. Thông tin bổ sung có thể để trống.")
        self.paragraph(c, "2. Bấm Phân tích & viết kịch bản, chỉnh lời bình/caption rồi tạo và nghe thử giọng đọc.")
        self.paragraph(c, "3. Chọn logo, nhạc và thư mục xuất. Tạo video chạy trọn quy trình; Render với giọng đã chọn dùng file âm thanh hiện tại.")
        self.paragraph(c, "Bạn có thể tự nhập lời bình và dùng Edge-TTS. Nút Dừng hủy tác vụ đang chạy; mở Nhật ký để xem chi tiết.")

    def show_page(self, key):
        self.current_page = key
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)

    def toggle_help(self):
        if self.help_panel.winfo_manager():
            self.help_panel.pack_forget()
        else:
            self.help_panel.pack(fill="x", before=self.editor_columns)
            self.update_idletasks()
            self.pages["video"].canvas.yview_moveto(0)

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
        self.key_badge.configure(text="●  Đã nhập API Key" if present else "●  Chưa nhập API Key",
                                 fg=GREEN if present else MUTED)

    def _refresh_media(self, *args):
        path = self.vars["video"].get()
        self.media_label.configure(text=Path(path).name if path else "Chưa chọn video")
        detail = "MP4, MOV, MKV, AVI hoặc WEBM"
        if path:
            try:
                detail = f"{Path(path).suffix.lstrip('.').upper()}  ·  {Path(path).stat().st_size / 1024**2:.1f} MB"
            except OSError:
                detail = "Không tìm thấy file. Hãy chọn lại video."
        self.media_detail.configure(text=detail)
        self.preview.configure(image="", text="▷\n\nXem khung hình để kiểm tra" if path else "▷\n\nKhung hình của bạn")
        self.preview_image = None

    def _update_word_count(self, event=None):
        if self.script_text.edit_modified():
            words = len(self.script_text.get("1.0", "end").split())
            self.word_count.configure(text=f"{words} từ  ·  Nội dung sẽ được đọc thành lời")
            self.script_text.edit_modified(False)
