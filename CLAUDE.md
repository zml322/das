# DASViewer development guide

## Current scope

DASViewer is a PyQt5 application for BIN-based Distributed Acoustic Sensing data, two-dimensional filtering, vehicle analysis and standalone video playback. UI labels and error messages use Chinese; Python names use English.

DAT/scouter support, generic data export, BIN-to-DASPy conversion, feature statistics, standalone spectrum analysis, SNR, EMD, standalone IIR design and wavelet analysis have been removed. Video tagging, annotation projects/CSV, DAS matching, clock synchronization and video-side trajectory analysis have also been removed. Single-channel amplitude plots and two-dimensional filter algorithms remain supported.

## Commands

```powershell
.venv/Scripts/python.exe main.py
.venv/Scripts/python.exe -m compileall -q core ui services vendor utils
.venv/Scripts/python.exe -m ruff check ui/main_window.py ui/tabs ui/components --select F,I
.venv/Scripts/python.exe -m pip check
```

Build helpers are in `utils/build_windows.py` and `utils/build_macos.py`. The application version is defined once in `utils/version.py`.

## Architecture

See [ui/README.md](ui/README.md) for the window module map.

- `ui/main_window.py`: composes independent feature controllers and coordinates startup, refreshes and shutdown. It holds controller references and preferences only.
- `ui/components/window_feature.py`: QObject ownership and a typed window reference. Feature state, controls, menus and resource cleanup belong to the corresponding controller. Use explicit paths such as `window.playback.backend` and `window.data.raw_data` across features.
- `ui/components/`: workspace layout, range controls and plot overlays.
- `ui/tabs/`: data, plotting, filtering, vehicle analysis and video playback controllers. Feature modules must not import `MainWindow` at runtime.
- `ui/dialogs/`, `ui/widgets/`: specialized dialogs and controls.
- `core/data/bin_reader.py`: BIN header validation and full/windowed reading.
- `core/data/bin_loader.py`: Qt-independent group validation, stitching, detrending and initial metadata.
- `core/data/data_group.py`, `data_timeline.py`: source segments, memory guard and corrected continuous time mapping.
- `core/filter/`: DAS filtering, pipeline replay and saved history.
- `core/analysis/binary_image.py`: image thresholding.
- `core/tracking/`: vehicle preprocessing, trajectory extraction, prescreening and speed ruler.
- `core/data/window_reader.py`: shared cross-file BIN rectangle reading used by vehicle analysis.
- `core/video/`: media probing/cache and FFmpeg frame worker.
- `services/preferences.py`: persistent user preferences.
- `utils/theme.py`: shared Qt/Matplotlib fonts and application theme.
- `vendor/`: existing third-party vehicle tracking implementation.

## Data contracts

BIN files contain an 80-byte header (20 float32 values). Header `[0:6]` is the recorded end time, `[7]` is sample count, `[8]` is channel count and `[9]` is sampling rate. The payload is channel-major, shaped `(channels, samples)`. Detect byte order and verify payload length before allocating arrays.

Multi-file loading validates all headers and the memory budget first. The loaded group is naturally sorted and detrended. `raw_data` is an immutable baseline; `origin_data` is the working data and `data` is the visible selection. Preserve source segments and sample coordinates across plotting and analysis.

Time axes use corrected, continuously inferred times anchored to the first source file's recorded end time. Video playback is independent of the DAS time axis.

## Filtering and video

Filter edits update a pending pipeline. Explicit application replays enabled steps from the baseline. Preserve the existing history, presets and configured automatic reapplication when changing datasets. Restore operations must keep the original baseline intact.

The video page only loads and plays media. Qt handles ordinary videos; MPEG-PS recordings are converted into an independent cache and decoded through the FFmpeg frame worker. Keep conversion off the GUI thread and leave source videos unchanged. The player must not depend on DAS data or annotation models.

Keep input/format/memory checks, cancellation, worker error handling and Qt resource cleanup. Remove redundant checks only when the initialization order or input contract guarantees the condition.

Regression tests use temporary BIN/media/settings files and offscreen Qt windows; they must not alter real recordings or personal preferences.
