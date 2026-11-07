"""Full-sampling-rate adapter for vendored das_veh KF_tracking.

No decimation, temporal resampling, spatial interpolation, or annotation input
is used. Each peak index addresses an acquired sample in an original channel.
"""

from dataclasses import replace

import numpy as np
from scipy import signal

from ..vendor.das_veh.tracking import KF_tracking
from .vehicle_preprocessing import read_vehicle_response
from .trajectory_prescreen import (
    PrescreenResult, TrackProposal, check_cancel, simplify_track,
)


DEFAULT_DAS_VEH_PARAMETERS = {
    'algorithm': 'das_veh', 'channel_from': 290, 'channel_to': 520,
    'frequency_low': 0.01, 'frequency_high': 1.0, 'channel_spacing': 4.0,
    'minimum_speed': 0.0, 'maximum_speed': 120 / 3.6,
    'peak_prominence': 1.5, 'minimum_separation': 1.0,
    'prominence_window': 12.0, 'seed_sigma': 0.08, 'seed_width': 3,
    'seed_stride': 32, 'maximum_seeds': 1000, 'maximum_candidates': 100,
    'minimum_track_channels': 20, 'maximum_missed_channels': 5,
    'tracking_tolerance': 1.2, 'sigma_a': 0.01,
    'direction': 'auto', 'polarity': 'both',
}


def _options(parameters):
    options = {**DEFAULT_DAS_VEH_PARAMETERS, **parameters}
    for name in ('frequency_low', 'frequency_high', 'channel_spacing',
                 'minimum_speed', 'maximum_speed', 'peak_prominence',
                 'minimum_separation', 'prominence_window', 'seed_sigma',
                 'tracking_tolerance', 'sigma_a'):
        options[name] = float(options[name])
        if not np.isfinite(options[name]):
            raise ValueError(f'参数 {name} 必须是有限数值')
    if options['minimum_speed'] < 0 or options['maximum_speed'] <= options['minimum_speed']:
        raise ValueError('投影速度需满足 0 ≤ 下限 < 上限；下限 0 表示不限制最低速度')
    for name in ('channel_spacing', 'peak_prominence', 'minimum_separation',
                 'prominence_window', 'seed_sigma', 'tracking_tolerance', 'sigma_a'):
        if options[name] <= 0:
            raise ValueError(f'参数 {name} 必须大于 0')
    for name in ('seed_width', 'seed_stride', 'maximum_seeds', 'maximum_candidates',
                 'minimum_track_channels', 'maximum_missed_channels'):
        value = float(options[name])
        if not np.isfinite(value) or value != int(value) or value < (0 if name == 'maximum_missed_channels' else 1):
            raise ValueError(f'参数 {name} 的整数范围无效')
        options[name] = int(value)
    if options['minimum_track_channels'] < 3:
        raise ValueError('最短轨迹至少需要 3 个有效通道')
    if options['direction'] not in ('auto', 'increasing', 'decreasing'):
        raise ValueError('搜索方向无效')
    if options['polarity'] not in ('both', 'positive', 'negative'):
        raise ValueError('信号极性无效')
    return options


def _is_duplicate(proposal, existing, fs, tolerance=0.15):
    """Require substantial shared extent; keep extensions and brief crossings."""
    a = np.asarray(proposal.vertices, dtype=float)
    for other in existing:
        b = np.asarray(other.vertices, dtype=float)
        if (a[-1, 0] - a[0, 0]) * (b[-1, 0] - b[0, 0]) <= 0:
            continue
        first, last = max(a[0, 1], b[0, 1]), min(a[-1, 1], b[-1, 1])
        if last <= first or (last - first) < 0.7 * (a[-1, 1] - a[0, 1]):
            continue
        channels = np.arange(np.ceil(first), np.floor(last) + 1)
        differences = np.abs(np.interp(channels, a[:, 1], a[:, 0]) -
                             np.interp(channels, b[:, 1], b[:, 0])) / fs
        if len(differences) and np.mean(differences <= tolerance) >= 0.8:
            return True
    return False


def detect_das_veh_tracks(data, sampling_rate, parameters=None, *, sample_origin=0,
                          channel_origin=1, sample_bounds=None, cancel=None, progress=None):
    """Run upstream detection/association on normalized full-rate traces."""
    options = _options(parameters or {})
    fs = float(sampling_rate)
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError('采样率无效')
    array = np.asarray(data)
    if array.ndim != 2 or min(array.shape) < 2 or not np.isfinite(array).all():
        raise ValueError('跟踪需要有限数值的二维 DAS 数据')
    check_cancel(cancel)
    progress = progress or (lambda percent, message: None)
    detection = {
        'minprominence': options['peak_prominence'],
        'minseparation': max(1, int(round(options['minimum_separation'] * fs))),
        'prominenceWindow': max(3, int(round(options['prominence_window'] * fs)) | 1),
    }
    signs = (1, -1) if options['polarity'] == 'both' else ((1,) if options['polarity'] == 'positive' else (-1,))
    directions = (1, -1) if options['direction'] == 'auto' else ((1,) if options['direction'] == 'increasing' else (-1,))
    n_channels = array.shape[0]
    t_axis = np.arange(array.shape[1], dtype=float) / fs
    x_axis = np.arange(n_channels, dtype=float) * options['channel_spacing']
    proposals = []
    seed_budget = options['maximum_seeds']
    used_seeds = 0
    budget_hit = False
    pass_count = len(signs) * len(directions)
    for sign_index, sign in enumerate(signs):
        peaks, strengths = [], []
        for row, trace in enumerate(array):
            check_cancel(cancel)
            locations, properties = signal.find_peaks(
                trace if sign == 1 else -trace,
                prominence=detection['minprominence'],
                distance=detection['minseparation'], wlen=detection['prominenceWindow'])
            peaks.append(locations)
            strengths.append(properties['prominences'])
            progress(35 + int(64 * (sign_index + 0.15 * (row + 1) / n_channels) / len(signs)), '在原始采样点检测峰值')
        for direction_index, direction in enumerate(directions):
            check_cancel(cancel)
            oriented_peaks = peaks if direction > 0 else peaks[::-1]
            oriented_strengths = strengths if direction > 0 else strengths[::-1]
            # A reversed view changes traversal only, never the time grid or dx.
            oriented_data = array if direction > 0 else array[::-1]
            arguments = {
                'detect': detection, 'peak_locations': oriented_peaks,
                'channel_step': 1, 'measurement_variance': (fs / 50) ** 2,
                'association_window': (-options['tracking_tolerance'] * fs,
                                       options['tracking_tolerance'] * fs),
                'initialize_slope': True, 'nearest_peak': True, 'observed_only': True,
                'maximum_missed_channels': options['maximum_missed_channels'],
                'check_cancel': lambda: check_cancel(cancel),
            }
            tracker = KF_tracking(oriented_data, t_axis, x_axis, arguments)
            starts = list(range(0, n_channels - options['minimum_track_channels'] + 1, options['seed_stride']))
            job_limit = max(1, seed_budget // max(1, pass_count * len(starts)))
            for start_index, start in enumerate(starts):
                check_cancel(cancel)
                def report(fraction):
                    progress(35 + int(64 * (sign_index + 0.15 + 0.85 *
                             (direction_index + (start_index + fraction) / max(1, len(starts))) / len(directions)) / len(signs)),
                             '原版卡尔曼逐通道跟踪（原始采样率）')
                arguments['progress'] = report
                tracker.progress = report
                bases = tracker.detect_in_one_section(x_axis[start], nx=options['seed_width'],
                                                       sigma=options['seed_sigma'], show_plot=False)
                if sample_bounds is not None:
                    samples = sample_origin + bases
                    bases = bases[(samples >= sample_bounds[0]) & (samples < sample_bounds[1])]
                remaining = min(job_limit, max(0, seed_budget - used_seeds))
                if len(bases) > remaining:
                    budget_hit = True
                    # Spread budget over space, direction, polarity, and time.
                    bases = bases[np.linspace(0, len(bases) - 1, remaining).astype(int)]
                used_seeds += len(bases)
                if not len(bases):
                    continue
                states = tracker.tracking_with_veh_base(x_axis[start], x_axis[-1], bases,
                                                        sigma_a=options['sigma_a'] * (fs / 50) ** 2)
                for state in states:
                    check_cancel(cancel)
                    rows = np.flatnonzero(np.isfinite(state)) + start
                    times = state[np.isfinite(state)]
                    global_samples = np.rint(sample_origin + times).astype(np.int64)
                    keep = np.ones(len(rows), dtype=bool)
                    if sample_bounds is not None:
                        keep = (global_samples >= sample_bounds[0]) & (global_samples < sample_bounds[1])
                    rows, times, global_samples = rows[keep], times[keep], global_samples[keep]
                    if len(rows) < options['minimum_track_channels']:
                        continue
                    centered = rows - rows.mean()
                    slope = float(centered @ (times - times.mean()) / (centered @ centered)) / fs
                    if slope <= 0:
                        continue
                    speed = options['channel_spacing'] / slope
                    if speed > options['maximum_speed'] or speed < options['minimum_speed']:
                        continue
                    # Filter local sustained slope reversals / extreme speed,
                    # allowing individual waveform peak jitter and crossings.
                    if len(rows) >= 9:
                        slopes = (times[8:] - times[:-8]) / (rows[8:] - rows[:-8]) / fs
                        minimum_slope = options['channel_spacing'] / options['maximum_speed']
                        if np.mean(slopes < minimum_slope * 0.5) > 0.2:
                            continue
                    global_channels = (rows if direction > 0 else n_channels - 1 - rows) + channel_origin
                    order = np.argsort(global_channels)
                    points = np.column_stack((global_samples[order], global_channels[order]))
                    response = []
                    for row, time in zip(rows, times):
                        index = np.searchsorted(oriented_peaks[row], int(round(time)))
                        if index < len(oriented_strengths[row]):
                            response.append(float(oriented_strengths[row][index]))
                    continuity = len(rows) / (rows[-1] - rows[0] + 1)
                    jitter = np.std(times / fs - (rows - rows[0]) * slope)
                    proposals.append(TrackProposal(0, points.tolist(), continuity,
                                                  float(np.mean(response)) if response else 0,
                                                  bool(jitter > options['tracking_tolerance'])))
    proposals.sort(key=lambda p: (-(p.vertices[-1][1] - p.vertices[0][1]), -p.strength))
    retained = []
    for proposal in proposals:
        check_cancel(cancel)
        if not _is_duplicate(proposal, retained, fs):
            retained.append(proposal)
    notes = [f'das_veh 原版核心；{fs:g} Hz 全采样点处理；正负极性分别检测，不使用人工标注约束']
    if budget_hit:
        notes.append('达到起点预算，部分起点未搜索；可缩小时间范围后重试')
    if len(retained) > options['maximum_candidates']:
        notes.append(f'候选超过上限，仅保留最长的 {options["maximum_candidates"]} 条')
    if not retained:
        notes.append('未检出满足条件的轨迹，不代表范围内无车；可调整灵敏度、最短轨迹或容差后重试')
    retained = retained[:options['maximum_candidates']]
    retained.sort(key=lambda p: min(v[0] for v in p.vertices))
    result = tuple(replace(p, identifier=i, vertices=simplify_track(p.vertices, fs))
                   for i, p in enumerate(retained, 1))
    return PrescreenResult(result, tuple(notes))


def analyze_das_veh(group, raw_data, visible_start, visible_end, channel_from, channel_to,
                    parameters, cancel=None, progress=None):
    """Read padded blocks and filter every original sample at the supplied fs."""
    options = _options(parameters)
    fs = float(group.sampling_rate)
    data, start, notes = read_vehicle_response(
        group, raw_data, visible_start, visible_end, channel_from, channel_to,
        options, check_cancel=lambda: check_cancel(cancel), progress=progress)
    result = detect_das_veh_tracks(data, fs, options, sample_origin=start, channel_origin=channel_from,
                                   sample_bounds=(visible_start, visible_end), cancel=cancel, progress=progress)
    return PrescreenResult(result.proposals, tuple(notes) + result.notes)
