"""CPU-only, cancellable trajectory proposals in canonical DAS coordinates.

Filtering is performed on anti-aliased, channel-block downsampled data. A small
beam follows signed peaks in both spatial directions; proposals are never
annotations until the user confirms them.
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy import signal
from scipy.ndimage import gaussian_filter

from .data_group import ensure_memory_budget
from .vehicle_tracking import _downsample, VehicleTrajectory
from .video_trajectory import read_group_window

DEFAULT_PARAMETERS = {
    'frequency_low': 0.01, 'frequency_high': 1.0, 'channel_spacing': 4.0,
    'peak_prominence': 1.5, 'minimum_separation': 0.8,
    'minimum_speed': 2.0, 'maximum_speed': 60.0, 'tracking_tolerance': 0.6,
    'maximum_missed_channels': 5, 'minimum_track_channels': 12,
    'seed_stride': 8, 'maximum_seeds': 1000, 'maximum_candidates': 100,
    'direction': 'auto',
}

class PrescreenCancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise PrescreenCancelled()


@dataclass
class TrackProposal:
    identifier: int
    vertices: list
    continuity: float
    strength: float
    ambiguous: bool = False
    edited: bool = False


@dataclass(frozen=True)
class PrescreenResult:
    proposals: tuple
    notes: tuple = ()


def simplify_track(points, sampling_rate, tolerance_seconds=0.08, tolerance_channels=0.75):
    """RDP simplification in scaled time/channel units; preserve endpoints."""
    points = np.asarray(points, dtype=float)
    if len(points) <= 2:
        return [[int(round(p[0])), float(p[1])] for p in points]
    scaled = points / [sampling_rate * tolerance_seconds, tolerance_channels]
    keep = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    while pending:
        first, last = pending.pop()
        if last - first < 2:
            continue
        a, b = scaled[first], scaled[last]
        delta = b - a
        inner = scaled[first + 1:last]
        ratio = np.clip((inner - a) @ delta / max(float(delta @ delta), 1e-12), 0, 1)
        distance = np.linalg.norm(inner - a - ratio[:, None] * delta, axis=1)
        index = int(np.argmax(distance))
        if distance[index] > 1:
            middle = first + 1 + index
            keep.add(middle)
            pending.extend(((first, middle), (middle, last)))
    return [[int(round(points[i, 0])), float(points[i, 1])] for i in sorted(keep)]


def _extend(peaks, strengths, seed, initial_slope, step, options, cancel):
    """Retain three plausible paths, penalizing slope changes and missing rows."""
    # Nodes, slope (seconds per ascending channel), cost, missed, ambiguity.
    beams = [([seed], initial_slope, 0.0, 0, False)]
    best = beams[0]
    tolerance = options['tracking_tolerance']
    low = options['channel_spacing'] / options['maximum_speed']
    high = options['channel_spacing'] / options['minimum_speed']
    for channel in range(seed[0] + step, len(peaks) if step > 0 else -1, step):
        check_cancel(cancel)
        branches = []
        for nodes, slope, cost, missed, ambiguous in beams:
            last_channel, last_time, _strength = nodes[-1]
            predicted = last_time + (channel - last_channel) * slope
            locations = peaks[channel]
            start = np.searchsorted(locations, predicted - tolerance)
            stop = np.searchsorted(locations, predicted + tolerance, side='right')
            choices = []
            for index in range(start, stop):
                observed = float(locations[index])
                measured = (observed - last_time) / (channel - last_channel)
                # Individual peak positions jitter between channels. Constrain
                # the fitted local motion rather than every one-row difference.
                recent = nodes[-4:] + [(channel, observed, 0)]
                fit_channels = np.asarray([p[0] for p in recent], dtype=float)
                fit_times = np.asarray([p[1] for p in recent], dtype=float)
                centered = fit_channels - fit_channels.mean()
                measured = float(centered @ (fit_times - fit_times.mean()) / max(centered @ centered, 1e-12))
                if measured * initial_slope <= 0 or abs(measured) > high:
                    continue
                measured = float(np.sign(initial_slope) * max(low, abs(measured)))
                smoothness = abs(measured - slope) / max(abs(slope), low)
                if smoothness > 2.0:
                    continue
                strength = float(strengths[channel][index])
                increment = abs(observed - predicted) / tolerance + 1.2 * smoothness - 0.08 * min(strength, 8)
                choices.append((increment, observed, strength, measured))
            choices.sort()
            crossing = len(choices) > 1 and choices[1][0] - choices[0][0] < 0.3
            for increment, observed, strength, measured in choices[:2]:
                branches.append((nodes + [(channel, observed, strength)],
                                 0.65 * slope + 0.35 * measured,
                                 cost + increment, 0, ambiguous or crossing))
            if missed < options['maximum_missed_channels']:
                branches.append((nodes, slope, cost + 1.8, missed + 1, ambiguous))
        if not branches:
            break
        branches.sort(key=lambda state: state[2] - 0.7 * len(state[0]))
        beams = branches[:3]
        for state in beams:
            if len(state[0]) > len(best[0]) or (len(state[0]) == len(best[0]) and state[2] < best[2]):
                best = state
    return best


def _initial_slopes(peaks, strengths, seed, options, slope_sign):
    channel, time, _strength = seed
    low = options['channel_spacing'] / options['maximum_speed']
    high = options['channel_spacing'] / options['minimum_speed']
    choices = []
    for step in (1, -1):
        for distance in (4, 8, 1):
            row = channel + step * distance
            if not 0 <= row < len(peaks):
                break
            delta_low, delta_high = sorted((step * slope_sign * distance * low,
                                           step * slope_sign * distance * high))
            first = np.searchsorted(peaks[row], time + delta_low)
            last = np.searchsorted(peaks[row], time + delta_high, side='right')
            if first < last:
                indices = np.arange(first, last)
                strongest = indices[np.argsort(strengths[row][indices])[-2:]]
                choices.extend((float(strengths[row][i]), (float(peaks[row][i]) - time) / (row - channel)) for i in strongest)
    # A one-row difference is sensitive to peak jitter. Prefer slopes supported
    # on several neighbouring rows, including seeds in the middle of a curve.
    supported = []
    for strength, slope in choices:
        errors = []
        for offset in (-8, -4, 4, 8):
            row = channel + offset
            if not 0 <= row < len(peaks) or not len(peaks[row]):
                continue
            expected = time + offset * slope
            index = np.searchsorted(peaks[row], expected)
            nearby = peaks[row][max(0, index - 1):index + 1]
            errors.append(min(float(np.min(np.abs(nearby - expected))), 2.0))
        if errors:
            supported.append((np.mean(errors) - 0.015 * min(strength, 8), slope))
    supported.sort()
    slopes = []
    for _cost, slope in supported:
        if not any(abs(slope - other) < 0.03 for other in slopes):
            slopes.append(slope)
        if len(slopes) == 2:
            break
    return slopes


def _join_fragments(tracks, options, cancel):
    """Join agreeing overlaps or short gaps; do not connect crossing slopes."""
    tracks = sorted(tracks, key=lambda track: -len(track.channels))
    tolerance = min(options['tracking_tolerance'], 0.4)
    merged = []
    for track in tracks:
        check_cancel(cancel)
        for existing in merged:
            lower = max(existing.channels[0], track.channels[0])
            upper = min(existing.channels[-1], track.channels[-1])
            if upper - lower >= 5:
                rows = np.linspace(lower, upper, min(50, int(upper - lower) + 1))
                a = np.interp(rows, existing.channels, existing.times)
                b = np.interp(rows, track.channels, track.times)
                slope_a, slope_b = np.polyfit(rows, a, 1)[0], np.polyfit(rows, b, 1)[0]
                agree = (slope_a * slope_b > 0 and np.mean(np.abs(a - b) <= tolerance) >= 0.85)
            elif upper < lower:
                left, right = sorted((existing, track), key=lambda item: item.channels[0])
                gap = right.channels[0] - left.channels[-1]
                if gap > options['maximum_missed_channels'] + 1:
                    continue
                slope_a = np.polyfit(left.channels[-5:], left.times[-5:], 1)[0]
                slope_b = np.polyfit(right.channels[:5], right.times[:5], 1)[0]
                agree = (slope_a * slope_b > 0
                         and abs(slope_a - slope_b) <= 0.5 * max(abs(slope_a), abs(slope_b))
                         and abs(left.times[-1] + gap * (slope_a + slope_b) / 2 - right.times[0]) <= tolerance)
            else:
                agree = False
            if not agree:
                continue
            pairs = {}
            for source in (existing, track):
                for channel, time in zip(source.channels, source.times):
                    pairs.setdefault(int(channel), []).append(float(time))
            channels = np.asarray(sorted(pairs))
            existing.channels = channels
            existing.times = np.asarray([np.median(pairs[int(channel)]) for channel in channels])
            existing.coverage = len(channels) / (channels[-1] - channels[0] + 1)
            existing.quality = max(existing.quality, track.quality)
            existing.ambiguous |= track.ambiguous
            break
        else:
            merged.append(track)
    return merged


def _duplicate_track(channels, times, existing, tolerance):
    """Suppress contained paths, preserving extensions and brief crossings."""
    for track in existing:
        lower = max(channels[0], track.channels[0])
        upper = min(channels[-1], track.channels[-1])
        if upper - lower < 0.8 * (channels[-1] - channels[0]):
            continue
        rows = np.linspace(lower, upper, min(60, int(upper - lower) + 1))
        a = np.interp(rows, channels, times)
        b = np.interp(rows, track.channels, track.times)
        if (a[-1] - a[0]) * (b[-1] - b[0]) <= 0:
            continue
        if np.mean(np.abs(a - b) <= tolerance) >= 0.8:
            return True
    return False


def detect_tracks(data, sampling_rate, options, *, sample_origin=0, channel_origin=1,
                  original_rate=None, sample_bounds=None, cancel=None, progress=None):
    """Find curves from signed, already-filtered traces without altering input."""
    options = {**DEFAULT_PARAMETERS, **options}
    original_rate = float(original_rate or sampling_rate)
    progress = progress or (lambda percent, message: None)
    n_channels = len(data)
    all_tracks = []
    seed_limit_hit = False
    for polarity_index, sign in enumerate((1, -1, 0, 2)):
        polarity_track_start = len(all_tracks)
        peaks, strengths = [], []
        # The envelope supplies paths where the signed waveform alternates or
        # fragments. It is still a proposal and is reviewed like signed paths.
        source = data if sign else gaussian_filter(np.abs(data), sigma=(1.0, sampling_rate * 0.15))
        for trace in source:
            check_cancel(cancel)
            if sign == 2:
                positive, plus = signal.find_peaks(trace, prominence=options['peak_prominence'],
                    distance=max(1, int(options['minimum_separation'] * sampling_rate)))
                negative, minus = signal.find_peaks(-trace, prominence=options['peak_prominence'],
                    distance=max(1, int(options['minimum_separation'] * sampling_rate)))
                indices = np.concatenate((positive, negative))
                response = np.concatenate((plus['prominences'], minus['prominences']))
                order = np.argsort(indices)
                indices, response = indices[order], response[order]
            else:
                indices, properties = signal.find_peaks(
                    sign * trace if sign else trace,
                    prominence=options['peak_prominence'] if sign else options['peak_prominence'] * 0.4,
                    distance=max(1, int(round(options.get('minimum_separation', 0.8) * sampling_rate))),
                    wlen=max(3, int(round(12 * sampling_rate)) | 1),
                )
                response = properties['prominences']
            peaks.append(indices / sampling_rate)
            strengths.append(response)
        rows = sorted(set(range(0, n_channels, options.get('seed_stride', 8))) | {n_channels - 1})
        seeds = [(float(strength), row, float(time))
                 for row in rows for time, strength in zip(peaks[row], strengths[row])
                 if sample_bounds is None or sample_bounds[0] <= sample_origin + time * original_rate < sample_bounds[1]]
        # Round-robin rows before applying the budget so energetic sections
        # cannot exhaust all seeds and hide weaker paths elsewhere in the ROI.
        buckets = {row: [] for row in rows}
        for seed in sorted(seeds, reverse=True):
            buckets[seed[1]].append(seed)
        seeds = [bucket[index] for index in range(max((len(b) for b in buckets.values()), default=0))
                 for bucket in buckets.values() if index < len(bucket)]
        seed_limit_hit |= len(seeds) > options.get('maximum_seeds', 1000)
        seeds = seeds[:options.get('maximum_seeds', 1000)]
        directions = (1, -1) if options.get('direction', 'auto') == 'auto' else (
            (1,) if options['direction'] == 'increasing' else (-1,))
        for seed_index, (strength, channel, time) in enumerate(seeds):
            check_cancel(cancel)
            if len(all_tracks) - polarity_track_start >= options.get('maximum_candidates', 100) * 2:
                seed_limit_hit = True
                break
            progress(40 + int(15 * polarity_index + 15 * seed_index / max(1, len(seeds))), '连接轨迹片段')
            # Strong long paths are searched first; covered seeds need no repeat.
            if any(np.min(t.channels) <= channel <= np.max(t.channels)
                   and abs(float(np.interp(channel, t.channels, t.times)) - time) <= 0.1
                   for t in all_tracks):
                continue
            seed = (channel, time, strength)
            found = []
            for direction in directions:
                for slope in _initial_slopes(peaks, strengths, seed, options, direction):
                    forward = _extend(peaks, strengths, seed, slope, 1, options, cancel)
                    backward = _extend(peaks, strengths, seed, slope, -1, options, cancel)
                    nodes = list(reversed(backward[0][1:])) + forward[0]
                    found.append((nodes, forward[2] + backward[2], forward[4] or backward[4]))
            found.sort(key=lambda entry: (-len(entry[0]), entry[1]))
            for nodes, _cost, ambiguous in found[:1]:
                channels, times, response = np.asarray(nodes, dtype=float).T
                samples = np.rint(sample_origin + times * original_rate).astype(np.int64)
                visible = np.ones(len(samples), dtype=bool)
                if sample_bounds is not None:
                    visible = (samples >= sample_bounds[0]) & (samples < sample_bounds[1])
                channels, times, response = channels[visible], times[visible], response[visible]
                if len(channels) < options['minimum_track_channels']:
                    continue
                continuity = len(channels) / (channels[-1] - channels[0] + 1)
                if continuity < 0.65:
                    continue
                centered = channels - channels.mean()
                fitted = abs(float(centered @ (times - times.mean()) / max(centered @ centered, 1e-12)))
                if not options['channel_spacing'] / options['maximum_speed'] <= fitted <= options['channel_spacing'] / options['minimum_speed']:
                    continue
                if _duplicate_track(channels, times, all_tracks, 0.12):
                    continue
                track = VehicleTrajectory(len(all_tracks) + 1, channels, times, continuity,
                                          float('nan'), float(np.mean(response)))
                track.ambiguous = ambiguous
                all_tracks.append(track)
    all_tracks = _join_fragments(all_tracks, options, cancel)
    # Prefer the longer path among duplicates found in separate polarities.
    all_tracks.sort(key=lambda track: (-len(track.channels), -track.quality))
    retained = []
    for track in all_tracks:
        if not _duplicate_track(track.channels, track.times, retained, 0.12):
            retained.append(track)
    limit = options.get('maximum_candidates', 100)
    notes = []
    if seed_limit_hit:
        notes.append('起点较多，本次优先搜索强响应；弱轨迹可缩小范围后重试')
    if len(retained) > limit:
        notes.append(f'候选较多，本次保留最长的 {limit} 条，请缩小范围复查')
    retained = retained[:limit]
    retained.sort(key=lambda track: float(track.times.min()))
    proposals = []
    for identifier, track in enumerate(retained, 1):
        vertices = np.column_stack((np.rint(sample_origin + track.times * original_rate),
                                    track.channels + channel_origin))
        proposals.append(TrackProposal(identifier, simplify_track(vertices, original_rate),
                                       track.coverage, track.quality, track.ambiguous))
    return PrescreenResult(tuple(proposals), tuple(notes))


def analyze_prescreen(group, raw_data, visible_start, visible_end, channel_from, channel_to,
                      parameters, cancel=None, progress: Callable | None = None):
    """Read/filter padding in bounded channel blocks, then crop proposals."""
    options = {**DEFAULT_PARAMETERS, **parameters}
    progress = progress or (lambda percent, message: None)
    if channel_to - channel_from + 1 < 8:
        raise ValueError('初筛至少需要 8 个可见通道，请先扩大通道范围')
    if visible_end <= visible_start:
        raise ValueError('当前视图没有有效的 DAS 时间范围')
    if options['minimum_speed'] <= 0 or options['maximum_speed'] <= options['minimum_speed']:
        raise ValueError('投影速度上限必须大于正的下限')
    fs = float(group.sampling_rate)
    if not 0 < options['frequency_low'] < options['frequency_high'] < fs / 2:
        raise ValueError('滤波频率需满足 0 < 低频 < 高频 < 原始采样率的一半')
    if options['channel_spacing'] <= 0:
        raise ValueError('通道间距 dx 必须大于 0')
    padding = int(np.ceil(max(5, 1 / options['frequency_low']) * fs))
    start = max(0, int(visible_start) - padding)
    end = min(group.total_samples, int(visible_end) + padding)
    duration = (end - start) / fs
    if duration < 5:
        raise ValueError('来源数据不足 5 秒，无法稳定进行低频轨迹初筛')
    notes = []
    low = max(options['frequency_low'], 2 / duration)
    if low >= options['frequency_high']:
        raise ValueError('来源数据太短，无法使用当前滤波频段，请提高频率上限')
    if low > options['frequency_low'] + 1e-9:
        notes.append(f'短记录的滤波低频下限调整为 {low:.3g} Hz')
    target_rate = min(fs, max(50.0, 5 * options['frequency_high']))
    ensure_memory_budget(channel_to - channel_from + 1, int(duration * target_rate) + 2,
                         32.0, '轻量轨迹初筛')
    blocks = []
    for first in range(channel_from, channel_to + 1, 16):
        check_cancel(cancel)
        last = min(first + 15, channel_to)
        if raw_data is None:
            block = read_group_window(group, start, end, first, last)
        else:
            if raw_data.shape != (group.channel_count, group.total_samples):
                raise ValueError('原始数据与 DAS 来源范围不一致，请重新载入数据')
            block = np.array(raw_data[first - 1:last, start:end], dtype=np.float32, copy=True)
        block, reduced_rate = _downsample(block, fs, target_rate)
        blocks.append(np.asarray(block, dtype=np.float32))
        progress(int(30 * (last - channel_from + 1) / (channel_to - channel_from + 1)), '读取并降采样 DAS 数据')
    check_cancel(cancel)
    data = np.concatenate(blocks).astype(np.float64)
    del blocks
    if not np.isfinite(data).all():
        raise ValueError('DAS 数据含有 NaN 或无穷值，无法初筛')
    data -= np.median(data, axis=0, keepdims=True)
    # Nearby channels observe the same passage with small delays. Modest
    # smoothing suppresses isolated extrema while retaining slanted responses.
    data = gaussian_filter(data, sigma=(0.8, max(0.5, reduced_rate * 0.025)))
    sos = signal.butter(4, [low, options['frequency_high']], btype='bandpass', fs=reduced_rate, output='sos')
    data = signal.sosfiltfilt(sos, data, axis=1)
    center = np.median(data, axis=1, keepdims=True)
    scale = 1.4826 * np.median(np.abs(data - center), axis=1, keepdims=True)
    valid = scale[:, 0] > max(float(np.median(scale)) * 1e-4, 1e-12)
    data = (data - center) / np.maximum(scale, 1e-12)
    data[~valid] = 0
    check_cancel(cancel)
    result = detect_tracks(data, reduced_rate, options, original_rate=fs,
                           sample_origin=start, channel_origin=channel_from,
                           sample_bounds=(visible_start, visible_end), cancel=cancel, progress=progress)
    return PrescreenResult(result.proposals, tuple(notes) + result.notes)
