"""Video comparison page and annotation sidebar construction."""

from PyQt5 import QtMultimedia
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedLayout,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from core.video.annotation import GEOMETRY_LABELS, VEHICLE_TYPES
from ui.components.window_feature import WindowFeature
from ui.dialogs.trajectory_prescreen_dialog import TrajectoryPrescreenController
from ui.tabs.video_constants import VIDEO_DISPLAY_WINDOW_SECONDS
from ui.widgets.annotation_canvas import AnnotationCanvas
from ui.widgets.custom_widgets import (
    ComboBox,
    Label,
    LineEdit,
    MyPlotWidget,
    PushButton,
    SpinBox,
)
from ui.widgets.flow_layout import FlowLayout, control_group
from utils.theme import SMALL_POINT_SIZE, ui_font

try:
    from PyQt5.QtMultimediaWidgets import QVideoWidget
except ImportError:
    QVideoWidget = None


class VideoLayoutController(WindowFeature):
    """Video comparison page and annotation sidebar construction."""

    def shutdown(self):
        self.trajectory_prescreen.shutdown()

    def initVideoComparisonTab(self):
        """Create a video sidebar and a DAS-first comparison workspace."""

        self.video_compare_container = QWidget()
        root = QVBoxLayout(self.video_compare_container)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        video_panel = QWidget()
        self.video_sidebar_panel = video_panel
        video_panel.setObjectName("videoSidebarPanel")
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(6, 4, 6, 4)
        video_layout.setSpacing(3)
        self.window.playback.source_label = Label("未载入摄像头视频")
        self.window.playback.source_label.setObjectName("secondaryLabel")
        self.window.playback.source_label.setWordWrap(False)
        self.window.playback.source_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.window.playback.media_info_label = Label("媒体探测：等待选择录像")
        self.window.playback.media_info_label.setObjectName("secondaryLabel")
        self.window.playback.media_info_label.setWordWrap(False)
        self.window.playback.media_info_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        video_layout.addWidget(self.window.playback.source_label)
        video_layout.addWidget(self.window.playback.media_info_label)

        self.window.playback.load_button = PushButton("选择视频")
        self.window.playback.load_button.setFixedWidth(76)
        self.window.playback.load_button.setToolTip("选择摄像头录像；不会修改源视频")
        self.window.video_files.video_das_load_button = PushButton("自动匹配 DAS")
        self.window.video_files.video_das_load_button.setFixedWidth(108)
        self.window.video_files.video_das_load_button.setToolTip(
            "按录像时间范围匹配 DAS 文件；只读取文件头，播放时再读取当前窗口"
        )
        self.window.playback.play_button = PushButton("播放")
        self.window.playback.play_button.setFixedWidth(60)
        self.window.playback.play_button.setObjectName("primaryAction")
        self.window.playback.back_button = PushButton("−1 s")
        self.window.playback.back_button.setFixedWidth(54)
        self.window.playback.forward_button = PushButton("+1 s")
        self.window.playback.forward_button.setFixedWidth(54)
        self.window.playback.speed_combo = ComboBox()
        for label, rate in (("0.25×", 0.25), ("0.5×", 0.5), ("1×", 1.0), ("2×", 2.0)):
            self.window.playback.speed_combo.addItem(label, rate)
        self.window.playback.speed_combo.setCurrentIndex(2)
        self.window.playback.speed_combo.setFixedWidth(72)
        self.window.playback.fit_combo = ComboBox()
        self.window.playback.fit_combo.addItem("完整画面", Qt.KeepAspectRatio)
        self.window.playback.fit_combo.addItem("填满裁剪", Qt.KeepAspectRatioByExpanding)
        self.window.playback.fit_combo.setFixedWidth(92)
        self.window.playback.fit_combo.setToolTip("完整画面保留全部内容；填满裁剪可减少黑边但会裁掉少量边缘")
        self.window.playback.position_slider = QSlider(Qt.Horizontal)
        self.window.playback.position_slider.setRange(0, 0)
        self.window.playback.position_slider.setAccessibleName("视频播放位置")
        self.window.playback.time_label = Label("--:--:--.--- / --:--:--.---")
        self.window.playback.time_label.setFont(ui_font(SMALL_POINT_SIZE))
        self.window.playback.time_label.setAlignment(Qt.AlignCenter)
        transport_actions = FlowLayout(spacing=4)
        transport_actions.addWidget(self.window.playback.load_button)
        transport_actions.addWidget(self.window.video_files.video_das_load_button)
        transport_actions.addWidget(self.window.playback.play_button)
        transport_actions.addWidget(self.window.playback.back_button)
        transport_actions.addWidget(self.window.playback.forward_button)
        transport_actions.addWidget(control_group(self.window.playback.speed_combo, self.window.playback.fit_combo))
        video_layout.addLayout(transport_actions)

        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(8, 0, 8, 0)
        slider_row.addWidget(self.window.playback.position_slider)
        video_layout.addLayout(slider_row)
        video_layout.addWidget(self.window.playback.time_label)
        self.window.playback.speed_combo.setAccessibleName("视频播放倍速")
        self.window.playback.speed_combo.setToolTip("视频播放倍速")

        self.window.playback.viewport = QWidget()
        self.window.playback.viewport_stack = QStackedLayout(self.window.playback.viewport)
        self.window.playback.viewport_stack.setContentsMargins(0, 0, 0, 0)
        if QVideoWidget is None:
            self.window.playback.surface = Label("当前 PyQt 安装未包含视频画面组件。")
            self.window.playback.surface.setAlignment(Qt.AlignCenter)
            self.window.playback.surface.setObjectName("videoUnavailable")
        else:
            self.window.playback.surface = QVideoWidget()
            self.window.playback.surface.setObjectName("videoSurface")
        self.window.playback.frame_surface = Label("等待兼容播放缓存")
        self.window.playback.frame_surface.setAlignment(Qt.AlignCenter)
        self.window.playback.frame_surface.setObjectName("videoSurface")
        self.window.playback.frame_surface.setScaledContents(False)
        self.window.playback.frame_surface.setMinimumSize(0, 0)
        self.window.playback.frame_surface.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.window.playback.frame_surface.installEventFilter(self.window.playback)
        self.window.playback.viewport_stack.addWidget(self.window.playback.surface)
        self.window.playback.viewport_stack.addWidget(self.window.playback.frame_surface)
        self.window.playback.viewport.setFixedHeight(180)
        self.window.playback.viewport.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        video_layout.addWidget(self.window.playback.viewport, 1)

        self.window.sync.video_sync_summary_label = Label("对时：等待视频与 DAS 数据")
        self.window.sync.video_sync_summary_label.setObjectName("secondaryLabel")
        self.window.sync.video_sync_summary_label.setWordWrap(True)
        self.window.sync.video_sync_summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        video_layout.addWidget(self.window.sync.video_sync_summary_label)
        video_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        das_panel = QWidget()
        das_panel.setObjectName("videoDasPanel")
        das_layout = QVBoxLayout(das_panel)
        das_layout.setContentsMargins(4, 2, 4, 2)
        das_layout.setSpacing(3)
        self.window.video_plot.video_das_layout = das_layout
        self.window.video_plot.video_das_plot_widget = MyPlotWidget(
            "", "推算时间", "通道", check_mouse=False, time_axis=True
        )
        self.window.video_plot.video_das_plot_widget.setMinimumHeight(150)
        self.window.sync.video_camera_channel_spin_box = SpinBox()
        self.window.sync.video_camera_channel_spin_box.setRange(1, 1)
        self.window.sync.video_camera_channel_spin_box.setKeyboardTracking(False)
        self.window.sync.video_camera_channel_apply_button = PushButton("设置通道")
        self.window.sync.video_camera_visible_checkbox = QCheckBox("通道线")
        self.window.sync.video_camera_visible_checkbox.setToolTip("显示摄像头通道线")
        self.window.sync.video_camera_visible_checkbox.setChecked(True)
        self.window.video_plot.video_follow_checkbox = QCheckBox("播放时跟随")
        self.window.video_plot.video_follow_checkbox.setChecked(True)
        self.window.video_plot.video_annotations_visible_checkbox = QCheckBox("显示标注")
        self.window.video_plot.video_annotations_visible_checkbox.setChecked(True)
        self.window.video_analysis.video_display_mode_combo = ComboBox()
        self.window.video_analysis.video_display_mode_combo.addItem("事件增强", "enhanced")
        self.window.video_analysis.video_display_mode_combo.addItem("原始去趋势", "raw")
        self.window.video_analysis.video_display_mode_combo.setToolTip("快速对照显示处理后的结果与未滤波的去趋势数据")
        self.window.video_analysis.video_window_combo = ComboBox()
        for seconds in (30, 60, 120, 240):
            self.window.video_analysis.video_window_combo.addItem(f"{seconds} s", seconds)
        self.window.video_analysis.video_window_combo.setCurrentIndex(
            self.window.video_analysis.video_window_combo.findData(int(VIDEO_DISPLAY_WINDOW_SECONDS))
        )
        self.window.video_analysis.video_window_combo.setToolTip(
            "播放跟随时右侧 DAS 的可见时间窗；后台会提前预读后续数据以连续滚动"
        )
        self.window.video_analysis.video_filter_button = PushButton("二维滤波…")
        self.window.video_analysis.video_filter_button.setToolTip(
            "打开与主数据页相同的二维滤波窗口，按顺序叠加显示滤波"
        )
        self.window.video_analysis.video_filter_summary_label = Label("车辆事件增强")
        self.window.video_analysis.video_filter_summary_label.setObjectName("secondaryLabel")
        self.window.video_analysis.video_filter_summary_label.setToolTip(
            "带通 0.01–1 Hz → 中位数共模抑制 → MAD 归一化；仅影响显示"
        )
        self.window.video_plot.video_focus_button = PushButton("专注模式")
        self.window.video_plot.video_focus_button.setCheckable(True)
        self.window.video_plot.video_focus_button.setToolTip("隐藏左栏与事件范围栏，让 DAS 图占满窗口；F11 可切换")
        self.window.video_plot.video_current_das_label = Label("DAS：等待对时")
        self.window.video_plot.video_current_das_label.setObjectName("statusBadge")
        self.window.video_files.video_sequence_status_label = Label("匹配 DAS：未加载")
        self.window.video_files.video_sequence_status_label.setObjectName("secondaryLabel")
        self.window.video_files.video_sequence_status_label.setWordWrap(True)
        self.window.video_files.video_sequence_status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.window.video_analysis.video_trajectory_status_label = Label("轨迹：等待匹配 DAS")
        self.window.video_analysis.video_trajectory_status_label.setObjectName("secondaryLabel")
        self.window.video_analysis.video_trajectory_status_label.setWordWrap(True)
        self.window.video_analysis.video_trajectory_status_label.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred
        )
        self.window.video_analysis.video_trajectory_dx_spin_box = QDoubleSpinBox()
        self.window.video_analysis.video_trajectory_dx_spin_box.setRange(0.001, 1_000_000.0)
        self.window.video_analysis.video_trajectory_dx_spin_box.setDecimals(3)
        self.window.video_analysis.video_trajectory_dx_spin_box.setSingleStep(0.1)
        self.window.video_analysis.video_trajectory_dx_spin_box.setSuffix(" m")
        self.window.video_analysis.video_trajectory_dx_spin_box.setValue(4.0)
        self.window.video_analysis.video_trajectory_dx_spin_box.setKeyboardTracking(False)
        self.window.sync.video_camera_channel_spin_box.setFixedWidth(60)
        self.window.video_analysis.video_display_mode_combo.setFixedWidth(105)
        self.window.video_analysis.video_window_combo.setFixedWidth(76)
        self.window.video_analysis.video_trajectory_dx_spin_box.setFixedWidth(104)
        self.window.video_analysis.video_filter_summary_label.hide()
        self.window.video_plot.video_reset_view_button = PushButton("复位视图")
        self.window.video_plot.video_reset_view_button.setToolTip(
            "恢复当前视频时间窗口和全部通道；无视频时恢复完整 DAS 图"
        )
        self.window.video_plot.video_reset_view_button.clicked.connect(self.window.video_plot.resetVideoComparisonView)
        self.video_prescreen_button = PushButton("轨迹初筛…")
        self.video_prescreen_button.setToolTip("检测当前可见 DAS 范围，校对候选后确认保存")
        self.video_prescreen_button.clicked.connect(lambda: self.trajectory_prescreen.show())
        das_controls = FlowLayout(spacing=4)
        das_controls.addWidget(
            control_group(
                Label("摄像头通道"),
                self.window.sync.video_camera_channel_spin_box,
                self.window.sync.video_camera_channel_apply_button,
            )
        )
        for widget in (
            self.window.sync.video_camera_visible_checkbox,
            self.window.video_plot.video_follow_checkbox,
            self.window.video_plot.video_annotations_visible_checkbox,
        ):
            das_controls.addWidget(widget)
        das_controls.addWidget(
            control_group(
                Label("显示"),
                self.window.video_analysis.video_display_mode_combo,
                self.window.video_analysis.video_filter_button,
            )
        )
        das_controls.addWidget(control_group(Label("窗口"), self.window.video_analysis.video_window_combo))
        das_controls.addWidget(control_group(Label("dx"), self.window.video_analysis.video_trajectory_dx_spin_box))
        das_controls.addWidget(self.window.video_plot.video_reset_view_button)
        das_controls.addWidget(self.video_prescreen_button)
        das_controls.addWidget(self.window.video_plot.video_focus_button)
        das_layout.addLayout(das_controls)

        das_status = QGridLayout()
        das_status.setContentsMargins(0, 0, 0, 0)
        das_status.setHorizontalSpacing(12)
        das_status.setVerticalSpacing(2)
        das_status.addWidget(self.window.video_files.video_sequence_status_label, 0, 0)
        das_status.addWidget(self.window.video_plot.video_current_das_label, 0, 1, Qt.AlignRight)
        das_status.addWidget(self.window.video_analysis.video_trajectory_status_label, 1, 0, 1, 2)
        das_status.setColumnStretch(0, 1)
        das_layout.addWidget(self.window.video_plot.video_das_plot_widget, 1)
        das_layout.addLayout(das_status)
        das_panel.setMinimumHeight(270)

        root.addWidget(das_panel, 1)

        self.window.playback.load_button.clicked.connect(self.window.playback.chooseVideoComparisonFile)
        self.window.video_files.video_das_load_button.clicked.connect(self.window.video_files.chooseVideoDasFolder)
        self.window.playback.play_button.clicked.connect(self.window.playback.toggleVideoPlayback)
        self.window.playback.back_button.clicked.connect(lambda: self.window.playback.seekVideoByMilliseconds(-1000))
        self.window.playback.forward_button.clicked.connect(lambda: self.window.playback.seekVideoByMilliseconds(1000))
        self.window.playback.speed_combo.currentIndexChanged.connect(self.window.playback.setVideoPlaybackRate)
        self.window.playback.fit_combo.currentIndexChanged.connect(self.window.playback.setVideoFitMode)
        self.window.playback.position_slider.sliderPressed.connect(self.window.playback._videoSliderPressed)
        self.window.playback.position_slider.sliderReleased.connect(self.window.playback._videoSliderReleased)
        self.window.playback.position_slider.sliderMoved.connect(self.window.playback._videoSliderMoved)
        self.window.sync.video_camera_channel_apply_button.clicked.connect(self.window.sync.applyVideoCameraChannel)
        self.window.sync.video_camera_visible_checkbox.toggled.connect(self.window.sync.setVideoCameraVisible)
        self.window.video_plot.video_annotations_visible_checkbox.toggled.connect(
            self.window.sync.setVideoAnnotationsVisible
        )
        self.window.video_analysis.video_display_mode_combo.currentIndexChanged.connect(
            self.window.video_analysis._videoDisplayModeChanged
        )
        self.window.video_analysis.video_window_combo.currentIndexChanged.connect(
            self.window.video_analysis._videoVisibleWindowChanged
        )
        self.window.video_analysis.video_filter_button.clicked.connect(self.window.video_analysis.showVideoFilterDialog)
        self.window.video_plot.video_focus_button.toggled.connect(self.window.video_plot.setVideoFocusMode)
        self.window.video_analysis.video_trajectory_dx_spin_box.editingFinished.connect(
            self.window.video_analysis._configureVideoTrajectoryAnalysis
        )
        self.window.video_plot.video_das_plot_widget.scene().sigMouseClicked.connect(self.window.sync._videoDasClicked)

        self._createVideoAnnotationSidebar(video_panel)
        self.window.annotations.annotation_canvas = AnnotationCanvas(
            self.window.video_plot.video_das_plot_widget, self.window
        )
        self.window.annotations.annotation_canvas.shape_drawn.connect(self.window.annotations._addDasGeometryAnnotation)
        self.window.annotations.annotation_canvas.shape_edited.connect(
            self.window.annotations._updateDasGeometryAnnotation
        )
        self.window.annotations.annotation_canvas.selected.connect(self.window.annotations._selectAnnotationFromPlot)
        self.window.annotations.annotation_canvas.edit_requested.connect(
            self.window.annotations._editAnnotationProperties
        )
        self.window.annotations.annotation_canvas.remove_requested.connect(
            self.window.annotations._deleteAnnotationFromPlot
        )
        self.window.annotations.annotation_canvas.state_changed.connect(
            self.window.annotations._annotationCanvasStateChanged
        )
        self.window.annotations.annotation_canvas.message.connect(self.window.annotations._showAnnotationMessage)
        self.trajectory_prescreen = TrajectoryPrescreenController(self.window)
        if QVideoWidget is not None:
            self.window.playback.qt_player = QtMultimedia.QMediaPlayer(self.window.playback)
            self.window.playback.qt_player.setVideoOutput(self.window.playback.surface)
            self.window.playback.qt_player.positionChanged.connect(self.window.sync._videoPositionChanged)
            self.window.playback.qt_player.durationChanged.connect(self.window.playback._videoDurationChanged)
            self.window.playback.qt_player.stateChanged.connect(self.window.playback._videoStateChanged)
            self.window.playback.qt_player.mediaStatusChanged.connect(self.window.playback._videoMediaStatusChanged)
            self.window.playback.qt_player.error.connect(self.window.playback._videoPlayerError)
        else:
            self.window.playback.play_button.setEnabled(False)
            self.window.playback.back_button.setEnabled(False)
            self.window.playback.forward_button.setEnabled(False)
            self.window.playback.speed_combo.setEnabled(False)
        self.window.sync._syncVideoProjectWidgets()
        self.window.annotations.refreshVideoAnnotationTable()

    def _createVideoAnnotationSidebar(self, video_panel):
        """Keep video visible above scrollable synchronization/annotation tools."""

        self.annotation_sidebar_widget = QWidget()
        self.annotation_sidebar_widget.setObjectName("annotationSidebar")
        self.annotation_sidebar_widget.installEventFilter(self.window.playback)
        sidebar_layout = QVBoxLayout(self.annotation_sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_layout.addWidget(video_panel)

        self.window.annotations.annotation_controls_scroll = QScrollArea()
        self.window.annotations.annotation_controls_scroll.setWidgetResizable(True)
        self.window.annotations.annotation_controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        annotation_content = QWidget()
        self.window.annotations.annotation_controls_scroll.setWidget(annotation_content)
        sidebar_layout.addWidget(self.window.annotations.annotation_controls_scroll, 1)
        layout = QVBoxLayout(annotation_content)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(4)

        project_group = QGroupBox("标注工程")
        project_form = QFormLayout(project_group)
        project_form.setContentsMargins(8, 8, 8, 8)
        project_form.setVerticalSpacing(3)
        self.window.annotations.annotation_project_label = Label("未保存：标签仅在本次会话保留")
        self.window.annotations.annotation_project_label.setObjectName("secondaryLabel")
        self.window.annotations.annotation_project_label.setWordWrap(True)
        self.window.annotations.annotation_new_button = PushButton("新建")
        self.window.annotations.annotation_open_button = PushButton("打开")
        self.window.annotations.annotation_save_button = PushButton("保存")
        self.window.annotations.annotation_export_button = PushButton("导出 CSV")
        project_buttons = QWidget()
        project_buttons_layout = FlowLayout(project_buttons)
        for button in (
            self.window.annotations.annotation_new_button,
            self.window.annotations.annotation_open_button,
            self.window.annotations.annotation_save_button,
            self.window.annotations.annotation_export_button,
        ):
            project_buttons_layout.addWidget(button)
        self.window.annotations.annotation_new_button.setToolTip("清空标注，保留已加载的视频、DAS 和对时设置")
        project_form.addRow(self.window.annotations.annotation_project_label)
        project_form.addRow(project_buttons)
        layout.addWidget(project_group)

        sync_group = QGroupBox("视频对时")
        sync_form = QFormLayout(sync_group)
        self.window.sync.video_sync_form = sync_form
        sync_form.setContentsMargins(8, 8, 8, 8)
        sync_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        sync_form.setVerticalSpacing(3)
        self.window.sync.video_start_time_edit = QDateTimeEdit()
        self.window.sync.video_start_time_edit.setFont(ui_font(SMALL_POINT_SIZE))
        self.window.sync.video_start_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss.zzz")
        self.window.sync.video_start_time_edit.setCalendarPopup(True)
        self.window.sync.video_start_time_edit.setKeyboardTracking(False)
        self.window.sync.video_start_time_edit.setAccessibleName("视频开始时间")
        self.window.sync.video_start_time_edit.setToolTip(
            "修改完成后自动应用；也可拖动右侧紫色虚线，用当前视频帧反算开始时间"
        )
        self.window.sync.video_sync_offset_spin_box = QDoubleSpinBox()
        self.window.sync.video_sync_offset_spin_box.setRange(-3600.0, 3600.0)
        self.window.sync.video_sync_offset_spin_box.setDecimals(3)
        self.window.sync.video_sync_offset_spin_box.setSingleStep(0.01)
        self.window.sync.video_sync_offset_spin_box.setSuffix(" s")
        self.window.sync.video_sync_offset_spin_box.setKeyboardTracking(False)
        self.window.sync.video_sync_rate_spin_box = QDoubleSpinBox()
        self.window.sync.video_sync_rate_spin_box.setRange(0.900000, 1.100000)
        self.window.sync.video_sync_rate_spin_box.setDecimals(6)
        self.window.sync.video_sync_rate_spin_box.setSingleStep(0.000100)
        self.window.sync.video_sync_rate_spin_box.setValue(1.0)
        self.window.sync.video_sync_rate_spin_box.setKeyboardTracking(False)
        self.window.sync.video_sync_apply_button = PushButton("应用对时")
        self.window.sync.video_sync_apply_button.setObjectName("primaryAction")
        self.window.sync.video_sync_single_button = PushButton("校正当前时刻")
        self.window.sync.video_sync_single_button.setCheckable(True)
        self.window.sync.video_sync_single_button.setToolTip("暂停视频后点击此按钮，再在右侧 DAS 图上点击同一事件时刻")
        self.window.sync.video_sync_anchor_button = PushButton("添加校准点")
        self.window.sync.video_sync_anchor_button.setCheckable(True)
        self.window.sync.video_sync_anchor_button.setToolTip("记录两个相隔较远的同一事件点，同时校正偏移和时钟漂移")
        self.window.sync.video_sync_undo_button = PushButton("撤销校正")
        self.window.sync.video_sync_reset_button = PushButton("恢复初始")
        self.window.sync.video_sync_state_label = Label("等待选择视频")
        self.window.sync.video_sync_state_label.setObjectName("statusBadge")
        self.window.sync.video_sync_state_label.setWordWrap(True)
        self.window.sync.video_sync_hint_label = Label(
            "单点校正固定偏移；两个相隔较远的校准点可同时校正长录像的时钟漂移。"
        )
        self.window.sync.video_sync_hint_label.setObjectName("secondaryLabel")
        self.window.sync.video_sync_hint_label.setWordWrap(True)
        sync_form.addRow("开始时间", self.window.sync.video_start_time_edit)
        layout.addWidget(sync_group)

        mark_group = QGroupBox("人工标注")
        mark_form = QFormLayout(mark_group)
        mark_form.setContentsMargins(8, 8, 8, 8)
        mark_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        mark_form.setVerticalSpacing(3)
        self.window.annotations.annotation_kind_combo = ComboBox()
        self.window.annotations.annotation_kind_combo.setEditable(True)
        self.window.annotations.annotation_kind_combo.addItems(
            ["车辆经过", "进入视野", "离开视野", "多车", "异常", "其他"]
        )
        self.window.annotations.annotation_vehicle_combo = ComboBox()
        self.window.annotations.annotation_vehicle_combo.addItems(list(VEHICLE_TYPES))
        self.window.annotations.annotation_lane_combo = ComboBox()
        for lane in range(1, 6):
            self.window.annotations.annotation_lane_combo.addItem(str(lane), lane)
        self.window.annotations.annotation_direction_combo = ComboBox()
        self.window.annotations.annotation_direction_combo.setEditable(True)
        self.window.annotations.annotation_direction_combo.setInsertPolicy(ComboBox.InsertAtBottom)
        self.window.annotations.annotation_direction_combo.lineEdit().setPlaceholderText("自定义，如东→西、进城、出城")
        self.window.annotations.annotation_advanced_toggle = PushButton("更多标注选项 ▸")
        self.window.annotations.annotation_advanced_toggle.setCheckable(True)
        self.window.annotations.annotation_advanced_widget = QWidget()
        advanced_form = QFormLayout(self.window.annotations.annotation_advanced_widget)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        advanced_form.setVerticalSpacing(3)
        self.window.annotations.annotation_advanced_widget.hide()
        self.window.annotations.annotation_advanced_toggle.toggled.connect(self._setAnnotationAdvancedVisible)
        # Keep the frequently used labels accessible above the DAS plot too.
        label_tools = FlowLayout()
        self.window.annotations.annotation_plot_controls = label_tools
        self.window.annotations.annotation_quick_vehicle_combo = ComboBox()
        self.window.annotations.annotation_quick_vehicle_combo.setModel(
            self.window.annotations.annotation_vehicle_combo.model()
        )
        self.window.annotations.annotation_quick_lane_combo = ComboBox()
        self.window.annotations.annotation_quick_lane_combo.setModel(
            self.window.annotations.annotation_lane_combo.model()
        )
        self.window.annotations.annotation_quick_direction_combo = ComboBox()
        self.window.annotations.annotation_quick_direction_combo.setEditable(True)
        self.window.annotations.annotation_quick_direction_combo.setModel(
            self.window.annotations.annotation_direction_combo.model()
        )
        self.window.annotations.annotation_quick_direction_combo.lineEdit().setPlaceholderText("自定义方向")
        self.window.annotations.annotation_vehicle_combo.currentIndexChanged.connect(
            self.window.annotations.annotation_quick_vehicle_combo.setCurrentIndex
        )
        self.window.annotations.annotation_quick_vehicle_combo.currentIndexChanged.connect(
            self.window.annotations.annotation_vehicle_combo.setCurrentIndex
        )
        self.window.annotations.annotation_lane_combo.currentIndexChanged.connect(
            self.window.annotations.annotation_quick_lane_combo.setCurrentIndex
        )
        self.window.annotations.annotation_quick_lane_combo.currentIndexChanged.connect(
            self.window.annotations.annotation_lane_combo.setCurrentIndex
        )
        self.window.annotations.annotation_direction_combo.currentTextChanged.connect(
            self.window.annotations.annotation_quick_direction_combo.setEditText
        )
        self.window.annotations.annotation_quick_direction_combo.currentTextChanged.connect(
            self.window.annotations.annotation_direction_combo.setEditText
        )
        self.window.annotations.annotation_quick_vehicle_combo.setFixedWidth(74)
        self.window.annotations.annotation_quick_lane_combo.setFixedWidth(52)
        self.window.annotations.annotation_quick_direction_combo.setFixedWidth(120)
        label_tools.addWidget(control_group(Label("车辆"), self.window.annotations.annotation_quick_vehicle_combo))
        label_tools.addWidget(control_group(Label("车道"), self.window.annotations.annotation_quick_lane_combo))
        label_tools.addWidget(control_group(Label("方向"), self.window.annotations.annotation_quick_direction_combo))
        self.window.video_plot.video_das_layout.insertLayout(1, label_tools)
        self.window.annotations.annotation_outcome_combo = ComboBox()
        self.window.annotations.annotation_outcome_combo.addItems(
            ["未核对", "确认匹配", "拒绝", "不确定", "DAS未检测到", "疑似误检"]
        )
        self.window.annotations.annotation_note_edit = LineEdit()
        self.window.annotations.annotation_note_edit.setPlaceholderText("可选备注")
        self.window.annotations.annotation_point_button = PushButton("标记车辆 (T)")
        self.window.annotations.annotation_point_button.setObjectName("primaryAction")
        self.window.annotations.annotation_interval_start_button = PushButton("开始区间 (I)")
        self.window.annotations.annotation_interval_finish_button = PushButton("结束并保存 (O)")
        self.window.annotations.annotation_interval_finish_button.setEnabled(False)
        self.window.annotations.annotation_interval_label = Label("未开始区间标注")
        self.window.annotations.annotation_interval_label.setObjectName("secondaryLabel")
        self.window.annotations.annotation_trajectory_tolerance_spin_box = QDoubleSpinBox()
        self.window.annotations.annotation_trajectory_tolerance_spin_box.setRange(0.0, 120.0)
        self.window.annotations.annotation_trajectory_tolerance_spin_box.setDecimals(3)
        self.window.annotations.annotation_trajectory_tolerance_spin_box.setValue(2.0)
        self.window.annotations.annotation_trajectory_tolerance_spin_box.setSuffix(" s")
        self.window.annotations.annotation_trajectory_combo = ComboBox()
        self.window.annotations.annotation_trajectory_combo.addItem("不关联轨迹", None)
        self.window.annotations.annotation_update_button = PushButton("更新选中标注")
        mark_buttons = QWidget()
        mark_buttons_layout = QHBoxLayout(mark_buttons)
        mark_buttons_layout.setContentsMargins(0, 0, 0, 0)
        mark_buttons_layout.setSpacing(5)
        mark_buttons_layout.addWidget(self.window.annotations.annotation_point_button)
        mark_buttons_layout.addWidget(self.window.annotations.annotation_interval_start_button)
        mark_buttons_layout.addWidget(self.window.annotations.annotation_interval_finish_button)
        mark_form.addRow(
            control_group(
                Label("车辆"),
                self.window.annotations.annotation_vehicle_combo,
                Label("车道"),
                self.window.annotations.annotation_lane_combo,
            )
        )
        mark_form.addRow("行驶方向", self.window.annotations.annotation_direction_combo)
        advanced_form.addRow("事件类型", self.window.annotations.annotation_kind_combo)
        advanced_form.addRow("结论", self.window.annotations.annotation_outcome_combo)
        advanced_form.addRow("备注", self.window.annotations.annotation_note_edit)
        drawing_tools = QWidget()
        tools_layout = QGridLayout(drawing_tools)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(5)
        self.window.annotations.annotation_shape_buttons = {}
        self.window.annotations.annotation_plot_tool_buttons = {}
        plot_tools = self.window.annotations.annotation_plot_controls
        for index, (kind, label) in enumerate(GEOMETRY_LABELS.items()):
            shortcut = {"bbox": "B", "obb": "R", "kp": "K", "lin": "L"}[kind]
            button = PushButton(f"{label} ({shortcut})")
            button.setCheckable(True)
            button.setAccessibleName(f"绘制{label}")
            button.clicked.connect(
                lambda checked, k=kind: self.window.annotations._setAnnotationDrawingTool(k if checked else "")
            )
            tools_layout.addWidget(button, index // 2, index % 2)
            self.window.annotations.annotation_shape_buttons[kind] = button
            plot_button = PushButton(f"{label} ({shortcut})")
            plot_button.setCheckable(True)
            plot_button.clicked.connect(
                lambda checked, k=kind: self.window.annotations._setAnnotationDrawingTool(k if checked else "")
            )
            self.window.annotations.annotation_plot_tool_buttons[kind] = plot_button
            plot_tools.addWidget(plot_button)
        self.window.annotations.annotation_plot_finish_button = PushButton("完成 (Enter)")
        self.window.annotations.annotation_plot_finish_button.clicked.connect(
            self.window.annotations._finishAnnotationShape
        )
        self.window.annotations.annotation_plot_cancel_button = PushButton("浏览 (Esc)")
        self.window.annotations.annotation_plot_cancel_button.clicked.connect(
            lambda: self.window.annotations.annotation_canvas.cancel()
        )
        plot_tools.addWidget(self.window.annotations.annotation_plot_finish_button)
        plot_tools.addWidget(self.window.annotations.annotation_plot_cancel_button)
        self.window.annotations.annotation_shape_save_button = PushButton("保存形状 (Enter)")
        self.window.annotations.annotation_shape_save_button.clicked.connect(
            lambda: self.window.annotations.annotation_canvas.commit_edit()
        )
        self.window.annotations.annotation_shape_cancel_button = PushButton("取消 / 浏览 (Esc)")
        self.window.annotations.annotation_shape_cancel_button.clicked.connect(
            lambda: self.window.annotations.annotation_canvas.cancel()
        )
        tools_layout.addWidget(self.window.annotations.annotation_shape_save_button, 2, 0)
        tools_layout.addWidget(self.window.annotations.annotation_shape_cancel_button, 2, 1)
        self.window.annotations.annotation_draw_hint = Label("在 DAS 图上画框或逐点描绘轨迹；Enter 完成，Esc 取消")
        self.window.annotations.annotation_draw_hint.setWordWrap(True)
        self.window.annotations.annotation_draw_hint.setObjectName("secondaryLabel")
        advanced_form.addRow("DAS 图标注", drawing_tools)
        advanced_form.addRow(self.window.annotations.annotation_draw_hint)
        advanced_form.addRow(mark_buttons)
        advanced_form.addRow(self.window.annotations.annotation_interval_label)
        advanced_form.addRow("候选窗口", self.window.annotations.annotation_trajectory_tolerance_spin_box)
        advanced_form.addRow("关联轨迹", self.window.annotations.annotation_trajectory_combo)
        mark_form.addRow(self.window.annotations.annotation_update_button)
        mark_form.addRow(self.window.annotations.annotation_advanced_toggle)
        mark_form.addRow(self.window.annotations.annotation_advanced_widget)
        layout.addWidget(mark_group)

        table_group = QGroupBox("标注列表")
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(8, 8, 8, 8)
        self.window.annotations.annotation_table = QTableWidget(0, 11)
        self.window.annotations.annotation_table.setHorizontalHeaderLabels(
            [
                "显",
                "#",
                "形状 / 事件",
                "摄像头时间",
                "DAS 时间",
                "轨迹 / 速度",
                "结论",
                "通道",
                "车辆",
                "车道",
                "行驶方向",
            ]
        )
        self.window.annotations.annotation_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.window.annotations.annotation_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.window.annotations.annotation_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.window.annotations.annotation_table.verticalHeader().setVisible(False)
        self.window.annotations.annotation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.window.annotations.annotation_table.horizontalHeader().setStretchLastSection(True)
        self.window.annotations.annotation_table.setMinimumHeight(110)
        self.window.annotations.annotation_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.window.annotations.annotation_table.customContextMenuRequested.connect(
            self.window.annotations._annotationTableContextMenu
        )
        self.window.annotations.annotation_table.itemDoubleClicked.connect(
            lambda item: self.window.annotations._editAnnotationProperties(
                self.window.annotations.annotation_table.item(item.row(), 1).data(Qt.UserRole)
            )
        )
        table_layout.addWidget(self.window.annotations.annotation_table)
        self.window.annotations.annotation_delete_button = PushButton("删除选中")
        self.window.annotations.annotation_delete_button.setObjectName("dangerAction")
        self.window.annotations.annotation_undo_button = PushButton("撤销")
        self.window.annotations.annotation_redo_button = PushButton("重做")
        table_buttons = QHBoxLayout()
        table_buttons.addWidget(self.window.annotations.annotation_delete_button)
        table_buttons.addWidget(self.window.annotations.annotation_undo_button)
        table_buttons.addWidget(self.window.annotations.annotation_redo_button)
        table_buttons.addStretch(1)
        table_layout.addLayout(table_buttons)
        layout.addWidget(table_group, 1)

        self.window.annotations.annotation_new_button.clicked.connect(self.window.annotations.newVideoAnnotationProject)
        self.window.annotations.annotation_open_button.clicked.connect(
            self.window.annotations.openVideoAnnotationProject
        )
        self.window.annotations.annotation_save_button.clicked.connect(
            self.window.annotations.saveVideoAnnotationProject
        )
        self.window.annotations.annotation_export_button.clicked.connect(
            self.window.annotations.exportVideoAnnotationsCsv
        )
        self.window.sync.video_start_time_edit.editingFinished.connect(self.window.sync.applyVideoSync)
        self.window.sync.video_sync_apply_button.clicked.connect(self.window.sync.applyVideoSync)
        self.window.sync.video_sync_single_button.clicked.connect(
            lambda: self.window.sync._beginVideoSyncPick("single")
        )
        self.window.sync.video_sync_anchor_button.clicked.connect(
            lambda: self.window.sync._beginVideoSyncPick("anchor")
        )
        self.window.sync.video_sync_undo_button.clicked.connect(self.window.sync.undoVideoSyncCalibration)
        self.window.sync.video_sync_reset_button.clicked.connect(self.window.sync.resetVideoSyncCalibration)
        self.window.annotations.annotation_point_button.clicked.connect(self.window.annotations.addVideoPointAnnotation)
        self.window.annotations.annotation_interval_start_button.clicked.connect(
            self.window.annotations.beginVideoIntervalAnnotation
        )
        self.window.annotations.annotation_interval_finish_button.clicked.connect(
            self.window.annotations.finishVideoIntervalAnnotation
        )
        self.window.annotations.annotation_update_button.clicked.connect(
            self.window.annotations.updateSelectedVideoAnnotation
        )
        self.window.annotations.annotation_delete_button.clicked.connect(
            self.window.annotations.deleteSelectedVideoAnnotation
        )
        self.window.annotations.annotation_undo_button.clicked.connect(self.window.annotations.undoLastVideoAnnotation)
        self.window.annotations.annotation_redo_button.clicked.connect(self.window.annotations.redoVideoAnnotation)
        self.window.annotations.annotation_table.itemSelectionChanged.connect(
            self.window.annotations._videoAnnotationTableSelectionChanged
        )
        self.window.annotations.annotation_table.itemChanged.connect(
            self.window.annotations._videoAnnotationTableItemChanged
        )

    def _setAnnotationAdvancedVisible(self, visible):
        self.window.annotations.annotation_advanced_widget.setVisible(visible)
        self.window.annotations.annotation_advanced_toggle.setText("更多标注选项 ▾" if visible else "更多标注选项 ▸")
