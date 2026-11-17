"""二维 DAS 滤波算法（无 Qt 依赖）。

数据形状固定为 ``(通道, 采样点)``。入口只有 :func:`apply_das_filter`：
按算法名分发到下面各个小函数，最后统一检查输出形状和数值。
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
from daspy.advanced_tools import fk_filter
from daspy.advanced_tools.denoising import common_mode_noise_removal, spike_removal
from daspy.basic_tools.filter import bandpass, bandstop, highpass, lowpass
from scipy.ndimage import median_filter

ALGORITHM_LABELS = (
    ("bandpass", "带通滤波"),
    ("lowpass", "低通滤波"),
    ("highpass", "高通滤波"),
    ("bandstop", "带阻滤波 / 工频抑制"),
    ("fk", "F-K 扇形滤波"),
    ("spike", "尖峰噪声去除"),
    ("common_mode", "共模噪声去除"),
    ("mad_normalize", "各通道 MAD 归一化"),
)

# DASPy 的方向标志排除指定符号；这里取反，让界面文字符合物理含义。
_FK_DIRECTION_FLAGS = {"both": 0, "positive": -1, "negative": 1}


def _check_frequencies(sampling_rate: float, low: float, high: Optional[float] = None) -> None:
    nyquist = float(sampling_rate) / 2.0
    if low <= 0 or low >= nyquist:
        raise ValueError(f"频率必须大于 0 且小于 Nyquist 频率 {nyquist:g} Hz")
    if high is not None and (high <= low or high >= nyquist):
        raise ValueError(f"高频必须大于低频且小于 Nyquist 频率 {nyquist:g} Hz")


def _band(data, sampling_rate, algorithm, p):
    low, high = float(p["frequency_low"]), float(p["frequency_high"])
    _check_frequencies(sampling_rate, low, high)
    function = bandpass if algorithm == "bandpass" else bandstop
    return function(
        data,
        fs=float(sampling_rate),
        freqmin=low,
        freqmax=high,
        corners=int(p["order"]),
        zerophase=bool(p["zero_phase"]),
    )


def _cutoff(data, sampling_rate, algorithm, p):
    frequency = float(p["frequency"])
    _check_frequencies(sampling_rate, frequency)
    function = lowpass if algorithm == "lowpass" else highpass
    return function(
        data,
        fs=float(sampling_rate),
        freq=frequency,
        corners=int(p["order"]),
        zerophase=bool(p["zero_phase"]),
    )


def _fk(data, sampling_rate, _algorithm, p):
    dx = float(p["channel_spacing"])
    if dx <= 0:
        raise ValueError("F-K 滤波需要大于 0 的相邻通道距离 dx（米）")
    mode = str(p["fk_mode"])
    if mode not in {"retain", "remove"}:
        raise ValueError("F-K 模式只能是保留扇形或去除扇形")
    direction = str(p["fk_direction"])
    if direction not in _FK_DIRECTION_FLAGS:
        raise ValueError("F-K 传播方向无效")

    def limit(name: str) -> Optional[float]:
        value = float(p[name])
        return value if value > 0 else None  # 0 表示不限制

    fmin, fmax = limit("fk_frequency_low"), limit("fk_frequency_high")
    vmin, vmax = limit("fk_velocity_low"), limit("fk_velocity_high")
    nyquist = float(sampling_rate) / 2.0
    if fmin is not None and fmin >= nyquist:
        raise ValueError("F-K 频率下限必须小于 Nyquist 频率")
    if fmax is not None and fmax >= nyquist:
        raise ValueError("F-K 频率上限必须小于 Nyquist 频率")
    if fmin is not None and fmax is not None and fmin >= fmax:
        raise ValueError("F-K 频率下限必须小于频率上限")
    if vmin is not None and vmax is not None and vmin >= vmax:
        raise ValueError("F-K 表观速度下限必须小于速度上限")
    if direction == "both" and all(value is None for value in (fmin, fmax, vmin, vmax)):
        raise ValueError("请至少设置一个 F-K 频率/速度限制或传播方向")

    return fk_filter(
        data,
        dx=dx,
        fs=float(sampling_rate),
        taper=(0.02, 0.05),
        pad="default",
        mode=mode,
        fmin=fmin,
        fmax=fmax,
        vmin=vmin,
        vmax=vmax,
        edge=0.1,
        flag=_FK_DIRECTION_FLAGS[direction],
    )


def _spike_fallback(data, channel_window, sample_window, threshold):
    """DASPy 在某一采样点所有通道都被判为离群时会抛错，此时改用本地实现。"""
    absolute = np.abs(data)
    medians = median_filter(absolute, size=(channel_window, 1), mode="nearest")
    medians = median_filter(medians, size=(1, sample_window), mode="nearest")
    bad = (medians > 0) & (absolute / np.maximum(medians, np.finfo(float).eps) > threshold)
    result = data.copy()
    # 沿通道方向插值，保留时间采样。
    for sample in np.flatnonzero(np.any(bad, axis=0)):
        good = ~bad[:, sample]
        if np.count_nonzero(good) == 0:
            continue
        result[~good, sample] = np.interp(
            np.flatnonzero(~good), np.flatnonzero(good), data[good, sample]
        )
    return result


def _spike(data, _sampling_rate, _algorithm, p):
    channel_window = max(1, int(p["channel_window"]))
    sample_window = max(1, int(p["sample_window"]))
    threshold = float(p["threshold"])
    try:
        return spike_removal(data, nch=channel_window, nsp=sample_window, thresh=threshold)
    except ValueError as error:
        if "all channels are outliers" not in str(error):
            raise
        return _spike_fallback(data, channel_window, sample_window, threshold)


def _common_mode(data, _sampling_rate, _algorithm, p):
    method = str(p["method"])
    if method not in {"median", "mean"}:
        raise ValueError("共模噪声方法只能是 median 或 mean")
    common = np.median(data, axis=0) if method == "median" else np.mean(data, axis=0)
    # DASPy 不防护共模能量为 0；没有共模分量时原样返回。
    if float(np.sum(common.astype(np.float64) ** 2)) <= np.finfo(float).eps:
        return data.copy()
    return common_mode_noise_removal(data, method=method)


def _mad_normalize(data, _sampling_rate, _algorithm, _p):
    """每个通道独立计算稳健 z 分数。"""
    if not np.all(np.isfinite(data)):
        raise ValueError("MAD 归一化输入不能包含 NaN 或无穷值")
    values = np.asarray(data, dtype=np.float64)  # float32 数据用 float64 中间量更稳
    medians = np.median(values, axis=1, keepdims=True)
    mad = np.median(np.abs(values - medians), axis=1, keepdims=True)
    # 无波动的通道没有定义的尺度，输出全零而不是 NaN。
    normalized = np.zeros_like(values)
    amplitudes = np.max(np.abs(values), axis=1, keepdims=True)
    tolerance = np.finfo(np.float64).eps * np.maximum(amplitudes, np.finfo(np.float64).tiny)
    np.divide(values - medians, 1.4826 * mad, out=normalized, where=mad > tolerance)
    return normalized.astype(np.float32)


_DISPATCH = {
    "bandpass": _band,
    "bandstop": _band,
    "lowpass": _cutoff,
    "highpass": _cutoff,
    "fk": _fk,
    "spike": _spike,
    "common_mode": _common_mode,
    "mad_normalize": _mad_normalize,
}


def apply_das_filter(
    data: np.ndarray,
    sampling_rate: float,
    algorithm: str,
    parameters: Dict[str, object],
) -> np.ndarray:
    """对二维数组执行一种滤波，返回同形状的 float32 结果。"""

    array = np.asarray(data, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError("DAS 数据必须是二维数组（通道 × 采样点）")
    if array.shape[0] == 0 or array.shape[1] == 0:
        raise ValueError("选择的滤波范围为空")
    if algorithm not in _DISPATCH:
        raise ValueError(f"不支持的滤波算法: {algorithm}")

    result = np.asarray(_DISPATCH[algorithm](array, sampling_rate, algorithm, parameters), dtype=np.float32)
    if result.shape != array.shape:
        raise ValueError("滤波器改变了数据形状，已拒绝应用结果")
    if not np.all(np.isfinite(result)):
        raise ValueError("滤波结果包含 NaN 或无穷值")
    return result
