"""Read a channel/time rectangle across stitched BIN file boundaries."""

from typing import List

import numpy as np

from core.data.bin_reader import bin_window
from core.data.data_group import DataGroup


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
