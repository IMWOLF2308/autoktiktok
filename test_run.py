import os
from core.ai_reviewer import analyze_video_and_generate_script, generate_voiceover_mp3
from core.video_renderer import render_tiktok_video

# 1. Đọc API Key từ môi trường; không ghi khóa cá nhân vào mã nguồn.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# 2. Đường dẫn video đầu vào và đầu ra:
INPUT_VIDEO = "input_videos/phong_mau.mp4"
OUTPUT_VIDEO = "output_videos/tiktok_final.mp4"

# 3. Thông tin bổ sung tùy chọn; để trống để Gemini phân tích từ video:
ROOM_INFO = os.environ.get("ROOM_INFO", "")
CONTACT_LINE_1 = "LH Ngay"
CONTACT_LINE_2 = os.environ.get("CONTACT_LINE_2", "SDT/ZALO : ")

if __name__ == "__main__":
    if not GEMINI_API_KEY:
        raise SystemExit("Hãy đặt biến môi trường GEMINI_API_KEY trước khi chạy.")
    if not os.path.exists(INPUT_VIDEO):
        print(f"⚠️ Hãy copy 1 video vào đường dẫn: {INPUT_VIDEO} rồi chạy lại nhé!")
    else:
        # Bước 1: AI xem video và viết lời bình + caption
        ai_result = analyze_video_and_generate_script(
            api_key=GEMINI_API_KEY,
            video_path=INPUT_VIDEO,
            room_info=ROOM_INFO,
        )
        print("\n--- KỊCH BẢN LỒNG TIẾNG AI VIẾT ---")
        print(ai_result.voiceover_script)
        print("\n--- CAPTION ĐĂNG TIKTOK ---")
        print(ai_result.tiktok_caption)

        # Lưu caption ra file text kèm theo video
        os.makedirs("output_videos", exist_ok=True)
        with open("output_videos/caption.txt", "w", encoding="utf-8") as f:
            f.write(ai_result.tiktok_caption)

        # Bước 2: Chuyển lời bình thành file âm thanh giọng đọc tiếng Việt (truyền biến GEMINI_API_KEY)
        voice_path = generate_voiceover_mp3(
            text=ai_result.voiceover_script,
            output_audio_path="temp/voiceover.mp3",
            voice="vi-VN-HoaiMyNeural",
            rate="+24%",
            api_key=GEMINI_API_KEY,
        )

        # Bước 3: Tự động Render Video khớp khít thời lượng + Nhạc nền + Logo + Sticker SĐT cuối clip
        render_tiktok_video(
            input_video_path=INPUT_VIDEO,
            voice_audio_path=voice_path,
            output_video_path=OUTPUT_VIDEO,
            contact_line1=CONTACT_LINE_1,
            contact_line2=CONTACT_LINE_2,
            logo_path="assets/logo/logo.png",
        )
