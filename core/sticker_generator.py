import os
import random
from PIL import Image, ImageDraw, ImageFont


def _draw_torn_paper_strip(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    fill_color: tuple[int, int, int, int] = (250, 250, 250, 255),
    roughness: int = 6,
) -> None:
    """
    Vẽ dải băng trắng có viền răng cưa (Torn-Paper / Brush Stroke) giống hiệu ứng CapCut.
    bbox: (x1, y1, x2, y2)
    """
    x1, y1, x2, y2 = bbox
    points: list[tuple[int, int]] = []
    rng = random.Random(42)

    # Cạnh trên (trái qua phải) - gợn nhẹ
    step_x = 12
    for x in range(x1, x2, step_x):
        points.append((x, y1 + rng.randint(-2, 2)))

    # Cạnh phải (trên xuống dưới) - xé răng cưa rõ như vết cọ
    step_y = 6
    for y in range(y1, y2, step_y):
        points.append((x2 + rng.randint(-roughness, roughness), y))

    # Cạnh dưới (phải qua trái) - gợn nhẹ
    for x in range(x2, x1, -step_x):
        points.append((x, y2 + rng.randint(-2, 2)))

    # Cạnh trái (dưới lên trên) - xé răng cưa rõ như vết cọ
    for y in range(y2, y1, -step_y):
        points.append((x1 + rng.randint(-roughness, roughness), y))

    draw.polygon(points, fill=fill_color)


def create_capcut_contact_sticker(
    line1_text: str = "LH Ngay",
    line2_text: str = "SDT/ZALO : 0388512394",
    output_path: str = "temp/contact_sticker.png",
    video_width: int = 1080,
) -> str:
    """
    Sinh ảnh PNG trong suốt chứa 2 dải băng thông tin liên hệ chuẩn tỷ lệ khung hình dọc điện thoại.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    scale = float(video_width) / 1080.0
    font_size = max(24, int(54 * scale))
    padding_x = int(42 * scale)
    padding_y = int(18 * scale)
    gap_between_strips = int(14 * scale)

    font_candidates = [
        "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/timesbd.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
    for fp in font_candidates:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    # Đo kích thước chữ thực tế và ép kiểu int() để tương thích tuyệt đối với Pillow 13.0+
    dummy_img = Image.new("RGBA", (10, 10))
    dummy_draw = ImageDraw.Draw(dummy_img)

    raw_b1 = dummy_draw.textbbox((0, 0), line1_text, font=font)
    b1 = (int(raw_b1[0]), int(raw_b1[1]), int(raw_b1[2]), int(raw_b1[3]))
    w1, h1 = b1[2] - b1[0], b1[3] - b1[1]

    raw_b2 = dummy_draw.textbbox((0, 0), line2_text, font=font)
    b2 = (int(raw_b2[0]), int(raw_b2[1]), int(raw_b2[2]), int(raw_b2[3]))
    w2, h2 = b2[2] - b2[0], b2[3] - b2[1]

    strip1_w: int = w1 + padding_x * 2
    strip1_h: int = h1 + padding_y * 2

    strip2_w: int = w2 + padding_x * 2
    strip2_h: int = h2 + padding_y * 2

    margin: int = int(20 * scale)
    canvas_w: int = max(strip1_w, strip2_w) + margin * 2
    canvas_h: int = strip1_h + gap_between_strips + strip2_h + margin * 2

    # Tạo canvas trong suốt
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Vẽ dải băng trên ("LH Ngay") căn giữa
    s1_x1 = (canvas_w - strip1_w) // 2
    s1_y1 = margin
    s1_x2 = s1_x1 + strip1_w
    s1_y2 = s1_y1 + strip1_h
    _draw_torn_paper_strip(
        draw, (s1_x1, s1_y1, s1_x2, s1_y2), roughness=max(3, int(8 * scale))
    )

    t1_x = s1_x1 + (strip1_w - w1) // 2 - b1[0]
    t1_y = s1_y1 + (strip1_h - h1) // 2 - b1[1]
    draw.text((t1_x, t1_y), line1_text, font=font, fill=(15, 15, 15, 255))

    # 2. Vẽ dải băng dưới ("SDT/ZALO : ...") căn giữa
    s2_x1 = (canvas_w - strip2_w) // 2
    s2_y1 = s1_y2 + gap_between_strips
    s2_x2 = s2_x1 + strip2_w
    s2_y2 = s2_y1 + strip2_h
    _draw_torn_paper_strip(
        draw, (s2_x1, s2_y1, s2_x2, s2_y2), roughness=max(3, int(8 * scale))
    )

    t2_x = s2_x1 + (strip2_w - w2) // 2 - b2[0]
    t2_y = s2_y1 + (strip2_h - h2) // 2 - b2[1]
    draw.text((t2_x, t2_y), line2_text, font=font, fill=(15, 15, 15, 255))

    img.save(output_path, "PNG")
    return output_path