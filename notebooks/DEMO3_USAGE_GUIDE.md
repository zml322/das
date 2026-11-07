# Demo3 完整使用指南

## 📚 概述

`demo3.ipynb` 现在集成了完整的DAS车辆检测流程：

1. **数据读取** - 跨文件读取，自动处理边界
2. **预处理** - 去趋势、滤波、共模去除、Hilbert包络
3. **F-K滤波** - 方向分离
4. **轨迹提取** - 峰值检测 + 霍夫变换
5. **可视化** - 叠加轨迹在数据上

---

## 🔧 核心功能模块

### 1. 数据预处理 (`process` 函数)

```python
data, sampling_rate = process(
    source_path,                    # 数据文件路径
    start_seconds=0.0,              # 起始时间
    duration=60.0,                  # 持续时间
    channel_from=321,               # 起始通道
    channel_to=520,                 # 结束通道
    
    # 降采样
    downsample_factor=50,           # 降采样倍数（1000Hz → 20Hz）
    
    # 滤波参数
    frequency_low=0.01,             # 带通低频
    frequency_high=1.0,             # 带通高频
    remove_common=True,             # 共模噪声去除
    detrend=True,                   # 去趋势
    
    # Hilbert包络（TTMuTian方法）
    use_envelope=True,              # 是否使用包络
    envelope_smoothing=0.25,        # 平滑窗口（秒）
    
    # F-K滤波（方向分离）
    use_fk=True,                    # 是否使用F-K
    direction='decreasing',         # 方向：increasing/decreasing/both
    channel_spacing=4.0,            # 通道间距（米）
    minimum_speed_kmh=0.0,          # 最小速度
    maximum_speed_kmh=120.0,        # 最大速度
    
    padding_seconds=100.0,          # 前后padding（避免边界效应）
)
```

**输出**：
- `data`: (channels, samples) 处理后的数据
- `sampling_rate`: 降采样后的采样率

---

### 2. 轨迹提取 (`extract_tracks` 函数)

```python
track_params = {
    # 峰值检测
    'peak_method': 'simple',        # simple 或 ridge
    'prominence': 2.5,              # 峰值突出度阈值
    'min_separation': 2.0,          # 峰值最小间隔（秒）
    
    # 霍夫变换
    'hough_channel_window': 60,    # 局部窗口大小（通道数）
    'hough_overlap': 30,           # 窗口重叠
    
    # 轨迹延伸
    'max_gap': 20,                 # 最大连续缺失通道数
    'poly_degree': 1,              # 拟合次数（1=直线，2=曲线）
    'min_track_length': 50,        # 最小轨迹长度（通道数）
}

tracks, binary = extract_tracks(data, sampling_rate, track_params)
```

**输出**：
- `tracks`: 轨迹列表，每个轨迹包含 `{channels, times, length}`
- `binary`: 峰值二值图

---

### 3. 可视化 (`plot_tracks` 函数)

```python
fig = plot_tracks(
    data, tracks, sampling_rate,
    channel_from=321,
    title="Vehicle Tracks"
)
plt.show()
```

---

## 🎯 典型使用场景

### 场景1：基础轨迹提取（不用包络和F-K）

```python
# 预处理：只做基本滤波
data, sr = process(
    source_path,
    channel_from=321, channel_to=520,
    downsample_factor=50,
    use_envelope=False,    # ❌ 不用包络
    use_fk=False,          # ❌ 不用F-K
)

# 提取轨迹
tracks, _ = extract_tracks(data, sr, track_params)

# 可视化
plot_tracks(data, tracks, sr, channel_from=321)
```

**适用**：数据质量好，噪声小，单方向车流

---

### 场景2：使用Hilbert包络（降噪）

```python
data, sr = process(
    source_path,
    channel_from=321, channel_to=520,
    downsample_factor=50,
    use_envelope=True,     # ✅ 使用包络
    envelope_smoothing=0.25,
    use_fk=False,
)

tracks, _ = extract_tracks(data, sr, track_params)
plot_tracks(data, tracks, sr, channel_from=321)
```

**适用**：噪声大，轨迹不清晰

---

### 场景3：使用F-K滤波（方向分离）

```python
data, sr = process(
    source_path,
    channel_from=321, channel_to=520,
    downsample_factor=50,
    use_envelope=False,
    use_fk=True,           # ✅ 使用F-K
    direction='decreasing', # 只保留一个方向
    maximum_speed_kmh=120.0,
)

tracks, _ = extract_tracks(data, sr, track_params)
plot_tracks(data, tracks, sr, channel_from=321)
```

**适用**：双向车流，需要分离方向

---

### 场景4：组合方法（TTMuTian推荐）

```python
data, sr = process(
    source_path,
    channel_from=321, channel_to=520,
    downsample_factor=50,
    use_envelope=True,     # ✅ 包络降噪
    envelope_smoothing=0.25,
    use_fk=True,           # ✅ F-K方向分离
    direction='decreasing',
    maximum_speed_kmh=120.0,
)

tracks, _ = extract_tracks(data, sr, track_params)
plot_tracks(data, tracks, sr, channel_from=321)
```

**适用**：噪声大 + 双向车流 + 需要最佳效果

---

## ⚙️ 参数调优指南

### 预处理参数

| 参数 | 默认值 | 调优建议 |
|------|--------|----------|
| `downsample_factor` | 50 | 数据太大→增大；需要高时间分辨率→减小 |
| `frequency_low` | 0.01 Hz | 车辆信号通常在 0.1-50 Hz |
| `frequency_high` | 1.0 Hz | 低频车辆用1Hz；高频振动用50Hz |
| `envelope_smoothing` | 0.25s | 轨迹不平滑→增大；丢失细节→减小 |
| `maximum_speed_kmh` | 120 | 根据实际道路限速调整 |

### 峰值检测参数

| 参数 | 默认值 | 调优建议 |
|------|--------|----------|
| `prominence` | 2.5 | 噪声峰太多→增大；漏检→减小 |
| `min_separation` | 2.0s | 相邻车辆太近→减小 |
| `peak_method` | simple | 噪声大用ridge（更严格） |

### 霍夫变换参数

| 参数 | 默认值 | 调优建议 |
|------|--------|----------|
| `hough_channel_window` | 60 | 轨迹短→减小；长→增大 |
| `max_gap` | 20 | 轨迹断裂→增大；误连接→减小 |
| `min_track_length` | 50 | 短轨迹太多→增大 |
| `poly_degree` | 1 | 直线用1；弯曲轨迹用2 |

---

## 📊 输出结果解读

### 轨迹数据结构

```python
track = {
    'channels': array([321, 322, 323, ..., 450]),  # 通道索引
    'times': array([100, 105, 110, ..., 1500]),    # 时间索引（采样点）
    'length': 130                                  # 轨迹长度（通道数）
}
```

### 计算车辆速度

```python
# 从轨迹计算速度
def calculate_speed(track, channel_spacing=4.0, sampling_rate=20.0):
    """
    track: 轨迹字典
    channel_spacing: 通道间距（米）
    sampling_rate: 采样率（Hz）
    
    返回: 速度（km/h）
    """
    distance = (track['channels'][-1] - track['channels'][0]) * channel_spacing  # 米
    time = (track['times'][-1] - track['times'][0]) / sampling_rate  # 秒
    
    speed_ms = distance / time  # m/s
    speed_kmh = speed_ms * 3.6  # km/h
    
    return speed_kmh

# 使用
for i, track in enumerate(tracks):
    speed = calculate_speed(track)
    print(f"轨迹 {i+1}: 速度 = {speed:.1f} km/h")
```

---

## 🐛 常见问题

### Q1: 找不到轨迹或轨迹太少

**可能原因**：
- 峰值检测阈值太高
- 霍夫变换窗口不合适
- F-K滤波把信号滤掉了

**解决**：
```python
# 降低峰值阈值
track_params['prominence'] = 2.0  # 从2.5降到2.0

# 检查F-K滤波速度范围
# 如果车速~50km/h，但maximum_speed_kmh=120，应该没问题
# 但如果设置的vmin-vmax太窄，会滤掉信号

# 不用F-K试试
use_fk=False
```

### Q2: 轨迹断裂

**可能原因**：
- 信号质量差，某些通道缺失峰值
- `max_gap` 太小

**解决**：
```python
# 增大容忍缺失
track_params['max_gap'] = 30  # 从20增到30

# 或使用包络平滑信号
use_envelope=True
```

### Q3: 误检测太多

**可能原因**：
- 噪声峰值被当成车辆
- 峰值阈值太低

**解决**：
```python
# 提高峰值阈值
track_params['prominence'] = 3.0

# 使用ridge峰值检测（更严格）
track_params['peak_method'] = 'ridge'

# 增加最小轨迹长度
track_params['min_track_length'] = 80
```

### Q4: 包络后丢失信号

**可能原因**：
- 平滑窗口太大

**解决**：
```python
# 减小平滑窗口
envelope_smoothing=0.1  # 从0.25减到0.1

# 或不用包络
use_envelope=False
```

---

## 📁 文件结构

```
D:\projects\das\notebooks\
├── demo3.ipynb                    # 主notebook
├── track_extraction.py            # 轨迹提取模块
├── HILBERT_ENVELOPE_USAGE.md      # Hilbert包络使用指南
├── explain_hilbert_transform.py   # Hilbert原理演示
└── figures/
    ├── hilbert_envelope_comparison.png
    ├── fk_direction_comparison.png
    └── ...
```

---

## 🚀 快速开始

### 1. 打开notebook
```bash
cd D:\projects\das\notebooks
jupyter notebook demo3.ipynb
```

### 2. 运行最后一个cell
这个cell包含完整的演示流程，会：
- 读取数据
- 预处理（包络 + F-K）
- 提取轨迹
- 可视化

### 3. 根据结果调参数
参考上面的"参数调优指南"

---

## 📚 相关文献

1. **TTMuTian (2024)** - Hilbert包络方法
   https://arxiv.org/pdf/2403.02791

2. **Urban DAS (2022)** - 预处理流程
   https://www.mdpi.com/1424-8220/22/24/9976

3. **DAS Review (2024)** - 综述
   https://www.mdpi.com/2412-3811/10/9/228

---

## 💡 下一步工作

- [ ] 添加速度估计
- [ ] 轨迹去重优化
- [ ] 支持曲线拟合（poly_degree=2）
- [ ] 添加轨迹质量评分
- [ ] 输出到CSV文件
- [ ] 批量处理多个文件

---

祝实验顺利！🚀

有问题随时问我！
