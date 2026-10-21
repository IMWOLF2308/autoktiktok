import dataclasses
import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from desktop.pipeline import JobConfig, QueueLog, cleanup_work, run_job, validate_job, worker_entry


class DesktopPipelineTests(unittest.TestCase):
    def test_manual_script_and_edge_need_no_api_key(self):
        config = JobConfig(output_dir="output_videos", script="Lời bình tự viết", engine="Edge-TTS")
        validate_job(config, "voice")

    def test_validation_rejects_missing_inputs(self):
        for action in ["draft", "inspect", "render", "all", "voice", "unknown"]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_job(JobConfig(), action)

    def test_paths_and_numeric_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "phòng mẫu.mp4"
            voice = Path(folder) / "giọng đọc.wav"
            video.touch()
            voice.touch()
            config = JobConfig(video=str(video), voice_file=str(voice), output_dir=folder, contact2="0901234567")
            validate_job(config, "render")
            for changes in [{"bgm_volume": float("nan")}, {"contact_duration": 0},
                            {"logo": "missing-logo.png"}, {"bgm": "missing-bgm.mp3"}, {"rate": "fast"}]:
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    validate_job(dataclasses.replace(config, **changes), "render")

    def test_worker_reports_error_and_redacts_key(self):
        events = []
        class CaptureQueue:
            def put(self, event):
                events.append(event)
        config = JobConfig(api_key="secret-test-key")
        with patch("desktop.pipeline.run_job", side_effect=RuntimeError("bad key secret-test-key")):
            worker_entry(config, "all", CaptureQueue())
        self.assertEqual(events[-1], ("error", "bad key [API KEY]"))
        self.assertNotIn("secret-test-key", repr(events))

    def test_logs_handle_carriage_return_and_flush(self):
        events = []
        stream = QueueLog(lambda kind, text: events.append((kind, text)))
        stream.write("one\rtwo\nthree")
        stream.flush()
        self.assertEqual(events, [("log", "one"), ("log", "two"), ("log", "three")])

    def test_workspace_cleanup_and_reusable_outputs(self):
        for action in ("inspect", "draft", "voice", "render", "all"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as folder, contextlib.ExitStack() as stack:
                root = Path(folder)
                source = root / "source.mp4"
                source.write_bytes(b"input video")
                audio = root / "input.wav"
                audio.write_bytes(b"input voice")
                output = root / "output"
                config = JobConfig(video=str(source), voice_file=str(audio), output_dir=str(output),
                                   script="Lời bình", room_info="Phòng mẫu", api_key="fake",
                                   use_logo=False, use_bgm=False)
                stack.enter_context(patch("core.ai_reviewer.ensure_ffmpeg_available"))
                stack.enter_context(patch("desktop.pipeline.run_command", return_value=SimpleNamespace(
                    returncode=0, stdout=json.dumps({"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}))))

                def storyboard(*args):
                    Path("temp").mkdir(exist_ok=True)
                    Path("temp/storyboard.jpg").write_bytes(b"preview")

                def draft(*args):
                    storyboard()
                    return SimpleNamespace(room_info="Chi tiết quan sát", voiceover_script="Lời bình", tiktok_caption="#test")

                def voice(text, path, **kwargs):
                    target = Path(path).with_suffix(".wav")
                    target.write_bytes(b"generated voice")
                    return str(target)

                def render(video, voice, path, **kwargs):
                    self.assertTrue(Path(voice).is_file())
                    Path(path).write_bytes(b"completed video")

                stack.enter_context(patch("core.ai_reviewer._create_storyboard_bytes", side_effect=storyboard))
                stack.enter_context(patch("core.ai_reviewer.analyze_video_and_generate_script", side_effect=draft))
                stack.enter_context(patch("core.ai_reviewer.generate_voiceover_mp3", side_effect=voice))
                stack.enter_context(patch("core.video_renderer.render_tiktok_video", side_effect=render))
                previous_cwd = Path.cwd()
                result = run_job(config, action, lambda *args: None)
                self.assertEqual(Path.cwd(), previous_cwd)
                self.assertFalse((output / ".autoedit_work").exists())
                for path in result.values():
                    self.assertTrue(Path(path).is_file(), path)
                self.assertEqual(source.read_bytes(), b"input video")
                self.assertEqual(audio.read_bytes(), b"input voice")
                if action in {"voice", "all"}:
                    self.assertTrue(result["voice_file"].endswith(".voice.wav"))

    def test_failed_job_cleans_partial_and_restores_cwd(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "output"
            config = JobConfig(output_dir=str(output), script="Lời bình", engine="Edge-TTS")
            previous_cwd = Path.cwd()

            def fail(text, path, **kwargs):
                Path(path).write_bytes(b"partial")
                raise RuntimeError("TTS failed")

            with patch("core.ai_reviewer.ensure_ffmpeg_available"), patch("core.ai_reviewer.generate_voiceover_mp3", side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, "TTS failed"):
                    run_job(config, "voice", lambda *args: None)
            self.assertEqual(Path.cwd(), previous_cwd)
            self.assertFalse((output / ".autoedit_work").exists())
            self.assertEqual(list(output.iterdir()), [])

    def test_cleanup_preserves_other_jobs_and_rejects_outside_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            work = output / ".autoedit_work" / "20261021_120000_abcdef"
            neighbor = work.with_name("20261021_120001_123456")
            work.mkdir(parents=True)
            neighbor.mkdir()
            (work / "partial.mp4").touch()
            cleanup_work(work, output)
            self.assertFalse(work.exists())
            self.assertTrue(neighbor.is_dir())
            with self.assertRaises(ValueError):
                cleanup_work(output, output)


if __name__ == "__main__":
    unittest.main()
