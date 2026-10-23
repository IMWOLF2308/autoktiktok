import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from google.genai.errors import APIError
from httpx import ReadTimeout, Response
from pydantic import ValidationError

from core.ai_reviewer import (
    TikTokReviewOutput, _call_gemini_worker, _parse_json_safely,
    analyze_video_and_generate_script,
)
from desktop.pipeline import JobConfig, run_job, validate_job
from core.content_rules import REQUIRED_OUTRO, prepare_voiceover


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
                    self.assertEqual(result.model_dump(), dict(payload, voiceover_script=prepare_voiceover(payload["voiceover_script"])))
                    client.return_value.close.assert_called_once()

    def test_user_notes_are_supplemental_and_not_substituted_for_model_output(self):
        with tempfile.TemporaryDirectory() as folder, patch("core.ai_reviewer._create_storyboard_bytes", return_value=b"images"), patch("core.ai_reviewer.genai.Client") as client:
            video = Path(folder) / "room.mp4"
            video.touch()
            notes = 'Thông tin đã xác nhận: giá 4 triệu; ghi chú "gần trường"'
            payload = dict(room_info="Quan sát từ video", voiceover_script="Lời bình riêng", tiktok_caption="Caption riêng")
            client.return_value.models.generate_content.return_value = SimpleNamespace(text=json.dumps(payload))
            result = analyze_video_and_generate_script("fake", str(video), notes)
            request = client.return_value.models.generate_content.call_args.kwargs
            self.assertEqual(request["model"], "gemini-3.8-flash")
            self.assertEqual(JobConfig().model, "gemini-3.8-flash")
            prompt = request["contents"][1]
            self.assertIn(json.dumps(notes, ensure_ascii=False), prompt)
            self.assertIn("không phải kịch bản để sao chép", prompt)
            self.assertIn("Không chép nguyên đoạn tư liệu", prompt)
            self.assertIn("Giữ chính xác giá, địa chỉ, tên riêng, số liệu", prompt)
            self.assertIn("Câu đầu BẮT BUỘC", prompt)
            self.assertIn(REQUIRED_OUTRO, prompt)
            self.assertIn("nội dung đăng bài RIÊNG", prompt)
            self.assertEqual(result.room_info, payload["room_info"])

    def test_display_names_are_sent_as_api_ids_and_custom_models_are_preserved(self):
        models = {
            "Gemini 3.8 Flash": "gemini-3.8-flash",
            "  Gemini   3.8 FLASH  ": "gemini-3.8-flash",
            "models/gemini-3.8-flash": "gemini-3.8-flash",
            "gemini-3.8-flash-lite": "gemini-3.8-flash-lite",
            "chosen-model": "chosen-model",
            "tunedModels/customResource123": "tunedModels/customResource123",
        }
        payload = dict(room_info="Observations", voiceover_script="Narration", tiktok_caption="Caption")
        for label, model_id in models.items():
            with self.subTest(label=label), patch("core.ai_reviewer.genai.Client") as client:
                client.return_value.models.generate_content.return_value = SimpleNamespace(text=json.dumps(payload))
                result = _call_gemini_worker("fake", label, b"image", "prompt")
                self.assertEqual(client.return_value.models.generate_content.call_args.kwargs["model"], model_id)
                self.assertEqual(result.model_dump(), payload)
                client.return_value.models.generate_content.assert_called_once()

    def test_api_error_retains_google_reason_and_model_without_exposing_key(self):
        cases = (
            (400, "GenerateContentRequest.model: unexpected model name format", "Tên model không đúng"),
            (400, "API key secret-test-key not valid", "API Key bị Google từ chối"),
            (400, "Invalid response schema: unsupported field", "Google từ chối yêu cầu"),
            (503, "This model is currently experiencing high demand", "Model đang quá tải"),
        )
        for code, detail, hint in cases:
            with self.subTest(code=code, detail=detail), patch("core.ai_reviewer.time.sleep"), patch("core.ai_reviewer.genai.Client") as client:
                client.return_value.models.generate_content.side_effect = APIError(code, {"error": {"message": detail}})
                with self.assertRaises(RuntimeError) as caught:
                    _call_gemini_worker("secret-test-key", "Gemini 3.8 Flash", b"image", "prompt")
                message = str(caught.exception)
                self.assertIn(str(code), message)
                self.assertIn("gemini-3.8-flash", message)
                self.assertIn(hint, message)
                self.assertIn(detail.replace("secret-test-key", "[API KEY]"), message)
                self.assertNotIn("secret-test-key", message)
                self.assertEqual(client.return_value.models.generate_content.call_count, 3 if code == 503 else 1)
                client.return_value.close.assert_called_once()

    def test_overload_retries_same_video_and_returns_only_valid_ai_output(self):
        with tempfile.TemporaryDirectory() as folder, patch("core.ai_reviewer.time.sleep") as wait, patch("core.ai_reviewer.random.uniform", return_value=0), patch("core.ai_reviewer._create_storyboard_bytes", return_value=b"same-video") as extract, patch("core.ai_reviewer.genai.Client") as client:
            video = Path(folder) / "video.mp4"
            video.touch()
            payload = dict(room_info="New analysis", voiceover_script="New narration", tiktok_caption="New caption")
            client.return_value.models.generate_content.side_effect = [
                APIError(503, {"error": {"message": "high demand"}}),
                APIError(503, {"error": {"message": "high demand"}}),
                SimpleNamespace(text=json.dumps(payload)),
            ]
            progress = []
            result = analyze_video_and_generate_script("fake", str(video), on_progress=progress.append)
            self.assertEqual(result.model_dump(), dict(payload, voiceover_script=prepare_voiceover(payload["voiceover_script"])))
            self.assertEqual([call.args[0] for call in wait.call_args_list], [15, 30])
            extract.assert_called_once()
            calls = client.return_value.models.generate_content.call_args_list
            self.assertEqual(len(calls), 3)
            for call in calls:
                self.assertEqual(call.kwargs["model"], "gemini-3.8-flash")
                self.assertEqual(call.kwargs["contents"][0].inline_data.data, b"same-video")
                self.assertNotIn("temperature", call.kwargs["config"])
            self.assertTrue(any("thử lại 2/3" in message for message in progress))
            self.assertTrue(any("lần 3/3" in message for message in progress))
            client.return_value.close.assert_called_once()

    def test_retry_after_is_respected_without_unbounded_waits(self):
        for retry_after, expected_delay, call_count in (("40", 40, 2), ("120", None, 1), ("invalid", 15, 2)):
            with self.subTest(retry_after=retry_after), patch("core.ai_reviewer.time.sleep") as wait, patch("core.ai_reviewer.random.uniform", return_value=0), patch("core.ai_reviewer.genai.Client") as client:
                error = APIError(503, {"error": {"message": "busy"}}, response=Response(503, headers={"Retry-After": retry_after}))
                payload = dict(room_info="Analysis", voiceover_script="Narration", tiktok_caption="Caption")
                client.return_value.models.generate_content.side_effect = [error, SimpleNamespace(text=json.dumps(payload))]
                if expected_delay is None:
                    with self.assertRaises(RuntimeError):
                        _call_gemini_worker("fake", "chosen", b"image", "prompt")
                    wait.assert_not_called()
                else:
                    self.assertEqual(_call_gemini_worker("fake", "chosen", b"image", "prompt").model_dump(), payload)
                    wait.assert_called_once_with(expected_delay)
                self.assertEqual(client.return_value.models.generate_content.call_count, call_count)
                client.return_value.close.assert_called_once()

    def test_overload_uses_flash_lite_temporarily_with_same_images_and_notes(self):
        with tempfile.TemporaryDirectory() as folder, patch("core.ai_reviewer.time.sleep"), patch("core.ai_reviewer._create_storyboard_bytes", return_value=b"same-images") as extract, patch("core.ai_reviewer.genai.Client") as client:
            video = Path(folder) / "room.mp4"
            video.touch()
            notes = "Giá 5,7 triệu, có thang máy và hầm xe"
            payload = dict(room_info="Analysis", voiceover_script="Edited narration", tiktok_caption="Caption")
            client.return_value.models.generate_content.side_effect = [
                APIError(503, {"error": {"message": "high demand"}}),
                SimpleNamespace(text=json.dumps(payload)),
                SimpleNamespace(text=json.dumps(payload)),
            ]
            progress = []
            result = analyze_video_and_generate_script("fake", str(video), notes, fallback_model="gemini-3.5-flash-lite", on_progress=progress.append)
            calls = client.return_value.models.generate_content.call_args_list
            self.assertEqual([call.kwargs["model"] for call in calls], ["gemini-3.8-flash", "gemini-3.5-flash-lite"])
            self.assertEqual(calls[0].kwargs["contents"], calls[-1].kwargs["contents"])
            self.assertIn(notes, calls[-1].kwargs["contents"][1])
            extract.assert_called_once()
            self.assertEqual(result.model_used, "gemini-3.5-flash-lite")
            self.assertEqual(result.model_dump(), dict(payload, voiceover_script=prepare_voiceover(payload["voiceover_script"])))
            self.assertTrue(any("Đang dùng tạm gemini-3.5-flash-lite" in message for message in progress))
            # A subsequent job goes back to the primary model, never overwriting settings.
            next_result = analyze_video_and_generate_script("fake", str(video), fallback_model="gemini-3.5-flash-lite")
            self.assertEqual(next_result.model_used, "gemini-3.8-flash")

    def test_fallback_is_bounded_and_never_used_for_auth_or_quota_errors(self):
        for code, expected_calls in ((400, 1), (401, 1), (403, 1), (404, 1), (429, 1), (503, 2)):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as folder, patch("core.ai_reviewer.time.sleep"), patch("core.ai_reviewer._create_storyboard_bytes", return_value=b"image"), patch("core.ai_reviewer.genai.Client") as client:
                video = Path(folder) / "room.mp4"
                video.touch()
                client.return_value.models.generate_content.side_effect = APIError(code, {"error": {"message": "unavailable"}})
                with self.assertRaises(RuntimeError):
                    analyze_video_and_generate_script("fake", str(video), fallback_model="gemini-3.5-flash-lite")
                self.assertEqual(client.return_value.models.generate_content.call_count, expected_calls)
                self.assertEqual(client.return_value.close.call_count, 2 if code == 503 else 1)

    def test_slow_primary_uses_lite_once_instead_of_repeating_timed_out_request(self):
        with tempfile.TemporaryDirectory() as folder, patch("core.ai_reviewer.time.sleep") as wait, patch("core.ai_reviewer._create_storyboard_bytes", return_value=b"image"), patch("core.ai_reviewer.genai.Client") as client:
            video = Path(folder) / "room.mp4"
            video.touch()
            payload = dict(room_info="Analysis", voiceover_script="Narration", tiktok_caption="Caption")
            client.return_value.models.generate_content.side_effect = [ReadTimeout("too slow"), SimpleNamespace(text=json.dumps(payload))]
            result = analyze_video_and_generate_script("fake", str(video), fallback_model="gemini-3.5-flash-lite")
            self.assertEqual(result.model_used, "gemini-3.5-flash-lite")
            self.assertEqual([call.kwargs["model"] for call in client.return_value.models.generate_content.call_args_list], ["gemini-3.8-flash", "gemini-3.5-flash-lite"])
            wait.assert_not_called()

    def test_api_errors_and_timeout_never_return_canned_content(self):
        for error in (APIError(403, {"error": {"message": "denied"}}),
                      APIError(404, {"error": {"message": "missing model"}}),
                      APIError(429, {"error": {"message": "quota"}}),
                      ReadTimeout("too slow")):
            with self.subTest(error=type(error).__name__), patch("core.ai_reviewer.time.sleep") as wait, patch("core.ai_reviewer.genai.Client") as client:
                client.return_value.models.generate_content.side_effect = error
                with self.assertRaises(RuntimeError):
                    _call_gemini_worker("fake", "chosen", b"image", "prompt")
                self.assertEqual(client.return_value.models.generate_content.call_count, 1)
                wait.assert_not_called()
                client.return_value.close.assert_called_once()

    def test_copied_caption_gets_one_rewrite_and_preserves_original_analysis(self):
        for keep_copy in (False, True):
            with self.subTest(keep_copy=keep_copy), tempfile.TemporaryDirectory() as folder, patch("core.ai_reviewer._create_storyboard_bytes", return_value=b"frames"), patch("core.ai_reviewer.genai.Client") as client:
                video = Path(folder) / "room.mp4"
                video.touch()
                script = "Cửa sổ này đón ánh sáng vào cả căn phòng."
                original = dict(room_info="Original observations", voiceover_script=script, tiktok_caption=script + " #room")
                revised = dict(room_info="Changed observations", voiceover_script="Changed script", tiktok_caption=script if keep_copy else "Góc phòng sáng đáng xem! #room")
                client.return_value.models.generate_content.side_effect = [SimpleNamespace(text=json.dumps(value)) for value in (original, revised)]
                if keep_copy:
                    with self.assertRaisesRegex(ValueError, "trùng lời review"):
                        analyze_video_and_generate_script("fake", str(video))
                else:
                    result = analyze_video_and_generate_script("fake", str(video))
                    self.assertEqual(result.room_info, original["room_info"])
                    self.assertEqual(result.voiceover_script, prepare_voiceover(script))
                    self.assertEqual(result.tiktok_caption, revised["tiktok_caption"])
                self.assertEqual(client.return_value.models.generate_content.call_count, 2)

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
