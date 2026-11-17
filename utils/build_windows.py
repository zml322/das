"""Build a versioned Windows DASViewer executable."""

from __future__ import annotations

import subprocess
import shutil
import sys
import zipfile
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
        "--add-data",
        f"{PROJECT_ROOT / 'image' / 'img.png'};image",
        "--add-data",
        f"{PROJECT_ROOT / 'licenses'};licenses",
        "--add-data",
        f"{PROJECT_ROOT / 'THIRD_PARTY_NOTICES.md'};.",
        "--collect-data",
        "imageio_ffmpeg",
        "--hidden-import",
        "imageio_ffmpeg",
        str(PROJECT_ROOT / "main.py"),
    ]
    print("Building", APP_NAME)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    source_archive = dist_path / f"{APP_NAME}-source.zip"
    source_files = [
        PROJECT_ROOT / name for name in (
            'main.py', 'build_windows.py', 'build_macos.py', 'requirements.txt',
            'THIRD_PARTY_NOTICES.md', f'RELEASE_NOTES_v{__version__}.md',
        )
    ]
    for directory in ('utils', 'image', 'test', 'licenses'):
        source_files.extend(
            path for path in (PROJECT_ROOT / directory).rglob('*')
            if path.is_file() and '__pycache__' not in path.parts
            and path.suffix.lower() in ('.py', '.png', '.jpg', '.ico', '.icns', '.txt', '.md')
        )
    with zipfile.ZipFile(source_archive, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(source_files)):
            if path.is_file():
                archive.write(path, arcname=f'{APP_NAME}-source/{path.relative_to(PROJECT_ROOT).as_posix()}')
    for name in ('THIRD_PARTY_NOTICES.md', f'RELEASE_NOTES_v{__version__}.md'):
        shutil.copy2(PROJECT_ROOT / name, dist_path / name)
    shutil.copytree(PROJECT_ROOT / 'licenses', dist_path / 'licenses', dirs_exist_ok=True)
    print(f"Build complete: {dist_path / (APP_NAME + '.exe')}")
    print(f"Source archive: {source_archive}")


if __name__ == "__main__":
    main()
