"""深入理解Hilbert变换和包络提取"""
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import hilbert
from scipy.ndimage import gaussian_filter1d


def explain_hilbert_step_by_step():
    """一步步展示Hilbert变换的每个步骤"""

    # 1. 创建一个简单的调制信号（模拟DAS车辆信号）
    # 这就像一个车辆经过时的信号：慢慢增强，然后减弱
    t = np.linspace(0, 2, 1000)  # 2秒，1000个采样点

    # 载波（快速振荡）：高频振动
    carrier_freq = 20  # Hz，模拟DAS的快速振荡
    carrier = np.sin(2 * np.pi * carrier_freq * t)

    # 调制包络（慢变化）：车辆接近-经过-离开的能量变化
    envelope_true = np.exp(-((t - 1.0) ** 2) / 0.1)  # 高斯包络，峰值在1秒处

    # 调制信号 = 包络 × 载波
    signal = envelope_true * carrier

    # 添加一些噪声
    signal += 0.1 * np.random.randn(len(signal))

    print("="*70)
    print("步骤1: 原始信号构造")
    print("="*70)
    print(f"信号长度: {len(signal)} 个采样点")
    print(f"时间范围: {t[0]:.2f} - {t[-1]:.2f} 秒")
    print(f"载波频率: {carrier_freq} Hz (快速振荡)")
    print(f"包络形状: 高斯型 (模拟车辆经过)")
    print()

    # 2. 应用Hilbert变换
    print("="*70)
    print("步骤2: Hilbert变换")
    print("="*70)

    analytic_signal = hilbert(signal)
    print(f"原始信号: 实数数组, shape={signal.shape}")
    print(f"解析信号: 复数数组, shape={analytic_signal.shape}")
    print(f"  实部 = 原始信号 x(t)")
    print(f"  虚部 = Hilbert变换 H[x(t)]")
    print()

    # 分解解析信号
    real_part = analytic_signal.real  # 实部 = 原始信号
    imag_part = analytic_signal.imag  # 虚部 = Hilbert变换

    print(f"实部统计: mean={real_part.mean():.3f}, std={real_part.std():.3f}")
    print(f"虚部统计: mean={imag_part.mean():.3f}, std={imag_part.std():.3f}")
    print()

    # 3. 提取瞬时幅度（包络）
    print("="*70)
    print("步骤3: 提取包络")
    print("="*70)

    envelope_extracted = np.abs(analytic_signal)
    print(f"包络公式: E(t) = √[x²(t) + H²[x(t)]]")
    print(f"包络 = |解析信号| = 复数的模")
    print(f"包络统计: mean={envelope_extracted.mean():.3f}, std={envelope_extracted.std():.3f}")
    print(f"包络范围: [{envelope_extracted.min():.3f}, {envelope_extracted.max():.3f}]")
    print()

    # 4. 高斯平滑
    print("="*70)
    print("步骤4: 高斯平滑")
    print("="*70)

    sampling_rate = len(signal) / (t[-1] - t[0])
    smoothing_seconds = 0.05  # 50ms平滑窗口
    sigma = smoothing_seconds * sampling_rate

    envelope_smoothed = gaussian_filter1d(envelope_extracted, sigma=sigma, mode='nearest')

    print(f"采样率: {sampling_rate:.1f} Hz")
    print(f"平滑窗口: {smoothing_seconds} 秒 = {sigma:.1f} 个采样点")
    print(f"平滑后统计: mean={envelope_smoothed.mean():.3f}, std={envelope_smoothed.std():.3f}")
    print()

    # 5. 绘图展示
    print("="*70)
    print("步骤5: 可视化")
    print("="*70)

    fig, axes = plt.subplots(5, 1, figsize=(14, 12), sharex=True)

    # 子图1: 真实包络（我们要提取的目标）
    axes[0].plot(t, envelope_true, 'g-', linewidth=2, label='True envelope')
    axes[0].fill_between(t, 0, envelope_true, alpha=0.3, color='green')
    axes[0].set_ylabel('Amplitude')
    axes[0].set_title('1. True Envelope (目标：车辆能量变化)', fontweight='bold')
    axes[0].legend(loc='upper right')
    axes[0].grid(alpha=0.3)

    # 子图2: 调制信号（原始输入）
    axes[1].plot(t, signal, 'b-', linewidth=0.5, alpha=0.7, label='Modulated signal')
    axes[1].plot(t, envelope_true, 'g--', linewidth=2, alpha=0.8, label='True envelope')
    axes[1].plot(t, -envelope_true, 'g--', linewidth=2, alpha=0.8)
    axes[1].set_ylabel('Amplitude')
    axes[1].set_title('2. Original Signal = Envelope × Carrier (快速振荡 + 噪声)', fontweight='bold')
    axes[1].legend(loc='upper right')
    axes[1].grid(alpha=0.3)
    axes[1].axhline(0, color='k', linewidth=0.5, linestyle='-')

    # 子图3: Hilbert变换（虚部）
    axes[2].plot(t, signal, 'b-', linewidth=0.5, alpha=0.5, label='Original (real part)')
    axes[2].plot(t, imag_part, 'r-', linewidth=0.5, alpha=0.7, label='Hilbert transform (imaginary part)')
    axes[2].set_ylabel('Amplitude')
    axes[2].set_title('3. Hilbert Transform: 90° Phase Shift (正交分量)', fontweight='bold')
    axes[2].legend(loc='upper right')
    axes[2].grid(alpha=0.3)
    axes[2].axhline(0, color='k', linewidth=0.5, linestyle='-')

    # 子图4: 提取的包络（未平滑）
    axes[3].plot(t, envelope_extracted, 'orange', linewidth=1, alpha=0.8, label='Extracted envelope (raw)')
    axes[3].plot(t, envelope_true, 'g--', linewidth=2, alpha=0.6, label='True envelope')
    axes[3].fill_between(t, 0, envelope_extracted, alpha=0.2, color='orange')
    axes[3].set_ylabel('Amplitude')
    axes[3].set_title('4. Extracted Envelope = |Analytic Signal| (有噪声波动)', fontweight='bold')
    axes[3].legend(loc='upper right')
    axes[3].grid(alpha=0.3)

    # 子图5: 平滑后的包络（最终结果）
    axes[4].plot(t, envelope_smoothed, 'r-', linewidth=2, label='Smoothed envelope')
    axes[4].plot(t, envelope_true, 'g--', linewidth=2, alpha=0.6, label='True envelope')
    axes[4].fill_between(t, 0, envelope_smoothed, alpha=0.3, color='red')
    axes[4].set_ylabel('Amplitude')
    axes[4].set_xlabel('Time (s)')
    axes[4].set_title('5. Final Smoothed Envelope (高斯平滑后)', fontweight='bold')
    axes[4].legend(loc='upper right')
    axes[4].grid(alpha=0.3)

    plt.tight_layout()
    from pathlib import Path
    output_path = Path('figures')
    output_path.mkdir(exist_ok=True)
    plt.savefig(output_path / 'hilbert_transform_explained.png', dpi=150, bbox_inches='tight')
    print(f"图像已保存: {output_path / 'hilbert_transform_explained.png'}")
    plt.show()

    # 6. 数值验证
    print("\n" + "="*70)
    print("步骤6: 数值验证")
    print("="*70)

    # 包络提取误差
    mse = np.mean((envelope_smoothed - envelope_true) ** 2)
    print(f"平滑包络 vs 真实包络 MSE: {mse:.6f}")

    # 相关系数
    correlation = np.corrcoef(envelope_smoothed, envelope_true)[0, 1]
    print(f"相关系数: {correlation:.4f}")

    print("\n✅ Hilbert变换成功提取了信号包络！")


def explain_why_hilbert_works():
    """解释为什么Hilbert变换能提取包络"""

    print("\n" + "="*70)
    print("理论解释：为什么Hilbert变换能提取包络？")
    print("="*70)
    print()

    print("📐 数学原理：")
    print("-" * 70)
    print("1. 调制信号可以表示为：")
    print("   x(t) = A(t) · cos(ωt + φ)")
    print("   其中 A(t) 是包络（慢变化），cos(ωt+φ) 是载波（快速振荡）")
    print()

    print("2. Hilbert变换 H[x(t)] 将信号相位移动 90°：")
    print("   H[cos(ωt)] = sin(ωt)")
    print("   H[sin(ωt)] = -cos(ωt)")
    print()

    print("3. 构造解析信号（复数形式）：")
    print("   z(t) = x(t) + j·H[x(t)]")
    print("        = A(t)·cos(ωt) + j·A(t)·sin(ωt)")
    print("        = A(t)·exp(j·ωt)")
    print()

    print("4. 提取包络（取模）：")
    print("   |z(t)| = |A(t)·exp(j·ωt)| = A(t)")
    print("   因为 |exp(j·ωt)| = 1")
    print()

    print("✨ 关键洞察：")
    print("-" * 70)
    print("• 原始信号和Hilbert变换是正交的（90°相位差）")
    print("• 它们构成了一个复平面上的向量")
    print("• 向量的长度（模）就是包络幅度")
    print("• 向量的角度就是瞬时相位（我们不需要）")
    print()

    print("🎯 类比理解：")
    print("-" * 70)
    print("想象一个在圆周运动的点：")
    print("  x(t) = A(t)·cos(θ)  ← 水平坐标")
    print("  y(t) = A(t)·sin(θ)  ← 垂直坐标")
    print("  距离原点的距离 = √(x² + y²) = A(t)  ← 包络")
    print()
    print("Hilbert变换就是找到这个'垂直坐标'，")
    print("然后用勾股定理算出'到原点的距离'。")
    print()


def compare_with_alternatives():
    """对比其他包络提取方法"""

    print("\n" + "="*70)
    print("其他包络提取方法对比")
    print("="*70)
    print()

    # 创建测试信号
    t = np.linspace(0, 2, 1000)
    carrier_freq = 20
    envelope_true = np.exp(-((t - 1.0) ** 2) / 0.1)
    signal = envelope_true * np.sin(2 * np.pi * carrier_freq * t)
    signal += 0.05 * np.random.randn(len(signal))

    # 方法1: 直接取绝对值
    envelope_abs = np.abs(signal)

    # 方法2: Hilbert变换
    envelope_hilbert = np.abs(hilbert(signal))

    # 方法3: 滑动窗口RMS（STA/LTA的简化版）
    window = 50
    envelope_rms = np.zeros_like(signal)
    for i in range(len(signal)):
        start = max(0, i - window // 2)
        end = min(len(signal), i + window // 2)
        envelope_rms[i] = np.sqrt(np.mean(signal[start:end] ** 2))

    # 平滑所有方法以便对比
    from scipy.ndimage import gaussian_filter1d
    sigma = 25
    envelope_abs_smooth = gaussian_filter1d(envelope_abs, sigma=sigma)
    envelope_hilbert_smooth = gaussian_filter1d(envelope_hilbert, sigma=sigma)
    envelope_rms_smooth = gaussian_filter1d(envelope_rms, sigma=sigma)

    # 绘图对比
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # 上图：原始信号
    axes[0].plot(t, signal, 'gray', linewidth=0.5, alpha=0.5, label='Original signal')
    axes[0].plot(t, envelope_true, 'g-', linewidth=2, label='True envelope')
    axes[0].set_ylabel('Amplitude')
    axes[0].set_title('Original Signal', fontweight='bold')
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    # 下图：三种方法对比
    axes[1].plot(t, envelope_true, 'g-', linewidth=3, label='True envelope', alpha=0.7)
    axes[1].plot(t, envelope_abs_smooth, 'b--', linewidth=2, label='Method 1: Abs + Smooth', alpha=0.8)
    axes[1].plot(t, envelope_hilbert_smooth, 'r-', linewidth=2, label='Method 2: Hilbert + Smooth', alpha=0.8)
    axes[1].plot(t, envelope_rms_smooth, 'orange', linewidth=2, linestyle=':', label='Method 3: RMS + Smooth', alpha=0.8)
    axes[1].set_ylabel('Envelope')
    axes[1].set_xlabel('Time (s)')
    axes[1].set_title('Envelope Extraction Methods Comparison', fontweight='bold')
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    plt.tight_layout()
    from pathlib import Path
    output_path = Path('figures')
    plt.savefig(output_path / 'envelope_methods_comparison.png', dpi=150, bbox_inches='tight')
    print(f"对比图已保存: {output_path / 'envelope_methods_comparison.png'}")
    plt.show()

    # 计算误差
    print("\n方法对比（与真实包络的误差）：")
    print("-" * 70)

    for name, env in [('直接取绝对值', envelope_abs_smooth),
                      ('Hilbert变换', envelope_hilbert_smooth),
                      ('滑动RMS', envelope_rms_smooth)]:
        mse = np.mean((env - envelope_true) ** 2)
        corr = np.corrcoef(env, envelope_true)[0, 1]
        print(f"{name:15s}: MSE={mse:.6f}, 相关系数={corr:.4f}")

    print()
    print("🏆 结论：")
    print("  Hilbert变换在不需要调整窗口参数的情况下，")
    print("  就能精确提取包络，且对信号形状更鲁棒。")
    print()


if __name__ == '__main__':
    # 主演示
    explain_hilbert_step_by_step()

    # 理论解释
    explain_why_hilbert_works()

    # 方法对比
    compare_with_alternatives()

    print("\n" + "="*70)
    print("总结")
    print("="*70)
    print("""
在你的代码中：
    analytic_signal = hilbert(filtered[row])  # 步骤2: 构造解析信号
    amplitude = np.abs(analytic_signal)       # 步骤3: 提取包络
    amplitude = gaussian_filter1d(...)        # 步骤4: 平滑

这三行做的事情：
    1. 找到信号的'正交伙伴'（相位移90°）
    2. 用勾股定理算出'瞬时能量'
    3. 平滑掉剩余的快速波动

最终得到：干净的、平滑的、单极性的车辆能量轨迹。
    """)
