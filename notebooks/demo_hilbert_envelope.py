"""演示Hilbert包络在DAS车辆检测中的应用"""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from daspy.basic_tools.filter import bandpass
from daspy.basic_tools.preprocessing import normalization, downsampling, detrending
from daspy.advanced_tools.denoising import common_mode_noise_removal


def compute_hilbert_envelope(data, smoothing_seconds=0.25, sampling_rate=20.0):
    """
    计算Hilbert包络（沿时间轴）

    参数：
        data: (channels, samples) 数组
        smoothing_seconds: 高斯平滑窗口，单位秒
        sampling_rate: 采样率 Hz

    返回：
        envelope: (channels, samples) 包络数组，值≥0
    """
    envelope = np.empty_like(data, dtype=np.float32)

    for i in range(len(data)):
        # 1. Hilbert变换
        analytic_signal = signal.hilbert(data[i])

        # 2. 计算瞬时幅度（包络）
        amplitude = np.abs(analytic_signal)

        # 3. 高斯平滑（去除快速振荡）
        if smoothing_seconds > 0:
            sigma = smoothing_seconds * sampling_rate  # 转换为采样点数
            amplitude = gaussian_filter1d(amplitude, sigma=sigma, mode='nearest')

        envelope[i] = amplitude.astype(np.float32)

    return envelope


def preprocess_data():
    """读取并预处理数据"""
    file_path = Path(r'D:\projects\das\下午\ch1_2026-09-05-13-51-27_2_30720_520_1000.bin')
    header = np.fromfile(file_path, dtype='<f4', count=20)
    channels, samples = int(header[8]), int(header[7])
    sampling_rate = float(header[9])

    # 读取通道321-520
    data = np.memmap(file_path, dtype='<f4', mode='r', offset=80, shape=(channels, samples))
    selected = data[320:520, :].copy()

    # 降采样
    downsampled = downsampling(selected, tint=50)
    sampling_rate /= 50

    # 去趋势
    detrended = np.empty_like(downsampled, dtype=np.float32)
    for i in range(len(downsampled)):
        detrended[i] = detrending(downsampled[i])

    # 带通滤波
    filtered = bandpass(detrended, fs=sampling_rate, freqmin=0.01, freqmax=1.0,
                       corners=4, zerophase=True)

    # 共模去除
    common = np.median(filtered, axis=0)
    if np.sum(common.astype(float) ** 2) > np.finfo(float).eps:
        filtered = common_mode_noise_removal(filtered, method='median')

    return filtered.astype(np.float32), sampling_rate


def compare_original_vs_envelope():
    """对比原始信号和包络信号"""
    print("读取并预处理数据...")
    data, sampling_rate = preprocess_data()
    print(f"数据形状: {data.shape}, 采样率: {sampling_rate} Hz\n")

    # 计算包络（不同平滑参数）
    print("计算Hilbert包络...")
    smoothing_values = [0.0, 0.1, 0.25, 0.5]
    envelopes = {}

    for smooth in smoothing_values:
        env = compute_hilbert_envelope(data, smoothing_seconds=smooth,
                                      sampling_rate=sampling_rate)
        envelopes[smooth] = env
        print(f"  平滑 {smooth}s: 完成")

    # 绘制对比图
    fig, axes = plt.subplots(3, 2, figsize=(16, 12), sharex=True, sharey=True)
    axes = axes.ravel()

    extent = [0, data.shape[1] / sampling_rate, 321, 520]

    # 原始信号（双极性，有正有负）
    vmax_orig = np.percentile(np.abs(data), 99)
    axes[0].imshow(data, aspect='auto', cmap='RdBu_r',
                  extent=extent, vmin=-vmax_orig, vmax=vmax_orig,
                  origin='lower', interpolation='none')
    axes[0].set_title('Original Signal (bipolar, ±amplitude)', fontsize=11, fontweight='bold')
    axes[0].set_ylabel('Channel')

    # MAD归一化后的原始信号（这是你当前用的）
    data_normalized = normalization(data, method='MAD')
    axes[1].imshow(data_normalized, aspect='auto', cmap='RdBu_r',
                  extent=extent, vmin=-5, vmax=5,
                  origin='lower', interpolation='none')
    axes[1].set_title('MAD Normalized (current method)', fontsize=11, fontweight='bold')

    # 不同平滑参数的包络
    for idx, (smooth, env) in enumerate(envelopes.items(), 2):
        # 包络用magma色图（单极性，只有正值）
        vmax_env = np.percentile(env, 99)
        axes[idx].imshow(env, aspect='auto', cmap='magma',
                        extent=extent, vmin=0, vmax=vmax_env,
                        origin='lower', interpolation='none')
        axes[idx].set_title(f'Hilbert Envelope (smooth={smooth}s)',
                           fontsize=11, fontweight='bold')

        if idx % 2 == 0:
            axes[idx].set_ylabel('Channel')
        if idx >= 4:
            axes[idx].set_xlabel('Time (s)')

    plt.tight_layout()

    output_path = Path('figures')
    output_path.mkdir(exist_ok=True)
    fig.savefig(output_path / 'hilbert_envelope_comparison.png', dpi=150, bbox_inches='tight')
    print(f"\nComparison saved: {output_path / 'hilbert_envelope_comparison.png'}")
    plt.show()

    return data, envelopes


def analyze_single_channel():
    """分析单个通道上的包络效果"""
    data, sampling_rate = preprocess_data()

    # 选择一个有明显信号的通道（中间通道）
    channel_idx = 100
    trace = data[channel_idx, :]

    # 计算包络
    envelope = compute_hilbert_envelope(data[channel_idx:channel_idx+1, :],
                                       smoothing_seconds=0.25,
                                       sampling_rate=sampling_rate)[0]

    time = np.arange(len(trace)) / sampling_rate

    # 绘图
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # 原始波形
    axes[0].plot(time, trace, 'b-', linewidth=0.5, alpha=0.7, label='Original signal')
    axes[0].plot(time, envelope, 'r-', linewidth=1.5, label='Hilbert envelope')
    axes[0].plot(time, -envelope, 'r-', linewidth=1.5, alpha=0.5)
    axes[0].set_ylabel('Amplitude')
    axes[0].set_title(f'Channel {321 + channel_idx}: Original vs Envelope', fontweight='bold')
    axes[0].legend(loc='upper right')
    axes[0].grid(alpha=0.3)
    axes[0].axhline(0, color='k', linewidth=0.5, linestyle='--')

    # 只显示包络
    axes[1].plot(time, envelope, 'r-', linewidth=1.0)
    axes[1].fill_between(time, 0, envelope, alpha=0.3, color='red')
    axes[1].set_ylabel('Envelope amplitude')
    axes[1].set_xlabel('Time (s)')
    axes[1].set_title('Envelope only (always ≥ 0)', fontweight='bold')
    axes[1].grid(alpha=0.3)

    plt.tight_layout()

    output_path = Path('figures')
    fig.savefig(output_path / 'hilbert_envelope_single_channel.png', dpi=150, bbox_inches='tight')
    print(f"Single channel analysis saved: {output_path / 'hilbert_envelope_single_channel.png'}")
    plt.show()


def main():
    print("="*70)
    print("Hilbert包络演示 - TTMuTian论文方法")
    print("="*70)
    print("\n核心思想：")
    print("  1. 包络提取信号的能量变化趋势，忽略快速振荡细节")
    print("  2. 包络总是 ≥ 0，代表瞬时能量/幅度")
    print("  3. 车辆轨迹在包络图中更平滑、连续")
    print("  4. 峰值噪声被抑制，信噪比提高")
    print("\n" + "="*70 + "\n")

    # 分析单通道
    print("1. 单通道波形分析...")
    analyze_single_channel()

    print("\n" + "="*70 + "\n")

    # 对比全图
    print("2. 不同平滑参数对比...")
    compare_original_vs_envelope()

    print("\n" + "="*70)
    print("关键观察：")
    print("  - 原始信号：有正有负振荡，噪声明显")
    print("  - 包络信号：只有正值，轨迹更清晰")
    print("  - 平滑参数：越大越平滑，但可能丢失细节")
    print("  - 建议：0.25s 是比较好的折中")
    print("="*70)


if __name__ == '__main__':
    main()
