import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from google.genai.errors import APIError
from httpx import ReadTimeout
from pydantic import ValidationError

from core.ai_reviewer import (
    TikTokReviewOutput, _call_gemini_worker, _parse_json_safely,
    analyze_video_and_generate_script,
)
from desktop.pipeline import JobConfig, run_job, validate_job


class GeminiReviewTests(unittest.TestCase):
    def test_video_only_uses_its_own_images_and_gemini_response(self):
        # Different videos and responses must remain different end to end.
        for suffix in ("one", "two"):
            with self.subTest(video=suffix), tempfile.TemporaryDirectory() as folder:
                video = Path(folder) / f"{suffix}.mp4"
                video.touch()
                payload = dict(room_info=f"Observations {suffix}",
                               voiceover_script=f"Narration {suffix}", tiktok_caption=f"Caption {suffix}")
                images = f"jpeg-{suffix}".encode()
                config = JobConfig(video=str(video), output_dir=folder, api_key="fake", room_info="")
                validate_job(config, "draft")
                with patch("core.ai_reviewer._create_storyboard_bytes", return_value=images) as extract, patch("core.ai_reviewer.genai.Client") as client:
                    client.return_value.models.generate_content.return_value = SimpleNamespace(text=json.dumps(payload))
                    result = analyze_video_and_generate_script("fake", str(video), model_name="chosen-model")
                    extract.assert_called_once_with(str(video), num_frames=6)
                    request = client.return_value.models.generate_content.call_args.kwargs
                    self.assertEqual(request["model"], "chosen-model")
                    self.assertEqual(request["contents"][0].inline_data.data, images)
                    self.assertIs(request["config"]["response_schema"], TikTokReviewOutput)
                    self.assertEqual(result.model_dump(), payload)
                    client.return_value.close.assert_called_once()

    def test_user_notes_are_supplemental_and_not_substituted_for_model_output(self):
        with tempfile.TemporaryDirectory() as folder, patch("core.ai_reviewer._create_storyboard_bytes", return_value=b"images"), patch("core.ai_reviewer.genai.Client") as client:
            video = Path(folder) / "room.mp4"
            video.touch()
            notes = 'Thông tin đã xác nhận: giá 4 triệu; ghi chú "gần trường"'
            payload = dict(room_info="Quan sát từ video", voiceover_script="Lời bình riêng", tiktok_caption="Caption riêng")
            client.return_value.models.generate_content.return_value = SimpleNamespace(text=json.dumps(payload))
            result = analyze_video_and_generate_script("fake", str(video), notes)
            prompt = client.return_value.models.generate_content.call_args.kwargs["contents"][1]
            self.assertIn(json.dumps(notes, ensure_ascii=False), prompt)
            self.assertEqual(result.room_info, payload["room_info"])

    def test_api_errors_and_timeout_never_return_canned_content(self):
        for error in (APIError(403, {"error": {"message": "denied"}}),
                      APIError(404, {"error": {"message": "missing model"}}),
                      APIError(429, {"error": {"message": "quota"}}),
                      ReadTimeout("too slow")):
            with self.subTest(error=type(error).__name__), patch("core.ai_reviewer.genai.Client") as client:
                client.return_value.models.generate_content.side_effect = error
                with self.assertRaises(RuntimeError):
                    _call_gemini_worker("fake", "chosen", b"image", "prompt")
                self.assertEqual(client.return_value.models.generate_content.call_count, 1)
                client.return_value.close.assert_called_once()

    def test_missing_wrong_type_or_blank_output_is_rejected(self):
        valid = dict(room_info="Quan sát", voiceover_script="Lời bình", tiktok_caption="#room")
        for field in valid:
            for value in (None, "", "   ", 123, []):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    _parse_json_safely(json.dumps({**valid, field: value}))
            invalid = {key: value for key, value in valid.items() if key != field}
            with self.assertRaises(ValidationError):
                _parse_json_safely(json.dumps(invalid))
        self.assertEqual(_parse_json_safely('```json\n' + json.dumps(valid) + '\n```').model_dump(), valid)

    def test_empty_or_malformed_gemini_reply_is_an_error(self):
        for text in (None, "", "not json", "[]", "{}"):
            with self.subTest(text=text), patch("core.ai_reviewer.genai.Client") as client:
                client.return_value.models.generate_content.return_value = SimpleNamespace(text=text)
                with self.assertRaises(ValueError):
                    _call_gemini_worker("fake", "chosen", b"images", "prompt")

    def test_ai_failure_stops_full_pipeline_before_tts_or_render(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "room.mp4"
            video.touch()
            output = Path(folder) / "result"
            config = JobConfig(video=str(video), output_dir=str(output), api_key="fake",
                               use_logo=False, use_bgm=False)
            with patch("core.ai_reviewer.ensure_ffmpeg_available"), patch("desktop.pipeline.run_command", return_value=SimpleNamespace(returncode=0, stdout='{"streams":[{"codec_type":"video"}]}')), patch("core.ai_reviewer.analyze_video_and_generate_script", side_effect=RuntimeError("Gemini failed")), patch("core.ai_reviewer.generate_voiceover_mp3") as tts, patch("core.video_renderer.render_tiktok_video") as render:
                with self.assertRaisesRegex(RuntimeError, "Gemini failed"):
                    run_job(config, "all", lambda *args: None)
                tts.assert_not_called()
                render.assert_not_called()
                self.assertFalse((output / ".autoedit_work").exists())
                self.assertEqual(list(output.iterdir()), [])
