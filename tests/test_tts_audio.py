import io
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.ai_reviewer import _save_tts_audio, _try_gemini_native_tts


def wav_with_metadata():
    pcm = struct.pack("<4h", 0, 1000, -1000, 0)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm)
    data = bytearray(buffer.getvalue())
    metadata = b"trainedAlgorithmicMedia\x00\x00"
    data.extend(b"LIST" + struct.pack("<I", len(metadata)) + metadata)
    struct.pack_into("<I", data, 4, len(data) - 8)
    return bytes(data), pcm


class TTSAudioTests(unittest.TestCase):
    def test_wav_metadata_is_not_audio(self):
        data, pcm = wav_with_metadata()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "voice.wav"
            _save_tts_audio(data, "audio/wav", str(output))
            self.assertEqual(output.read_bytes(), data)
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getnframes(), 4)
                self.assertEqual(wav.readframes(100), pcm)

    def test_legacy_pcm_keeps_samples_and_sample_rate(self):
        _, pcm = wav_with_metadata()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "voice.wav"
            _save_tts_audio(pcm, "audio/L16;codec=pcm;rate=16000", str(output))
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.readframes(100), pcm)

    def test_invalid_audio_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            output = str(Path(folder) / "voice.wav")
            for data, mime in [(b"ID3audio", "audio/mpeg"), (b"x", "audio/L16"), (b"", "audio/L16")]:
                with self.subTest(mime=mime, data=data), self.assertRaises(ValueError):
                    _save_tts_audio(data, mime, output)

    def test_style_is_separate_from_spoken_text_including_fallback(self):
        data, _ = wav_with_metadata()
        response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
            SimpleNamespace(inline_data=None),
            SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type="audio/wav")),
        ]))])
        script = "Căn phòng thoáng sáng, nhắn Zalo để xem phòng nhé!"
        for use_legacy in (False, True):
            with self.subTest(legacy=use_legacy), tempfile.TemporaryDirectory() as folder:
                def generate(**kwargs):
                    if use_legacy and kwargs["model"].startswith("gemini-3.8"):
                        raise RuntimeError("Model unavailable")
                    return response

                with patch("core.ai_reviewer.genai.Client") as client:
                    generate_mock = client.return_value.models.generate_content
                    generate_mock.side_effect = generate
                    model = _try_gemini_native_tts("test-key", script, str(Path(folder) / "voice.wav"))
                    self.assertIsNotNone(model)
                    for call in generate_mock.call_args_list:
                        part = call.kwargs["contents"][0].parts[0]
                        self.assertEqual(part.text, script)
                        if call.kwargs["model"].startswith("gemini-3.8"):
                            self.assertTrue(part.speech_metadata.style)
                        else:
                            self.assertIsNone(part.speech_metadata)


if __name__ == "__main__":
    unittest.main()
