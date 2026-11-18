# 主窗口代码结构

`main_window.py` 只负责组装控制器，以及启动、数据刷新和关闭流程。每个功能控制器是独立的 `QObject`，在所属模块初始化状态、创建菜单、维护控件和释放资源。主窗口只保存控制器实例与配置对象。

例如，播放状态和控件通过 `window.playback.backend`、`window.playback.position_ms`、`window.playback.qt_player` 访问；数据通过 `window.data.raw_data` 访问。模块内部直接使用自身字段，跨模块通过 `self.window.模块名` 显式访问。`components/window_feature.py` 只提供 QObject 父子关系和窗口引用。

布局模块组合各功能控件，控件引用保存到所属控制器。Qt 信号连接到控制器方法，窗口事件委托给工作区控制器。关闭时，窗口调用各控制器的 `shutdown()`，定时器、播放器和后台线程池由各模块释放。

| 模块 | 职责 |
| --- | --- |
| `components/workspace.py` | 主工作区布局、页签切换、窗口事件 |
| `components/data_controls.py` | 时间修正、查看范围、通道切换 |
| `components/plot_overlays.py` | 文件分段展示、事件范围联动 |
| `components/file_segment_bar.py` | 可点击的文件分段图形项 |
| `tabs/data_files.py` | BIN 文件选择、加载流程、数据概览刷新 |
| `tabs/data_plots.py` | 灰度／彩色图、单通道波形和幅值图、热力图、二值图、应变图 |
| `tabs/multi_waves.py` | 多通道云图及浏览控件 |
| `tabs/filtering.py` | DAS 二维滤波、预览、恢复、历史与预设 |
| `tabs/vehicle_analysis.py` | 车辆轨迹拾取、叠加和速度标尺 |
| `tabs/video_layout.py` | 独立视频播放器页面及控件绑定 |
| `tabs/video_playback.py` | Qt／FFmpeg 播放、转码、跳转与倍速 |

主窗口控制器实例：`workspace`、`data`、`controls`、`plots`、`waves`、`overlays`、`vehicles`、`filtering`、`video_ui`、`playback`。

`core/data/bin_loader.py` 独立处理 BIN 文件组的校验、拼接、去趋势、时间轴和采集元数据，不依赖 Qt。窗口只在读取成功后替换现有数据。`core/data/window_reader.py` 提供跨文件窗口读取，供车辆分析使用。

数据入口只接受 BIN。已删除 DAT/scouter、通用数据导出、BIN 转 DASPy、特征统计、独立谱分析、SNR、EMD、独立 IIR 和小波分析。

视频页仅保留选择视频、播放暂停、前后跳转、倍速、进度条和时间显示，固定保持画面比例。普通视频使用 Qt；MPEG-PS 等兼容路径在后台生成独立缓存，再通过 FFmpeg 播放。视频功能不读取 DAS、不解析录像开始时间，也不维护标注工程。标签、几何标注、标注 CSV、视频对时、DAS 匹配及视频侧轨迹分析均已删除。

保留文件格式／尺寸／内存校验、用户输入检查、后台任务和关闭图形项时的异常处理；删除 DAT 分支、失效状态、重复加载流程和可由控件类型保证的判断。

回归检查：

```powershell
.venv/Scripts/python.exe -m compileall -q core ui services utils
.venv/Scripts/python.exe -m ruff check ui/main_window.py ui/tabs ui/components --select F,I
```

本次精简通过 11 项临时离屏回归检查，覆盖视频选择、播放暂停、跳转、倍速、进度条、真实视频解码与重播、MPEG-PS 转码、切换文件、关闭释放，以及保留的数据和滤波流程。检查使用临时 BIN、视频、缓存和设置，不修改真实数据或个人设置。
