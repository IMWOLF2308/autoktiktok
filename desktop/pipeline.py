"""Validated desktop-to-core boundary and per-job temporary workspace."""
from dataclasses import dataclass, field
from datetime import datetime
import contextlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import traceback
import uuid
from core.process_utils import run_command
from core.gemini_config import DEFAULT_REVIEW_MODEL, FALLBACK_REVIEW_MODEL
from core.content_rules import prepare_voiceover


def default_asset(relative: str) -> str:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return str(root / "assets" / relative)


def cleanup_work(work: Path, output_dir: Path) -> None:
    """Delete only a validated job directory, never user inputs or sibling jobs."""
    work = Path(work)
    root = Path(output_dir).resolve() / ".autoedit_work"
    if (root.is_symlink() or work.is_symlink() or work.resolve().parent != root
            or not re.fullmatch(r"\d{8}_\d{6}_[0-9a-f]{6}", work.name)):
        raise ValueError("Đường dẫn thư mục tạm không hợp lệ.")
    if work.exists():
        shutil.rmtree(work)
    try:
        root.rmdir()  # Keep the parent when another job still uses it.
    except (FileNotFoundError, OSError):
        pass


@dataclass
class JobConfig:
    video: str = ""
    output_dir: str = ""
    room_info: str = ""
    api_key: str = ""
    model: str = DEFAULT_REVIEW_MODEL
    allow_model_fallback: bool = True
    script: str = ""
    caption: str = ""
    voice_file: str = ""
    engine: str = "Gemini + Edge dự phòng"
    voice: str = "vi-VN-HoaiMyNeural"
    rate: str = "+24%"
    logo: str = field(default_factory=lambda: default_asset("logo/logo.png"))
    bgm: str = ""  # Empty means automatic licensed music download/cache.
    use_logo: bool = True
    use_bgm: bool = True
    use_contact: bool = True
    contact1: str = "LH Ngay"
    contact2: str = "SDT/ZALO : "
    contact_duration: float = 8.0
    bgm_volume: float = 0.16


def validate_job(config: JobConfig, action: str) -> None:
    if action not in {"inspect", "draft", "voice", "check_voice", "render", "all"}:
        raise ValueError("Tác vụ không hợp lệ.")
    if not config.output_dir.strip():
        raise ValueError("Hãy chọn thư mục xuất video.")
    if Path(config.output_dir).exists() and not Path(config.output_dir).is_dir():
        raise ValueError("Đường dẫn xuất phải là thư mục.")
    if action != "voice" and not Path(config.video).is_file():
        raise ValueError("Hãy chọn một tệp video có thật.")
    needs_ai = action == "draft" or (action == "all" and not config.script.strip())
    if needs_ai and not config.api_key.strip():
        raise ValueError("Để AI phân tích video và viết kịch bản, hãy nhập Gemini API Key.")
    if needs_ai and not config.model.strip():
        raise ValueError("Hãy nhập model Gemini dùng để phân tích video.")
    if action == "voice" and not config.script.strip():
        raise ValueError("Hãy nhập hoặc tạo lời bình trước khi tạo giọng đọc.")
    if action in {"render", "check_voice"} and not Path(config.voice_file).is_file():
        raise ValueError("Hãy tạo hoặc chọn tệp giọng đọc trước khi render.")
    if config.engine not in {"Gemini + Edge dự phòng", "Edge-TTS"}:
        raise ValueError("Bộ tạo giọng đọc không hợp lệ.")
    if not re.fullmatch(r"[+-]\d{1,3}%", config.rate) or not -50 <= int(config.rate[:-1]) <= 100:
        raise ValueError("Tốc độ Edge-TTS phải từ -50% đến +100%.")
    if action in {"render", "all"}:
        validate_style(config)


def validate_style(config: JobConfig) -> None:
    for enabled, path, label in [(config.use_logo, config.logo, "logo"), (config.use_bgm and bool(config.bgm.strip()), config.bgm, "nhạc nền")]:
        if enabled and not Path(path).is_file():
            raise ValueError(f"Hãy chọn tệp {label}, hoặc tắt tùy chọn này.")
    if not math.isfinite(config.bgm_volume) or not 0 <= config.bgm_volume <= 1:
        raise ValueError("Âm lượng nhạc nền phải từ 0 đến 100%.")
    if not math.isfinite(config.contact_duration) or not 0.5 <= config.contact_duration <= 60:
        raise ValueError("Thời gian hiện liên hệ phải từ 0,5 đến 60 giây.")
    if config.use_contact and not config.contact2.strip():
        raise ValueError("Hãy nhập dòng thông tin liên hệ.")


def run_job(config: JobConfig, action: str, emit) -> dict:
    validate_job(config, action)
    from core.ai_reviewer import (
        _create_storyboard_bytes, analyze_video_and_generate_script,
        ensure_ffmpeg_available, generate_voiceover_mp3,
    )
    from core.video_renderer import render_tiktok_video

    ensure_ffmpeg_available()
    media_inputs = []
    if action != "voice":
        media_inputs.append((config.video, "video", "Video nguồn"))
    if action in {"render", "check_voice"}:
        media_inputs.append((config.voice_file, "audio", "Tệp giọng đọc"))
    if action in {"render", "all"} and config.use_bgm and config.bgm.strip():
        media_inputs.append((config.bgm, "audio", "Nhạc nền"))
    for path, stream_type, label in media_inputs:
        probe = run_command(["ffprobe", "-v", "error", "-show_streams", "-of", "json", path], capture_output=True, timeout=20)
        if probe.returncode or not any(s.get("codec_type") == stream_type for s in json.loads(probe.stdout).get("streams", [])):
            raise ValueError(f"{label} không chứa luồng {stream_type} hợp lệ.")
    if action == "check_voice":
        return {"voice_file": config.voice_file}
    if action in {"render", "all"} and config.use_logo:
        from PIL import Image
        with Image.open(config.logo) as logo:
            logo.verify()
    output_dir = Path(config.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    work = output_dir / ".autoedit_work" / job_id
    work.mkdir(parents=True)
    # Core still uses relative temp paths. This cwd belongs only to the worker.
    old_cwd = Path.cwd()
    config.video = str(Path(config.video).resolve()) if config.video else ""
    config.logo = str(Path(config.logo).resolve()) if config.logo else ""
    config.bgm = str(Path(config.bgm).resolve()) if config.bgm.strip() else ""
    config.voice_file = str(Path(config.voice_file).resolve()) if config.voice_file else ""
    result = {}
    prefix = output_dir / f"tiktok_{job_id}"
    emit("work", {"path": str(work), "output_dir": str(output_dir)})

    def publish_storyboard():
        storyboard = work / "temp/storyboard.jpg"
        if storyboard.exists():
            target = prefix.with_suffix(".storyboard.jpg")
            shutil.copy2(storyboard, target)
            result["storyboard"] = str(target)
            emit("storyboard", str(target))

    os.chdir(work)
    try:
        if action == "inspect":
            emit("stage", "Đang lấy khung hình video")
            _create_storyboard_bytes(config.video)
            publish_storyboard()
            return result
        if action == "draft" or (action == "all" and not config.script.strip()):
            emit("stage", "01 / AI viết kịch bản")
            review = analyze_video_and_generate_script(
                config.api_key, config.video, config.room_info, config.model,
                on_progress=lambda message: emit("stage", message),
                fallback_model=FALLBACK_REVIEW_MODEL if config.allow_model_fallback else "",
            )
            config.script, config.caption = prepare_voiceover(review.voiceover_script), review.tiktok_caption
            if not config.script.strip():
                raise ValueError("AI trả về lời bình trống. Hãy thử lại hoặc tự nhập lời bình.")
            room_file = prefix.with_suffix(".room.txt")
            room_file.write_text(review.room_info, encoding="utf-8")
            result["room_info_file"] = str(room_file)
            emit("script", {"script": config.script, "caption": config.caption, "room_info": review.room_info,
                            "model": getattr(review, "model_used", "") or config.model})
            publish_storyboard()
        if action in {"voice", "all"}:
            config.script = prepare_voiceover(config.script)
            emit("stage", "02 / Tạo giọng đọc")
            config.voice_file = generate_voiceover_mp3(
                config.script, str(work / "voiceover.mp3"), voice=config.voice, rate=config.rate,
                api_key=config.api_key if config.engine != "Edge-TTS" else None,
            )
            generated = Path(config.voice_file)
            saved_voice = prefix.with_suffix(".voice" + generated.suffix)
            shutil.copy2(generated, saved_voice)
            config.voice_file = str(saved_voice)
            result["voice_file"] = config.voice_file
            emit("voice", config.voice_file)
        if action in {"render", "all"}:
            if config.use_bgm and not config.bgm:
                from core.music_library import automatic_music
                config.bgm, track = automatic_music(work, emit)
                credit_file = prefix.with_suffix(".music.txt")
                credit_file.write_text(track.credit, encoding="utf-8")
                result["music_credit_file"] = str(credit_file)
                emit("music", {"title": track.title, "path": config.bgm, "credit": track.credit})
            emit("stage", "03 / Ghép hình, âm thanh và hiệu ứng")
            # Render into work first; only publish a complete video.
            partial = work / "render.mp4"
            render_tiktok_video(
                config.video, config.voice_file, str(partial),
                contact_line1=config.contact1, contact_line2=config.contact2,
                logo_path=config.logo or None, bgm_path=config.bgm or None,
                contact_duration_end=config.contact_duration, bgm_volume=config.bgm_volume,
                use_logo=config.use_logo, use_bgm=config.use_bgm, use_contact=config.use_contact,
            )
            final = prefix.with_suffix(".mp4")
            os.replace(partial, final)
            result["video"] = str(final)
        if config.script.strip():
            script_file = prefix.with_suffix(".script.txt")
            script_file.write_text(config.script, encoding="utf-8")
            result["script_file"] = str(script_file)
        if config.caption.strip():
            caption_file = prefix.with_suffix(".caption.txt")
            caption_file.write_text(config.caption, encoding="utf-8")
            result["caption_file"] = str(caption_file)
        return result
    finally:
        os.chdir(old_cwd)
        try:
            cleanup_work(work, output_dir)
        except (OSError, ValueError) as exc:
            emit("log", f"Chưa dọn được thư mục tạm {work}: {exc}")


class QueueLog(io.TextIOBase):
    def __init__(self, emit):
        self.emit = emit
        self.pending = ""

    def write(self, text):
        self.pending += text.replace("\r", "\n")
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line.strip():
                self.emit("log", line.strip())
        return len(text)

    def flush(self):
        if self.pending.strip():
            self.emit("log", self.pending.strip())
        self.pending = ""


def worker_entry(config: JobConfig, action: str, queue) -> None:
    def emit(kind, value):
        if isinstance(value, str) and config.api_key:
            value = value.replace(config.api_key, "[API KEY]")
        queue.put((kind, value))

    stream = QueueLog(emit)
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        try:
            result = run_job(config, action, emit)
            stream.flush()
            emit("done", result)
        except Exception as exc:
            stream.flush()
            emit("log", traceback.format_exc())
            emit("error", str(exc))
