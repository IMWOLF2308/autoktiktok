"""Probe a Python installation without fragile PowerShell inline-code quoting."""
import sys


def main():
    try:
        if not (3, 14) <= sys.version_info[:2] < (3, 16):
            raise RuntimeError("Requires Python 3.14 or 3.15")
        if sys.maxsize <= 2**32:
            raise RuntimeError("Requires 64-bit Python")
        import tkinter
        import venv  # noqa: F401 - ensure the standard venv module is present

        tkinter.Tcl().eval("info patchlevel")
        print(sys._base_executable)
        return 0
    except Exception as exc:
        print(f"Python probe failed ({sys.executable}): {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
