# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DASViewer is a PyQt5-based application for viewing and processing Distributed Acoustic Sensing (DAS) signals. It handles proprietary BIN format files with a 20-float (80-byte) header, provides real-time visualization, filtering, and video synchronization for fiber-optic sensing data analysis.

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
# Run all test checks
python test/filter_pipeline_check.py
python test/timeline_check.py
python test/speed_ruler_check.py
python test/mad_normalization_check.py
python test/daspy_conversion_check.py
python test/video_annotation_check.py
python test/video_pipeline_check.py

# Validate Python syntax across the codebase
python -m compileall .

# Check dependency integrity
pip check
```

## Architecture

### Data Flow

1. **Import Layer** (`utils/bin_reader.py`):
   - Reads proprietary BIN format with 20-float header
   - Auto-detects endianness (little/big) via date field validation
   - Returns data as `(channels, samples)` numpy arrays
   - Supports full file loading (`bin2numpy`) and windowed reading (`bin_window`)

2. **Data Management**:
   - `DataGroup` (`utils/classes/data_group.py`): Stitches multiple BIN files into continuous timelines with memory budget management
   - `DataTimeline` (`utils/classes/data_timeline.py`): Manages temporal metadata and file-to-time mapping
   - `raw_data`: Immutable baseline kept separate from filtered results

3. **Filter Pipeline** (`utils/classes/das_filter.py`, `filter_pipeline.py`):
   - Edit/apply separation: modifying steps does NOT auto-compute
   - `FilterStep`: Immutable operation with algorithm, parameters, selection rectangle, enabled flag
   - `FilterPipeline`: Ordered collection that replays from `raw_data` on "Apply"
   - Supports per-segment and continuous stitching modes
   - History management: recent entries + named presets stored in preferences

4. **Visualization** (`utils/mainwindow.py`, `utils/plot.py`):
   - PyQtGraph for real-time DAS waterfall plots
   - Matplotlib for frequency/wavelet analysis
   - Custom file segment bar for navigating stitched datasets
   - Video synchronization with trajectory overlay

5. **Video Integration** (`utils/classes/video_*.py`):
   - `AnnotationProject`: Sidecar JSON workflow, never modifies DAS data
   - Dual playback backends: Qt multimedia (default) and FFmpeg fallback
   - Trajectory analysis: correlates DAS events with video timeline
   - Speed ruler: measure projected speeds from DAS waterfall ROI

### Key Classes

- **MainWindow** (`utils/mainwindow.py`): 7000+ line monolithic Qt window managing all UI state and coordination
- **BinaryImageHandler**: Threshold-based binarization (Otsu, two-peaks methods)
- **DASFilterDialog**: Two-dimensional filtering UI (bandpass, notch, median, FK, MAD normalization)
- **VehicleTrackingDialog**: Cross-correlation vehicle trajectory detection
- **EMDHandler**, **DWTHandler**, **CWTHandler**, **DWPTHandler**: Signal decomposition tools
- **SpectrumHandler**: FFT analysis
- **SNRCalculator**: Signal-to-noise ratio computation
- **FeatureCalculator**: Energy/variance/zero-crossing feature extraction
- **DASPyConverterDialog**: Export BIN → DASPy formats (PKL, HDF5, SEG-Y)

### File Organization

```
utils/
  mainwindow.py          # Primary application window (all tabs, menus, state)
  bin_reader.py          # BIN format I/O with header validation
  widget.py              # Custom PyQt5 widgets
  theme.py               # Application styling and dark mode support
  plot.py                # Matplotlib/PyQtGraph plot helpers
  function.py            # Utility functions
  preferences.py         # User settings persistence
  version.py             # Single source of truth for __version__
  classes/               # Domain logic modules
    das_filter.py        # 2D filter algorithms and UI
    filter_pipeline.py   # Immutable filter history replay
    filter_history.py    # Preset management
    data_group.py        # Multi-file stitching
    data_timeline.py     # Temporal coordinate system
    video_annotation.py  # Video/DAS alignment
    video_media.py       # Format conversion and playback prep
    ffmpeg_video_player.py  # FFmpeg fallback player
    video_trajectory.py  # Background trajectory analysis
    vehicle_tracking.py  # Cross-correlation detector
    speed_ruler.py       # Speed measurement from ROI
    daspy_conversion.py  # BIN → DASPy export logic
    [wavelet/emd/spectrum/snr/feature].py  # Analysis tools
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

## Common Patterns

### Reading DAS Data
```python
from utils.bin_reader import bin2numpy, read_bin_header

# Full file
data = bin2numpy("path.bin", ch1=0, ch2=None)  # (channels, samples)

# Header only
header, sampling_times, channels_num, sampling_rate, endian = read_bin_header("path.bin")

# Windowed (for large files)
from utils.bin_reader import bin_window
window = bin_window("path.bin", sample_start=1000, sample_end=2000, ch1=0, ch2=100)
```

### Working with Filter Pipeline
```python
from utils.classes.filter_pipeline import FilterStep, FilterPipeline

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
from utils.classes.filter_pipeline import replay_filter_pipeline
result = replay_filter_pipeline(raw_data, steps, sampling_rate, algorithm_registry)
```

### DASPy Export
```python
from utils.classes.daspy_conversion import convert_bin_to_daspy, read_bin_metadata

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
