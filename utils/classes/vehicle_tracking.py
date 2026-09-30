"""Vehicle-trajectory picking for channel-by-time DAS arrays.

The implementation intentionally keeps the vehicle-picking workflow separate
from filtering.  It consumes a copy of the selected data and returns only
trajectory coordinates, so it can never modify the viewer's working data.

The workflow follows the public ``das_veh`` idea (low-frequency vehicle
response, peak candidates, then Kalman association), but avoids its
site-specific geometry and legacy SciPy dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
from scipy import signal


@dataclass
class VehicleTrajectory:
    """One picked vehicle path in the full imported-data coordinate system."""

    identifier: int
    channels: np.ndarray  # 1-based global channel numbers
    times: np.ndarray  # seconds from the start of the imported data
    coverage: float
    projected_speed: float  # m/s along the fibre; ``nan`` when unavailable
    quality: float
    visible: bool = True

    @property
    def start_time(self) -> float:
        return float(self.times[0])

    @property
    def end_time(self) -> float:
        return float(self.times[-1])

    @property
    def start_channel(self) -> int:
        return int(self.channels[0])

    @property
    def end_channel(self) -> int:
        return int(self.channels[-1])


def _float_parameter(parameters: Dict[str, object], name: str, default: float) -> float:
    try:
        return float(parameters.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _int_parameter(parameters: Dict[str, object], name: str, default: int) -> int:
    try:
        return int(parameters.get(name, default))
    except (TypeError, ValueError):
        return int(default)


def _validate_parameters(
    shape: Tuple[int, int], sampling_rate: float, parameters: Dict[str, object]
) -> Dict[str, object]:
    """Validate and normalize picker options before the worker starts."""

    channel_count, sample_count = shape
    if channel_count < 8:
        raise ValueError("车辆轨迹拾取至少需要 8 个通道")
    if sample_count < 32:
        raise ValueError("车辆轨迹拾取的时间范围过短")
    if not np.isfinite(sampling_rate) or sampling_rate <= 0:
        raise ValueError("采样率无效")

    options: Dict[str, object] = {
        "channel_spacing": _float_parameter(parameters, "channel_spacing", 0.0),
        "frequency_low": _float_parameter(parameters, "frequency_low", 0.01),
        "frequency_high": _float_parameter(parameters, "frequency_high", 1.0),
        "target_sampling_rate": _float_parameter(
            parameters, "target_sampling_rate", 50.0
        ),
        "seed_width": _int_parameter(parameters, "seed_width", 8),
        "peak_prominence": _float_parameter(parameters, "peak_prominence", 1.5),
        "minimum_separation": _float_parameter(
            parameters, "minimum_separation", 0.8
        ),
        "prominence_window": _float_parameter(
            parameters, "prominence_window", 12.0
        ),
        "minimum_speed": _float_parameter(parameters, "minimum_speed", 2.0),
        "maximum_speed": _float_parameter(parameters, "maximum_speed", 60.0),
        "tracking_tolerance": _float_parameter(
            parameters, "tracking_tolerance", 0.15
        ),
        "minimum_coverage": _float_parameter(
            parameters, "minimum_coverage", 0.55
        ),
        "maximum_missed_channels": _int_parameter(
            parameters, "maximum_missed_channels", 3
        ),
        "direction": str(parameters.get("direction", "auto")),
        "polarity": str(parameters.get("polarity", "auto")),
    }

    spacing = float(options["channel_spacing"])
    low = float(options["frequency_low"])
    high = float(options["frequency_high"])
    target = float(options["target_sampling_rate"])
    minimum_speed = float(options["minimum_speed"])
    maximum_speed = float(options["maximum_speed"])
    coverage = float(options["minimum_coverage"])
    nyquist = sampling_rate / 2.0

    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("请填写真实的相邻通道距离 dx（米），不能使用 gauge length")
    if not (0 < low < high < nyquist):
        raise ValueError(f"低频和高频必须满足 0 < 低频 < 高频 < {nyquist:g} Hz")
    if not np.isfinite(target) or target < 2.5 * high:
        raise ValueError("目标采样率至少应为最高跟踪频率的 2.5 倍")
    if minimum_speed <= 0 or maximum_speed <= minimum_speed:
        raise ValueError("投影速度范围无效")
    if not 0 < coverage <= 1:
        raise ValueError("最小有效轨迹覆盖率必须位于 0 到 1 之间")
    if int(options["seed_width"]) < 1 or int(options["seed_width"]) >= channel_count:
        raise ValueError("起始检测通道数必须小于所选通道数")
    if float(options["peak_prominence"]) <= 0:
        raise ValueError("峰突出度必须大于 0")
    if float(options["minimum_separation"]) <= 0:
        raise ValueError("最小车辆间隔必须大于 0")
    if float(options["tracking_tolerance"]) <= 0:
        raise ValueError("跟踪容差必须大于 0")
    if int(options["maximum_missed_channels"]) < 0:
        raise ValueError("允许缺失通道数不能为负")
    if options["direction"] not in {"auto", "increasing", "decreasing"}:
        raise ValueError("车辆方向无效")
    if options["polarity"] not in {"auto", "positive", "negative"}:
        raise ValueError("峰极性无效")

    duration = sample_count / sampling_rate
    recommended_duration = max(5.0, 2.0 / low)
    if duration < recommended_duration:
        raise ValueError(
            f"当前时间范围仅 {duration:g} 秒；{low:g} Hz 低频建议至少使用 "
            f"{recommended_duration:g} 秒。可扩大时间范围或提高低频下限。"
        )
    return options


def _replace_bad_traces(data: np.ndarray) -> np.ndarray:
    """Interpolate empty or exceptionally energetic channels from neighbours."""

    result = np.asarray(data, dtype=np.float64).copy()
    scales = np.median(np.abs(result), axis=1)
    center = float(np.median(scales))
    mad = float(np.median(np.abs(scales - center)))
    spread = max(1.4826 * mad, np.finfo(float).eps)
    bad = (scales <= np.finfo(float).eps) | (scales > center + 6.0 * spread)
    good_indices = np.flatnonzero(~bad)
    if good_indices.size < 2:
        return result

    for index in np.flatnonzero(bad):
        left_candidates = good_indices[good_indices < index]
        right_candidates = good_indices[good_indices > index]
        if left_candidates.size and right_candidates.size:
            left = int(left_candidates[-1])
            right = int(right_candidates[0])
            ratio = (index - left) / (right - left)
            result[index] = (1.0 - ratio) * result[left] + ratio * result[right]
        elif left_candidates.size:
            result[index] = result[int(left_candidates[-1])]
        elif right_candidates.size:
            result[index] = result[int(right_candidates[0])]
    return result


def _robust_trace_normalize(data: np.ndarray) -> np.ndarray:
    centered = data - np.median(data, axis=1, keepdims=True)
    scales = np.median(np.abs(centered), axis=1, keepdims=True) * 1.4826
    scales = np.maximum(scales, np.finfo(float).eps)
    return centered / scales


def _downsample(data: np.ndarray, sampling_rate: float, target_rate: float) -> Tuple[np.ndarray, float]:
    if sampling_rate <= target_rate * 1.05:
        return data, sampling_rate
    fraction = Fraction(target_rate / sampling_rate).limit_denominator(2000)
    reduced = signal.resample_poly(data, fraction.numerator, fraction.denominator, axis=1)
    return reduced, sampling_rate * fraction.numerator / fraction.denominator


def prepare_vehicle_tracking_data(
    data: np.ndarray, sampling_rate: float, parameters: Dict[str, object]
) -> Tuple[np.ndarray, float, Dict[str, object]]:
    """Run the non-mutating preprocessing shared by picker and video view.

    Keeping this stage public lets the long-video workflow display precisely
    the bad-channel-repaired, band-passed, downsampled data on which it bases
    its trajectory candidates.  The caller receives a new array.
    """
    array = np.asarray(data, dtype=np.float64)
    if array.ndim != 2 or min(array.shape) == 0:
        raise ValueError("车辆轨迹拾取需要非空的二维 DAS 数据（通道 × 采样点）")
    options = _validate_parameters(array.shape, float(sampling_rate), parameters)
    if not np.all(np.isfinite(array)):
        raise ValueError("输入数据含有 NaN 或无穷值，无法进行车辆轨迹拾取")
    working = array.copy()
    low = float(options["frequency_low"])
    high = float(options["frequency_high"])
    sos = signal.butter(4, [low, high], btype="bandpass", fs=float(sampling_rate), output="sos")
    # Repair dead/saturated traces before the zero-phase filter.  A bad trace
    # otherwise smears its transient across the long low-frequency window.
    repaired = _replace_bad_traces(working)
    filtered = signal.sosfiltfilt(sos, repaired, axis=1)
    normalized = _robust_trace_normalize(filtered)
    tracking_data, tracking_rate = _downsample(
        normalized, float(sampling_rate), float(options["target_sampling_rate"])
    )
    return tracking_data, tracking_rate, options


def _peaks_for_trace(
    trace: np.ndarray,
    sampling_rate: float,
    prominence: float,
    minimum_separation: float,
    prominence_window: float,
    polarity: str,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return local peak sample indices and their normalized prominences."""

    distance = max(1, int(round(minimum_separation * sampling_rate)))
    window = max(3, int(round(prominence_window * sampling_rate)))
    if window % 2 == 0:
        window += 1
    window = min(window, trace.size - (1 - trace.size % 2))
    kwargs = {"prominence": prominence, "distance": distance}
    if window >= 3:
        kwargs["wlen"] = window

    polarities: Sequence[int]
    if polarity == "positive":
        polarities = (1,)
    elif polarity == "negative":
        polarities = (-1,)
    else:
        polarities = (1, -1)

    locations: List[np.ndarray] = []
    strengths: List[np.ndarray] = []
    for sign in polarities:
        points, metadata = signal.find_peaks(sign * trace, **kwargs)
        if points.size:
            locations.append(points.astype(int, copy=False))
            strengths.append(np.asarray(metadata["prominences"], dtype=float))
    if not locations:
        return np.empty(0, dtype=int), np.empty(0, dtype=float)

    all_locations = np.concatenate(locations)
    all_strengths = np.concatenate(strengths)
    order = np.argsort(all_locations)
    all_locations, all_strengths = all_locations[order], all_strengths[order]

    # Auto polarity can produce two adjacent extrema of the same pulse.  Keep
    # the stronger candidate inside one sample so association remains stable.
    keep_locations: List[int] = []
    keep_strengths: List[float] = []
    for location, strength in zip(all_locations, all_strengths):
        if keep_locations and location - keep_locations[-1] <= 1:
            if strength > keep_strengths[-1]:
                keep_locations[-1] = int(location)
                keep_strengths[-1] = float(strength)
        else:
            keep_locations.append(int(location))
            keep_strengths.append(float(strength))
    return np.asarray(keep_locations, dtype=int), np.asarray(keep_strengths, dtype=float)


def _initial_match(
    peak_locations: Sequence[np.ndarray],
    peak_strengths: Sequence[np.ndarray],
    start_channel: int,
    step: int,
    start_time: float,
    sample_rate: float,
    spacing: float,
    minimum_speed: float,
    maximum_speed: float,
) -> Tuple[int, float, float] | None:
    """Find the first physically plausible next observation for a seed peak."""

    channel = start_channel + step
    while 0 <= channel < len(peak_locations):
        distance = abs(channel - start_channel) * spacing
        low = distance / maximum_speed
        high = distance / minimum_speed
        values = peak_locations[channel] / sample_rate
        valid = (values - start_time >= low) & (values - start_time <= high)
        if np.any(valid):
            candidate_indices = np.flatnonzero(valid)
            strengths = peak_strengths[channel][candidate_indices]
            best = int(candidate_indices[np.argmax(strengths)])
            matched_time = float(values[best])
            return channel, matched_time, float(strengths[np.argmax(strengths)])
        # Do not jump farther than three channels during initialization.  A
        # larger jump makes the initial apparent speed too ambiguous.
        if abs(channel - start_channel) >= 3:
            break
        channel += step
    return None


def _track_from_seed(
    peak_locations: Sequence[np.ndarray],
    peak_strengths: Sequence[np.ndarray],
    start_channel: int,
    start_sample: int,
    start_strength: float,
    step: int,
    sample_rate: float,
    spacing: float,
    minimum_speed: float,
    maximum_speed: float,
    tolerance: float,
    maximum_missed_channels: int,
) -> Tuple[np.ndarray, np.ndarray, float] | None:
    """Associate one trajectory with a two-state (time, slowness) Kalman filter."""

    start_time = start_sample / sample_rate
    initial = _initial_match(
        peak_locations,
        peak_strengths,
        start_channel,
        step,
        start_time,
        sample_rate,
        spacing,
        minimum_speed,
        maximum_speed,
    )
    if initial is None:
        return None
    second_channel, second_time, second_strength = initial
    delta_distance = abs(second_channel - start_channel) * spacing
    slowness = (second_time - start_time) / delta_distance
    if not (1.0 / maximum_speed <= slowness <= 1.0 / minimum_speed):
        return None

    state = np.array([second_time, slowness], dtype=float)
    covariance = np.diag([tolerance**2, (tolerance / max(delta_distance, spacing)) ** 2])
    channels = [start_channel, second_channel]
    times = [start_time, second_time]
    strengths = [start_strength, second_strength]
    previous_channel = second_channel
    missed = 0
    channel = second_channel + step

    while 0 <= channel < len(peak_locations):
        distance = abs(channel - previous_channel) * spacing
        transition = np.array([[1.0, distance], [0.0, 1.0]], dtype=float)
        # A small process variance lets the apparent speed change gradually;
        # the user-facing time tolerance remains the dominant control.
        process = np.diag([(0.25 * tolerance) ** 2, (0.05 * tolerance / max(distance, spacing)) ** 2])
        state = transition @ state
        covariance = transition @ covariance @ transition.T + process
        predicted_time = float(state[0])

        candidate_times = peak_locations[channel] / sample_rate
        candidate_strengths = peak_strengths[channel]
        if candidate_times.size:
            residuals = candidate_times - predicted_time
            allowed = np.abs(residuals) <= tolerance
            indices = np.flatnonzero(allowed)
        else:
            indices = np.empty(0, dtype=int)

        if indices.size:
            residuals = candidate_times[indices] - predicted_time
            # Prefer temporal agreement; use prominence only to break close
            # candidates so a stronger unrelated event cannot hijack a path.
            costs = np.abs(residuals) / tolerance - 0.08 * candidate_strengths[indices]
            chosen = int(indices[np.argmin(costs)])
            observed = float(candidate_times[chosen])
            measurement_variance = tolerance**2
            observation = np.array([1.0, 0.0])
            gain = covariance @ observation / (
                measurement_variance + observation @ covariance @ observation
            )
            state = state + gain * (observed - observation @ state)
            covariance = covariance - np.outer(gain, observation) @ covariance
            channels.append(channel)
            times.append(observed)
            strengths.append(float(candidate_strengths[chosen]))
            previous_channel = channel
            missed = 0
        else:
            missed += 1
            previous_channel = channel
            if missed > maximum_missed_channels:
                break
        channel += step

    if len(channels) < 3:
        return None
    return (
        np.asarray(channels, dtype=int),
        np.asarray(times, dtype=float),
        float(np.mean(strengths)),
    )


def _trajectory_speed(channels: np.ndarray, times: np.ndarray, spacing: float) -> float:
    if channels.size < 2:
        return float("nan")
    x = (channels - channels[0]).astype(float) * spacing
    try:
        slope = float(np.polyfit(x, times, 1)[0])
    except (TypeError, np.linalg.LinAlgError):
        return float("nan")
    return float(1.0 / abs(slope)) if abs(slope) > np.finfo(float).eps else float("nan")


def _is_duplicate(
    candidate_channels: np.ndarray,
    candidate_times: np.ndarray,
    existing: Iterable[VehicleTrajectory],
    duplicate_tolerance: float,
) -> bool:
    for trajectory in existing:
        shared_start = max(int(candidate_channels.min()), int(trajectory.channels.min()))
        shared_end = min(int(candidate_channels.max()), int(trajectory.channels.max()))
        if shared_end - shared_start < 2:
            continue
        shared = np.arange(shared_start, shared_end + 1)
        candidate_order = np.argsort(candidate_channels)
        existing_order = np.argsort(trajectory.channels)
        candidate_time = np.interp(
            shared, candidate_channels[candidate_order], candidate_times[candidate_order]
        )
        existing_time = np.interp(
            shared,
            trajectory.channels[existing_order],
            trajectory.times[existing_order],
        )
        if float(np.median(np.abs(candidate_time - existing_time))) <= duplicate_tolerance:
            return True
    return False


def pick_vehicle_trajectories(
    data: np.ndarray,
    sampling_rate: float,
    parameters: Dict[str, object],
    channel_start: int = 1,
    time_start: float = 0.0,
) -> List[VehicleTrajectory]:
    """Pick vehicle trajectories without mutating ``data``.

    Args:
        data: Selected DAS data with shape ``(channels, samples)``.
        sampling_rate: Sampling rate of the original data in Hz.
        parameters: User-facing picker parameters from the dialog.
        channel_start: 1-based full-data number of ``data[0]``.
        time_start: Full-data time in seconds corresponding to ``data[:, 0]``.
    """

    tracking_data, tracking_rate, options = prepare_vehicle_tracking_data(
        data, sampling_rate, parameters
    )

    peak_locations: List[np.ndarray] = []
    peak_strengths: List[np.ndarray] = []
    for trace in tracking_data:
        locations, strengths = _peaks_for_trace(
            trace,
            tracking_rate,
            float(options["peak_prominence"]),
            float(options["minimum_separation"]),
            float(options["prominence_window"]),
            str(options["polarity"]),
        )
        peak_locations.append(locations)
        peak_strengths.append(strengths)

    channel_count = tracking_data.shape[0]
    seed_width = min(int(options["seed_width"]), channel_count - 1)
    direction = str(options["direction"])
    scan_directions = (1, -1) if direction == "auto" else ((1,) if direction == "increasing" else (-1,))
    trajectories: List[VehicleTrajectory] = []

    for scan_direction in scan_directions:
        seed_indices = range(seed_width) if scan_direction > 0 else range(channel_count - 1, channel_count - seed_width - 1, -1)
        for seed_channel in seed_indices:
            locations = peak_locations[seed_channel]
            strengths = peak_strengths[seed_channel]
            # Limit pathological noisy data while retaining the strongest
            # events in temporal order for reproducible IDs.
            if locations.size > 300:
                strongest = np.argsort(strengths)[-300:]
                strongest.sort()
                locations, strengths = locations[strongest], strengths[strongest]
            for seed_sample, seed_strength in zip(locations, strengths):
                picked = _track_from_seed(
                    peak_locations,
                    peak_strengths,
                    seed_channel,
                    int(seed_sample),
                    float(seed_strength),
                    scan_direction,
                    tracking_rate,
                    float(options["channel_spacing"]),
                    float(options["minimum_speed"]),
                    float(options["maximum_speed"]),
                    float(options["tracking_tolerance"]),
                    int(options["maximum_missed_channels"]),
                )
                if picked is None:
                    continue
                channels, times, quality = picked
                coverage = channels.size / channel_count
                if coverage < float(options["minimum_coverage"]):
                    continue
                speed = _trajectory_speed(channels, times, float(options["channel_spacing"]))
                if not np.isfinite(speed) or not (
                    float(options["minimum_speed"]) <= speed <= float(options["maximum_speed"])
                ):
                    continue
                global_channels = channels + int(channel_start)
                global_times = times + float(time_start)
                if _is_duplicate(
                    global_channels,
                    global_times,
                    trajectories,
                    float(options["minimum_separation"]) / 2.0,
                ):
                    continue
                trajectories.append(
                    VehicleTrajectory(
                        identifier=0,
                        channels=global_channels,
                        times=global_times,
                        coverage=float(coverage),
                        projected_speed=float(speed),
                        quality=float(quality),
                    )
                )

    trajectories.sort(key=lambda trajectory: trajectory.start_time)
    for identifier, trajectory in enumerate(trajectories, start=1):
        trajectory.identifier = identifier
    return trajectories
