"""Run media tools without flashing console windows in the desktop app."""
import os
import subprocess


def run_command(args, **kwargs):
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    return subprocess.run(args, **kwargs)
