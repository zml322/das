# macOS 运行与打包

Windows 生成的 `DASViewer.exe` 不能在 macOS 运行。请将整个项目复制到 Mac 后，在项目根目录执行以下命令。

## 首次环境安装

建议使用 Python 3.12 或 3.13。以下示例使用系统可用的 `python3`：

```bash
python3 -m venv .venv-macos
source .venv-macos/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
```

## 从源码运行

```bash
source .venv-macos/bin/activate
python main.py
```

首次启动请导入一个 `.dat` 和一个 `.bin` 文件，确认采样率、采样次数、灰度图与多通道云图均正确。

## 构建 macOS 应用

```bash
source .venv-macos/bin/activate
python build_macos.py
open dist/macos/DASViewer.app
```

脚本默认按当前 Mac 的 CPU 架构构建：Apple 芯片为 `arm64`，Intel Mac 为 `x86_64`。如要尝试构建同时适配两类 Mac 的应用，可执行：

```bash
python build_macos.py --target-architecture universal2
```

`universal2` 依赖所有 Python 扩展也提供通用二进制；若构建失败，请分别在 Apple 芯片和 Intel Mac 上构建对应架构的 `.app`。

## 图标与分发

若在 `image/favicon.icns` 放入 macOS 图标，构建脚本会自动使用；缺失时会使用系统默认图标，不影响运行。

未签名的 `.app` 可自己使用或发给他人，对方首次打开时可能需右键应用并选择“打开”。若希望下载后可直接双击打开，需要另行使用 Apple Developer ID 签名和公证；这不是本项目运行或本地打包的前置条件。
