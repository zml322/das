"""Windowed, read-only trajectory analysis for long video/DAS comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from scipy import signal

from .data_group import DataGroup, ensure_memory_budget
from .das_filter import apply_das_filter
from .vehicle_tracking import (
    VehicleTrajectory,
    pick_vehicle_trajectories,
    prepare_vehicle_tracking_data,
)
from ..bin_reader import bin_window


@dataclass(frozen=True)
class VideoTrajectoryWindow:
    """A completed or requested long-recording analysis window."""

    start_sample: int
    end_sample: int
    channel_from: int
    channel_to: int
    trajectories: Tuple[VehicleTrajectory, ...]
    processed_data: np.ndarray
    processed_sampling_rate: float

    @property
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample


def required_window_seconds(parameters: Dict[str, object], requested_seconds: float) -> float:
    """Honor the two-period low-frequency rule used by the picker itself."""

    try:
        low = float(parameters.get("frequency_low", 0.01))
    except (TypeError, ValueError):
        low = 0.01
    if not np.isfinite(low) or low <= 0:
        raise ValueError("轨迹低频下限必须是正数")
    return max(float(requested_seconds), 2.0 / low)


def read_group_window(
    data_group: DataGroup,
    start_sample: int,
    end_sample: int,
    channel_from: int,
    channel_to: int,
) -> np.ndarray:
    """Read one global window across BIN boundaries without loading full BINs."""

    start = max(0, int(start_sample))
    end = min(int(end_sample), data_group.total_samples)
    channel_from = max(1, int(channel_from))
    channel_to = min(int(channel_to), data_group.channel_count)
    if end <= start or channel_from > channel_to:
        raise ValueError("连续 DAS 窗口或通道范围无效")
    chunks: List[np.ndarray] = []
    for segment in data_group.segments:
        local_start = max(start, segment.start_sample)
        local_end = min(end, segment.end_sample)
        if local_end <= local_start:
            continue
        chunks.append(
            bin_window(
                segment.path,
                local_start - segment.start_sample,
                local_end - segment.start_sample,
                channel_from - 1,
                channel_to,
            )
        )
    if not chunks:
        raise ValueError("没有与连续 DAS 窗口重叠的 BIN 文件")
    result = np.concatenate(chunks, axis=1)
    expected = end - start
    if result.shape != (channel_to - channel_from + 1, expected):
        raise ValueError("跨文件窗口读取不连续；不会把不完整数据当作无车")
    return result


def _process_display_data(
    data: np.ndarray,
    sampling_rate: float,
    parameters: Dict[str, object],
) -> tuple[np.ndarray, float]:
    """Apply the selected read-only video/DAS display pipeline."""

    mode = str(parameters.get("display_mode", "vehicle"))
    if mode == "raw":
        full_resolution = np.asarray(data, dtype=np.float32)
        return (
            np.asarray(signal.detrend(full_resolution, axis=1), dtype=np.float32),
            float(sampling_rate),
        )

    if mode == "current":
        working = np.asarray(data, dtype=np.float32)
        steps = tuple(parameters.get("display_filter_steps", ()))
        if not any(bool(step.get("enabled", True)) for step in steps):
            return (
                np.asarray(signal.detrend(working, axis=1), dtype=np.float32),
                float(sampling_rate),
            )
        working = working.copy()
        window_channel_from = int(parameters.get("window_channel_from", 1))
        window_channel_to = window_channel_from + working.shape[0] - 1
        for step in steps:
            if not bool(step.get("enabled", True)):
                continue
            selection = tuple(step.get("selection", (window_channel_from, window_channel_to, 1, working.shape[1])))
            if len(selection) != 4:
                raise ValueError("视频显示滤波步骤范围无效")
            selected_from, selected_to = sorted((int(selection[0]), int(selection[1])))
            selected_from = max(window_channel_from, selected_from)
            selected_to = min(window_channel_to, selected_to)
            if selected_from > selected_to:
                continue
            local_from = selected_from - window_channel_from
            local_to = selected_to - window_channel_from + 1
            source = working[local_from:local_to]
            filtered = apply_das_filter(
                source,
                float(sampling_rate),
                str(step["algorithm"]),
                dict(step.get("parameters", {})),
            )
            filtered = np.asarray(filtered, dtype=np.float32)
            if filtered.shape != source.shape:
                raise ValueError("视频显示滤波改变了窗口形状")
            working[local_from:local_to] = filtered
        return working, float(sampling_rate)

    if mode == "vibration":
        nyquist = float(sampling_rate) / 2.0
        high = min(50.0, nyquist * 0.9)
        low = min(5.0, high * 0.5)
        filtered = apply_das_filter(
            np.asarray(data, dtype=np.float32),
            float(sampling_rate),
            "bandpass",
            {
                "frequency_low": low,
                "frequency_high": min(high, float(sampling_rate) / 2.0 * 0.9),
                "order": 4,
                "zero_phase": True,
            },
        )
        return (
            apply_das_filter(filtered, float(sampling_rate), "mad_normalize", {}),
            float(sampling_rate),
        )

    # Preserve every acquired sample in the displayed vehicle-response image.
    # Trajectory detection has its own internal resampling path and must not
    # reduce the resolution of the user-facing DAS data.
    low = float(parameters.get("frequency_low", 0.01))
    high = float(parameters.get("frequency_high", 1.0))
    filtered = apply_das_filter(
        np.asarray(data, dtype=np.float32),
        float(sampling_rate),
        "bandpass",
        {
            "frequency_low": low,
            "frequency_high": min(high, float(sampling_rate) / 2.0 * 0.9),
            "order": 4,
            "zero_phase": True,
        },
    )
    if filtered.shape[0] >= 2:
        filtered = apply_das_filter(
            filtered,
            float(sampling_rate),
            "common_mode",
            {"method": str(parameters.get("common_mode_method", "median"))},
        )
    return (
        apply_das_filter(filtered, float(sampling_rate), "mad_normalize", {}),
        float(sampling_rate),
    )


def analyze_group_window(
    data_group: DataGroup,
    start_sample: int,
    end_sample: int,
    channel_from: int,
    channel_to: int,
    parameters: Dict[str, object],
) -> VideoTrajectoryWindow:
    """Run the established picker on a suitable long read-only window."""

    ensure_memory_budget(
        channel_to - channel_from + 1,
        end_sample - start_sample,
        4.0,
        "视频 DAS 窗口处理",
    )
    data = read_group_window(data_group, start_sample, end_sample, channel_from, channel_to)
    processed_data, processed_rate = _process_display_data(
        data, data_group.sampling_rate, parameters
    )
    trajectories: Tuple[VehicleTrajectory, ...] = ()
    if bool(parameters.get("detect_trajectories", True)):
        # Keep detection on the established low-frequency pipeline.  In the
        # default vehicle display mode this is the same signal family shown to
        # the user; other display modes remain useful for visual comparison.
        _tracking_data, _tracking_rate, _options = prepare_vehicle_tracking_data(
            data, data_group.sampling_rate, parameters
        )
        trajectories = tuple(pick_vehicle_trajectories(
            data,
            data_group.sampling_rate,
            parameters,
            channel_start=channel_from,
            time_start=start_sample / data_group.sampling_rate,
        ))
    return VideoTrajectoryWindow(
        int(start_sample), int(end_sample), int(channel_from), int(channel_to),
        trajectories, processed_data, float(processed_rate),
    )
