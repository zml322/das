"""Windowed, read-only trajectory analysis for long video/DAS comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from .data_group import DataGroup
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


def analyze_group_window(
    data_group: DataGroup,
    start_sample: int,
    end_sample: int,
    channel_from: int,
    channel_to: int,
    parameters: Dict[str, object],
) -> VideoTrajectoryWindow:
    """Run the established picker on a suitable long read-only window."""

    data = read_group_window(data_group, start_sample, end_sample, channel_from, channel_to)
    # This array is retained solely for the current-window image; the full
    # sequence is never materialised or altered.  The picker repeats the same
    # deterministic preprocessing internally, keeping its established API.
    processed_data, processed_rate, _options = prepare_vehicle_tracking_data(
        data, data_group.sampling_rate, parameters
    )
    trajectories = pick_vehicle_trajectories(
        data,
        data_group.sampling_rate,
        parameters,
        channel_start=channel_from,
        time_start=start_sample / data_group.sampling_rate,
    )
    return VideoTrajectoryWindow(
        int(start_sample), int(end_sample), int(channel_from), int(channel_to),
        tuple(trajectories), processed_data, float(processed_rate),
    )
