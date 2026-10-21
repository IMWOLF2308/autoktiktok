"""Offline integration check for both source and frozen Windows builds."""
import json
from pathlib import Path
import time
from unittest.mock import patch

from core.ai_reviewer import ensure_ffmpeg_available
from core.process_utils import run_command


def slow_media_worker(pid_file):
    """Exercise cancellation of a real FFmpeg descendant, without network."""
    import os
    import subprocess
    ensure_ffmpeg_available()
    process = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-re", "-f", "lavfi", "-i", "sine=duration=60", "-f", "null", "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    Path(pid_file).write_text(str(process.pid), encoding="ascii")
    process.wait()


def run_smoke(folder: str):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    report = {"ok": False}
    app = None
    try:
        ensure_ffmpeg_available()
        video = folder / "phòng mẫu.mp4"
        voice = folder / "giọng đọc.wav"
        run_command(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x253a58:s=360x640:r=30:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], capture_output=True, check=True)
        run_command(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000:duration=2", str(voice)], capture_output=True, check=True)
        from desktop.app import AutoEditApp
        (folder / "test-settings.json").unlink(missing_ok=True)
        with patch("desktop.app.settings_path", return_value=folder / "test-settings.json"):
            app = AutoEditApp()
            app.vars["video"].set(str(video))
            app.vars["voice_file"].set(str(voice))
            app.vars["output_dir"].set(str(folder / "kết quả"))
            app.vars["contact2"].set("ZALO : 0901234567")
            assert app.vars["use_logo"].get() and app.vars["use_bgm"].get()
            app.vars["api_key"].set("offline-test-key")
            app.vars["use_bgm"].set(False)
            assert list(app.pages) == ["video"]
            assert not app.room_text.get("1.0", "end").strip()
            assert not app.script_text.get("1.0", "end").strip()
            assert not app.analysis_text.get("1.0", "end").strip()
            app.update()
            from PIL import ImageGrab
            app.lift()
            app.update()
            time.sleep(0.3)
            ImageGrab.grab(window=app.winfo_id()).save(folder / "interface.png")
            for page in app.pages:
                app.show_page(page)
                app.update()
                ImageGrab.grab(window=app.winfo_id()).save(folder / f"page_{page}.png")
            for position in (0.35, 0.7, 1.0):
                app.pages["video"].canvas.yview_moveto(position)
                app.update()
                ImageGrab.grab(window=app.winfo_id()).save(folder / f"workspace_{position}.png")
            original_geometry = app.geometry()
            app.geometry("1160x760")
            app.update()
            assert app._layout_mode == 2
            app.pages["video"].canvas.yview_moveto(0)
            app.update()
            ImageGrab.grab(window=app.winfo_id()).save(folder / "workspace_medium.png")
            app.geometry("960x720")
            app.update()
            assert not app._wide_layout
            app.pages["video"].canvas.yview_moveto(0.45)
            app.update()
            ImageGrab.grab(window=app.winfo_id()).save(folder / "workspace_narrow.png")
            app.geometry(original_geometry)
            app.update()
            app.toggle_log()
            app.update()
            assert app.logs.winfo_viewable()
            assert app.run_button.winfo_viewable()
            app.toggle_log()
            app._set_text(app.script_text, "Kiểm tra đếm từ")
            app.update()
            assert app.word_count.cget("text").startswith("4 từ")
            app._set_text(app.script_text, "")
            assert app.snapshot().video == str(video)
            app.toggle_help()
            app.update()
            assert app.help_panel.winfo_manager() == "pack"
            app.toggle_help()
            app.pages["video"].canvas.yview_moveto(0)
            app.show_page("video")
            app.start("render")
            assert app.process is not None, "Render did not start"
            deadline = time.monotonic() + 90
            ticks = 0
            while app.process and time.monotonic() < deadline:
                app.update()
                ticks += 1
                time.sleep(0.02)
            assert app.process is None, "Render timed out"
            assert app.last_video and Path(app.last_video).is_file(), "No rendered video"
            assert app.run_button.cget("state") == "normal"
            assert ticks > 1, "UI event loop was not exercised"
            probe = run_command(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", app.last_video], capture_output=True, check=True)
            media = json.loads(probe.stdout)
            assert {s["codec_type"] for s in media["streams"]} >= {"audio", "video"}
            assert 1.8 < float(media["format"]["duration"]) < 2.5
            app._save_settings()
            saved = json.loads((folder / "test-settings.json").read_text(encoding="utf-8"))
            assert saved["api_key"] == "offline-test-key"
            app.vars["api_key"].set("")
            app.vars["use_logo"].set(False)
            app.vars["use_bgm"].set(True)
            app._load_settings()
            assert app.vars["api_key"].get() == "offline-test-key"
            assert app.vars["use_logo"].get() and not app.vars["use_bgm"].get()
            assert Path(app.vars["logo"].get()).is_file()
            assert app.vars["bgm"].get() == "", "Automatic music must survive settings reload"
            saved["room_info"] = "Legacy room description must not be reused"
            (folder / "test-settings.json").write_text(json.dumps(saved), encoding="utf-8")
            app._load_settings()
            assert not app.room_text.get("1.0", "end").strip()
            assert not (folder / "kết quả" / ".autoedit_work").exists()
            # Exercise enabled logo/music and the full pipeline with local AI/TTS doubles.
            from PIL import Image
            from desktop.pipeline import JobConfig, run_job
            from core.ai_reviewer import TikTokReviewOutput
            import shutil
            logo = folder / "logo.png"
            Image.new("RGBA", (100, 50), (40, 220, 160, 255)).save(logo)
            config = JobConfig(video=str(video), output_dir=str(folder / "full_flow"),
                               api_key="test", room_info="Thông tin mẫu", use_logo=True, logo=str(logo),
                               use_bgm=True, bgm=str(voice), contact2="ZALO : 0901234567")
            emitted = []
            def local_voice(text, output, **kwargs):
                assert text == "Lời bình mẫu."
                shutil.copy2(voice, output)
                return output
            with patch("core.ai_reviewer.analyze_video_and_generate_script", return_value=TikTokReviewOutput(room_info="Phòng từ phản hồi giả lập trong kiểm thử.", voiceover_script="Lời bình mẫu.", tiktok_caption="#phongtro")), patch("core.ai_reviewer.generate_voiceover_mp3", side_effect=local_voice):
                full_result = run_job(config, "all", lambda k, v: emitted.append((k, v)))
            assert Path(full_result["video"]).is_file()
            assert Path(full_result["script_file"]).read_text(encoding="utf-8") == "Lời bình mẫu."
            assert Path(full_result["caption_file"]).read_text(encoding="utf-8") == "#phongtro"
            assert Path(full_result["room_info_file"]).read_text(encoding="utf-8") == "Phòng từ phản hồi giả lập trong kiểm thử."
            app.active_video = str(video)
            for kind, value in emitted:
                if kind == "script":
                    app._handle(kind, value)
            assert app.analysis_text.get("1.0", "end").strip() == "Phòng từ phản hồi giả lập trong kiểm thử."
            assert app.script_text.get("1.0", "end").strip() == "Lời bình mẫu."
            assert app.generated_content_video == str(video)
            app.pages["video"].canvas.yview_moveto(0)
            app.update()
            ImageGrab.grab(window=app.winfo_id()).save(folder / "workspace_result.png")
            assert any(kind == "voice" for kind, _ in emitted)
            assert Path(full_result["voice_file"]).is_file()
            assert not (folder / "full_flow" / ".autoedit_work").exists()
            # Empty music path triggers the downloader, then real FFmpeg mixing.
            # Network is doubled with local audio; cache/probe/render stay real.
            from core.music_library import TRACKS
            import io
            response = io.BytesIO(voice.read_bytes())
            response.headers = {"Content-Type": "audio/wav"}
            config.bgm = ""
            config.output_dir = str(folder / "auto_music")
            music_events = []
            with patch("core.music_library.music_cache_dir", return_value=folder / "music_cache"), patch("core.music_library.urllib.request.urlopen", return_value=response) as download:
                music_result = run_job(config, "render", lambda k, v: music_events.append((k, v)))
                assert download.call_count == 1
            assert Path(music_result["video"]).is_file()
            assert Path(music_result["caption_file"]).read_text(encoding="utf-8") == config.caption
            assert Path(music_result["music_credit_file"]).is_file()
            assert "CC0" in Path(music_result["music_credit_file"]).read_text(encoding="utf-8")
            assert not (folder / "auto_music" / ".autoedit_work").exists()
            for kind, value in music_events:
                if kind == "music":
                    app._handle(kind, value)
            app.copy_caption()
            assert app.clipboard_get() == "#phongtro"
            assert any(track.title in app.music_status.cget("text") for track in TRACKS)
            app.use_auto_music()
            assert app.vars["use_bgm"].get() and app.vars["bgm"].get() == ""
            app._save_settings()
            app.vars["bgm"].set(str(voice))
            app._load_settings()
            assert app.vars["bgm"].get() == "" and app.vars["use_bgm"].get()
            app.pages["video"].canvas.yview_moveto(0)
            app.update()
            ImageGrab.grab(window=app.winfo_id()).save(folder / "music_automatic.png")
            # Stop while FFmpeg is really running; verify it is not orphaned.
            import multiprocessing
            context = multiprocessing.get_context("spawn")
            pid_file = folder / "cancel-child.pid"
            pid_file.unlink(missing_ok=True)
            app.events = context.Queue()
            app.process = context.Process(target=slow_media_worker, args=(str(pid_file),))
            app.process.start()
            app._busy(True)
            deadline = time.monotonic() + 20
            while not pid_file.exists() and time.monotonic() < deadline:
                app.update()
                time.sleep(0.03)
            assert pid_file.exists(), "Cancellation worker did not start"
            child_pid = int(pid_file.read_text(encoding="ascii"))
            app.cancel()
            deadline = time.monotonic() + 15
            while app.process and time.monotonic() < deadline:
                app.update()
                time.sleep(0.03)
            assert app.process is None, "Cancellation did not finish"
            import os
            if os.name == "nt":
                import ctypes
                handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, child_pid)
                if handle:
                    try:
                        assert ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0, "FFmpeg left running"
                    finally:
                        ctypes.windll.kernel32.CloseHandle(handle)
            report = {"ok": True, "video": app.last_video, "ui_ticks": ticks, "duration": media["format"]["duration"], "pages": list(app.pages), "full_pipeline_mock_ai": True, "automatic_music_mock_network_real_render": True, "cancel_ffmpeg_tree": True}
    except Exception:
        import traceback
        report["error"] = traceback.format_exc()
    finally:
        if app:
            if app.process:
                app.cancel()
                deadline = time.monotonic() + 10
                while app.process and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.05)
            app.destroy()
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
