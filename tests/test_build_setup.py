import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import build_exe


class BuildSetupTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows PowerShell required")
    def test_python_probe_runs_through_powershell_with_spaces_in_path(self):
        with tempfile.TemporaryDirectory(prefix="python probe ") as folder:
            probe = Path(folder) / "check build python.py"
            shutil.copy2(Path(__file__).resolve().parents[1] / "scripts/check_build_python.py", probe)
            launcher = Path(folder) / "probe.ps1"
            launcher.write_text('param([string]$PythonExe, [string]$Probe)\n& $PythonExe -X utf8 $Probe\nexit $LASTEXITCODE\n', encoding="ascii")
            result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                     str(launcher), "-PythonExe", sys.executable, "-Probe", str(probe)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), Path(sys._base_executable))

    def test_check_only_never_starts_pyinstaller_or_copies_outputs(self):
        with patch.object(sys, "argv", ["build_exe.py", "--check-only"]), patch("build_exe.ensure_ffmpeg_available"), patch("build_exe.shutil.which", side_effect=lambda name: f"C:/tools/{name}.exe"), patch("build_exe.subprocess.run") as run, patch("build_exe.shutil.copy2") as copy, patch.dict(sys.modules, {"PyInstaller": SimpleNamespace(__version__="test")}):
            build_exe.main()
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                self.assertEqual(call.args[0][1:], ["-version"])
            copy.assert_not_called()
