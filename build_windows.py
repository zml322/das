"""Build a versioned Windows DASViewer executable."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from utils.version import __version__


PROJECT_ROOT = Path(__file__).resolve().parent
APP_NAME = f"DASViewer-v{__version__}"


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("build_windows.py must run on Windows")

    dist_path = PROJECT_ROOT / "dist" / f"v{__version__}"
    work_path = PROJECT_ROOT / "build" / f"v{__version__}"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(dist_path),
        "--workpath",
        str(work_path),
        "--specpath",
        str(work_path),
        "--icon",
        str(PROJECT_ROOT / "image" / "favicon.ico"),
        str(PROJECT_ROOT / "main.py"),
    ]
    print("Building", APP_NAME)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    print(f"Build complete: {dist_path / (APP_NAME + '.exe')}")


if __name__ == "__main__":
    main()

