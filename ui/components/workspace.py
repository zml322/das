"""Workspace layout, navigation and window events."""

import ctypes
import sys

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QScrollBar,
    QSizePolicy,
    QSplitter,
    QTabBar,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from image.image import folder_jpg, play_jpg, stop_jpg
from ui.components.window_feature import WindowFeature
from ui.widgets.custom_widgets import (
    ComboBox,
    Label,
    LineEdit,
    LineEditWithReg,
    MyPlotWidget,
    PushButton,
    SpinBox,
)
from utils.function import resourcePath, setPicture
from utils.version import __version__


class WorkspaceController(WindowFeature):
    """Workspace layout, navigation and window events."""

    def __init__(self, window):
        super().__init__(window)
        self._preferred_sidebar_width = self.window.preferences.sidebar_width()

    def initMainWindow(self):
        """获取屏幕分辨率，设置主窗口初始大小"""
        screen = QApplication.desktop()
        screen_height = int(screen.screenGeometry().height() * 0.8)
        screen_width = int(screen.screenGeometry().width() * 0.8)
        self.window.resize(screen_width, screen_height)

    def initUI(self):
        """初始化 ui"""
        self.menu_bar = self.window.menuBar()  # 菜单栏
        self.window.setWindowTitle(f"DAS数据查看 v{__version__}")
        self.window.setWindowIcon(QIcon(resourcePath("image/img.png")))

        # AppUserModelID 仅适用于 Windows；macOS/Linux 没有 ctypes.windll。
        if sys.platform == "win32":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("myappid")
            except (AttributeError, OSError):
                # 任务栏图标设置失败不应影响主程序启动。
                pass

    def initLayout(self):
        """初始化主窗口布局"""
        main_window_widget = QWidget()
        main_window_hbox = QHBoxLayout()
        main_window_hbox.setContentsMargins(8, 8, 8, 8)
        main_window_hbox.setSpacing(8)

        # 左侧导航：目录和文件列表始终可见，数据概览与其归在一起。
        file_hbox = QHBoxLayout()
        file_area_vbox = QVBoxLayout()
        file_area_vbox.setContentsMargins(0, 0, 0, 0)
        file_area_vbox.setSpacing(12)

        self.window.data.file_path_line_edit = LineEdit(focus=False)
        self.window.data.file_path_line_edit.setPlaceholderText("选择数据文件夹")

        change_file_path_button = PushButton()
        setPicture(
            change_file_path_button,
            folder_jpg,
            "folder.jpg",
        )
        change_file_path_button.setToolTip("选择数据文件夹")
        change_file_path_button.setAccessibleName("选择数据文件夹")
        change_file_path_button.clicked.connect(self.window.data.changeFilePath)

        file_table_scrollbar = QScrollBar(Qt.Vertical)
        file_table_scrollbar.setMinimumHeight(100)
        self.window.data.files_table_widget = QTableWidget(30, 1)
        self.window.data.files_table_widget.setVerticalScrollBar(file_table_scrollbar)
        self.window.data.files_table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)  # 设置表格不可编辑
        self.window.data.files_table_widget.setHorizontalHeaderLabels(["文件"])  # 设置表头
        self.window.data.files_table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.window.data.files_table_widget.verticalHeader().setVisible(False)
        self.window.data.files_table_widget.setWordWrap(False)
        self.window.data.files_table_widget.setAlternatingRowColors(True)
        self.window.data.files_table_widget.setMinimumHeight(180)
        self.window.data.files_table_widget.setToolTip(
            "鼠标悬停可查看完整路径；使用 Ctrl 或 Shift 选择多个文件，选择完成后点击确定加载"
        )
        QTableWidget.resizeRowsToContents(self.window.data.files_table_widget)
        self.window.data.files_table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)  # 设置一次选中一排内容
        self.window.data.files_table_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.window.data.files_table_widget.itemSelectionChanged.connect(self.window.data.updatePendingFileSelection)

        self.window.data.pending_file_selection_label = Label("待拼接：请选择文件")
        self.window.data.pending_file_selection_label.setWordWrap(True)
        self.window.data.pending_file_selection_label.setObjectName("secondaryLabel")
        self.window.data.load_selected_files_button = PushButton("确定加载并拼接")
        self.window.data.load_selected_files_button.setEnabled(False)
        self.window.data.load_selected_files_button.setToolTip("按文件表中的顺序一次性读取、拼接并绘制所选文件")
        self.window.data.load_selected_files_button.clicked.connect(self.window.data.selectDataFromTable)

        # 文件区布局
        file_hbox.addWidget(self.window.data.file_path_line_edit)
        file_hbox.addWidget(change_file_path_button)
        file_area_vbox.addLayout(file_hbox)
        file_area_vbox.addWidget(self.window.data.files_table_widget, 1)
        file_area_vbox.addWidget(self.window.data.pending_file_selection_label)
        file_area_vbox.addWidget(self.window.data.load_selected_files_button)

        self.window.data.stitched_files_group = QGroupBox("当前拼接文件（0）")
        self.window.data.stitched_files_list = QListWidget()
        self.window.data.stitched_files_list.setAlternatingRowColors(True)
        self.window.data.stitched_files_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.window.data.stitched_files_list.setMinimumHeight(70)
        self.window.data.stitched_files_list.setMaximumHeight(120)
        self.window.data.stitched_files_list.setToolTip("按拼接顺序显示来源文件；点击可高亮图中的对应分段")
        self.window.data.stitched_files_list.currentRowChanged.connect(self.window.overlays._stitchedFileRowChanged)
        stitched_files_vbox = QVBoxLayout()
        stitched_files_vbox.setContentsMargins(8, 8, 8, 8)
        stitched_files_vbox.addWidget(self.window.data.stitched_files_list)
        self.window.data.stitched_files_group.setLayout(stitched_files_vbox)
        file_area_vbox.addWidget(self.window.data.stitched_files_group)

        # 数据元信息移至导航区，避免长期挤占绘图区的上下空间。
        self.window.data.sampling_rate_line_edit = LineEditWithReg(digit=True, focus=False)
        self.window.data.current_sampling_times_line_edit = LineEditWithReg(focus=False)
        self.window.data.current_channels_line_edit = LineEditWithReg(focus=False)
        self.window.data.gps_from_line_edit = LineEdit(focus=False)
        self.window.data.gps_to_line_edit = LineEdit(focus=False)
        self.window.controls.time_correction_spin_box = QDoubleSpinBox()
        self.window.controls.time_correction_spin_box.setRange(-86400.0, 86400.0)
        self.window.controls.time_correction_spin_box.setDecimals(3)
        self.window.controls.time_correction_spin_box.setSingleStep(0.1)
        self.window.controls.time_correction_spin_box.setSuffix(" s")
        self.window.controls.time_correction_spin_box.setKeyboardTracking(False)
        self.window.controls.time_correction_spin_box.setValue(self.window.controls.time_correction_seconds)
        self.window.controls.time_correction_spin_box.setToolTip(
            "设备时间落后真实时间时填正数；例如落后 12 秒填写 +12.000 s"
        )
        self.window.controls.time_correction_apply_button = PushButton("应用")
        self.window.controls.time_correction_apply_button.setObjectName("timeCorrectionApplyButton")
        self.window.controls.time_correction_apply_button.setToolTip("保存时间修正，并重新计算显示中的推算时间")
        self.window.controls.time_correction_apply_button.clicked.connect(
            self.window.controls.applyTimeCorrectionFromSidebar
        )
        time_correction_controls = QWidget()
        time_correction_layout = QHBoxLayout(time_correction_controls)
        time_correction_layout.setContentsMargins(0, 0, 0, 0)
        time_correction_layout.setSpacing(6)
        time_correction_layout.addWidget(self.window.controls.time_correction_spin_box, 1)
        time_correction_layout.addWidget(self.window.controls.time_correction_apply_button)
        for field in (
            self.window.data.sampling_rate_line_edit,
            self.window.data.current_sampling_times_line_edit,
            self.window.data.current_channels_line_edit,
            self.window.data.gps_from_line_edit,
            self.window.data.gps_to_line_edit,
        ):
            field.setReadOnly(True)
            field.setFixedHeight(22)
            field.setObjectName("metadataValue")

        self.window.data.overview_group = QGroupBox("数据概览")
        self.window.data.overview_group.setObjectName("dataOverview")
        self.window.data.overview_group.setMaximumHeight(170)
        self.window.data.overview_form = QFormLayout()
        self.window.data.overview_form.setContentsMargins(5, 2, 5, 2)
        self.window.data.overview_form.setHorizontalSpacing(6)
        self.window.data.overview_form.setVerticalSpacing(1)
        self.window.data.overview_form.addRow("采样率", self.window.data.sampling_rate_line_edit)
        self.window.data.overview_form.addRow("采样次数", self.window.data.current_sampling_times_line_edit)
        self.window.data.overview_form.addRow("通道数", self.window.data.current_channels_line_edit)
        self.window.data.overview_form.addRow("推算开始", self.window.data.gps_from_line_edit)
        self.window.data.overview_form.addRow("推算结束", self.window.data.gps_to_line_edit)
        self.window.data.overview_form.addRow("设备时间修正", time_correction_controls)
        self.window.data.overview_group.setLayout(self.window.data.overview_form)
        file_area_vbox.addWidget(self.window.data.overview_group)

        # 单通道操作只在“单通道”页中显示。
        channel_number_label = Label("通道号")
        self.window.controls.channel_number_spinbx = SpinBox()
        self.window.controls.channel_number_spinbx.setValue(1)
        self.window.controls.channel_number_spinbx.setMinimumWidth(88)
        self.window.controls.channel_number_spinbx.valueChanged.connect(self.window.controls.changeChannelNumber)
        self.window.controls.channel_number_spinbx.valueChanged.connect(self.window.plots.plotSingleChannelTime)
        self.window.controls.channel_number_spinbx.valueChanged.connect(self.window.plots.plotAmplitudeFrequency)

        # 播放音频按钮
        self.window.plots.player_play_button = PushButton()
        setPicture(self.window.plots.player_play_button, play_jpg, "play.jpg")
        self.window.plots.player_play_button.clicked.connect(self.window.plots.createWavFile)
        self.window.plots.player_play_button.clicked.connect(self.window.plots.createPlayer)
        self.window.plots.player_play_button.clicked.connect(self.window.plots.playBtnChangeState)

        # 停止音频播放按钮
        self.window.plots.player_stop_button = PushButton()
        setPicture(self.window.plots.player_stop_button, stop_jpg, "stop.jpg")
        self.window.plots.player_stop_button.clicked.connect(self.window.plots.resetPlayer)

        self.window.plots.player_play_button.setDisabled(True)
        self.window.plots.player_stop_button.setDisabled(True)  # 默认不可选中

        channel_controls_hbox = QHBoxLayout()
        channel_controls_hbox.setContentsMargins(0, 0, 0, 0)
        channel_controls_hbox.setSpacing(6)
        channel_controls_hbox.addWidget(channel_number_label)
        channel_controls_hbox.addWidget(self.window.controls.channel_number_spinbx)
        channel_controls_hbox.addSpacing(10)
        channel_controls_hbox.addWidget(self.window.plots.player_play_button)
        channel_controls_hbox.addWidget(self.window.plots.player_stop_button)
        channel_controls_hbox.addStretch(1)

        # 灰度图显示控制只在灰度图页面显示。
        image_colormap_label = Label("图像颜色")
        self.window.plots.image_colormap_combx = ComboBox()
        self.window.plots.image_colormap_combx.addItems(
            [
                "灰度",
                "RdBu",
                "viridis",
                "plasma",
                "inferno",
                "magma",
                "turbo",
                "jet",
                "seismic",
                "coolwarm",
            ]
        )
        self.window.plots.image_colormap_combx.setCurrentText(self.window.plots.image_colormap)
        self.window.plots.image_colormap_combx.setFixedWidth(100)
        self.window.plots.image_colormap_combx.currentTextChanged.connect(self.window.plots.updateImageColorParams)

        image_level_min_label = Label("最小值(%)")
        self.window.plots.image_level_min_line_edit = LineEdit()
        self.window.plots.image_level_min_line_edit.setFixedWidth(76)
        self.window.plots.image_level_min_line_edit.setPlaceholderText("自动")
        self.window.plots.image_level_min_line_edit.setToolTip("相对于当前图像最大绝对值的百分比，例如 -80")

        image_level_max_label = Label("最大值(%)")
        self.window.plots.image_level_max_line_edit = LineEdit()
        self.window.plots.image_level_max_line_edit.setFixedWidth(76)
        self.window.plots.image_level_max_line_edit.setPlaceholderText("自动")
        self.window.plots.image_level_max_line_edit.setToolTip("相对于当前图像最大绝对值的百分比，例如 80")

        image_auto_button = PushButton("自动")
        image_auto_button.clicked.connect(self.window.plots.autoImageLevels)

        image_apply_button = PushButton("应用")
        image_apply_button.clicked.connect(self.window.plots.updateImageColorParams)

        image_controls_hbox = QHBoxLayout()
        image_controls_hbox.setSpacing(4)
        image_controls_hbox.addWidget(image_colormap_label)
        image_controls_hbox.addWidget(self.window.plots.image_colormap_combx)
        image_controls_hbox.addSpacing(6)
        image_controls_hbox.addWidget(image_level_min_label)
        image_controls_hbox.addWidget(self.window.plots.image_level_min_line_edit)
        image_controls_hbox.addSpacing(3)
        image_controls_hbox.addWidget(image_level_max_label)
        image_controls_hbox.addWidget(self.window.plots.image_level_max_line_edit)
        image_controls_hbox.addSpacing(6)
        image_controls_hbox.addWidget(image_auto_button)
        image_controls_hbox.addWidget(image_apply_button)

        speed_ruler_controls_hbox = QHBoxLayout()
        speed_ruler_controls_hbox.setSpacing(4)
        self.window.vehicles.speed_ruler_spacing_spin_box = QDoubleSpinBox()
        self.window.vehicles.speed_ruler_spacing_spin_box.setRange(0.001, 1_000_000.0)
        self.window.vehicles.speed_ruler_spacing_spin_box.setDecimals(3)
        self.window.vehicles.speed_ruler_spacing_spin_box.setSingleStep(0.1)
        self.window.vehicles.speed_ruler_spacing_spin_box.setSuffix(" m")
        self.window.vehicles.speed_ruler_spacing_spin_box.setValue(self.window.vehicles.speed_ruler_channel_spacing)
        self.window.vehicles.speed_ruler_spacing_spin_box.setKeyboardTracking(False)
        self.window.vehicles.speed_ruler_spacing_spin_box.setToolTip("真实相邻通道距离 dx；不能使用 gauge length")
        self.window.vehicles.speed_ruler_spacing_spin_box.valueChanged.connect(
            self.window.vehicles.updateSpeedRulerChannelSpacing
        )
        self.window.vehicles.speed_ruler_reset_button = PushButton("添加速度标尺")
        self.window.vehicles.speed_ruler_reset_button.setEnabled(False)
        self.window.vehicles.speed_ruler_reset_button.setToolTip("在当前灰度图范围内添加或重置可拖动的速度测量线")
        self.window.vehicles.speed_ruler_reset_button.clicked.connect(self.window.vehicles.addOrResetSpeedRuler)
        self.window.vehicles.speed_ruler_remove_button = PushButton("移除速度标尺")
        self.window.vehicles.speed_ruler_remove_button.setEnabled(False)
        self.window.vehicles.speed_ruler_remove_button.clicked.connect(self.window.vehicles.removeSpeedRuler)
        self.window.vehicles.speed_ruler_status_label = Label("未添加")
        self.window.vehicles.speed_ruler_status_label.setObjectName("statusBadge")
        self.window.vehicles.speed_ruler_status_label.setProperty("state", "inactive")
        self.window.vehicles.speed_ruler_status_label.setToolTip("速度标尺未添加")
        self.window.vehicles.speed_ruler_status_label.setWordWrap(False)
        self.window.vehicles.speed_ruler_status_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        speed_ruler_controls_hbox.addWidget(Label("车辆速度标尺  dx"))
        speed_ruler_controls_hbox.addWidget(self.window.vehicles.speed_ruler_spacing_spin_box)
        speed_ruler_controls_hbox.addWidget(self.window.vehicles.speed_ruler_reset_button)
        speed_ruler_controls_hbox.addWidget(self.window.vehicles.speed_ruler_remove_button)
        speed_ruler_controls_hbox.addWidget(self.window.vehicles.speed_ruler_status_label)

        # 绘制灰度图
        self.window.plots.plot_gray_scale_widget = MyPlotWidget(
            "", "推算时间", "通道", check_mouse=False, time_axis=True
        )
        self.window.plots.gray_scale_container = QWidget()
        gray_scale_vbox = QVBoxLayout()
        gray_scale_vbox.setContentsMargins(8, 8, 8, 8)
        gray_scale_vbox.setSpacing(8)
        self.window.plots.plot_toolbar = QWidget()
        self.window.plots.plot_toolbar.setObjectName("plotToolbar")
        plot_toolbar_hbox = QHBoxLayout(self.window.plots.plot_toolbar)
        plot_toolbar_hbox.setContentsMargins(8, 6, 8, 6)
        plot_toolbar_hbox.setSpacing(10)
        plot_toolbar_hbox.addLayout(image_controls_hbox)
        plot_toolbar_hbox.addLayout(speed_ruler_controls_hbox)
        plot_toolbar_hbox.addStretch(1)
        gray_scale_vbox.addWidget(self.window.plots.plot_toolbar)
        gray_scale_vbox.addWidget(self.window.plots.plot_gray_scale_widget)
        self.window.plots.gray_scale_container.setLayout(gray_scale_vbox)

        # 绘制单通道相位差-时间图
        self.window.plots.plot_single_channel_time_widget = MyPlotWidget(
            "相位差图", "推算时间", "相位差（rad）", grid=True, time_axis=True
        )

        # 绘制频谱图
        self.window.plots.plot_amplitude_frequency_widget = MyPlotWidget("幅值图", "频率（Hz）", "幅值", grid=True)

        combine_image_widget = QWidget()
        image_vbox = QVBoxLayout()
        image_vbox.setContentsMargins(6, 6, 6, 6)
        image_vbox.setSpacing(6)
        image_vbox.addLayout(channel_controls_hbox)
        image_vbox.addWidget(self.window.plots.plot_single_channel_time_widget)
        image_vbox.addWidget(self.window.plots.plot_amplitude_frequency_widget)
        combine_image_widget.setLayout(image_vbox)

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("workspaceTabs")
        self.tab_widget.setMovable(True)  # 设置tab可移动
        self.tab_widget.setTabsClosable(True)  # 设置tab可关闭
        self.tab_widget.tabCloseRequested[int].connect(self.removeTab)
        self.tab_widget.addTab(self.window.plots.gray_scale_container, "灰度图")
        self.tab_widget.addTab(combine_image_widget, "单通道")
        self.window.waves.initMultiWavesTab()
        self.tab_widget.addTab(self.window.waves.multi_waves_container, "多通道云图")
        self.window.video_ui.initVideoComparisonTab()
        self.tab_widget.addTab(self.window.video_ui.video_compare_container, "视频对照")
        self.tab_widget.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.tab_widget.tabBar().setTabButton(1, QTabBar.RightSide, None)  # 设置删除按钮消失
        self.tab_widget.tabBar().setTabButton(2, QTabBar.RightSide, None)
        self.tab_widget.tabBar().setTabButton(3, QTabBar.RightSide, None)
        self.tab_widget.currentChanged.connect(self._workspaceTabChanged)

        self.window.overlays.event_range_widget = QWidget()
        self.window.overlays.event_range_widget.setObjectName("eventRangeBar")
        event_range_hbox = QHBoxLayout()
        event_range_hbox.setContentsMargins(8, 5, 8, 5)
        event_range_hbox.setSpacing(6)
        self.window.overlays.event_range_from_edit = QDateTimeEdit()
        self.window.overlays.event_range_to_edit = QDateTimeEdit()
        for editor in (self.window.overlays.event_range_from_edit, self.window.overlays.event_range_to_edit):
            editor.setDisplayFormat("yyyy-MM-dd HH:mm:ss.zzz")
            editor.setCalendarPopup(True)
            editor.setKeyboardTracking(False)
            editor.setMinimumWidth(190)
        self.window.overlays.event_range_set_button = PushButton("设置标记")
        self.window.overlays.event_range_view_button = PushButton("查看此范围")
        self.window.overlays.event_range_reset_button = PushButton("恢复全部")
        self.window.overlays.event_markers_visible_checkbox = QCheckBox("显示事件标记")
        self.window.overlays.event_markers_visible_checkbox.setChecked(True)
        self.window.overlays.event_markers_visible_checkbox.setToolTip(
            "显示或隐藏图中的事件开始、结束标记；不会改变当前查看范围"
        )
        self.window.overlays.event_range_set_button.setToolTip("移动图中的开始/结束竖线，不改变数据查看范围")
        self.window.overlays.event_range_view_button.setToolTip("按竖线范围更新当前视图，不修改导入原始数据")
        self.window.overlays.event_range_reset_button.setToolTip("恢复完整时间视图并把竖线重置到数据两端")
        self.window.overlays.event_range_set_button.clicked.connect(self.window.overlays.setEventRangeFromInputs)
        self.window.overlays.event_range_view_button.clicked.connect(self.window.overlays.viewEventRange)
        self.window.overlays.event_range_reset_button.clicked.connect(self.window.overlays.restoreFullEventRange)
        self.window.overlays.event_markers_visible_checkbox.toggled.connect(self.window.overlays.setEventMarkersVisible)
        event_range_hbox.addWidget(Label("事件开始"))
        event_range_hbox.addWidget(self.window.overlays.event_range_from_edit)
        event_range_hbox.addWidget(Label("事件结束"))
        event_range_hbox.addWidget(self.window.overlays.event_range_to_edit)
        event_range_hbox.addWidget(self.window.overlays.event_range_set_button)
        event_range_hbox.addWidget(self.window.overlays.event_range_view_button)
        event_range_hbox.addWidget(self.window.overlays.event_range_reset_button)
        event_range_hbox.addWidget(self.window.overlays.event_markers_visible_checkbox)
        event_range_hbox.addStretch(1)
        self.window.overlays.event_range_widget.setLayout(event_range_hbox)
        self.window.overlays.setEventRangeControlsEnabled(False)

        # Tab 是唯一的主工作区，最大化图形可用面积。
        main_window_vbox = QVBoxLayout()
        main_window_vbox.setContentsMargins(0, 0, 0, 0)
        main_window_vbox.setSpacing(0)
        main_window_vbox.addWidget(self.window.overlays.event_range_widget)
        main_window_vbox.addWidget(self.tab_widget)

        self.window.data.data_sidebar_widget = QWidget()
        self.window.data.data_sidebar_widget.setLayout(file_area_vbox)

        self.window.filtering.filter_sidebar_widget = QWidget()
        self.window.filtering.filter_sidebar_layout = QVBoxLayout(self.window.filtering.filter_sidebar_widget)
        self.window.filtering.filter_sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.window.filtering.filter_sidebar_placeholder = Label("请先导入 DAS 数据，再打开二维滤波页。")
        self.window.filtering.filter_sidebar_placeholder.setAlignment(Qt.AlignCenter)
        self.window.filtering.filter_sidebar_placeholder.setWordWrap(True)
        self.window.filtering.filter_sidebar_placeholder.setObjectName("secondaryLabel")
        self.window.filtering.filter_sidebar_placeholder.setContentsMargins(16, 16, 16, 16)
        self.window.filtering.filter_sidebar_layout.addWidget(self.window.filtering.filter_sidebar_placeholder)

        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setObjectName("sidebarTabs")
        self.sidebar_tabs.setMinimumWidth(380)
        self.sidebar_tabs.addTab(self.window.data.data_sidebar_widget, "数据")
        self.sidebar_tabs.addTab(self.window.filtering.filter_sidebar_widget, "二维滤波")
        self.sidebar_tabs.addTab(self.window.video_ui.annotation_sidebar_widget, "标注")
        self.sidebar_tabs.currentChanged.connect(self._sidebarTabChanged)

        content_widget = QWidget()
        content_widget.setMinimumWidth(500)
        content_widget.setLayout(main_window_vbox)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(8)
        self.main_splitter.addWidget(self.sidebar_tabs)
        self.main_splitter.addWidget(content_widget)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([self._preferred_sidebar_width, 1060])
        self.main_splitter.splitterMoved.connect(self._rememberSidebarWidth)

        main_window_hbox.addWidget(self.main_splitter)
        main_window_widget.setLayout(main_window_hbox)
        self.window.setCentralWidget(main_window_widget)

    def closeEvent(self, event: QEvent):
        """
        退出时的提示
        Args:
            event: 事件

        Returns:

        """
        if self.window.filtering.das_filter_dialog is not None and self.window.filtering.das_filter_dialog.is_busy():
            QMessageBox.warning(self.window, "滤波处理中", "请等待滤波链计算完成后再退出。")
            event.ignore()
            return
        reply = QMessageBox.question(
            self.window, "提示", "是否退出？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        # 判断返回值，如果点击的是Yes按钮，我们就关闭组件和应用，否则就忽略关闭事件
        if reply == QMessageBox.Yes:
            self.window.shutdown()
            event.accept()
        else:
            event.ignore()

    def keyPressEvent(self, event):
        """Expose visible video-label shortcuts without hijacking text editors."""

        focus = QApplication.focusWidget()
        if focus is not None and any(
            focus.inherits(name) for name in ("QLineEdit", "QAbstractSpinBox", "QComboBox", "QTableWidget")
        ):
            QMainWindow.keyPressEvent(self.window, event)
            return
        if (
            hasattr(self, "tab_widget")
            and self.tab_widget.currentWidget() is self.window.video_ui.video_compare_container
        ):
            key = event.key()
            if event.modifiers() & Qt.ControlModifier and key == Qt.Key_Z:
                if event.modifiers() & Qt.ShiftModifier:
                    self.window.annotations.redoVideoAnnotation()
                else:
                    self.window.annotations.undoLastVideoAnnotation()
                event.accept()
                return
            if event.modifiers() & Qt.ControlModifier and key == Qt.Key_S:
                self.window.annotations.saveVideoAnnotationProject()
                event.accept()
                return
            shapes = {
                Qt.Key_B: "bbox",
                Qt.Key_R: "obb",
                Qt.Key_K: "kp",
                Qt.Key_L: "lin",
            }
            if key in shapes:
                self.window.annotations._setAnnotationDrawingTool(shapes[key])
                event.accept()
                return
            if key == Qt.Key_F11:
                self.window.video_plot.video_focus_button.toggle()
                event.accept()
                return
            if key == Qt.Key_Escape and self.window.video_plot._video_focus_mode:
                self.window.video_plot.video_focus_button.setChecked(False)
                event.accept()
                return
            if key == Qt.Key_Space:
                self.window.playback.toggleVideoPlayback()
                event.accept()
                return
            if key == Qt.Key_T:
                self.window.annotations.addVideoPointAnnotation()
                event.accept()
                return
            if key == Qt.Key_I:
                self.window.annotations.beginVideoIntervalAnnotation()
                event.accept()
                return
            if key == Qt.Key_O:
                self.window.annotations.finishVideoIntervalAnnotation()
                event.accept()
                return
        QMainWindow.keyPressEvent(self.window, event)

    def removeTab(self, index: int):
        """
        关闭对应选项卡
        Args:
            index: 选项卡索引

        Returns:

        """
        self.tab_widget.removeTab(index)

    def _sidebarTabChanged(self, index: int):
        """Lazily initialize filtering when the user clicks the sidebar tab."""

        if self.sidebar_tabs.widget(index) is not self.window.filtering.filter_sidebar_widget:
            return
        if self.window.data.raw_data is None:
            self.window.filtering.filter_sidebar_placeholder.setText("请先在“数据”页导入 DAS 数据。")
            return
        if self.window.filtering.das_filter_dialog is None:
            QTimer.singleShot(0, self.window.filtering.showDASFilterDialog)

    def _workspaceTabChanged(self, _index: int):
        """Pair the video workspace with its visible video/annotation sidebar."""

        video_active = self.tab_widget.currentWidget() is self.window.video_ui.video_compare_container
        self.window.overlays.event_range_widget.setVisible(not video_active)
        if video_active:
            if not self.window.video_plot._video_focus_mode:
                self.sidebar_tabs.setVisible(True)
                self.sidebar_tabs.setCurrentWidget(self.window.video_ui.annotation_sidebar_widget)
            return
        if self.window.video_plot._video_focus_mode:
            self.window.video_plot.video_focus_button.setChecked(False)
        if self.window.annotations.annotation_canvas is not None:
            self.window.annotations.annotation_canvas.cancel()

    def _rememberSidebarWidth(self, _position: int, _index: int):
        if not self.sidebar_tabs.isVisible():
            return
        sizes = self.main_splitter.sizes()
        if sizes and sizes[0] >= 380:
            self._preferred_sidebar_width = int(sizes[0])
            self.window.preferences.set_sidebar_width(self._preferred_sidebar_width)
