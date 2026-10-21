import os
import random
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from core.sticker_generator import create_capcut_contact_sticker
from core.ai_reviewer import ensure_ffmpeg_available
from core.process_utils import run_command


def get_media_info(file_path: str) -> dict[str, float | int]:
    """Lấy thời lượng chính xác (giây) và kích thước khung hình (width, height)."""
    ensure_ffmpeg_available()
    cmd_dur = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    res_dur = run_command(cmd_dur, capture_output=True, text=True, check=True)
    duration = float(res_dur.stdout.strip())

    width, height = 720, 1280
    cmd_dim = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        file_path,
    ]
    res_dim = run_command(cmd_dim, capture_output=True, text=True)
    if res_dim.returncode == 0 and "x" in res_dim.stdout:
        parts = res_dim.stdout.strip().split("x")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            width, height = int(parts[0]), int(parts[1])

    return {"duration": duration, "width": width, "height": height}


def ensure_bgm_available(bgm_folder: str = "assets/bgm") -> str | None:
    """Use a local library, otherwise download a validated CC0 track."""
    ensure_ffmpeg_available()
    os.makedirs(bgm_folder, exist_ok=True)
    valid_exts = (".mp3", ".wav", ".m4a", ".aac", ".mp4")

    existing_files = [
        os.path.join(bgm_folder, f)
        for f in os.listdir(bgm_folder)
        if f.lower().endswith(valid_exts) and os.path.isfile(os.path.join(bgm_folder, f))
    ]
    if existing_files:
        chosen = random.choice(existing_files)
        print(f"🎵 Đã chọn nhạc nền: {os.path.basename(chosen)}")
        return chosen

    from core.music_library import automatic_music
    with tempfile.TemporaryDirectory(prefix="autoedit-music-") as work:
        path, track = automatic_music(Path(work), lambda kind, value: print(value))
    Path(path).with_suffix(".music.txt").write_text(track.credit, encoding="utf-8")
    return path


def _trim_and_enhance_logo(raw_logo_path: str, output_trimmed_path: str = "temp/logo_trimmed.png") -> str:
    """
    1. Tự động cắt bỏ 100% khoảng trống trong suốt thừa (Alpha Padding) xung quanh Logo
       để Logo hiển thị TO đúng kích thước thật và bám sát mép trái màn hình.
    2. Tạo viền bóng mờ nhẹ (Subtle Drop-Shadow) giúp Logo màu xanh/trắng nổi bật rõ trên nền tường sáng.
    """
    os.makedirs(os.path.dirname(output_trimmed_path), exist_ok=True)
    with Image.open(raw_logo_path) as img:
        rgba = img.convert("RGBA")
        # Lấy vùng có độ đục alpha > 15 để loại bỏ cả các hạt nhiễu mờ ở rìa ảnh
        alpha = rgba.getchannel("A")
        mask = alpha.point([255 if p > 15 else 0 for p in range(256)], mode="1")
        bbox = mask.getbbox()
        if bbox:
            rgba = rgba.crop(bbox)

        # Tạo bóng đổ nhẹ phía sau chữ để Logo luôn rõ nét trên tường màu sáng
        pad = 6
        w, h = rgba.size
        canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        shadow_alpha = rgba.getchannel("A").point([int(p * 0.45) for p in range(256)])
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        shadow.putalpha(shadow_alpha)
        canvas.paste(shadow, (pad + 2, pad + 2))
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=2))
        canvas.alpha_composite(rgba, (pad, pad))

        canvas.save(output_trimmed_path, "PNG")
    return output_trimmed_path


def ensure_logo_available(logo_folder: str = "assets/logo") -> str | None:
    """
    Tự động tìm file logo của người dùng trong assets/logo/ và cắt sạch viền trong suốt thừa.
    """
    os.makedirs(logo_folder, exist_ok=True)
    valid_exts = (".png", ".webp", ".jpg", ".jpeg")

    existing_logos = [
        os.path.join(logo_folder, f)
        for f in os.listdir(logo_folder)
        if f.lower().endswith(valid_exts)
    ]
    user_logos = [p for p in existing_logos if os.path.basename(p).lower() != "logo_demo.png"]
    if user_logos:
        raw_logo = user_logos[0]
        print(f"🏷️ Đã nhận diện Logo: {os.path.basename(raw_logo)} (Đã tự động cắt viền thừa & phóng to sát góc trái)")
        return _trim_and_enhance_logo(raw_logo)

    if existing_logos:
        return _trim_and_enhance_logo(existing_logos[0])

    demo_logo_path = os.path.join(logo_folder, "logo_demo.png")
    if not os.path.exists(demo_logo_path):
        img = Image.new("RGBA", (360, 110), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((5, 5, 355, 105), radius=24, fill=(20, 20, 20, 175), outline=(255, 215, 0, 230), width=4)
        font_path = "C:/Windows/Fonts/arialbd.ttf"
        font = ImageFont.truetype(font_path, 34) if os.path.exists(font_path) else ImageFont.load_default()
        draw.text((32, 34), "PHÒNG ĐẸP 24/7", font=font, fill=(255, 255, 255, 255))
        img.save(demo_logo_path, "PNG")

    return _trim_and_enhance_logo(demo_logo_path)


def render_tiktok_video(
    input_video_path: str,
    voice_audio_path: str,
    output_video_path: str,
    contact_line1: str = "LH Ngay",
    contact_line2: str = "SDT/ZALO : ",
    logo_path: str | None = None,
    bgm_path: str | None = None,
    contact_duration_end: float = 8.0,
    wipe_duration: float = 1.2,
    bgm_volume: float = 0.16,
    use_logo: bool = True,
    use_bgm: bool = True,
    use_contact: bool = True,
) -> str:
    os.makedirs(os.path.dirname(output_video_path) or ".", exist_ok=True)

    v_info = get_media_info(input_video_path)
    a_info = get_media_info(voice_audio_path)

    T_v = float(v_info["duration"])
    T_a = float(a_info["duration"])
    vid_w = int(v_info["width"])
    vid_h = int(v_info["height"])
    if T_v <= 0 or T_a <= 0:
        raise ValueError("Video và giọng đọc phải có thời lượng lớn hơn 0.")
    if wipe_duration <= 0 or contact_duration_end <= 0 or not 0 <= bgm_volume <= 1:
        raise ValueError("Thông số hiệu ứng hoặc âm lượng không hợp lệ.")

    print(f"-> Thời lượng: Video gốc = {T_v:.2f}s | Giọng đọc AI = {T_a:.2f}s ({vid_w}x{vid_h})")

    # --- THUẬT TOÁN ZERO-GAP ELASTIC SYNC ---
    if T_v >= T_a:
        target_duration = T_a
        video_speed_factor = T_v / target_duration
        audio_speed_factor = 1.0
        print(f"-> Đồng bộ: Tua nhanh Video x{video_speed_factor:.2f} lần để khớp khít {target_duration:.2f}s.")
    else:
        raw_audio_speed = T_a / T_v
        if raw_audio_speed <= 1.25:
            audio_speed_factor = raw_audio_speed
            target_duration = T_v
            video_speed_factor = 1.0
            print(f"-> Đồng bộ: Tua nhanh Giọng đọc x{audio_speed_factor:.2f} lần để khớp khít {target_duration:.2f}s.")
        else:
            audio_speed_factor = 1.25
            target_duration = T_a / audio_speed_factor
            video_speed_factor = T_v / target_duration
            print(f"-> Đồng bộ kết hợp: Tăng tốc Giọng x1.25 & Giãn nhẹ Video về {target_duration:.2f}s.")

    sticker_path = create_capcut_contact_sticker(
        line1_text=contact_line1,
        line2_text=contact_line2,
        output_path="temp/contact_sticker.png",
        video_width=vid_w,
    )

    t_contact_start = max(0.0, target_duration - contact_duration_end)

    # Chuẩn bị Logo (tự động cắt viền trong suốt thừa để phóng to chuẩn)
    if not use_logo:
        prepared_logo_path = None
    elif logo_path and os.path.exists(logo_path):
        prepared_logo_path = _trim_and_enhance_logo(logo_path)
    else:
        prepared_logo_path = ensure_logo_available("assets/logo")

    if not use_bgm:
        bgm_path = None
    elif not bgm_path:
        bgm_path = ensure_bgm_available("assets/bgm")
    elif not os.path.isfile(bgm_path):
        raise FileNotFoundError(f"Không tìm thấy file nhạc đã chọn: {bgm_path}")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", input_video_path,                      # Input 0: Video gốc
        "-i", voice_audio_path,                      # Input 1: Giọng đọc AI
        "-loop", "1", "-i", sticker_path,            # Input 2: Sticker liên hệ
    ]

    next_idx = 3
    logo_idx: int | None = None
    if prepared_logo_path and os.path.exists(prepared_logo_path):
        ffmpeg_cmd.extend(["-i", prepared_logo_path])
        logo_idx = next_idx
        next_idx += 1

    bgm_idx: int | None = None
    if bgm_path and os.path.exists(bgm_path):
        ffmpeg_cmd.extend(["-stream_loop", "-1", "-i", bgm_path])
        bgm_idx = next_idx
        next_idx += 1

    filters: list[str] = []

    # 1. Nhánh Video: Co giãn thời lượng + chuẩn hóa FPS 30
    pts_multiplier = 1.0 / video_speed_factor
    filters.append(f"[0:v]setpts={pts_multiplier:.6f}*PTS,fps=30[v_base]")
    current_v = "[v_base]"

    # 2. Đóng dấu Logo TO RÕ (36% chiều ngang màn hình) và SÁT MÉP TRÁI (cách mép trái chỉ 1.2%)
    if logo_idx is not None:
        logo_w = max(130, int(vid_w * 0.36))
        margin_x = max(6, int(vid_w * 0.012))
        margin_y = max(12, int(vid_h * 0.025))
        filters.append(f"[{logo_idx}:v]scale={logo_w}:-1[logo_scaled]")
        filters.append(f"{current_v}[logo_scaled]overlay=x={margin_x}:y={margin_y}[v_logo]")
        current_v = "[v_logo]"

    # 3. Hiệu ứng Sticker Liên hệ quét mở từ trái sang phải ở trung tâm màn hình
    filters.append(
        f"[2:v]format=rgba,"
        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
        f"a='if(lte(X, W*(T-{t_contact_start:.3f})/{wipe_duration:.3f}), alpha(X,Y), 0)'[sticker_anim]"
    )
    contact_enable = f"gte(t,{t_contact_start:.3f})" if use_contact else "0"
    filters.append(
        f"{current_v}[sticker_anim]overlay=x=(W-w)/2:y=(H-h)/2:"
        f"enable='{contact_enable}':shortest=1[v_out]"
    )

    # 4. Nhánh Âm thanh: Giọng đọc + Nhạc nền BGM
    filters.append(f"[1:a]atempo={audio_speed_factor:.6f},volume=1.45[a_voice]")

    if bgm_idx is not None:
        fade_out_start = max(0.0, target_duration - 1.5)
        filters.append(
            f"[{bgm_idx}:a]atrim=0:{target_duration:.3f},asetpts=PTS-STARTPTS,"
            f"volume={bgm_volume:.3f},"
            f"afade=t=in:st=0:d=0.6,afade=t=out:st={fade_out_start:.3f}:d=1.5[a_bgm]"
        )
        filters.append(
            "[a_voice][a_bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a_out]"
        )
    else:
        filters.append("[a_voice]acopy[a_out]")

    filter_complex_str = ";".join(filters)

    ffmpeg_cmd.extend([
        "-filter_complex", filter_complex_str,
        "-map", "[v_out]",
        "-map", "[a_out]",
        "-t", f"{target_duration:.3f}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        output_video_path,
    ])

    print("-> Đang Render video bằng FFmpeg...")
    result = run_command(ffmpeg_cmd, capture_output=True)
    if result.returncode:
        raise RuntimeError("Render thất bại: " + result.stderr.decode("utf-8", errors="replace")[-3500:])
    print(f"✅ Render hoàn tất! File xuất tại: {output_video_path}")
    return output_video_path
