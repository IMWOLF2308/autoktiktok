"""Curated CC0 music, validated downloads and a reusable local cache."""
from dataclasses import dataclass
from http.client import HTTPException
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import urllib.request

from core.process_utils import run_command


@dataclass(frozen=True)
class MusicTrack:
    title: str
    key: str
    author: str
    source: str
    filename: str

    @property
    def url(self):
        return "https://opengameart.org/sites/default/files/" + self.filename

    @property
    def cache_name(self):
        return self.key + Path(self.filename).suffix

    @property
    def credit(self):
        return (f'Music: "{self.title}" — {self.author}\n'
                f"Source: {self.source}\n"
                "CC0 1.0: https://creativecommons.org/publicdomain/zero/1.0/\n"
                "Attribution is not required. Source information kept for reference.\n"
                "Edits: excerpted/looped, volume adjusted and faded for this video.")


# Track-specific licenses checked against the publisher's pages, 2026-10-21.
TRACKS = (
    MusicTrack("City Loop", "oga-city-loop", "wipics",
               "https://opengameart.org/content/city-loop-0", "city-loop_0.mp3"),
    MusicTrack("Our Expanse", "oga-our-expanse", "Bobjt",
               "https://opengameart.org/content/our-expanse", "our_expanse_-_loop-version-.mp3"),
    MusicTrack("Upbeat Song", "oga-upbeat-song", "Ruhinre",
               "https://opengameart.org/content/upbeat-song", "happy.wav"),
)
MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024


def music_cache_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AutoEditTikTok" / "music"
    return Path(__file__).resolve().parents[1] / ".appdata" / "music"


def valid_audio(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        result = run_command([
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type", "-of", "json", str(path),
        ], capture_output=True, timeout=15)
        return result.returncode == 0 and any(
            stream.get("codec_type") == "audio"
            for stream in json.loads(result.stdout).get("streams", [])
        )
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return False


def automatic_music(work_dir: Path, emit=lambda *args: None, cache_dir: Path | None = None):
    """Return (path, track). Never substitute an unlicensed bundled/random file."""
    from core.ai_reviewer import ensure_ffmpeg_available
    ensure_ffmpeg_available()
    cache = Path(cache_dir) if cache_dir is not None else music_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    tracks = list(TRACKS)
    random.shuffle(tracks)
    for track in tracks:
        path = cache / track.cache_name
        if valid_audio(path):
            emit("log", f"Nhạc đã tải: {track.title} · {track.author} · CC0")
            return str(path.resolve()), track

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    partial = work_dir / "music-download.part"
    errors = []
    for track in tracks:
        emit("stage", f"Đang tải nhạc miễn phí: {track.title}")
        try:
            request = urllib.request.Request(track.url, headers={"User-Agent": "AutoEditTikTok/1.0"})
            deadline = time.monotonic() + 60
            size = 0
            with urllib.request.urlopen(request, timeout=15) as response, partial.open("wb") as target:
                if "text/html" in response.headers.get("Content-Type", "").lower():
                    raise ValueError("Nguồn trả về trang web thay vì âm thanh")
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES or time.monotonic() > deadline:
                        raise ValueError("Vượt giới hạn dung lượng hoặc thời gian tải")
                    target.write(chunk)
            if not valid_audio(partial):
                raise ValueError("Tệp tải về không có âm thanh hợp lệ")
            destination = cache / track.cache_name
            # A cancelled download stays inside the job workspace. Validate cache
            # entries on reuse, including interruption during a cross-drive move.
            shutil.move(str(partial), str(destination))
            emit("log", f"Đã tải: {track.title} · {track.author} · CC0")
            return str(destination.resolve()), track
        except (OSError, ValueError, HTTPException) as exc:
            errors.append(f"{track.title}: {exc}")
            emit("log", f"Chưa tải được {track.title}; thử bản tiếp theo.")
        finally:
            partial.unlink(missing_ok=True)
    raise RuntimeError("Không tải được nhạc tự động. Kiểm tra mạng, chọn file nhạc hoặc tắt nhạc nền. " + " | ".join(errors))


