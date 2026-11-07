"""
脊线检测 - 用于DAS车辆轨迹提取
复用 scikit-image 和 scipy 的现成功能
"""
import numpy as np
from scipy import ndimage
from skimage.filters import frangi, meijering, sato
from skimage.morphology import skeletonize, remove_small_objects
from skimage.measure import label, regionprops


def ridge_detection_frangi(data, sigmas=range(1, 5, 1), alpha=0.5, beta=0.5, gamma=15):
    """
    使用 Frangi 滤波器检测脊线（血管检测算法）

    参数：
        data: (channels, samples) 预处理后的数据
        sigmas: 检测的尺度范围（通道数单位）
        alpha, beta, gamma: Frangi滤波器参数

    返回：
        ridge_response: 脊线响应图
        ridge_mask: 二值脊线掩膜
    """
    print("使用 Frangi 滤波器检测脊线...")

    # Frangi 滤波器（专门用于检测管状/线状结构）
    # 这是医学图像血管检测的标准方法，完美适合轨迹检测
    ridge_response = frangi(
        data,
        sigmas=sigmas,      # 多尺度检测
        alpha=alpha,        # 板状vs管状的权重
        beta=beta,          # 二阶导数的权重
        gamma=gamma,        # Hessian归一化
        black_ridges=False  # 检测亮脊线（车辆是正信号）
    )

    # 自适应阈值
    threshold = np.percentile(ridge_response, 95)
    ridge_mask = ridge_response > threshold

    print(f"  脊线响应范围: [{ridge_response.min():.3f}, {ridge_response.max():.3f}]")
    print(f"  阈值: {threshold:.3f}")
    print(f"  检测到的像素数: {ridge_mask.sum()}")

    return ridge_response, ridge_mask


def ridge_detection_meijering(data, sigmas=range(1, 5, 1), alpha=None):
    """
    使用 Meijering 滤波器检测脊线（神经元检测算法）

    参数：
        data: (channels, samples)
        sigmas: 尺度范围
        alpha: 灵敏度参数（None=自动）

    返回：
        ridge_response, ridge_mask
    """
    print("使用 Meijering 滤波器检测脊线...")

    ridge_response = meijering(
        data,
        sigmas=sigmas,
        alpha=alpha,
        black_ridges=False
    )

    threshold = np.percentile(ridge_response, 95)
    ridge_mask = ridge_response > threshold

    return ridge_response, ridge_mask


def ridge_detection_sato(data, sigmas=range(1, 5, 1), black_ridges=False):
    """
    使用 Sato 滤波器检测脊线

    参数：
        data: (channels, samples)
        sigmas: 尺度范围
        black_ridges: 是否检测暗脊线

    返回：
        ridge_response, ridge_mask
    """
    print("使用 Sato 滤波器检测脊线...")

    ridge_response = sato(
        data,
        sigmas=sigmas,
        black_ridges=black_ridges
    )

    threshold = np.percentile(ridge_response, 95)
    ridge_mask = ridge_response > threshold

    return ridge_response, ridge_mask


def extract_skeleton(ridge_mask, min_size=50):
    """
    从脊线掩膜提取骨架

    参数：
        ridge_mask: 二值脊线掩膜
        min_size: 最小连通域大小（像素数）

    返回：
        skeleton: 骨架二值图
        cleaned_mask: 清理后的掩膜
    """
    print("提取骨架...")

    # 1. 去除小噪声块
    cleaned_mask = remove_small_objects(ridge_mask, min_size=min_size)
    print(f"  去除小对象后: {cleaned_mask.sum()} 像素")

    # 2. 骨架化（Zhang-Suen算法）
    skeleton = skeletonize(cleaned_mask)
    print(f"  骨架像素数: {skeleton.sum()}")

    return skeleton, cleaned_mask


def skeleton_to_tracks(skeleton, min_length=50):
    """
    从骨架提取轨迹

    参数：
        skeleton: 骨架二值图
        min_length: 最小轨迹长度（通道数）

    返回：
        tracks: 轨迹列表
    """
    print("从骨架提取轨迹...")

    # 1. 连通域标记
    labeled = label(skeleton, connectivity=2)  # 8连通
    num_regions = labeled.max()
    print(f"  找到 {num_regions} 个连通域")

    # 2. 提取每个连通域的坐标
    tracks = []
    regions = regionprops(labeled)

    for region in regions:
        coords = region.coords  # (N, 2) - [channel, time]

        if len(coords) < min_length:
            continue

        # 按时间排序
        sorted_idx = np.argsort(coords[:, 1])
        coords_sorted = coords[sorted_idx]

        track = {
            'channels': coords_sorted[:, 0],
            'times': coords_sorted[:, 1],
            'length': len(coords_sorted)
        }
        tracks.append(track)

    print(f"  提取 {len(tracks)} 条轨迹（长度 ≥ {min_length}）")

    return tracks


def ridge_based_tracking(data, method='frangi', sigmas=range(1, 5, 1),
                        min_size=50, min_length=50):
    """
    完整的基于脊线检测的轨迹提取

    参数：
        data: (channels, samples) 预处理后的数据
        method: 'frangi', 'meijering', 或 'sato'
        sigmas: 检测尺度范围
        min_size: 最小连通域大小
        min_length: 最小轨迹长度

    返回：
        tracks: 轨迹列表
        ridge_response: 脊线响应图
        skeleton: 骨架
    """
    print("="*70)
    print(f"基于脊线检测的轨迹提取 (method={method})")
    print("="*70)

    # 1. 脊线检测
    if method == 'frangi':
        ridge_response, ridge_mask = ridge_detection_frangi(data, sigmas=sigmas)
    elif method == 'meijering':
        ridge_response, ridge_mask = ridge_detection_meijering(data, sigmas=sigmas)
    elif method == 'sato':
        ridge_response, ridge_mask = ridge_detection_sato(data, sigmas=sigmas)
    else:
        raise ValueError(f"未知方法: {method}")

    # 2. 骨架提取
    skeleton, cleaned_mask = extract_skeleton(ridge_mask, min_size=min_size)

    # 3. 轨迹提取
    tracks = skeleton_to_tracks(skeleton, min_length=min_length)

    print("="*70)
    print(f"完成！找到 {len(tracks)} 条轨迹")
    print("="*70)

    return tracks, ridge_response, skeleton


def plot_ridge_detection(data, ridge_response, skeleton, tracks,
                        sampling_rate, channel_from=1):
    """
    可视化脊线检测结果
    """
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True, sharey=True)
    axes = axes.ravel()

    extent = [0, data.shape[1] / sampling_rate,
              channel_from, channel_from + data.shape[0]]

    # 1. 原始数据
    vmax = np.percentile(np.abs(data), 99)
    axes[0].imshow(data, aspect='auto', cmap='RdBu_r',
                  extent=extent, vmin=-vmax, vmax=vmax,
                  origin='lower', interpolation='none')
    axes[0].set_title('1. Original Data', fontweight='bold')
    axes[0].set_ylabel('Channel')

    # 2. 脊线响应
    axes[1].imshow(ridge_response, aspect='auto', cmap='hot',
                  extent=extent, origin='lower', interpolation='none')
    axes[1].set_title('2. Ridge Response (Frangi/Meijering/Sato)', fontweight='bold')

    # 3. 骨架
    axes[2].imshow(skeleton, aspect='auto', cmap='gray',
                  extent=extent, origin='lower', interpolation='none')
    axes[2].set_title('3. Skeleton', fontweight='bold')
    axes[2].set_ylabel('Channel')
    axes[2].set_xlabel('Time (s)')

    # 4. 提取的轨迹
    axes[3].imshow(data, aspect='auto', cmap='RdBu_r',
                  extent=extent, vmin=-vmax, vmax=vmax,
                  origin='lower', interpolation='none', alpha=0.5)

    colors = plt.cm.tab10(np.linspace(0, 1, len(tracks)))
    for i, (track, color) in enumerate(zip(tracks, colors)):
        channels = track['channels'] + channel_from
        times = track['times'] / sampling_rate
        axes[3].plot(times, channels, 'o-', color=color, linewidth=2.5,
                    markersize=4, label=f"Track {i+1} ({track['length']}ch)",
                    alpha=0.9)

    axes[3].set_title(f'4. Extracted Tracks ({len(tracks)} tracks)', fontweight='bold')
    axes[3].set_xlabel('Time (s)')
    if len(tracks) > 0:
        axes[3].legend(loc='upper right', fontsize=8)

    plt.tight_layout()
    return fig


# ========== 对比不同方法 ==========
def compare_ridge_methods(data, sampling_rate, channel_from=1):
    """对比三种脊线检测方法"""
    import matplotlib.pyplot as plt

    methods = ['frangi', 'meijering', 'sato']
    results = {}

    for method in methods:
        print(f"\n{'='*70}")
        print(f"测试方法: {method.upper()}")
        print(f"{'='*70}")

        tracks, ridge_response, skeleton = ridge_based_tracking(
            data, method=method,
            sigmas=range(1, 6, 1),
            min_size=30,
            min_length=40
        )

        results[method] = {
            'tracks': tracks,
            'ridge_response': ridge_response,
            'skeleton': skeleton
        }

    # 可视化对比
    fig, axes = plt.subplots(3, 3, figsize=(18, 12), sharex=True, sharey=True)
    extent = [0, data.shape[1] / sampling_rate,
              channel_from, channel_from + data.shape[0]]

    for i, method in enumerate(methods):
        result = results[method]

        # 脊线响应
        axes[i, 0].imshow(result['ridge_response'], aspect='auto', cmap='hot',
                         extent=extent, origin='lower')
        axes[i, 0].set_title(f'{method.upper()}: Ridge Response', fontweight='bold')
        if i == 2:
            axes[i, 0].set_xlabel('Time (s)')
        axes[i, 0].set_ylabel('Channel')

        # 骨架
        axes[i, 1].imshow(result['skeleton'], aspect='auto', cmap='gray',
                         extent=extent, origin='lower')
        axes[i, 1].set_title(f'{method.upper()}: Skeleton', fontweight='bold')
        if i == 2:
            axes[i, 1].set_xlabel('Time (s)')

        # 轨迹
        vmax = np.percentile(np.abs(data), 99)
        axes[i, 2].imshow(data, aspect='auto', cmap='RdBu_r',
                         extent=extent, vmin=-vmax, vmax=vmax,
                         origin='lower', alpha=0.5)

        tracks = result['tracks']
        colors = plt.cm.tab10(np.linspace(0, 1, len(tracks)))
        for j, (track, color) in enumerate(zip(tracks, colors)):
            channels = track['channels'] + channel_from
            times = track['times'] / sampling_rate
            axes[i, 2].plot(times, channels, 'o-', color=color, linewidth=2,
                           markersize=3, alpha=0.9)

        axes[i, 2].set_title(f'{method.upper()}: {len(tracks)} Tracks', fontweight='bold')
        if i == 2:
            axes[i, 2].set_xlabel('Time (s)')

    plt.tight_layout()
    return fig, results


if __name__ == '__main__':
    print("✅ 脊线检测模块加载成功")
    print("\n主要函数：")
    print("  - ridge_based_tracking(): 一键提取轨迹")
    print("  - compare_ridge_methods(): 对比三种方法")
    print("  - plot_ridge_detection(): 可视化结果")
    print("\n示例：")
    print("  tracks, ridge_response, skeleton = ridge_based_tracking(data)")
    print("  fig = plot_ridge_detection(data, ridge_response, skeleton, tracks, sampling_rate)")
