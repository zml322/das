"""在 macOS 原生构建 DASViewer.app。

请先创建虚拟环境并安装 requirements.txt 与 PyInstaller；Windows 不能交叉构建
可运行的 macOS 应用。默认构建当前 Mac 架构的应用；如需 universal2，可传入
--target-architecture universal2（依赖也必须提供 universal2 版本）。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from utils.version import __version__


PROJECT_ROOT = Path(__file__).resolve().parent
APP_VERSION = __version__
APP_NAME = f'DASViewer-v{APP_VERSION}'
BUNDLE_IDENTIFIER = 'com.dasviewer.app'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build the native macOS DASViewer.app bundle.')
    parser.add_argument(
        '--target-architecture',
        choices=('arm64', 'x86_64', 'universal2'),
        help='PyInstaller target architecture. Omit to build for the current Mac.',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('此脚本必须在 macOS 上运行；Windows 不能生成可运行的 macOS .app。')

    dist_path = PROJECT_ROOT / 'dist' / 'macos'
    work_path = PROJECT_ROOT / 'build' / 'macos'
    command = [
        sys.executable,
        '-m',
        'PyInstaller',
        '--noconfirm',
        '--clean',
        '--windowed',
        '--name',
        APP_NAME,
        '--osx-bundle-identifier',
        BUNDLE_IDENTIFIER,
        '--distpath',
        str(dist_path),
        '--workpath',
        str(work_path),
        '--specpath',
        str(work_path),
        '--add-data',
        f"{PROJECT_ROOT / 'image' / 'img.png'}{os.pathsep}image",
    ]

    icon_path = PROJECT_ROOT / 'image' / 'favicon.icns'
    if icon_path.is_file():
        command.extend(('--icon', str(icon_path)))
    else:
        print('未找到 image/favicon.icns，将使用 macOS 默认应用图标。')

    if args.target_architecture:
        command.extend(('--target-architecture', args.target_architecture))

    command.append(str(PROJECT_ROOT / 'main.py'))
    print('执行：', ' '.join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    print(f'构建完成：{dist_path / (APP_NAME + ".app")}')


if __name__ == '__main__':
    main()
