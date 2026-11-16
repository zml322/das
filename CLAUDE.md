# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DASViewer is a PyQt5-based application for viewing and processing Distributed Acoustic Sensing (DAS) signals. It handles proprietary BIN format files with a 20-float (80-byte) header, provides real-time visualization, filtering, and video synchronization for fiber-optic sensing data analysis.

**架构状态**: 2026-11-16重构完成，采用模块化分层架构。详见`ARCHITECTURE.md`。

**架构状态**: 2026-11-16重构完成，采用模块化分层架构。详见`ARCHITECTURE.md`。

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment (if not exists)
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
# .venv\Scripts\activate.bat    # Windows cmd
# source .venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt
pip install PyInstaller  # For building executables
```

### Running the Application
```bash
python main.py
```

### Building Executables
```bash
# Windows (must run on Windows)
python build_windows.py

# macOS (must run on macOS)
python build_macos.py
# Optional: specify architecture
python build_macos.py --target-architecture universal2
```

Build outputs go to `dist/v{version}/` (Windows) or `dist/macos/` (macOS).

### Testing
```bash
# Validate Python syntax across the codebase
python -m compileall core ui services vendor utils

# Check dependency integrity
pip check
```

## Architecture (重构后)

### 新目录结构

```
das/
├── core/                   # 核心业务逻辑层（与UI无关）
│   ├── data/              # BIN文件读取、数据分组、时间轴
│   ├── filter/            # 二维滤波、管道重放、历史管理
│   ├── analysis/          # 频谱、小波、EMD、特征提取
│   ├── video/             # 视频标注、媒体处理、轨迹分析
│   ├── tracking/          # 车辆追踪、轨迹筛选、速度标尺
│   └── export/            # DASPy格式导出
│
├── ui/                    # 用户界面层
│   ├── main_window.py     # 主窗口框架（7252行，暂未拆分）
│   ├── dialogs/           # 功能对话框
│   ├── widgets/           # 自定义控件
│   ├── tabs/              # Tab页面（预留，未来拆分）
│   └── components/        # UI组件（预留）
│
├── services/              # 应用服务层
│   └── preferences.py     # 用户设置持久化
│
├── utils/                 # 通用工具
│   ├── function.py        # 通用函数
│   ├── theme.py           # 主题样式
│   ├── plot.py            # 绘图辅助
│   └── version.py         # 版本信息
│
├── vendor/                # 第三方代码
│   └── das_veh/           # DAS车辆追踪算法
│
└── image/                 # 图像资源
```

### Data Flow (保持不变)

1. **Import Layer** (`core/data/bin_reader.py`):
   - Reads proprietary BIN format with 20-float header
   - Auto-detects endianness (little/big) via date field validation
   - Returns data as `(channels, samples)` numpy arrays
   - Supports full file loading (`bin2numpy`) and windowed reading (`bin_window`)

2. **Data Management**:
   - `DataGroup` (`core/data/data_group.py`): Stitches multiple BIN files into continuous timelines with memory budget management
   - `DataTimeline` (`core/data/data_timeline.py`): Manages temporal metadata and file-to-time mapping
   - `raw_data`: Immutable baseline kept separate from filtered results

3. **Filter Pipeline** (`core/filter/das_filter.py`, `core/filter/filter_pipeline.py`):
   - Edit/apply separation: modifying steps does NOT auto-compute
   - `FilterStep`: Immutable operation with algorithm, parameters, selection rectangle, enabled flag
   - `FilterPipeline`: Ordered collection that replays from `raw_data` on "Apply"
   - Supports per-segment and continuous stitching modes
   - History management: recent entries + named presets stored in preferences

4. **Visualization** (`ui/main_window.py`, `utils/plot.py`):
   - PyQtGraph for real-time DAS waterfall plots
   - Matplotlib for frequency/wavelet analysis
   - Custom file segment bar for navigating stitched datasets
   - Video synchronization with trajectory overlay

5. **Video Integration** (`core/video/*.py`):
   - `AnnotationProject`: Sidecar JSON workflow, never modifies DAS data
   - Dual playback backends: Qt multimedia (default) and FFmpeg fallback
   - Trajectory analysis: correlates DAS events with video timeline
   - Speed ruler: measure projected speeds from DAS waterfall ROI

### Key Classes (重构后路径)

- **MainWindow** (`ui/main_window.py`): 7252行主窗口，管理所有UI状态和协调（未来将拆分）
- **DASFilterDialog** (`core/filter/das_filter.py`): 二维滤波UI（带通、陷波、中值、FK、MAD归一化）
- **VehicleTrackingDialog** (`ui/dialogs/vehicle_tracking_dialog.py`): 车辆追踪参数配置
- **BinaryImageHandler** (`core/analysis/binary_image.py`): 阈值二值化（Otsu、双峰法）
- **EMDHandler** (`core/analysis/emd.py`): 经验模态分解
- **DWTHandler, CWTHandler** (`core/analysis/wavelet.py`): 小波变换
- **DWPTHandler** (`core/analysis/wavelet_packet.py`): 小波包分解
- **SpectrumHandler** (`core/analysis/spectrum.py`): FFT频谱分析
- **SNRCalculator** (`core/analysis/snr.py`): 信噪比计算
- **FeatureCalculator** (`core/analysis/feature.py`): 特征提取
- **DASPyConverterDialog** (`ui/dialogs/daspy_converter_dialog.py`): DASPy格式导出

### File Organization (重构后)

```
core/                      # 核心业务逻辑
  data/
    bin_reader.py          # BIN格式I/O
    data_group.py          # 多文件拼接
    data_timeline.py       # 时间轴管理
  filter/
    das_filter.py          # 滤波算法和UI
    filter_pipeline.py     # 不可变管道重放
    filter_history.py      # 历史管理
  analysis/                # 信号分析工具
  video/                   # 视频处理
  tracking/                # 车辆追踪
  export/                  # 数据导出

ui/                        # 用户界面
  main_window.py           # 主窗口（暂未拆分）
  dialogs/                 # 功能对话框
  widgets/                 # 自定义控件
  
services/                  # 应用服务
  preferences.py           # 用户设置
  
utils/                     # 通用工具
  function.py              # 工具函数
  theme.py                 # 应用样式
  plot.py                  # 绘图辅助
  version.py               # 版本信息
  
vendor/                    # 第三方代码
  das_veh/                 # 车辆追踪算法
```

## Development Notes

### Version Management
- Version is defined ONCE in `utils/version.py` as `__version__`
- Build scripts import and embed this in executable names
- Update only that file when releasing

### BIN File Format
- 80-byte header: 20 × float32
  - `[0:6]`: year, month, day, hour, minute, second (used for endianness detection)
  - `[7]`: frame count (samples)
  - `[8]`: channel count
  - `[9]`: sampling rate (Hz)
- Data body: `channels × samples` float32 values, channel-major layout
- Cross-validation: file size must match `80 + (channels × samples × 4)` bytes

### Filter Pipeline Semantics (v2.1.15+)
- Editing steps (add/remove/enable/disable/reorder) only updates pending configuration
- "Apply Filter" is the sole execution trigger, replays ALL enabled steps from `raw_data`
- "Restore Original Data" reverts display without clearing pipeline
- No auto-apply on load/edit to prevent unintended computation
- Pipeline state stored in preferences, survives sessions

### Video Synchronization
- Video work uses separate data structures, never mutates main DAS workspace
- Annotations stored as JSON sidecar, not embedded in BIN files
- Trajectory analysis runs in background ThreadPoolExecutor
- Window-based loading for long recordings to avoid full-file memory load

### Memory Management
- `ensure_memory_budget()` tracks stitched dataset size
- Video sequence decimation for >60K samples display
- Windowed BIN reading (`bin_window`) for trajectory analysis avoids loading entire files

### Theme System
- Unified styling in `utils/theme.py`
- Applies to menus, tabs, group boxes, buttons, status labels
- Font configuration shared between PyQt5 and Matplotlib
- Windows/macOS platform-specific font fallbacks

### Testing Strategy
- Focused regression tests in `test/` directory (not full unit test suite)
- Each test file validates specific subsystem: filter pipeline, timeline, speed ruler, etc.
- Run before release to catch semantic regressions
- `compileall` and `pip check` for basic integrity

## Common Patterns (重构后)

### Reading DAS Data
```python
from core.data.bin_reader import bin2numpy, read_bin_header, bin_window

# Full file
data = bin2numpy("path.bin", ch1=0, ch2=None)  # (channels, samples)

# Header only
header, sampling_times, channels_num, sampling_rate, endian = read_bin_header("path.bin")

# Windowed (for large files)
window = bin_window("path.bin", sample_start=1000, sample_end=2000, ch1=0, ch2=100)
```

### Working with Filter Pipeline
```python
from core.filter.filter_pipeline import FilterStep, FilterPipeline, replay_filter_pipeline

# Create step
step = FilterStep(
    algorithm="butterworth_bandpass",
    parameters={"lowcut": 1.0, "highcut": 50.0, "order": 4},
    selection=(1, 100, 1, 5000),  # (ch_from, ch_to, sample_from, sample_to)
    label="1-50Hz bandpass",
    enabled=True,
    processing_mode="continuous"
)

# Replay pipeline
from core.filter.das_filter import apply_das_filter
result = replay_filter_pipeline(raw_data, steps, sampling_rate, apply_das_filter)
```

### DASPy Export
```python
from core.export.daspy_conversion import convert_bin_to_daspy, read_bin_metadata

metadata = read_bin_metadata("input.bin")
convert_bin_to_daspy(
    metadata=metadata,
    output_path="output.pkl",
    format_name="pkl",
    dx=4.0  # channel spacing in meters
)
```

## Language

The codebase is primarily in Chinese:
- UI labels, error messages, and comments use Chinese
- Code structure and logic follow English naming conventions
- Documentation files (DEVELOPMENT_PROGRESS_*.md) are in Chinese
- Maintain this bilingual pattern when adding features
