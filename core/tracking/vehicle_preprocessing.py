"""Shared vehicle-response processing on the original channel/sample grid."""

import numpy as np

from core.filter.das_filter import apply_das_filter
from core.data.data_group import ensure_memory_budget


def preprocess_vehicle_response(data, sampling_rate, parameters=None, *,
                                check_cancel=None, progress=None):
    """Order-4 zero-phase bandpass -> median common mode -> per-channel MAD.

    Use the same filters as the grayscale viewer. Channel blocks only bound
    filter temporaries; common mode is estimated across the entire selection.
    No bad-channel interpolation, smoothing, or resampling is applied.
    """
    options = parameters or {}
    fs = float(sampling_rate)
    low = float(options.get('frequency_low', 0.01))
    high = float(options.get('frequency_high', 1.0))
    if not np.isfinite(fs) or not 0 < low < high < fs / 2:
        raise ValueError('滤波频率需满足 0 < 低频 < 高频 < 原始采样率的一半')
    source = np.asarray(data)
    if source.ndim != 2 or min(source.shape) == 0:
        raise ValueError('车辆响应处理需要非空二维 DAS 数据')
    check = check_cancel or (lambda: None)
    report = progress or (lambda percent, message: None)
    check()
    filtered = np.empty(source.shape, dtype=np.float32)
    for first in range(0, len(source), 8):
        check()
        block = source[first:first + 8]
        if not np.isfinite(block).all():
            raise ValueError('DAS 数据含有 NaN 或无穷值，无法跟踪')
        filtered[first:first + 8] = apply_das_filter(block, fs, 'bandpass', {
            'frequency_low': low, 'frequency_high': high,
            'order': 4, 'zero_phase': True,
        })
        report(15 + int(12 * min(first + 8, len(source)) / len(source)),
               f'{fs:g} Hz 原始采样率：4 阶零相位带通')
    check()
    filtered = apply_das_filter(filtered, fs, 'common_mode', {'method': 'median'})
    report(30, '中位数共模噪声抑制')
    for first in range(0, len(filtered), 8):
        check()
        filtered[first:first + 8] = apply_das_filter(
            filtered[first:first + 8], fs, 'mad_normalize', {})
    check()
    report(35, '各通道 MAD 归一化完成（不降采样）')
    return filtered


def read_vehicle_response(group, raw_data, visible_start, visible_end,
                          channel_from, channel_to, parameters, *,
                          check_cancel=None, progress=None):
    """Read original samples plus filter context, retaining global origins."""
    from core.video.trajectory import read_group_window

    fs = float(group.sampling_rate)
    low = float(parameters.get('frequency_low', 0.01))
    high = float(parameters.get('frequency_high', 1.0))
    if not np.isfinite(fs) or not 0 < low < high < fs / 2:
        raise ValueError('滤波频率需满足 0 < 低频 < 高频 < 原始采样率的一半')
    if channel_from < 1 or channel_to > group.channel_count or channel_to - channel_from + 1 < 8:
        raise ValueError('检测范围至少需要 8 个有效通道，且不能超出来源通道范围')
    if not 0 <= visible_start < visible_end <= group.total_samples:
        raise ValueError('检测时间范围无效')
    if raw_data is not None and raw_data.shape != (group.channel_count, group.total_samples):
        raise ValueError('原始数据与 DAS 来源范围不一致，请重新载入数据')
    padding = int(np.ceil(fs / low))
    start = max(0, int(visible_start) - padding)
    end = min(group.total_samples, int(visible_end) + padding)
    if (end - start) / fs < 2 / low:
        raise ValueError(f'当前来源不足 {2 / low:g} 秒，无法稳定使用 {low:g} Hz；不会自动改变滤波频段')
    notes = []
    if start > visible_start - padding or end < visible_end + padding:
        notes.append('来源边界限制了滤波补充数据，请复查窗口两端候选')
    rows, samples = channel_to - channel_from + 1, end - start
    ensure_memory_budget(rows, samples, 8.0, '全采样率车辆响应处理')
    check = check_cancel or (lambda: None)
    report = progress or (lambda percent, message: None)
    check()
    data = np.empty((rows, samples), dtype=np.float32)
    for first in range(channel_from, channel_to + 1, 8):
        check()
        last = min(first + 7, channel_to)
        block = (read_group_window(group, start, end, first, last) if raw_data is None else
                 raw_data[first - 1:last, start:end])
        data[first - channel_from:last - channel_from + 1] = block
        report(int(15 * (last - channel_from + 1) / rows), '读取原始 DAS 采样点')
    data = preprocess_vehicle_response(data, fs, parameters, check_cancel=check, progress=report)
    return data, start, tuple(notes)
