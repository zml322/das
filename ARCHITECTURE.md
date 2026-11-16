# DASViewer 重构架构文档

## 📊 重构概述

**重构日期**: 2026-11-16  
**重构目标**: 将7252行的单体MainWindow拆分为模块化、分层架构  
**原则**: 保持所有功能不变，仅重组代码结构

---

## 🏗️ 新架构结构

```
das/
├── core/                   # 核心业务逻辑层（与UI无关）
│   ├── data/              # 数据管理
│   ├── filter/            # 滤波处理
│   ├── analysis/          # 信号分析
│   ├── video/             # 视频处理
│   ├── tracking/          # 车辆追踪
│   └── export/            # 数据导出
│
├── ui/                    # 用户界面层
│   ├── main_window.py     # 主窗口框架
│   ├── tabs/              # Tab页面（未来拆分）
│   ├── dialogs/           # 功能对话框
│   ├── widgets/           # 自定义控件
│   └── components/        # UI组件（未来拆分）
│
├── services/              # 应用服务层
│   └── preferences.py     # 用户设置持久化
│
├── utils/                 # 通用工具
│   ├── function.py        # 通用函数
│   ├── theme.py           # 主题样式
│   ├── plot.py            # 绘图辅助
│   └── version.py         # 版本信息
│
├── vendor/                # 第三方代码
│   └── das_veh/           # DAS车辆追踪算法
│
├── image/                 # 图像资源
└── main.py                # 应用入口
```

---

## 📦 模块详细说明

### core/ - 核心业务逻辑层

#### core/data/ - 数据管理
- `bin_reader.py`: BIN格式文件读取（20浮点头+数据体，自动端序检测）
- `data_group.py`: 多文件拼接与内存预算管理
- `data_timeline.py`: 时间轴元数据与文件-时间映射

#### core/filter/ - 滤波处理
- `das_filter.py`: 二维DAS滤波算法（带通、陷波、中值、FK、MAD归一化）
- `filter_pipeline.py`: 不可变滤波管道重放机制
- `filter_history.py`: 滤波历史与预设管理
- `filter.py`: 通用IIR滤波器设计

#### core/analysis/ - 信号分析
- `spectrum.py`: FFT频谱分析（幅度谱、功率谱、相位谱）
- `wavelet.py`: 小波变换（DWT离散、CWT连续）
- `wavelet_packet.py`: 小波包分解（DWPT）
- `emd.py`: 经验模态分解（EMD、EEMD、CEEMDAN）
- `snr.py`: 信噪比计算
- `feature.py`: 特征提取（能量、方差、过零率）
- `binary_image.py`: 阈值二值化（Otsu、双峰法）

#### core/video/ - 视频处理
- `annotation.py`: 视频标注项目（JSON侧载文件，不修改DAS数据）
- `media.py`: 格式转换与播放准备
- `trajectory.py`: 后台轨迹分析窗口
- `player.py`: FFmpeg回退播放器

#### core/tracking/ - 车辆追踪
- `vehicle_tracking.py`: 互相关车辆轨迹检测
- `das_veh_tracking.py`: 卡尔曼滤波追踪（DAS-VEH集成）
- `vehicle_preprocessing.py`: 车辆响应预处理
- `trajectory_prescreen.py`: 霍夫变换轨迹初筛
- `speed_ruler.py`: 速度标尺与ROI投影速度测量

#### core/export/ - 数据导出
- `daspy_conversion.py`: BIN → DASPy格式转换（PKL、HDF5、SEG-Y）

---

### ui/ - 用户界面层

#### ui/dialogs/ - 功能对话框
- `vehicle_tracking_dialog.py`: 车辆追踪参数配置
- `trajectory_prescreen_dialog.py`: 轨迹初筛控制器
- `daspy_converter_dialog.py`: DASPy格式转换器
- `data_sifting.py`: 数据筛选对话框

#### ui/widgets/ - 自定义控件
- `custom_widgets.py`: 通用PyQt5控件（按钮、输入框、下拉框等）
- `annotation_canvas.py`: 视频标注画布
- `flow_layout.py`: 流式布局管理器

#### ui/tabs/ - Tab页面（预留，未来拆分）
当前MainWindow.py仍保留完整的7252行代码，未来可拆分为：
- `data_tab.py`: 数据加载和显示
- `filter_tab.py`: 滤波处理
- `analysis_tab.py`: 信号分析
- `video_tab.py`: 视频同步
- `tracking_tab.py`: 车辆追踪

#### ui/components/ - UI组件（预留，未来拆分）
- `file_segment_bar.py`: 文件段条形图
- `timeline_controls.py`: 时间轴控制
- `data_table.py`: 数据表格

---

### services/ - 应用服务层
- `preferences.py`: 用户设置持久化（JSON格式）

---

### utils/ - 通用工具
- `function.py`: 通用函数（资源路径、数据处理、绘图辅助）
- `theme.py`: 应用样式与主题
- `plot.py`: Matplotlib/PyQtGraph绘图辅助
- `version.py`: 版本信息（单一真实来源）

---

### vendor/ - 第三方代码
- `das_veh/`: DAS车辆追踪算法（卡尔曼滤波、似然度计算）

---

## 🔗 依赖关系

```
main.py
  └─> ui.main_window.MainWindow
       ├─> services.preferences.AppPreferences
       │    (无下游依赖)
       │
       ├─> core.data.*
       │    └─> (纯数据逻辑，无UI依赖)
       │
       ├─> core.filter.*
       │    └─> core.data.* (内存预算管理)
       │
       ├─> core.analysis.*
       │    └─> ui.widgets.* (仅用于对话框UI)
       │
       ├─> core.video.*
       │    └─> core.data.* (数据读取)
       │         core.filter.* (轨迹预处理)
       │         core.tracking.* (车辆检测)
       │
       ├─> core.tracking.*
       │    └─> core.data.*
       │         vendor.das_veh.* (外部算法)
       │
       ├─> ui.dialogs.*
       │    └─> core.* (调用业务逻辑)
       │         ui.widgets.* (自定义控件)
       │
       └─> ui.widgets.*
            └─> utils.theme (样式)
```

---

## ⚙️ 关键设计决策

### 1. 循环依赖解决
**问题**: `utils.function` → `ui.widgets` → `utils.theme` 循环  
**解决方案**: 在`utils.function.py`中使用延迟导入
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.widgets.custom_widgets import MyPlotWidget

def initCombinedPlotWidget(...):
    from ui.widgets.custom_widgets import MyPlotWidget  # 运行时导入
    ...
```

### 2. MainWindow保持完整
当前重构仅移动辅助类和业务逻辑，MainWindow.py的7252行代码**暂不拆分**：
- 降低重构风险
- 保持UI逻辑连贯性
- 为下一阶段拆分做准备

### 3. 纯业务逻辑与UI分离
- `core/*` 模块**不依赖PyQt5界面组件**
- 业务逻辑可独立单元测试
- 未来可被CLI工具或Web服务复用

---

## 🔄 从旧架构迁移

### 旧路径 → 新路径映射

| 旧模块路径                           | 新模块路径                            |
|-------------------------------------|--------------------------------------|
| `utils.bin_reader`                  | `core.data.bin_reader`               |
| `utils.classes.data_group`          | `core.data.data_group`               |
| `utils.classes.das_filter`          | `core.filter.das_filter`             |
| `utils.classes.spectrum`            | `core.analysis.spectrum`             |
| `utils.classes.video_annotation`    | `core.video.annotation`              |
| `utils.classes.vehicle_tracking`    | `core.tracking.vehicle_tracking`     |
| `utils.classes.daspy_conversion`    | `core.export.daspy_conversion`       |
| `utils.widget`                      | `ui.widgets.custom_widgets`          |
| `utils.preferences`                 | `services.preferences`               |
| `utils.mainwindow`                  | `ui.main_window`                     |
| `utils.vendor.das_veh`              | `vendor.das_veh`                     |

### 导入语句更新示例

**旧代码**:
```python
from utils.bin_reader import bin2numpy
from utils.classes.das_filter import DASFilterDialog
from utils.widget import PushButton
```

**新代码**:
```python
from core.data.bin_reader import bin2numpy
from core.filter.das_filter import DASFilterDialog
from ui.widgets.custom_widgets import PushButton
```

---

## 📝 待办事项（下一阶段）

### Phase 2: MainWindow拆分（中高风险）
1. 创建`ui/tabs/`各Tab页面类
2. 创建`services/state_manager.py`统一状态管理
3. 精简`main_window.py`为框架代码（目标<1000行）

### Phase 3: 测试完善
1. 补充`core/*`模块的单元测试
2. 更新构建脚本（`build_windows.py`, `build_macos.py`）
3. 验证所有功能点无回归

---

## ✅ 重构验证清单

- [x] 所有文件移动到新目录结构
- [x] 更新所有import路径
- [x] 解决循环依赖问题
- [x] 添加`__init__.py`和模块文档
- [x] Python语法检查通过（`python -m compileall`）
- [x] MainWindow可正常import
- [x] 主程序可启动（`python main.py`）
- [ ] 运行完整功能测试（手动测试）
- [ ] 运行现有测试脚本（`tests/`目录）
- [ ] 构建脚本验证（PyInstaller打包）

---

## 📚 相关文档

- `CLAUDE.md`: 项目开发指南（已更新）
- `requirements.txt`: Python依赖列表
- `build_windows.py`, `build_macos.py`: 构建脚本

---

**重构完成**: 2026-11-16  
**下次重构建议**: 拆分MainWindow至独立Tab模块
