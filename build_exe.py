"""Manual build entry point; bundle default assets, never settings or user videos."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

from core.ai_reviewer import ensure_ffmpeg_available


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true")
    parser.add_argument("--check-only", action="store_true", help="Validate build inputs without running PyInstaller")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    ensure_ffmpeg_available()
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
               "--name", "AutoEditTikTok", "--onefile" if args.onefile else "--onedir",
               "--collect-all", "google.genai", "--collect-data", "certifi",
               "--copy-metadata", "edge-tts"]
    for executable in ("ffmpeg", "ffprobe"):
        path = shutil.which(executable)
        if not path:
            raise RuntimeError(f"Missing {executable}")
        subprocess.run([path, "-version"], check=True, capture_output=True)
        command.extend(["--add-binary", f"{path};bin"])
    # Music is downloaded on demand into the user's cache, not bundled.
    for asset in ("logo/logo.png",):
        source = root / "assets" / asset
        if not source.is_file():
            raise FileNotFoundError(f"Missing default asset: {source}")
        command.extend(["--add-data", f"{source};assets/{Path(asset).parent.as_posix()}"])
    command.append(str(root / "app.py"))
    if args.check_only:
        import PyInstaller
        import tkinter
        print(f"Build inputs OK: Python {sys.version.split()[0]}, PyInstaller {PyInstaller.__version__}, Tcl/Tk {tkinter.TkVersion}")
        return
    subprocess.run(command, cwd=root, check=True)
    target = root / "dist" if args.onefile else root / "dist" / "AutoEditTikTok"
    shutil.copy2(root / "HUONG_DAN.md", target / "HUONG_DAN.md")
    print(f"Build complete: {target / 'AutoEditTikTok.exe'}")


if __name__ == "__main__":
    main()
