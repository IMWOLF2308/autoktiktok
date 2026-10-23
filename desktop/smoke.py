"""Offline integration check for both source and frozen Windows builds."""
import json
from pathlib import Path
import time
from unittest.mock import patch

from core.ai_reviewer import ensure_ffmpeg_available
from core.process_utils import run_command
from core.content_rules import prepare_voiceover


def offline_wizard_worker(config, action, queue):
    """Run real workers with only the paid/network AI and TTS calls doubled."""
    from core.ai_reviewer import TikTokReviewOutput
    from desktop.pipeline import worker_entry
    def local_voice(text, output, **kwargs):
        ensure_ffmpeg_available()
        run_command(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                     "sine=frequency=440:duration=2", output], capture_output=True, check=True)
        return output
    with patch("core.ai_reviewer.analyze_video_and_generate_script", return_value=TikTokReviewOutput(
        room_info="Phòng từ phản hồi giả lập trong kiểm thử.", voiceover_script="Lời bình mẫu.", tiktok_caption="#phongtro"
    )), patch("core.ai_reviewer.generate_voiceover_mp3", side_effect=local_voice):
        worker_entry(config, action, queue)


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


def offline_tiktok_worker(action, folder, payload, events):
    """Only the remote TikTok operation is doubled; UI/IPC remain real."""
    if action == "tiktok_login":
        events.put(("tiktok_connected", {"username": "offline.user", "display_name": "Offline Test"}))
    else:
        assert Path(payload["video"]).is_file()
        assert payload["username"] == "offline.user"
        assert payload["caption"] == Path(payload["video"]).with_suffix(".caption.txt").read_text(encoding="utf-8")
        marker = Path(folder) / "offline-post.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(payload), encoding="utf-8")
        events.put(("tiktok_published", payload))


def offline_failed_render_worker(config, action, events):
    events.put(("error", "Offline simulated render failure"))


def overloaded_ai_worker(config, action, queue):
    """Exercise the real retry wait and cancellation, without any API requests."""
    from google.genai.errors import APIError
    from desktop.pipeline import worker_entry
    with patch("core.ai_reviewer.genai.Client") as client:
        client.return_value.models.generate_content.side_effect = APIError(503, {"error": {"message": "Test overload"}})
        worker_entry(config, action, queue)


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
        with patch("desktop.app.settings_path", return_value=folder / "test-settings.json"), patch("desktop.app.worker_entry", offline_wizard_worker), patch("desktop.app.tiktok_worker", offline_tiktok_worker):
            app = AutoEditApp()
            assert app.vars["model"].get() == "gemini-3.8-flash"
            assert app.vars["allow_model_fallback"].get()
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
            assert app.current_step == 0
            assert not app.script_text.winfo_viewable()
            assert not app.music_status.winfo_viewable()
            assert app.room_text.winfo_viewable()
            assert app.back_button.cget("state") == "disabled"
            # Settings stay outside the steps and can be reopened safely.
            app.open_connection()
            app.update()
            assert app.connection_dialog.winfo_viewable()
            entries = [child for row in app.connection_dialog.winfo_children() for child in row.winfo_children()
                       if child.winfo_class() == "TEntry"]
            key_entry = next(entry for entry in entries if str(entry.cget("textvariable")) == str(app.vars["api_key"]))
            assert key_entry.cget("show") == "" and key_entry.get() == "offline-test-key"
            app.connection_dialog.destroy()
            app.open_connection()
            app.connection_dialog.destroy()
            with patch("desktop.app.messagebox.showerror"):
                app.active_action = "draft"
                app._handle("error", "Offline simulated AI error")
            assert app.current_step == 0 and not app.script_text.winfo_viewable()
            app.toggle_log()
            def wait_job():
                deadline = time.monotonic() + 30
                while app.process and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.02)
                assert app.process is None, "Wizard worker timed out"
                app.update()

            # Use the actual primary button to draft, then automatically advance.
            app.run_button.invoke()
            assert app.process is not None and app.current_step == 0
            assert app.back_button.cget("state") == "disabled"
            wait_job()
            assert app.current_step == 1
            assert not app.room_text.winfo_viewable()
            assert app.script_text.winfo_viewable()
            assert app.script_text.get("1.0", "end").strip() == prepare_voiceover("Lời bình mẫu.")
            assert "gemini-3.8-flash" in app.review_model_label.cget("text")
            with patch("desktop.app.messagebox.showerror") as error:
                app.run_button.invoke()
                assert error.called and app.current_step == 1 and app.process is None
            app._set_text(app.script_text, "Kiểm tra đếm từ")
            app.update()
            assert app.word_count.cget("text").startswith("4 từ")
            app.start("voice")
            wait_job()
            assert app.current_step == 1, "Voice generation must wait for user confirmation"
            generated_voice = app.vars["voice_file"].get()
            assert Path(generated_voice).is_file()
            app._set_text(app.script_text, "Lời bình đã chỉnh sửa")
            with patch("desktop.app.messagebox.showerror") as error:
                app.next_step()
                assert error.called and app.current_step == 1 and app.process is None
            app._set_text(app.script_text, prepare_voiceover("Kiểm tra đếm từ"))
            bad_audio = folder / "invalid.wav"
            bad_audio.write_bytes(b"not audio")
            app.vars["voice_file"].set(str(bad_audio))
            with patch("desktop.app.messagebox.showerror") as error:
                app.next_step()
                wait_job()
                assert error.called and app.current_step == 1 and app.confirmed_voice is None
            if app.terminal.winfo_manager():
                app.toggle_log()
            app.vars["voice_file"].set(generated_voice)
            app.pages["video"].canvas.yview_moveto(0)
            app.update()
            ImageGrab.grab(window=app.winfo_id()).save(folder / "step_2_script_voice.png")
            original_geometry = app.geometry()
            app.geometry("1160x760")
            app.update()
            app.pages["video"].canvas.yview_moveto(0)
            app.update()
            ImageGrab.grab(window=app.winfo_id()).save(folder / "workspace_medium.png")
            app.geometry("960x720")
            app.update()
            app.pages["video"].canvas.yview_moveto(0)
            app.update()
            ImageGrab.grab(window=app.winfo_id()).save(folder / "workspace_narrow.png")
            app.geometry(original_geometry)
            app.deiconify()
            app.update()
            app.toggle_log()
            app.update()
            assert app.logs.winfo_viewable(), f"Log hidden: root={app.state()}, terminal={app.terminal.winfo_manager()}, height={app.winfo_height()}"
            assert app.run_button.winfo_viewable()
            app.toggle_log()
            assert app.snapshot().video == str(video)
            with patch("desktop.studio_ui.messagebox.showinfo") as help_message:
                app.toggle_help()
                assert help_message.called
            # Going back keeps the draft and does not silently request AI again.
            app.previous_step()
            assert app.current_step == 0
            app.next_step()
            assert app.current_step == 1 and app.process is None
            assert app.script_text.get("1.0", "end").strip() == prepare_voiceover("Kiểm tra đếm từ")
            app.next_step()
            wait_job()
            assert app.current_step == 2 and app.confirmed_voice
            assert not app.script_text.winfo_viewable() and app.music_status.winfo_viewable()
            app.update()
            ImageGrab.grab(window=app.winfo_id()).save(folder / "step_3_style.png")
            old_logo = app.vars["logo"].get()
            app.vars["logo"].set("missing.png")
            with patch("desktop.app.messagebox.showerror") as error:
                app.next_step()
                assert error.called and app.current_step == 2
            app.vars["logo"].set(old_logo)
            app.next_step()
            assert app.current_step == 3
            app.update()
            assert not app.music_status.winfo_viewable()
            ImageGrab.grab(window=app.winfo_id()).save(folder / "step_4_export.png")
            app.pages["video"].canvas.yview_moveto(0)
            app.show_page("video")
            app.run_button.invoke()
            assert app.process is not None, "Render did not start"
            deadline = time.monotonic() + 90
            ticks = 0
            while app.process and time.monotonic() < deadline:
                app.update()
                ticks += 1
                time.sleep(0.02)
            assert app.process is None, "Render timed out"
            assert app.last_video and Path(app.last_video).is_file(), "No rendered video"
            assert not app.auto_post.get()
            marker = folder / "tiktok" / "offline-post.json"
            assert not marker.exists(), "Unchecked option must not publish"
            app.connect_tiktok()
            wait_job()
            assert app.tiktok_account["username"] == "offline.user"
            assert "Đã đăng nhập thành công" in app.tiktok_status.cget("text")
            # Opting in after rendering uploads the exact saved video/caption.
            app.auto_post.set(True)
            app.auto_post_changed()
            wait_job()
            assert json.loads(marker.read_text(encoding="utf-8"))["video"] == app.last_video
            assert not app.auto_post.get()
            marker.unlink()
            # Opting in before render chains the worker only after render success.
            app.auto_post.set(True)
            app.start("render")
            wait_job()
            assert json.loads(marker.read_text(encoding="utf-8"))["video"] == app.last_video
            assert not app.auto_post.get()
            saved_video = app.last_video
            marker.unlink()
            app.auto_post.set(True)
            with patch("desktop.app.worker_entry", offline_failed_render_worker), patch("desktop.app.messagebox.showerror"):
                app.start("render")
                wait_job()
            assert not marker.exists(), "Failed render must not post the previous successful output"
            assert app.pending_publish is None
            app.auto_post.set(False)
            with patch("desktop.app.messagebox.showerror"):
                app._handle("error", "Offline simulated TikTok failure")
            assert app.last_video == saved_video and Path(saved_video).is_file()
            if app.terminal.winfo_manager():
                app.toggle_log()
            app.update()
            ImageGrab.grab(window=app.winfo_id()).save(folder / "tiktok_export.png")
            report["tiktok_ui_mock_network_login_manual_and_auto_publish"] = True
            assert app.run_button.cget("state") == "normal"
            assert ticks > 1, "UI event loop was not exercised"
            # An edited source must return to AI; changing the confirmed audio
            # must return to confirmation instead of exporting a stale selection.
            app.vars["voice_file"].set(str(voice))
            with patch("desktop.app.messagebox.showerror") as error:
                app.start("render")
                assert error.called and app.current_step == 1 and app.process is None
            app.next_step()
            wait_job()
            assert app.current_step == 2
            app.next_step()
            app._set_text(app.room_text, "Yêu cầu mới cho AI")
            with patch("desktop.app.messagebox.showerror") as error:
                app.post_latest_video()
                assert error.called and app.process is None
                error.reset_mock()
                app.start("render")
                assert error.called and app.current_step == 0 and app.process is None
            app._set_text(app.room_text, "")
            probe = run_command(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", app.last_video], capture_output=True, check=True)
            media = json.loads(probe.stdout)
            assert {s["codec_type"] for s in media["streams"]} >= {"audio", "video"}
            assert 1.8 < float(media["format"]["duration"]) < 2.5
            app.vars["model"].set("Gemini 3.8 Flash")
            assert app.snapshot("draft").model == "gemini-3.8-flash"
            app._save_settings()
            saved = json.loads((folder / "test-settings.json").read_text(encoding="utf-8"))
            assert saved["api_key"] == "offline-test-key"
            assert saved["model"] == "gemini-3.8-flash"
            assert saved["allow_model_fallback"] is True
            app.vars["allow_model_fallback"].set(False)
            app.vars["api_key"].set("")
            app.vars["use_logo"].set(False)
            app.vars["use_bgm"].set(True)
            app._load_settings()
            assert app.vars["api_key"].get() == "offline-test-key"
            assert app.vars["allow_model_fallback"].get()
            assert app.vars["use_logo"].get() and not app.vars["use_bgm"].get()
            assert Path(app.vars["logo"].get()).is_file()
            assert app.vars["bgm"].get() == "", "Automatic music must survive settings reload"
            saved["room_info"] = "Legacy room description must not be reused"
            saved["model"] = "Gemini 3.8 Flash"
            (folder / "test-settings.json").write_text(json.dumps(saved), encoding="utf-8")
            app._load_settings()
            assert app.vars["model"].get() == "gemini-3.8-flash"
            report["gemini_settings_normalized_and_key_visible"] = True
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
                assert text == prepare_voiceover("Lời bình mẫu.")
                shutil.copy2(voice, output)
                return output
            with patch("core.ai_reviewer.analyze_video_and_generate_script", return_value=TikTokReviewOutput(room_info="Phòng từ phản hồi giả lập trong kiểm thử.", voiceover_script="Lời bình mẫu.", tiktok_caption="#phongtro")), patch("core.ai_reviewer.generate_voiceover_mp3", side_effect=local_voice):
                full_result = run_job(config, "all", lambda k, v: emitted.append((k, v)))
            assert Path(full_result["video"]).is_file()
            assert Path(full_result["script_file"]).read_text(encoding="utf-8") == prepare_voiceover("Lời bình mẫu.")
            assert Path(full_result["caption_file"]).read_text(encoding="utf-8") == "#phongtro"
            assert Path(full_result["room_info_file"]).read_text(encoding="utf-8") == "Phòng từ phản hồi giả lập trong kiểm thử."
            app.active_video = str(video)
            for kind, value in emitted:
                if kind == "script":
                    app._handle(kind, value)
            assert app.analysis_text.get("1.0", "end").strip() == "Phòng từ phản hồi giả lập trong kiểm thử."
            assert app.script_text.get("1.0", "end").strip() == prepare_voiceover("Lời bình mẫu.")
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
            # Stop during backoff: the UI keeps responding and cleans the draft workspace.
            app.show_step(0)
            app._set_text(app.script_text, "")
            app.vars["allow_model_fallback"].set(False)
            with patch("desktop.app.worker_entry", overloaded_ai_worker):
                app.start("draft")
                deadline = time.monotonic() + 15
                while app.process and "thử lại" not in app.status.get() and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.02)
                assert "thử lại" in app.status.get(), "Retry state did not reach the UI"
                assert app.stop_button.cget("state") == "normal"
                assert app.current_step == 0 and app.process is not None
                app.cancel()
                wait_job()
                assert app.source_ready is None and app.current_step == 0
                assert not (folder / "drafts" / ".autoedit_work").exists()
            report.update({"ok": True, "video": app.last_video, "ui_ticks": ticks, "duration": media["format"]["duration"], "pages": list(app.pages), "wizard_steps": 4, "wizard_transitions_and_guards": True, "full_pipeline_mock_ai": True, "automatic_music_mock_network_real_render": True, "cancel_ffmpeg_tree": True, "cancel_during_gemini_retry": True})
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
