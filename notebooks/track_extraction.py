"""
精简版车辆轨迹提取 - 峰值检测 + 霍夫变换
从 das_veh.ipynb 精简而来
"""
import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter


def find_peaks_simple(data, sampling_rate,
                     prominence=2.5, min_separation_seconds=2.0):
    """
    简化的峰值检测：在每个通道上找突出峰

    参数：
        data: (channels, samples) 预处理后的数据
        sampling_rate: 采样率 Hz
        prominence: 突出度阈值
        min_separation_seconds: 峰值最小间隔（秒）

    返回：
        peaks_list: 列表，每个元素是一个通道的峰值索引数组
    """
    min_distance = int(min_separation_seconds * sampling_rate)
    peaks_list = []

    for channel_data in data:
        peaks, properties = signal.find_peaks(
            channel_data,
            prominence=prominence,
            distance=min_distance
        )
        peaks_list.append(peaks)

    return peaks_list


def find_peaks_ridge(data, sampling_rate,
                    prominence=2.5, min_separation_seconds=2.0,
                    ridge_radius=1):
    """
    脊线增强的峰值检测：要求峰值在2D脊线上

    参数：
        data: (channels, samples)
        ridge_radius: 邻道验证半径

    返回：
        peaks_list: 每通道的峰值列表
        strengths_list: 每峰值的强度
    """
    from scipy.ndimage import sobel

    # 1. 计算2D梯度
    grad_c = sobel(data, axis=0)  # 通道方向梯度
    grad_t = sobel(data, axis=1)  # 时间方向梯度

    # 2. Hessian矩阵的迹（简化脊线响应）
    ridge_response = -(grad_c**2 + grad_t**2)

    # 3. 在每个通道找峰值
    min_distance = int(min_separation_seconds * sampling_rate)
    peaks_list = []
    strengths_list = []

    for i, channel_data in enumerate(data):
        # 找1D峰值
        peaks, props = signal.find_peaks(
            channel_data,
            prominence=prominence,
            distance=min_distance
        )

        if len(peaks) == 0:
            peaks_list.append(np.array([], dtype=int))
            strengths_list.append(np.array([]))
            continue

        # 验证峰值是否在脊线上（邻道也有峰）
        valid_mask = np.zeros(len(peaks), dtype=bool)
        for idx, peak_t in enumerate(peaks):
            # 检查上下邻道
            neighbor_count = 0
            for di in range(-ridge_radius, ridge_radius + 1):
                if di == 0:
                    continue
                ni = i + di
                if 0 <= ni < len(data):
                    # 邻道在时间窗口内有峰值吗？
                    window_t = slice(max(0, peak_t - min_distance // 2),
                                    min(data.shape[1], peak_t + min_distance // 2))
                    if data[ni, window_t].max() > prominence:
                        neighbor_count += 1

            # 至少2个邻道支持
            if neighbor_count >= 2:
                valid_mask[idx] = True

        valid_peaks = peaks[valid_mask]
        valid_strengths = props['prominences'][valid_mask]

        peaks_list.append(valid_peaks)
        strengths_list.append(valid_strengths)

    return peaks_list, strengths_list


def peaks_to_binary_image(peaks_list, shape):
    """
    将峰值列表转换为二值图像

    参数：
        peaks_list: 每通道的峰值索引列表
        shape: (channels, samples)

    返回：
        binary: (channels, samples) bool数组
    """
    binary = np.zeros(shape, dtype=bool)
    for i, peaks in enumerate(peaks_list):
        if len(peaks) > 0:
            binary[i, peaks] = True
    return binary


def hough_transform_local(binary_image,
                         channel_window=60, channel_overlap=30,
                         theta_bins=180, rho_resolution=1.0):
    """
    局部霍夫变换：在滑动窗口内检测直线种子

    参数：
        binary_image: (channels, samples) bool数组，峰值二值图
        channel_window: 通道窗口大小
        channel_overlap: 窗口重叠
        theta_bins: 角度分辨率
        rho_resolution: 距离分辨率

    返回：
        seeds: 列表，每个元素是 (channel_start, time_start, channel_end, time_end, votes)
    """
    channels, samples = binary_image.shape
    seeds = []

    # 角度范围：主要关注斜线（±30°到±60°）
    theta_range = np.linspace(-np.pi/3, np.pi/3, theta_bins)

    # 滑动窗口
    for ch_start in range(0, channels - channel_window + 1, channel_window - channel_overlap):
        ch_end = min(ch_start + channel_window, channels)
        window = binary_image[ch_start:ch_end, :]

        if window.sum() < 3:  # 至少3个峰值
            continue

        # 获取峰值坐标
        coords = np.argwhere(window)  # (N, 2) - [channel, time]
        if len(coords) < 3:
            continue

        # 霍夫变换累加器
        max_rho = int(np.sqrt(channel_window**2 + samples**2))
        accumulator = np.zeros((2 * max_rho, theta_bins), dtype=int)

        for ch, t in coords:
            for theta_idx, theta in enumerate(theta_range):
                rho = int(ch * np.cos(theta) + t * np.sin(theta))
                rho_idx = rho + max_rho
                if 0 <= rho_idx < accumulator.shape[0]:
                    accumulator[rho_idx, theta_idx] += 1

        # 找局部最大值
        threshold = max(3, int(0.3 * coords.shape[0]))  # 至少30%的点支持
        local_max = maximum_filter(accumulator, size=5)
        peaks_mask = (accumulator >= threshold) & (accumulator == local_max)

        peak_coords = np.argwhere(peaks_mask)

        for rho_idx, theta_idx in peak_coords:
            rho = rho_idx - max_rho
            theta = theta_range[theta_idx]
            votes = accumulator[rho_idx, theta_idx]

            # 转换为起止点
            # rho = ch*cos(θ) + t*sin(θ)
            # 在窗口边界求交点
            if abs(np.sin(theta)) > 0.01:
                t_start = (rho - 0 * np.cos(theta)) / np.sin(theta)
                t_end = (rho - (ch_end - ch_start) * np.cos(theta)) / np.sin(theta)

                if 0 <= t_start < samples and 0 <= t_end < samples:
                    seeds.append({
                        'ch_start': ch_start,
                        't_start': int(t_start),
                        'ch_end': ch_end - 1,
                        't_end': int(t_end),
                        'votes': votes
                    })

    return seeds


def extend_track(seed, binary_image, max_gap=20, poly_degree=1):
    """
    从霍夫种子延伸轨迹，允许缺失和曲线拟合

    参数：
        seed: 霍夫种子字典
        binary_image: 峰值二值图
        max_gap: 最大连续缺失通道数
        poly_degree: 多项式拟合次数（1=直线，2=曲线）

    返回：
        track: 字典 {channels: [...], times: [...], ...]
    """
    channels, samples = binary_image.shape

    # 初始化轨迹
    ch_start, ch_end = seed['ch_start'], seed['ch_end']
    t_start, t_end = seed['t_start'], seed['t_end']

    track_channels = []
    track_times = []

    # 沿通道方向延伸
    direction = 1 if ch_end > ch_start else -1
    current_ch = ch_start
    consecutive_misses = 0

    # 初始斜率
    if ch_end != ch_start:
        slope = (t_end - t_start) / (ch_end - ch_start)
    else:
        slope = 0

    while 0 <= current_ch < channels and consecutive_misses < max_gap:
        # 预测时间位置
        if len(track_channels) > 0:
            # 用已有点重新拟合
            if len(track_channels) >= poly_degree + 1:
                coeffs = np.polyfit(track_channels, track_times, poly_degree)
                predicted_t = int(np.polyval(coeffs, current_ch))
            else:
                predicted_t = track_times[-1] + direction * int(slope)
        else:
            predicted_t = t_start if current_ch == ch_start else t_end

        # 在预测位置附近搜索峰值
        search_window = 20  # 采样点
        t_min = max(0, predicted_t - search_window)
        t_max = min(samples, predicted_t + search_window)

        if binary_image[current_ch, t_min:t_max].any():
            # 找到峰值
            local_peaks = np.where(binary_image[current_ch, t_min:t_max])[0]
            best_peak_t = t_min + local_peaks[np.argmin(np.abs(local_peaks + t_min - predicted_t))]

            track_channels.append(current_ch)
            track_times.append(best_peak_t)
            consecutive_misses = 0
        else:
            consecutive_misses += 1

        current_ch += direction

    if len(track_channels) < 3:
        return None

    return {
        'channels': np.array(track_channels),
        'times': np.array(track_times),
        'length': len(track_channels)
    }


def extract_tracks(data, sampling_rate, parameters):
    """
    完整的轨迹提取流程

    参数：
        data: (channels, samples) 预处理后数据
        sampling_rate: 采样率
        parameters: 参数字典
            - peak_method: 'simple' 或 'ridge'
            - prominence: 峰值突出度
            - min_separation: 峰值最小间隔（秒）
            - hough_channel_window: 霍夫窗口大小
            - max_gap: 最大缺失通道数
            - min_track_length: 最小轨迹长度

    返回：
        tracks: 轨迹列表
    """
    print("1. 峰值检测...")
    peak_method = parameters.get('peak_method', 'simple')

    if peak_method == 'ridge':
        peaks_list, strengths_list = find_peaks_ridge(
            data, sampling_rate,
            prominence=parameters.get('prominence', 2.5),
            min_separation_seconds=parameters.get('min_separation', 2.0)
        )
    else:
        peaks_list = find_peaks_simple(
            data, sampling_rate,
            prominence=parameters.get('prominence', 2.5),
            min_separation_seconds=parameters.get('min_separation', 2.0)
        )

    total_peaks = sum(len(p) for p in peaks_list)
    print(f"   找到 {total_peaks} 个峰值")

    # 2. 转换为二值图
    binary = peaks_to_binary_image(peaks_list, data.shape)

    # 3. 霍夫变换找种子
    print("2. 霍夫变换...")
    seeds = hough_transform_local(
        binary,
        channel_window=parameters.get('hough_channel_window', 60),
        channel_overlap=parameters.get('hough_overlap', 30)
    )
    print(f"   找到 {len(seeds)} 个霍夫种子")

    # 4. 延伸轨迹
    print("3. 轨迹延伸...")
    tracks = []
    for seed in seeds:
        track = extend_track(
            seed, binary,
            max_gap=parameters.get('max_gap', 20),
            poly_degree=parameters.get('poly_degree', 1)
        )
        if track is not None:
            min_length = parameters.get('min_track_length', 50)
            if track['length'] >= min_length:
                tracks.append(track)

    print(f"   提取 {len(tracks)} 条轨迹")

    # 5. 去重（简单：按起始通道和时间去重）
    if len(tracks) > 1:
        tracks = merge_overlapping_tracks(tracks, tolerance=10)
        print(f"   合并后 {len(tracks)} 条轨迹")

    return tracks, binary


def merge_overlapping_tracks(tracks, tolerance=10):
    """
    合并重叠的轨迹（简化版）

    参数：
        tracks: 轨迹列表
        tolerance: 通道重叠容差

    返回：
        merged_tracks: 去重后的轨迹
    """
    if len(tracks) <= 1:
        return tracks

    # 按起始通道排序
    sorted_tracks = sorted(tracks, key=lambda t: t['channels'][0])

    merged = [sorted_tracks[0]]

    for track in sorted_tracks[1:]:
        last_merged = merged[-1]

        # 检查是否重叠
        overlap_channels = set(track['channels']) & set(last_merged['channels'])

        if len(overlap_channels) > tolerance:
            # 合并：保留更长的
            if track['length'] > last_merged['length']:
                merged[-1] = track
        else:
            merged.append(track)

    return merged


def plot_tracks(data, tracks, sampling_rate, channel_from=1, title="Vehicle Tracks"):
    """
    绘制轨迹叠加在数据上

    参数：
        data: (channels, samples)
        tracks: 轨迹列表
        sampling_rate: 采样率
        channel_from: 起始通道编号
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(14, 8))

    # 绘制数据
    extent = [0, data.shape[1] / sampling_rate,
              channel_from, channel_from + data.shape[0]]
    vmax = np.percentile(np.abs(data), 99)

    ax.imshow(data, aspect='auto', cmap='RdBu_r',
             extent=extent, vmin=-vmax, vmax=vmax,
             origin='lower', interpolation='none')

    # 绘制轨迹
    colors = plt.cm.tab10(np.linspace(0, 1, len(tracks)))

    for i, (track, color) in enumerate(zip(tracks, colors)):
        channels = track['channels'] + channel_from
        times = track['times'] / sampling_rate

        ax.plot(times, channels, 'o-', color=color, linewidth=2,
               markersize=4, label=f"Track {i+1} ({track['length']}ch)",
               alpha=0.8)

    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Channel')
    ax.set_title(title, fontweight='bold')
    if len(tracks) > 0:
        ax.legend(loc='upper right')
    ax.grid(alpha=0.3)

    plt.tight_layout()
    return fig


if __name__ == '__main__':
    print("✅ 轨迹提取模块加载成功")
    print("\n使用示例：")
    print("  tracks, binary = extract_tracks(data, sampling_rate, parameters)")
    print("  fig = plot_tracks(data, tracks, sampling_rate)")
