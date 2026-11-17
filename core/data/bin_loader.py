"""BIN-only group loading, kept independent of the window and Qt."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import detrend

from core.data.bin_reader import bin2numpy, read_bin_header
from core.data.data_group import DataGroup, ensure_memory_budget, natural_sort_key
from core.data.data_timeline import DataTimeline, datetime_from_header, format_wall_time


@dataclass
class LoadedBinGroup:
    group: DataGroup
    timeline: DataTimeline
    data: np.ndarray
    time_headers: list[tuple[float, ...]]
    acquisition_params: dict[str, str]


def validate_bin_paths(paths):
    """Reject unsupported files even when passed without the file picker."""
    if not paths:
        raise ValueError("请选择 BIN 数据文件")
    for path in paths:
        if Path(path).suffix.lower() != ".bin":
            raise ValueError(f"{path}: 仅支持 BIN 数据文件")


def load_bin_group(paths, correction_seconds=0.0):
    """Validate all headers before allocating the stitched, detrended array."""
    validate_bin_paths(paths)
    paths = sorted(map(str, paths), key=lambda path: natural_sort_key(Path(path).name))
    metadata = [read_bin_header(path) for path in paths]
    _, _, channels, rate, _ = metadata[0]
    for path, (_, _, file_channels, file_rate, _) in zip(paths, metadata):
        if file_channels != channels or not np.isclose(file_rate, rate):
            raise ValueError(f"{path}: 通道数或采样率与首个文件不一致")
    counts = [entry[1] for entry in metadata]
    ensure_memory_budget(channels, sum(counts), 4.5, "BIN 多文件拼接加载")
    group = DataGroup.from_files(paths, counts, channels, rate)
    headers = [tuple(map(float, entry[0][:6])) for entry in metadata]
    timeline = DataTimeline.from_data_group(group, headers, correction_seconds=correction_seconds)
    arrays = [bin2numpy(path) for path in paths]
    data = detrend(detrend(np.concatenate(arrays, axis=1), axis=1, type="constant"), axis=1)
    params = {
        "文件记录结束时间": f"{format_wall_time(datetime_from_header(headers[0]) or timeline.segments[0].recorded_end)} 至 "
        f"{format_wall_time(datetime_from_header(headers[-1]) or timeline.segments[-1].recorded_end)}",
        "文件格式": ".bin",
        "采样频率": f"{rate:g}Hz",
        "传感点数（通道数）": str(channels),
        "单个文件采样点数": str(counts[0]) if len(set(counts)) == 1 else "、".join(map(str, counts)),
        "总采样点数": str(group.total_samples),
        "拼接文件数": str(len(paths)),
        "拼接顺序": " → ".join(segment.name for segment in group.segments),
        "时间口径": "文件名/文件头为采集结束时间；按采样率连续推算",
        "设备时间修正": f"记录时间 {correction_seconds:+.3f} s",
        "推算实际时间": f"{format_wall_time(timeline.start_time)} 至 {format_wall_time(timeline.end_time)}",
        "时间连续性警告": str(len(timeline.discontinuities)),
    }
    return LoadedBinGroup(group, timeline, np.asarray(data, dtype=np.float32), headers, params)
