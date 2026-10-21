import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from core.music_library import TRACKS, automatic_music, valid_audio
from core.ai_reviewer import ensure_ffmpeg_available


def audio_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000)
    return buffer.getvalue()


def response(data, content_type="audio/mpeg"):
    result = io.BytesIO(data)
    result.headers = {"Content-Type": content_type}
    return result


class MusicLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_ffmpeg_available()

    def test_download_validates_audio_and_cache_works_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("core.music_library.urllib.request.urlopen", return_value=response(audio_bytes())) as download:
                path, track = automatic_music(root / "job", cache_dir=root / "cache")
                self.assertEqual(download.call_count, 1)
                self.assertTrue(valid_audio(Path(path)))
                self.assertEqual(Path(path).name, track.cache_name)
            with patch("core.music_library.urllib.request.urlopen", side_effect=AssertionError("No network")):
                cached, same_track = automatic_music(root / "job", cache_dir=root / "cache")
            self.assertEqual(cached, path)
            self.assertEqual(same_track, track)
            self.assertEqual(list((root / "job").iterdir()), [])

    def test_invalid_cache_and_html_are_replaced_by_next_valid_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            cache.mkdir()
            for track in TRACKS:
                (cache / track.cache_name).write_bytes(b"invalid")
            with patch("core.music_library.urllib.request.urlopen", side_effect=[response(b"<html>error</html>", "text/html"), response(audio_bytes())]) as download:
                path, _ = automatic_music(root / "job", cache_dir=cache)
            self.assertEqual(download.call_count, 2)
            self.assertTrue(valid_audio(Path(path)))
            self.assertEqual(list((root / "job").iterdir()), [])

    def test_failed_downloads_leave_no_partial_or_fake_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            responses = [response(b"not real audio") for _ in TRACKS]
            with patch("core.music_library.urllib.request.urlopen", side_effect=responses):
                with self.assertRaisesRegex(RuntimeError, "Không tải được nhạc tự động"):
                    automatic_music(root / "job", cache_dir=root / "cache")
            self.assertEqual(list((root / "job").iterdir()), [])
            self.assertEqual(list((root / "cache").iterdir()), [])

    def test_oversize_download_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            responses = [response(audio_bytes()) for _ in TRACKS]
            with patch("core.music_library.MAX_DOWNLOAD_BYTES", 128), patch("core.music_library.urllib.request.urlopen", side_effect=responses):
                with self.assertRaises(RuntimeError):
                    automatic_music(root / "job", cache_dir=root / "cache")
            self.assertEqual(list((root / "cache").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
