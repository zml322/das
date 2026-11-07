# Hilbert包络使用指南

## 📖 什么是Hilbert包络？

Hilbert包络是TTMuTian论文中使用的预处理方法，用于：
- 提取信号的**瞬时幅度**（能量变化趋势）
- 忽略快速振荡细节
- 让车辆轨迹更平滑、连续
- 抑制峰值噪声

### 数学公式

```
E(t) = √[x²(t) + H²[x(t)]]
```

其中：
- `x(t)` 是原始信号
- `H[x(t)]` 是Hilbert变换
- `E(t)` 是包络（总是 ≥ 0）

---

## 🔧 已集成功能

### 1. `filter_data` 函数

新增参数：
- `use_envelope=False`：是否启用Hilbert包络
- `envelope_smoothing=0.25`：平滑窗口（秒）

### 2. `process` 函数

新增参数：
- `use_envelope=False`：是否启用Hilbert包络
- `envelope_smoothing=0.25`：平滑窗口（秒）

---

## 💡 使用示例

### 示例1：只用包络（不用F-K滤波）

```python
data, sampling_rate = process(
    source_path,
    channel_from=321, channel_to=520,
    downsample_factor=50,
    use_envelope=True,         # 启用包络
    envelope_smoothing=0.25,   # 0.25秒平滑
    use_fk=False,              # 不用F-K滤波
)
```

**适用场景**：
- 数据噪声大，轨迹不清晰
- 需要平滑的能量表示

---

### 示例2：包络 + F-K滤波（TTMuTian推荐组合）

```python
data, sampling_rate = process(
    source_path,
    channel_from=321, channel_to=520,
    downsample_factor=50,
    use_envelope=True,         # 启用包络
    envelope_smoothing=0.25,   # 0.25秒平滑
    use_fk=True,               # 启用F-K滤波
    direction='decreasing',    # 方向过滤
    maximum_speed_kmh=120.0,
)
```

**适用场景**：
- 杂糅轨迹需要方向分离
- 噪声大且需要平滑

---

### 示例3：调整平滑参数对比

```python
# 不平滑（包络有快速波动）
data_no_smooth, _ = process(..., use_envelope=True, envelope_smoothing=0.0)

# 轻度平滑（推荐）
data_light, _ = process(..., use_envelope=True, envelope_smoothing=0.1)

# 中度平滑（TTMuTian默认）
data_medium, _ = process(..., use_envelope=True, envelope_smoothing=0.25)

# 重度平滑（可能丢失细节）
data_heavy, _ = process(..., use_envelope=True, envelope_smoothing=0.5)
```

**调参建议**：
- `0.0`：不平滑，保留所有细节，但可能有噪声
- `0.1-0.25`：推荐范围，平衡平滑和细节
- `0.5+`：过度平滑，可能合并相近事件

---

## 📊 包络 vs 原始信号

### 原始信号特点
- ✅ 保留完整波形信息（相位、极性）
- ✅ 可以区分压缩/拉伸
- ⚠️ 有正有负，振荡明显
- ⚠️ 噪声毛刺突出

### 包络信号特点
- ✅ 只有正值（≥ 0），代表能量
- ✅ 轨迹更平滑连续
- ✅ 噪声抑制更好
- ⚠️ 丢失相位信息
- ⚠️ 无法区分压缩/拉伸

---

## 🎨 可视化差异

### 色图选择

```python
# 原始信号用双极色图（红蓝）
if use_envelope:
    cmap = 'magma'  # 单极色图
    vmin, vmax = 0, np.percentile(data, 99)
else:
    cmap = 'RdBu_r'  # 双极色图
    vmax = np.percentile(np.abs(data), 99)
    vmin, vmax = -vmax, vmax
```

---

## 🔬 处理流程

```
原始DAS数据
    ↓
1. 去趋势
    ↓
2. 带通滤波 (0.01-1.0 Hz)
    ↓
3. 共模噪声去除
    ↓
4. [可选] Hilbert包络提取 ← 新增步骤
    ├─ Hilbert变换
    ├─ 提取瞬时幅度
    └─ 高斯平滑
    ↓
5. MAD归一化
    ↓
6. [可选] F-K方向滤波
    ↓
输出处理后数据
```

---

## 📈 TTMuTian论文中的效果

### 优点（论文Figure 3）
1. **轨迹更明显**：包络图中车辆轨迹线更连续
2. **噪声抑制**：峰值噪声（红箭头标注的）被平滑
3. **便于U-Net训练**：包络代表能量，更容易合成训练数据

### 适用场景
- 数据噪声大
- 需要送入深度学习模型
- 轨迹需要更高的连续性

---

## ⚙️ 性能考虑

### 计算开销
- **Hilbert变换**：FFT操作，复杂度 O(N log N)
- **高斯平滑**：卷积操作，复杂度 O(N × kernel_size)

### 优化建议
- 分批处理（已实现）
- 降采样后再计算包络
- 调整平滑窗口平衡速度和效果

---

## 🧪 快速测试

运行notebook中的最后一个cell：

```python
# 自动对比四种方法
# 1. Baseline (原始)
# 2. Envelope only (只用包络)
# 3. F-K only (只用F-K)
# 4. Envelope + F-K (组合)
```

查看生成的对比图，选择最适合你数据的方法。

---

## 📚 参考文献

1. **TTMuTian (2024)**
   - "Intelligent Traffic Monitoring with Distributed Acoustic Sensing"
   - Seismological Research Letters
   - https://arxiv.org/pdf/2403.02791

2. **Hilbert变换理论**
   - scipy.signal.hilbert文档
   - https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.hilbert.html

---

## 🤝 需要帮助？

- 不确定是否用包络 → 先运行对比测试
- 轨迹不够平滑 → 增大 `envelope_smoothing`
- 丢失弱信号 → 减小 `envelope_smoothing`
- 计算太慢 → 先降采样再计算包络

祝实验顺利！🚀
