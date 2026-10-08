# -*- coding: utf-8 -*-
"""
@Time    : 2024/6/12 上午9:27
@Author  : zxy
@File    : mainwindow.py
"""
import ctypes
import os.path
import re
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta

import pandas as pd
from PyQt5 import QtMultimedia
try:

    from PyQt5.QtMultimediaWidgets import QVideoWidget
except ImportError:  # Keep the viewer usable on minimal PyQt installations.
    QVideoWidget = None
from PyQt5.QtCore import Qt, QUrl, QEvent, QRectF, QTimer, QDateTime
from PyQt5.QtGui import QBrush, QColor, QIcon, QPen, QPixmap
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, qApp, QTabWidget, QTableWidget, QAbstractItemView, \
    QTableWidgetItem, QHeaderView, QTabBar, QScrollBar, QHBoxLayout, QDoubleSpinBox, QSplitter, QVBoxLayout, QWidget, \
    QFormLayout, QGroupBox, QListWidget, QListWidgetItem, QGraphicsRectItem, QDateTimeEdit, QCheckBox, QSizePolicy, QSlider, \
    QProgressDialog, QStackedLayout, QGridLayout, QScrollArea
from matplotlib import pyplot as plt
from scipy.integrate import cumulative_trapezoid

from image.image import *
from .classes.binary_image import BinaryImageHandler
from .classes.data_group import DataGroup, ensure_memory_budget, natural_sort_key
from .classes.data_timeline import (
    DataTimeline,
    format_wall_time,
    parse_filename_end_time,
    recorded_end_time,
)
from .classes.data_sifting import DataSifting
from .classes.das_filter import ALGORITHM_LABELS, DASFilterDialog
from .classes.filter_history import (
    add_recent_history,
    history_entry_steps,
    make_history_entry,
    normalize_history,
    upsert_named_history,
)
from .classes.filter_pipeline import FilterStep, clone_steps
from .classes.daspy_converter_dialog import DASPyConverterDialog
from .classes.emd import EMDHandler
from .classes.feature import FeatureCalculator
from .classes.filter import FilterHandler
from .classes.snr import SNRCalculator
from .classes.spectrum import SpectrumHandler
from .classes.speed_ruler import SpeedRulerROI, calculate_projected_speed, format_speed_measurement
from .classes.vehicle_tracking_dialog import VehicleTrackingDialog
from .classes.video_annotation import (
    AnnotationProject,
    format_video_position,
    parse_video_start_time,
    trajectory_candidates,
    trajectory_crossing_time,
)
from .classes.video_media import cached_playable_video, probe_video
from .classes.ffmpeg_video_player import FfmpegFrameWorker
from .classes.video_trajectory import (
    VideoTrajectoryWindow,
    analyze_group_window,
    read_group_window,
    required_window_seconds,
)
from .classes.wavelet import DWTHandler, CWTHandler
from .classes.wavelet_packet import DWPTHandler
from .bin_reader import bin2numpy, read_bin_header
from .function import *
from .preferences import AppPreferences
from .theme import PLOT_LABEL_POINT_SIZE, PLOT_TICK_POINT_SIZE, PLOT_TITLE_POINT_SIZE, plot_font, plot_html, ui_font_family
from .widget import *
from .version import __version__


VIDEO_TRAJECTORY_REQUESTED_WINDOW_SECONDS = 240.0
VIDEO_TRAJECTORY_PREFETCH_SECONDS = 120.0
VIDEO_DISPLAY_WINDOW_SECONDS = 240.0
VIDEO_FOLLOW_WINDOW_SECONDS = 240.0
VIDEO_DAS_MATCH_MARGIN_SECONDS = 30.0
VIDEO_FILTER_PREVIEW_MAX_VALUES = 5_000_000
IMAGE_LEVEL_SAMPLE_LIMIT = 2_000_000


class FileSegmentBarItem(QGraphicsRectItem):
    """Clickable strip identifying one source file in a stitched plot."""

    def __init__(self, rect: QRectF, segment_index: int, on_clicked):
        super().__init__(rect)
        self.segment_index = int(segment_index)
        self._on_clicked = on_clicked
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(20)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_clicked(self.segment_index)
            event.accept()
            return
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self, preferences=None):
        """
        初始化界面
        Returns:

        """
        super().__init__()
        self._provided_preferences = preferences
        self.initMainWindow()
        self.initGlobalParams()
        self.initUI()
        self.initMenu()
        self.initLayout()

    def initMainWindow(self):
        """
        获取屏幕分辨率，设置主窗口初始大小
        Returns:

        """
        screen = QApplication.desktop()
        screen_height = int(screen.screenGeometry().height() * 0.8)
        screen_width = int(screen.screenGeometry().width() * 0.8)
        self.resize(screen_width, screen_height)

    def initGlobalParams(self):
        """
        初始化全局参数，即每次选择文件不改变
        Returns:

        """
        # plt绘图参数
        plt.rcParams['font.sans-serif'] = [ui_font_family(), 'Microsoft YaHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['axes.labelsize'] = 10
        plt.rcParams['axes.titlesize'] = 12
        plt.rcParams['xtick.labelsize'] = 9
        plt.rcParams['ytick.labelsize'] = 9

        # pg组件设置
        pg.setConfigOptions(leftButtonPan=True)  # 设置可用鼠标缩放
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')  # 设置界面前背景色

        self.image_colormap = '灰度'
        self.image_level_min = None
        self.image_level_max = None
        self.gray_scale_color_bar = None
        self.diverging_colormaps = {'RdBu', 'seismic', 'coolwarm'}

        # 导出输出设置
        np.set_printoptions(threshold=sys.maxsize, linewidth=sys.maxsize)  # 设置输出时每行的长度

        # 捕捉到的错误
        self.err = None

        # 文件读取格式
        self.is_scouter = False

        # 数据采集参数
        self.acquisition_params = {}

        # 每次打开程序初始化的参数
        self.channel_number = 1  # 当前通道
        self.channel_number_step = 1  # 通道号递增减步长

        # 滤波器是否更新数据
        self.update_data = False

        # 计算信噪比
        self.snr_calculator = None

        # 滤波器
        self.filter = None
        self.das_filter_dialog = None
        self.video_filter_dialog = None
        self.raw_data = None
        self._das_filter_settings = None
        self._das_filter_steps = []
        self._video_filter_settings = None
        self._video_filter_steps = []
        self._video_filter_customized = False
        self._last_das_filter_steps = []
        self._last_das_filter_shape = None
        self.data_group = None
        self.data_timeline = None
        self._source_time_headers = []
        self.selected_file_segment_index = None
        self._refreshing_stitched_files = False
        self._file_segment_plot_widgets = []
        self._event_range_plot_widgets = []
        self._syncing_event_range = False
        self.preferences = self._provided_preferences or AppPreferences()
        self._preferred_sidebar_width = self.preferences.sidebar_width()
        self.time_correction_seconds = self.preferences.time_correction_seconds()
        self.auto_reapply_filter_pipeline = self.preferences.auto_reapply_filter()
        stored_filter_history = self.preferences.filter_pipeline_history()
        self._filter_pipeline_history = normalize_history(stored_filter_history)
        if stored_filter_history != self._filter_pipeline_history:
            self.preferences.set_filter_pipeline_history(self._filter_pipeline_history)
        self._vehicle_tracking_settings = None
        self.vehicle_trajectories = []
        self._hide_vehicle_trajectories = False
        self.speed_ruler_channel_spacing = 4.0
        self.speed_ruler_active = False
        self.speed_ruler_points = None
        self.speed_ruler_roi = None
        # Video comparison is a project-sidecar workflow.  It intentionally
        # never changes the imported DAS array, its filter chain, or video.
        self.video_annotation_project = AnnotationProject()
        self.video_annotation_context_matches = True
        self.video_annotation_selected_id = None
        self.video_annotation_interval_start_ms = None
        self.video_annotation_dirty = False
        self._video_slider_dragging = False
        self._last_video_playhead_update_ms = -1000
        self.video_player = None
        self.video_playhead_line = None
        self.video_camera_line = None
        self._video_annotation_items = []
        self._video_trajectory_candidates = {}
        self.video_media_probe = None
        self.video_media_playback_path = None
        self.video_media_future: Future | None = None
        self.video_media_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='das-video-transcode'
        )
        self.video_media_poll_timer = QTimer(self)
        self.video_media_poll_timer.setInterval(250)
        self.video_media_poll_timer.timeout.connect(self._pollVideoMediaConversion)
        self.video_playback_backend = 'qt'
        self.video_ffmpeg_worker = None
        self.video_ffmpeg_duration_ms = 0
        self.video_ffmpeg_position_ms = 0
        self.video_ffmpeg_playing = False
        self._video_frame_pixmap = None
        self.video_sync_calibration_anchors = []
        self._video_sync_undo_stack = []
        self._video_sync_pick_mode = None
        self._video_playhead_dragging = False
        self._video_focus_mode = False
        self.video_trajectory_parameters = None
        self.video_trajectory_window_seconds = None
        self.video_trajectory_windows = {}
        self.video_trajectory_pending = []
        self.video_trajectory_future: Future | None = None
        self.video_trajectory_current_window = None
        self.video_trajectory_generation = 0
        self.video_trajectory_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='das-video-trajectory'
        )
        self.video_trajectory_poll_timer = QTimer(self)
        self.video_trajectory_poll_timer.setInterval(100)
        self.video_trajectory_poll_timer.timeout.connect(self._pollVideoTrajectoryWork)
        # Long recordings keep metadata only.  Raw DAS samples are read from
        # the matching BIN files for the current playback window on demand.
        self.video_sequence_data_group = None
        self.video_sequence_timeline = None
        self.video_sequence_source_paths = []
        self.video_sequence_selected_segment_index = None
        self.video_das_match_required = False

        # 二值图
        self.binary_image = None

        # 谱
        self.spectrum = None

        # emd
        self.emd = None

        # 小波分解
        self.cwt = None
        self.dwt = None

        # 小波包分解
        self.dwpt = None

        # 数据筛选
        self.data_sift = None

    def initUI(self):
        """
        初始化 ui
        Returns:

        """
        self.menu_bar = self.menuBar()  # 菜单栏
        self.setWindowTitle(f'DAS数据查看 v{__version__}')
        self.setWindowIcon(QIcon(resourcePath('image/img.png')))

        # AppUserModelID 仅适用于 Windows；macOS/Linux 没有 ctypes.windll。
        if sys.platform == 'win32':
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('myappid')
            except (AttributeError, OSError):
                # 任务栏图标设置失败不应影响主程序启动。
                pass

    def initMenu(self):
        """
        初始化菜单
        Returns:

        """
        # 文件
        self.file_menu = Menu(self.menu_bar, '文件')

        # 导入
        self.import_action = Action(self.file_menu,
                                    '导入',
                                    '导入数据文件',
                                    self.importData,
                                    shortcut='Ctrl+I')

        # 文件-导出
        self.export_action = Action(self.file_menu,
                                    '导出',
                                    '导出数据',
                                    self.exportData,
                                    shortcut='Ctrl+E')

        self.daspy_convert_action = Action(
            self.file_menu,
            'BIN 转 DASPy 格式',
            '将项目 BIN 文件转换为 DASPy 支持的格式，并手动填写元数据',
            self.showDASPyConverterDialog,
        )

        self.file_menu.addSeparator()

        # 文件-读取模式
        self.read_mode_action = Action(self.file_menu,
                                       '读取模式：普通采集',
                                       '改变读取模式，在普通与新模式（scouter 采集）之间变更',
                                       self.changeReadMode)

        # 显示当前数据采集参数
        self.show_aquisition_params_action = Action(self.file_menu,
                                                    '采集参数',
                                                    '显示数据采集参数',
                                                    self.showAcquisitionParams)

        self.file_menu.addSeparator()

        # 退出
        self.quit_action = Action(self.file_menu,
                                  '退出',
                                  '退出软件',
                                  qApp.quit,
                                  shortcut='Ctrl+Q')

        # 操作
        self.operation_menu = Menu(self.menu_bar,
                                   '操作',
                                   enabled=False)

        # 操作-计算信噪比
        self.calculate_snr_action = Action(self.operation_menu,
                                           '计算信噪比',
                                           '计算选中数据的信噪比',
                                           self.calculateSNR)

        self.operation_menu.addSeparator()

        # 操作-裁剪数据（时间）
        self.set_time_range_action = Action(self.operation_menu,
                                            '查看范围（相对秒）',
                                            '按相对秒设置数据查看范围',
                                            self.setTimeRangeDialog)

        self.time_correction_action = Action(
            self.operation_menu,
            '时间校正设置',
            '设置设备落后真实时间的秒数，并保存到下次启动',
            self.showTimeCorrectionDialog,
        )

        # 操作-裁剪数据（通道号）
        self.set_channel_range_action = Action(self.operation_menu,
                                               '查看范围（通道）',
                                               '按通道设置数据查看范围',
                                               self.setChannelRangeDialog)

        self.operation_menu.addSeparator()

        # 操作-设置通道切换步长
        self.change_channel_number_step_action = Action(self.operation_menu,
                                                        '设置通道切换步长',
                                                        '设置切换通道时的步长',
                                                        self.changeChannelNumberStep)

        # 绘图
        self.plot_menu = Menu(self.menu_bar, '绘图', enabled=False)

        # 绘图-时域特征
        self.plot_time_domain_features_menu = Menu(self.plot_menu,
                                                   '时域特征',
                                                   status_tip='绘制所有通道的时域特征')

        # 绘图-时域特征-最大值等
        time_domain = {
            '最大值': 'max_value',
            '峰值': 'peak_value',
            '最小值': 'min_value',
            '平均值': 'mean',
            '峰峰值': 'peak_peak_value',
            '绝对平均值': 'mean_absolute_value',
            '均方根值': 'root_mean_square',
            '方根幅值': 'square_root_amplitude',
            '方差': 'variance',
            '标准差': 'standard_deviation',
            '峭度': 'kurtosis',
            '偏度': 'skewness',
            '裕度因子': 'clearance_factor',
            '波形因子': 'shape_factor',
            '脉冲因子': 'impulse_factor',
            '峰值因子': 'crest_factor',
            '峭度因子': 'kurtosis_factor'
        }
        for k, v in time_domain.items():
            setattr(self, f'plot_{v}_action',
                    Action(self.plot_time_domain_features_menu, k, f'绘制{k}图', self.plotFeature))

        # 绘图-二值图
        self.plot_binary_image_action = Action(self.plot_menu,
                                               '二值图',
                                               '通过设置或计算阈值来绘制二值图',
                                               self.ployBinaryImage)

        # 绘图-热力图
        self.plot_heatmap_action = Action(self.plot_menu,
                                          '热力图',
                                          '绘制热力图',
                                          self.plotHeatMapImage)

        # 绘图-多通道云图
        self.plot_multichannel_image_action = Action(self.plot_menu,
                                                     '多通道云图',
                                                     '绘制多通道云图',
                                                     self.showMultiWavesTab)

        # 绘图-应变图
        self.plot_strain_image_action = Action(self.plot_menu,
                                               '应变图',
                                               '绘制应变图，单位为微应变',
                                               self.plotStrain)

        self.plot_menu.addSeparator()

        # 绘图-频域特征
        plot_frequency_domain_features_menu = Menu(self.plot_menu, '频域特征', status_tip='绘制所有通道的频域特征')

        # 绘图-频域特征-重心频率等
        frequency_domain = {
            '重心频率': 'centroid_frequency',
            '平均频率': 'mean_frequency',
            '均方根频率': 'root_mean_square_frequency',
            '均方频率': 'mean_square_frequency',
            '频率方差': 'frequency_variance',
            '频率标准差': 'frequency_standard_deviation'
        }
        for k, v in frequency_domain.items():
            setattr(self, f'plot_{v}_action',
                    Action(plot_frequency_domain_features_menu, k, f'绘制{k}图', self.plotFeature))

        # 绘图-绘制谱
        self.plot_spectrum_action = Action(self.plot_menu,
                                           '绘制谱',
                                           '绘制频谱及时频谱',
                                           self.plotSpectrum)

        # 滤波
        self.filter_menu = Menu(self.menu_bar, '滤波', enabled=False)

        # 滤波-更新数据
        self.update_data_action = Action(self.filter_menu,
                                         '更新数据（否）',
                                         '如果为是，每次滤波后数据会更新',
                                         self.updateUpdateDataMenu)

        self.das_filter_action = Action(self.filter_menu,
                                        'DAS二维滤波与去噪',
                                        '对选定的通道和采样点范围进行 DASPy 滤波与去噪',
                                        self.showDASFilterDialog)
        self.reset_das_filter_action = Action(self.filter_menu,
                                              '恢复原始数据',
                                              '撤销已应用的二维滤波与去噪结果',
                                              self.resetDASFilterData,
                                              enabled=False)

        self.filter_menu.addSeparator()

        # Vehicle trajectories are a non-destructive analysis result, not a filter.
        self.analysis_menu = Menu(self.menu_bar, '分析', enabled=False)
        self.vehicle_tracking_action = Action(
            self.analysis_menu,
            '车辆轨迹拾取',
            '使用低频峰值和卡尔曼跟踪拾取车辆时空轨迹',
            self.showVehicleTrackingDialog,
        )
        self.speed_ruler_action = Action(
            self.analysis_menu,
            '车辆速度标尺',
            '在灰度图上添加可拖动的车辆投影速度测量线',
            self.addOrResetSpeedRuler,
        )

        # 滤波-EMD
        self.emd_menu = Menu(self.filter_menu, 'EMD', status_tip='使用EMD及衍生方式滤波')

        # 滤波-EMD-分解或重构
        self.emd_action = Action(self.emd_menu,
                                 '分解或重构',
                                 '使用EMD系列进行数据分解与重构',
                                 self.plotEMD)

        self.emd_menu.addSeparator()

        # 滤波-EMD-绘制瞬时频率
        self.emd_plot_ins_fre_action = Action(self.emd_menu,
                                              '绘制瞬时频率',
                                              '绘制重构IMF的瞬时频率',
                                              self.plotEMDInstantaneousFrequency,
                                              enabled=False)

        # 滤波-IIR滤波器
        self.iir_menu = Menu(self.filter_menu, 'IIR滤波器')

        # 滤波-IIR滤波器-Butterworth等
        cal_filter_types = ['Butterworth', 'Chebyshev type I', 'Chebyshev type II', 'Elliptic (Cauer)']
        for x in cal_filter_types:
            Action(self.iir_menu, x, f'设计{x}滤波器', self.designIIRFilter)

        self.iir_menu.addSeparator()

        # 滤波-IIR滤波器-Bessel/Thomson
        self.iir_bessel_action = Action(self.iir_menu,
                                        'Bessel/Thomson',
                                        '设计Bessel/Thomson滤波器',
                                        self.designIIRFilter)

        self.iir_menu.addSeparator()

        # 滤波-IIR滤波器-notch等
        comb_filter_types = [
            'Notch Digital Filter',
            'Peak (Resonant) Digital Filter',
            'Notching or Peaking Digital Comb Filter'
        ]
        for x in comb_filter_types:
            Action(self.iir_menu, x, f'设计{x}滤波器', self.designIIRFilter)

        # 滤波-小波
        self.wavelet_menu = Menu(self.filter_menu, '小波')

        # 滤波-小波-连续小波变换
        self.wavelet_cwt_action = Action(self.wavelet_menu,
                                         '连续小波变换',
                                         '使用连续小波变换查看信号时频特征',
                                         self.plotCWT)

        # 滤波-小波-离散小波变换
        self.wavelet_dwt_action = Action(self.wavelet_menu,
                                         '离散小波变换',
                                         '使用离散小波变换进行数据分解与重构或去噪',
                                         self.plotDWT)

        # 滤波-小波-小波包
        self.wavelet_packets_action = Action(self.wavelet_menu,
                                             '小波包',
                                             '使用小波包进行数据分解并从选择的节点重构',
                                             self.plotDWPT)

        # # 其他
        # self.others_menu = Menu(self.menu_bar, '其他', enabled=True)
        #
        # # 其他-数据筛选
        # self.data_sifting_action = Action(self.others_menu,
        #                                   '数据筛选',
        #                                   '使用双门限法筛选数据',
        #                                   self.dataSiftingDialog)

    def initLayout(self):
        """
        初始化主窗口布局
        Returns:

        """
        main_window_widget = QWidget()
        main_window_hbox = QHBoxLayout()
        main_window_hbox.setContentsMargins(8, 8, 8, 8)
        main_window_hbox.setSpacing(8)

        # 左侧导航：目录和文件列表始终可见，数据概览与其归在一起。
        file_hbox = QHBoxLayout()
        file_area_vbox = QVBoxLayout()
        file_area_vbox.setContentsMargins(0, 0, 0, 0)
        file_area_vbox.setSpacing(12)

        self.file_path_line_edit = LineEdit(focus=False)
        self.file_path_line_edit.setPlaceholderText('选择数据文件夹')

        change_file_path_button = PushButton()
        setPicture(change_file_path_button, folder_jpg, 'folder.jpg', )
        change_file_path_button.setToolTip('选择数据文件夹')
        change_file_path_button.setAccessibleName('选择数据文件夹')
        change_file_path_button.clicked.connect(self.changeFilePath)

        file_table_scrollbar = QScrollBar(Qt.Vertical)
        file_table_scrollbar.setMinimumHeight(100)
        self.files_table_widget = QTableWidget(30, 1)
        self.files_table_widget.setVerticalScrollBar(file_table_scrollbar)
        self.files_table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)  # 设置表格不可编辑
        self.files_table_widget.setHorizontalHeaderLabels(['文件'])  # 设置表头
        self.files_table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.files_table_widget.verticalHeader().setVisible(False)
        self.files_table_widget.setWordWrap(False)
        self.files_table_widget.setAlternatingRowColors(True)
        self.files_table_widget.setMinimumHeight(180)
        self.files_table_widget.setToolTip(
            '鼠标悬停可查看完整路径；使用 Ctrl 或 Shift 选择多个文件，选择完成后点击确定加载'
        )
        QTableWidget.resizeRowsToContents(self.files_table_widget)
        self.files_table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)  # 设置一次选中一排内容
        self.files_table_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.files_table_widget.itemSelectionChanged.connect(self.updatePendingFileSelection)

        self.pending_file_selection_label = Label('待拼接：请选择文件')
        self.pending_file_selection_label.setWordWrap(True)
        self.pending_file_selection_label.setObjectName('secondaryLabel')
        self.load_selected_files_button = PushButton('确定加载并拼接')
        self.load_selected_files_button.setEnabled(False)
        self.load_selected_files_button.setToolTip('按文件表中的顺序一次性读取、拼接并绘制所选文件')
        self.load_selected_files_button.clicked.connect(self.selectDataFromTable)

        # 文件区布局
        file_hbox.addWidget(self.file_path_line_edit)
        file_hbox.addWidget(change_file_path_button)
        file_area_vbox.addLayout(file_hbox)
        file_area_vbox.addWidget(self.files_table_widget, 1)
        file_area_vbox.addWidget(self.pending_file_selection_label)
        file_area_vbox.addWidget(self.load_selected_files_button)

        self.stitched_files_group = QGroupBox('当前拼接文件（0）')
        self.stitched_files_list = QListWidget()
        self.stitched_files_list.setAlternatingRowColors(True)
        self.stitched_files_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.stitched_files_list.setMinimumHeight(70)
        self.stitched_files_list.setMaximumHeight(120)
        self.stitched_files_list.setToolTip('按拼接顺序显示来源文件；点击可高亮图中的对应分段')
        self.stitched_files_list.currentRowChanged.connect(self._stitchedFileRowChanged)
        stitched_files_vbox = QVBoxLayout()
        stitched_files_vbox.setContentsMargins(8, 8, 8, 8)
        stitched_files_vbox.addWidget(self.stitched_files_list)
        self.stitched_files_group.setLayout(stitched_files_vbox)
        file_area_vbox.addWidget(self.stitched_files_group)

        # 数据元信息移至导航区，避免长期挤占绘图区的上下空间。
        self.sampling_rate_line_edit = LineEditWithReg(digit=True, focus=False)
        self.current_sampling_times_line_edit = LineEditWithReg(focus=False)
        self.current_channels_line_edit = LineEditWithReg(focus=False)
        self.gps_from_line_edit = LineEdit(focus=False)
        self.gps_to_line_edit = LineEdit(focus=False)
        self.time_correction_spin_box = QDoubleSpinBox()
        self.time_correction_spin_box.setRange(-86400.0, 86400.0)
        self.time_correction_spin_box.setDecimals(3)
        self.time_correction_spin_box.setSingleStep(0.1)
        self.time_correction_spin_box.setSuffix(' s')
        self.time_correction_spin_box.setKeyboardTracking(False)
        self.time_correction_spin_box.setValue(self.time_correction_seconds)
        self.time_correction_spin_box.setToolTip(
            '设备时间落后真实时间时填正数；例如落后 12 秒填写 +12.000 s'
        )
        self.time_correction_apply_button = PushButton('应用')
        self.time_correction_apply_button.setObjectName('timeCorrectionApplyButton')
        self.time_correction_apply_button.setToolTip('保存时间修正，并重新计算显示中的推算时间')
        self.time_correction_apply_button.clicked.connect(self.applyTimeCorrectionFromSidebar)
        time_correction_controls = QWidget()
        time_correction_layout = QHBoxLayout(time_correction_controls)
        time_correction_layout.setContentsMargins(0, 0, 0, 0)
        time_correction_layout.setSpacing(6)
        time_correction_layout.addWidget(self.time_correction_spin_box, 1)
        time_correction_layout.addWidget(self.time_correction_apply_button)
        for field in (
                self.sampling_rate_line_edit,
                self.current_sampling_times_line_edit,
                self.current_channels_line_edit,
                self.gps_from_line_edit,
                self.gps_to_line_edit,
        ):
            field.setReadOnly(True)
            field.setFixedHeight(22)
            field.setObjectName('metadataValue')

        self.overview_group = QGroupBox('数据概览')
        self.overview_group.setObjectName('dataOverview')
        self.overview_group.setMaximumHeight(170)
        self.overview_form = QFormLayout()
        self.overview_form.setContentsMargins(5, 2, 5, 2)
        self.overview_form.setHorizontalSpacing(6)
        self.overview_form.setVerticalSpacing(1)
        self.overview_form.addRow('采样率', self.sampling_rate_line_edit)
        self.overview_form.addRow('采样次数', self.current_sampling_times_line_edit)
        self.overview_form.addRow('通道数', self.current_channels_line_edit)
        self.overview_form.addRow('推算开始', self.gps_from_line_edit)
        self.overview_form.addRow('推算结束', self.gps_to_line_edit)
        self.overview_form.addRow('设备时间修正', time_correction_controls)
        self.overview_group.setLayout(self.overview_form)
        file_area_vbox.addWidget(self.overview_group)

        # 单通道操作只在“单通道”页中显示。
        channel_number_label = Label('通道号')
        self.channel_number_spinbx = SpinBox()
        self.channel_number_spinbx.setValue(1)
        self.channel_number_spinbx.setMinimumWidth(88)
        self.channel_number_spinbx.valueChanged.connect(self.changeChannelNumber)
        self.channel_number_spinbx.valueChanged.connect(self.plotSingleChannelTime)
        self.channel_number_spinbx.valueChanged.connect(self.plotAmplitudeFrequency)

        # 播放音频按钮
        self.player_play_button = PushButton()
        setPicture(self.player_play_button, play_jpg, 'play.jpg')
        self.player_play_button.clicked.connect(self.createWavFile)
        self.player_play_button.clicked.connect(self.createPlayer)
        self.player_play_button.clicked.connect(self.playBtnChangeState)

        # 停止音频播放按钮
        self.player_stop_button = PushButton()
        setPicture(self.player_stop_button, stop_jpg, 'stop.jpg')
        self.player_stop_button.clicked.connect(self.resetPlayer)

        self.player_play_button.setDisabled(True)
        self.player_stop_button.setDisabled(True)  # 默认不可选中

        channel_controls_hbox = QHBoxLayout()
        channel_controls_hbox.setContentsMargins(0, 0, 0, 0)
        channel_controls_hbox.setSpacing(6)
        channel_controls_hbox.addWidget(channel_number_label)
        channel_controls_hbox.addWidget(self.channel_number_spinbx)
        channel_controls_hbox.addSpacing(10)
        channel_controls_hbox.addWidget(self.player_play_button)
        channel_controls_hbox.addWidget(self.player_stop_button)
        channel_controls_hbox.addStretch(1)

        # 灰度图显示控制只在灰度图页面显示。
        image_colormap_label = Label('图像颜色')
        self.image_colormap_combx = ComboBox()
        self.image_colormap_combx.addItems(['灰度', 'RdBu', 'viridis', 'plasma', 'inferno', 'magma', 'turbo',
                                            'jet', 'seismic', 'coolwarm'])
        self.image_colormap_combx.setCurrentText(self.image_colormap)
        self.image_colormap_combx.setFixedWidth(100)
        self.image_colormap_combx.currentTextChanged.connect(self.updateImageColorParams)

        image_level_min_label = Label('最小值(%)')
        self.image_level_min_line_edit = LineEdit()
        self.image_level_min_line_edit.setFixedWidth(76)
        self.image_level_min_line_edit.setPlaceholderText('自动')
        self.image_level_min_line_edit.setToolTip('相对于当前图像最大绝对值的百分比，例如 -80')

        image_level_max_label = Label('最大值(%)')
        self.image_level_max_line_edit = LineEdit()
        self.image_level_max_line_edit.setFixedWidth(76)
        self.image_level_max_line_edit.setPlaceholderText('自动')
        self.image_level_max_line_edit.setToolTip('相对于当前图像最大绝对值的百分比，例如 80')

        image_auto_button = PushButton('自动')
        image_auto_button.clicked.connect(self.autoImageLevels)

        image_apply_button = PushButton('应用')
        image_apply_button.clicked.connect(self.updateImageColorParams)

        image_controls_hbox = QHBoxLayout()
        image_controls_hbox.setSpacing(4)
        image_controls_hbox.addWidget(image_colormap_label)
        image_controls_hbox.addWidget(self.image_colormap_combx)
        image_controls_hbox.addSpacing(6)
        image_controls_hbox.addWidget(image_level_min_label)
        image_controls_hbox.addWidget(self.image_level_min_line_edit)
        image_controls_hbox.addSpacing(3)
        image_controls_hbox.addWidget(image_level_max_label)
        image_controls_hbox.addWidget(self.image_level_max_line_edit)
        image_controls_hbox.addSpacing(6)
        image_controls_hbox.addWidget(image_auto_button)
        image_controls_hbox.addWidget(image_apply_button)

        speed_ruler_controls_hbox = QHBoxLayout()
        speed_ruler_controls_hbox.setSpacing(4)
        self.speed_ruler_spacing_spin_box = QDoubleSpinBox()
        self.speed_ruler_spacing_spin_box.setRange(0.001, 1_000_000.0)
        self.speed_ruler_spacing_spin_box.setDecimals(3)
        self.speed_ruler_spacing_spin_box.setSingleStep(0.1)
        self.speed_ruler_spacing_spin_box.setSuffix(' m')
        self.speed_ruler_spacing_spin_box.setValue(self.speed_ruler_channel_spacing)
        self.speed_ruler_spacing_spin_box.setKeyboardTracking(False)
        self.speed_ruler_spacing_spin_box.setToolTip('真实相邻通道距离 dx；不能使用 gauge length')
        self.speed_ruler_spacing_spin_box.valueChanged.connect(self.updateSpeedRulerChannelSpacing)
        self.speed_ruler_reset_button = PushButton('添加速度标尺')
        self.speed_ruler_reset_button.setEnabled(False)
        self.speed_ruler_reset_button.setToolTip('在当前灰度图范围内添加或重置可拖动的速度测量线')
        self.speed_ruler_reset_button.clicked.connect(self.addOrResetSpeedRuler)
        self.speed_ruler_remove_button = PushButton('移除速度标尺')
        self.speed_ruler_remove_button.setEnabled(False)
        self.speed_ruler_remove_button.clicked.connect(self.removeSpeedRuler)
        self.speed_ruler_status_label = Label('未添加')
        self.speed_ruler_status_label.setObjectName('statusBadge')
        self.speed_ruler_status_label.setProperty('state', 'inactive')
        self.speed_ruler_status_label.setToolTip('速度标尺未添加')
        self.speed_ruler_status_label.setWordWrap(False)
        self.speed_ruler_status_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        speed_ruler_controls_hbox.addWidget(Label('车辆速度标尺  dx'))
        speed_ruler_controls_hbox.addWidget(self.speed_ruler_spacing_spin_box)
        speed_ruler_controls_hbox.addWidget(self.speed_ruler_reset_button)
        speed_ruler_controls_hbox.addWidget(self.speed_ruler_remove_button)
        speed_ruler_controls_hbox.addWidget(self.speed_ruler_status_label)

        # 绘制灰度图
        self.plot_gray_scale_widget = MyPlotWidget(
            '', '推算时间', '通道', check_mouse=False, time_axis=True
        )
        self.gray_scale_container = QWidget()
        gray_scale_vbox = QVBoxLayout()
        gray_scale_vbox.setContentsMargins(8, 8, 8, 8)
        gray_scale_vbox.setSpacing(8)
        self.plot_toolbar = QWidget()
        self.plot_toolbar.setObjectName('plotToolbar')
        plot_toolbar_hbox = QHBoxLayout(self.plot_toolbar)
        plot_toolbar_hbox.setContentsMargins(8, 6, 8, 6)
        plot_toolbar_hbox.setSpacing(10)
        plot_toolbar_hbox.addLayout(image_controls_hbox)
        plot_toolbar_hbox.addLayout(speed_ruler_controls_hbox)
        plot_toolbar_hbox.addStretch(1)
        gray_scale_vbox.addWidget(self.plot_toolbar)
        gray_scale_vbox.addWidget(self.plot_gray_scale_widget)
        self.gray_scale_container.setLayout(gray_scale_vbox)

        # 绘制单通道相位差-时间图
        self.plot_single_channel_time_widget = MyPlotWidget(
            '相位差图', '推算时间', '相位差（rad）', grid=True, time_axis=True
        )

        # 绘制频谱图
        self.plot_amplitude_frequency_widget = MyPlotWidget('幅值图', '频率（Hz）', '幅值', grid=True)

        combine_image_widget = QWidget()
        image_vbox = QVBoxLayout()
        image_vbox.setContentsMargins(6, 6, 6, 6)
        image_vbox.setSpacing(6)
        image_vbox.addLayout(channel_controls_hbox)
        image_vbox.addWidget(self.plot_single_channel_time_widget)
        image_vbox.addWidget(self.plot_amplitude_frequency_widget)
        combine_image_widget.setLayout(image_vbox)

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName('workspaceTabs')
        self.tab_widget.setMovable(True)  # 设置tab可移动
        self.tab_widget.setTabsClosable(True)  # 设置tab可关闭
        self.tab_widget.tabCloseRequested[int].connect(self.removeTab)
        self.tab_widget.addTab(self.gray_scale_container, '灰度图')
        self.tab_widget.addTab(combine_image_widget, '单通道')
        self.initMultiWavesTab()
        self.tab_widget.addTab(self.multi_waves_container, '多通道云图')
        self.initVideoComparisonTab()
        self.tab_widget.addTab(self.video_compare_container, '视频对照')
        self.tab_widget.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.tab_widget.tabBar().setTabButton(1, QTabBar.RightSide, None)  # 设置删除按钮消失
        self.tab_widget.tabBar().setTabButton(2, QTabBar.RightSide, None)
        self.tab_widget.tabBar().setTabButton(3, QTabBar.RightSide, None)
        self.tab_widget.currentChanged.connect(self._workspaceTabChanged)

        self.event_range_widget = QWidget()
        self.event_range_widget.setObjectName('eventRangeBar')
        event_range_hbox = QHBoxLayout()
        event_range_hbox.setContentsMargins(8, 5, 8, 5)
        event_range_hbox.setSpacing(6)
        self.event_range_from_edit = QDateTimeEdit()
        self.event_range_to_edit = QDateTimeEdit()
        for editor in (self.event_range_from_edit, self.event_range_to_edit):
            editor.setDisplayFormat('yyyy-MM-dd HH:mm:ss.zzz')
            editor.setCalendarPopup(True)
            editor.setKeyboardTracking(False)
            editor.setMinimumWidth(190)
        self.event_range_set_button = PushButton('设置标记')
        self.event_range_view_button = PushButton('查看此范围')
        self.event_range_reset_button = PushButton('恢复全部')
        self.event_markers_visible_checkbox = QCheckBox('显示事件标记')
        self.event_markers_visible_checkbox.setChecked(True)
        self.event_markers_visible_checkbox.setToolTip('显示或隐藏图中的事件开始、结束标记；不会改变当前查看范围')
        self.event_range_set_button.setToolTip('移动图中的开始/结束竖线，不改变数据查看范围')
        self.event_range_view_button.setToolTip('按竖线范围更新当前视图，不修改导入原始数据')
        self.event_range_reset_button.setToolTip('恢复完整时间视图并把竖线重置到数据两端')
        self.event_range_set_button.clicked.connect(self.setEventRangeFromInputs)
        self.event_range_view_button.clicked.connect(self.viewEventRange)
        self.event_range_reset_button.clicked.connect(self.restoreFullEventRange)
        self.event_markers_visible_checkbox.toggled.connect(self.setEventMarkersVisible)
        event_range_hbox.addWidget(Label('事件开始'))
        event_range_hbox.addWidget(self.event_range_from_edit)
        event_range_hbox.addWidget(Label('事件结束'))
        event_range_hbox.addWidget(self.event_range_to_edit)
        event_range_hbox.addWidget(self.event_range_set_button)
        event_range_hbox.addWidget(self.event_range_view_button)
        event_range_hbox.addWidget(self.event_range_reset_button)
        event_range_hbox.addWidget(self.event_markers_visible_checkbox)
        event_range_hbox.addStretch(1)
        self.event_range_widget.setLayout(event_range_hbox)
        self.setEventRangeControlsEnabled(False)

        # Tab 是唯一的主工作区，最大化图形可用面积。
        main_window_vbox = QVBoxLayout()
        main_window_vbox.setContentsMargins(0, 0, 0, 0)
        main_window_vbox.setSpacing(0)
        main_window_vbox.addWidget(self.event_range_widget)
        main_window_vbox.addWidget(self.tab_widget)

        self.data_sidebar_widget = QWidget()
        self.data_sidebar_widget.setLayout(file_area_vbox)

        self.filter_sidebar_widget = QWidget()
        self.filter_sidebar_layout = QVBoxLayout(self.filter_sidebar_widget)
        self.filter_sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_sidebar_placeholder = Label('请先导入 DAS 数据，再打开二维滤波页。')
        self.filter_sidebar_placeholder.setAlignment(Qt.AlignCenter)
        self.filter_sidebar_placeholder.setWordWrap(True)
        self.filter_sidebar_placeholder.setObjectName('secondaryLabel')
        self.filter_sidebar_placeholder.setContentsMargins(16, 16, 16, 16)
        self.filter_sidebar_layout.addWidget(self.filter_sidebar_placeholder)

        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setObjectName('sidebarTabs')
        self.sidebar_tabs.setMinimumWidth(380)
        self.sidebar_tabs.addTab(self.data_sidebar_widget, '数据')
        self.sidebar_tabs.addTab(self.filter_sidebar_widget, '二维滤波')
        self.sidebar_tabs.addTab(self.annotation_sidebar_widget, '标注')
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
        self.setCentralWidget(main_window_widget)

    def initMultiWavesTab(self):
        """创建固定的多通道云图页；数据变化时只重绘，不重复创建 Tab。"""
        self.multi_waves_view_box = pg.ViewBox(enableMenu=False)
        self.multi_waves_time_axis = AbsoluteTimeAxisItem(orientation='bottom')
        self.plot_multi_waves_widget = pg.PlotWidget(
            viewBox=self.multi_waves_view_box,
            axisItems={'bottom': self.multi_waves_time_axis},
        )
        self.plot_multi_waves_widget.setTitle(plot_html('多通道云图', PLOT_TITLE_POINT_SIZE))
        self.plot_multi_waves_widget.setLabel('bottom', plot_html('推算时间', PLOT_LABEL_POINT_SIZE))
        self.plot_multi_waves_widget.setLabel('left', plot_html('通道', PLOT_LABEL_POINT_SIZE))
        self.plot_multi_waves_widget.getAxis('bottom').setTickFont(plot_font(PLOT_TICK_POINT_SIZE))
        self.plot_multi_waves_widget.getAxis('left').setTickFont(plot_font(PLOT_TICK_POINT_SIZE))
        self.plot_multi_waves_widget.getAxis('left').setWidth(50)
        self.plot_multi_waves_widget.showGrid(x=True, y=True, alpha=0.2)

        self.multi_waves_channel_from_spin_box = SpinBox()
        self.multi_waves_channel_to_spin_box = SpinBox()
        for spin_box in (self.multi_waves_channel_from_spin_box, self.multi_waves_channel_to_spin_box):
            spin_box.setFixedWidth(90)
            spin_box.setKeyboardTracking(False)

        self.multi_waves_confirm_button = PushButton('确认')
        self.multi_waves_channel_range_label = Label('')
        self.multi_waves_time_range_label = Label('')
        self.multi_waves_time_from_spin_box = QDoubleSpinBox()
        self.multi_waves_time_to_spin_box = QDoubleSpinBox()
        for spin_box in (self.multi_waves_time_from_spin_box, self.multi_waves_time_to_spin_box):
            spin_box.setDecimals(6)
            spin_box.setFixedWidth(110)
            spin_box.setKeyboardTracking(False)
            spin_box.setSuffix(' s')
        self.multi_waves_time_confirm_button = PushButton('确认时间')
        self.multi_waves_left_button = PushButton('←')
        self.multi_waves_right_button = PushButton('→')
        self.multi_waves_up_button = PushButton('↑')
        self.multi_waves_down_button = PushButton('↓')
        for button in (self.multi_waves_left_button, self.multi_waves_right_button,
                       self.multi_waves_up_button, self.multi_waves_down_button):
            button.setFixedWidth(45)
        self.multi_waves_left_button.setToolTip('向前移动时间范围')
        self.multi_waves_right_button.setToolTip('向后移动时间范围')
        self.multi_waves_up_button.setToolTip('向更大通道号移动范围')
        self.multi_waves_down_button.setToolTip('向更小通道号移动范围')

        self.multi_waves_confirm_button.clicked.connect(self.confirmMultiWavesChannelRange)
        self.multi_waves_time_confirm_button.clicked.connect(self.confirmMultiWavesTimeRange)
        self.multi_waves_left_button.clicked.connect(lambda: self.moveMultiWavesTime(-1))
        self.multi_waves_right_button.clicked.connect(lambda: self.moveMultiWavesTime(1))
        self.multi_waves_up_button.clicked.connect(lambda: self.moveMultiWavesChannels(1))
        self.multi_waves_down_button.clicked.connect(lambda: self.moveMultiWavesChannels(-1))

        selection_controls_hbox = QHBoxLayout()
        selection_controls_hbox.setContentsMargins(0, 0, 0, 0)
        selection_controls_hbox.setSpacing(6)
        selection_controls_hbox.addWidget(Label('显示通道'))
        selection_controls_hbox.addWidget(self.multi_waves_channel_from_spin_box)
        selection_controls_hbox.addWidget(Label('至'))
        selection_controls_hbox.addWidget(self.multi_waves_channel_to_spin_box)
        selection_controls_hbox.addWidget(self.multi_waves_confirm_button)
        selection_controls_hbox.addSpacing(12)
        selection_controls_hbox.addWidget(Label('显示时间（相对秒）'))
        selection_controls_hbox.addWidget(self.multi_waves_time_from_spin_box)
        selection_controls_hbox.addWidget(Label('至'))
        selection_controls_hbox.addWidget(self.multi_waves_time_to_spin_box)
        selection_controls_hbox.addWidget(self.multi_waves_time_confirm_button)
        selection_controls_hbox.addStretch(1)

        navigation_controls_hbox = QHBoxLayout()
        navigation_controls_hbox.setContentsMargins(0, 0, 0, 0)
        navigation_controls_hbox.setSpacing(6)
        navigation_controls_hbox.addWidget(Label('浏览'))
        navigation_controls_hbox.addWidget(self.multi_waves_left_button)
        navigation_controls_hbox.addWidget(self.multi_waves_right_button)
        navigation_controls_hbox.addWidget(self.multi_waves_up_button)
        navigation_controls_hbox.addWidget(self.multi_waves_down_button)
        navigation_controls_hbox.addSpacing(12)
        navigation_controls_hbox.addWidget(self.multi_waves_channel_range_label)
        navigation_controls_hbox.addSpacing(12)
        navigation_controls_hbox.addWidget(self.multi_waves_time_range_label)
        navigation_controls_hbox.addStretch(1)

        self.multi_waves_container = QWidget()
        vbox = QVBoxLayout()
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(6)
        vbox.addLayout(selection_controls_hbox)
        vbox.addLayout(navigation_controls_hbox)
        vbox.addWidget(self.plot_multi_waves_widget)
        self.multi_waves_container.setLayout(vbox)
        self.multi_waves_view_box.sigRangeChanged.connect(self.syncMultiWavesTimeRange)
        self.multi_waves_reset_pending = True
        self.multi_waves_colors = ['red', 'lime', 'deepskyblue', 'yellow', 'plum', 'gold', 'blue', 'fuchsia',
                                   'aqua', 'orange']

    def initVideoComparisonTab(self):
        """Create a video sidebar and a DAS-first comparison workspace."""

        self.video_compare_container = QWidget()
        root = QVBoxLayout(self.video_compare_container)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        video_panel = QWidget()
        video_panel.setObjectName('videoSidebarPanel')
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(8, 8, 8, 8)
        video_layout.setSpacing(6)
        self.video_source_label = Label('未载入摄像头视频')
        self.video_source_label.setObjectName('secondaryLabel')
        self.video_source_label.setWordWrap(False)
        self.video_source_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.video_media_info_label = Label('媒体探测：等待选择录像')
        self.video_media_info_label.setObjectName('secondaryLabel')
        self.video_media_info_label.setWordWrap(False)
        self.video_media_info_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        video_layout.addWidget(self.video_source_label)
        video_layout.addWidget(self.video_media_info_label)

        self.video_load_button = PushButton('选择视频')
        self.video_load_button.setFixedWidth(76)
        self.video_load_button.setToolTip('选择摄像头录像；不会修改源视频')
        self.video_das_load_button = PushButton('自动匹配 DAS')
        self.video_das_load_button.setFixedWidth(108)
        self.video_das_load_button.setToolTip('按录像时间范围匹配 DAS 文件；只读取文件头，播放时再读取当前窗口')
        self.video_play_button = PushButton('播放')
        self.video_play_button.setFixedWidth(60)
        self.video_play_button.setObjectName('primaryAction')
        self.video_back_button = PushButton('−1 s')
        self.video_back_button.setFixedWidth(54)
        self.video_forward_button = PushButton('+1 s')
        self.video_forward_button.setFixedWidth(54)
        self.video_speed_combo = ComboBox()
        for label, rate in (('0.25×', 0.25), ('0.5×', 0.5), ('1×', 1.0), ('2×', 2.0)):
            self.video_speed_combo.addItem(label, rate)
        self.video_speed_combo.setCurrentIndex(2)
        self.video_speed_combo.setFixedWidth(72)
        self.video_fit_combo = ComboBox()
        self.video_fit_combo.addItem('完整画面', Qt.KeepAspectRatio)
        self.video_fit_combo.addItem('填满裁剪', Qt.KeepAspectRatioByExpanding)
        self.video_fit_combo.setFixedWidth(92)
        self.video_fit_combo.setToolTip('完整画面保留全部内容；填满裁剪可减少黑边但会裁掉少量边缘')
        self.video_position_slider = QSlider(Qt.Horizontal)
        self.video_position_slider.setRange(0, 0)
        self.video_position_slider.setAccessibleName('视频播放位置')
        self.video_time_label = Label('--:--:--.--- / --:--:--.---')
        self.video_time_label.setFixedWidth(190)
        transport_actions = QHBoxLayout()
        transport_actions.setContentsMargins(0, 0, 0, 0)
        transport_actions.setSpacing(5)
        transport_actions.addWidget(self.video_load_button)
        transport_actions.addWidget(self.video_das_load_button)
        transport_actions.addWidget(self.video_play_button)
        transport_actions.addWidget(self.video_back_button)
        transport_actions.addWidget(self.video_forward_button)
        transport_actions.addStretch(1)
        video_layout.addLayout(transport_actions)

        video_layout.addWidget(self.video_position_slider)
        transport_status = QHBoxLayout()
        transport_status.setContentsMargins(0, 0, 0, 0)
        transport_status.setSpacing(5)
        transport_status.addWidget(Label('倍速'))
        transport_status.addWidget(self.video_speed_combo)
        transport_status.addWidget(self.video_fit_combo)
        transport_status.addStretch(1)
        transport_status.addWidget(self.video_time_label)
        video_layout.addLayout(transport_status)

        self.video_viewport = QWidget()
        self.video_viewport_stack = QStackedLayout(self.video_viewport)
        self.video_viewport_stack.setContentsMargins(0, 0, 0, 0)
        if QVideoWidget is None:
            self.video_surface = Label('当前 PyQt 安装未包含视频画面组件。')
            self.video_surface.setAlignment(Qt.AlignCenter)
            self.video_surface.setObjectName('videoUnavailable')
        else:
            self.video_surface = QVideoWidget()
            self.video_surface.setObjectName('videoSurface')
        self.video_frame_surface = Label('等待兼容播放缓存')
        self.video_frame_surface.setAlignment(Qt.AlignCenter)
        self.video_frame_surface.setObjectName('videoSurface')
        self.video_frame_surface.setScaledContents(False)
        self.video_frame_surface.setMinimumSize(0, 0)
        self.video_frame_surface.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.video_frame_surface.installEventFilter(self)
        self.video_viewport_stack.addWidget(self.video_surface)
        self.video_viewport_stack.addWidget(self.video_frame_surface)
        self.video_viewport.setMinimumHeight(230)
        self.video_viewport.setMaximumHeight(280)
        self.video_viewport.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        video_layout.addWidget(self.video_viewport, 1)

        self.video_sync_summary_label = Label('对时：等待视频与 DAS 数据')
        self.video_sync_summary_label.setObjectName('secondaryLabel')
        self.video_sync_summary_label.setWordWrap(True)
        self.video_sync_summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        video_layout.addWidget(self.video_sync_summary_label)
        video_panel.setMinimumHeight(420)
        video_panel.setMaximumHeight(520)

        das_panel = QWidget()
        das_layout = QVBoxLayout(das_panel)
        das_layout.setContentsMargins(8, 8, 8, 8)
        das_layout.setSpacing(6)
        self.video_das_plot_widget = MyPlotWidget('', '推算时间', '通道', check_mouse=False, time_axis=True)
        self.video_das_plot_widget.setMinimumHeight(150)
        self.video_camera_channel_spin_box = SpinBox()
        self.video_camera_channel_spin_box.setRange(1, 1)
        self.video_camera_channel_spin_box.setKeyboardTracking(False)
        self.video_camera_channel_apply_button = PushButton('设置通道')
        self.video_camera_visible_checkbox = QCheckBox('显示摄像头通道线')
        self.video_camera_visible_checkbox.setChecked(True)
        self.video_follow_checkbox = QCheckBox('播放时跟随')
        self.video_follow_checkbox.setChecked(True)
        self.video_annotations_visible_checkbox = QCheckBox('显示标注')
        self.video_annotations_visible_checkbox.setChecked(True)
        self.video_display_mode_combo = ComboBox()
        self.video_display_mode_combo.addItem('事件增强', 'enhanced')
        self.video_display_mode_combo.addItem('原始去趋势', 'raw')
        self.video_display_mode_combo.setToolTip('快速对照显示处理后的结果与未滤波的去趋势数据')
        self.video_window_combo = ComboBox()
        for seconds in (30, 60, 120, 240):
            self.video_window_combo.addItem(f'{seconds} s', seconds)
        self.video_window_combo.setCurrentIndex(
            self.video_window_combo.findData(int(VIDEO_DISPLAY_WINDOW_SECONDS))
        )
        self.video_window_combo.setToolTip(
            '播放跟随时右侧 DAS 的可见时间窗；后台会提前预读后续数据以连续滚动'
        )
        self.video_filter_button = PushButton('二维滤波…')
        self.video_filter_button.setToolTip('打开与主数据页相同的二维滤波窗口，按顺序叠加显示滤波')
        self.video_filter_summary_label = Label('车辆事件增强')
        self.video_filter_summary_label.setObjectName('secondaryLabel')
        self.video_filter_summary_label.setToolTip(
            '带通 0.01–1 Hz → 中位数共模抑制 → MAD 归一化；仅影响显示'
        )
        self.video_focus_button = PushButton('专注模式')
        self.video_focus_button.setCheckable(True)
        self.video_focus_button.setToolTip('隐藏左栏与事件范围栏，让 DAS 图占满窗口；F11 可切换')
        self.video_current_das_label = Label('DAS：等待对时')
        self.video_current_das_label.setObjectName('statusBadge')
        self.video_sequence_status_label = Label('匹配 DAS：未加载')
        self.video_sequence_status_label.setObjectName('secondaryLabel')
        self.video_sequence_status_label.setWordWrap(True)
        self.video_sequence_status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.video_trajectory_status_label = Label('轨迹：等待匹配 DAS')
        self.video_trajectory_status_label.setObjectName('secondaryLabel')
        self.video_trajectory_status_label.setWordWrap(True)
        self.video_trajectory_status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.video_trajectory_dx_spin_box = QDoubleSpinBox()
        self.video_trajectory_dx_spin_box.setRange(0.001, 1_000_000.0)
        self.video_trajectory_dx_spin_box.setDecimals(3)
        self.video_trajectory_dx_spin_box.setSingleStep(0.1)
        self.video_trajectory_dx_spin_box.setSuffix(' m')
        self.video_trajectory_dx_spin_box.setValue(4.0)
        self.video_trajectory_dx_spin_box.setKeyboardTracking(False)
        das_controls = QVBoxLayout()
        das_controls.setContentsMargins(0, 0, 0, 0)
        das_controls.setSpacing(4)
        camera_controls = QHBoxLayout()
        camera_controls.setContentsMargins(0, 0, 0, 0)
        camera_controls.setSpacing(6)
        camera_controls.addWidget(Label('摄像头通道'))
        camera_controls.addWidget(self.video_camera_channel_spin_box)
        camera_controls.addWidget(self.video_camera_channel_apply_button)
        camera_controls.addWidget(self.video_camera_visible_checkbox)
        camera_controls.addWidget(self.video_follow_checkbox)
        camera_controls.addWidget(self.video_annotations_visible_checkbox)
        camera_controls.addStretch(1)
        display_controls = QHBoxLayout()
        display_controls.setContentsMargins(0, 0, 0, 0)
        display_controls.setSpacing(6)
        display_controls.addWidget(Label('显示'))
        display_controls.addWidget(self.video_display_mode_combo)
        display_controls.addWidget(self.video_filter_button)
        display_controls.addWidget(self.video_filter_summary_label)
        display_controls.addSpacing(8)
        display_controls.addWidget(Label('窗口'))
        display_controls.addWidget(self.video_window_combo)
        display_controls.addSpacing(8)
        display_controls.addWidget(Label('dx'))
        display_controls.addWidget(self.video_trajectory_dx_spin_box)
        display_controls.addStretch(1)
        display_controls.addWidget(self.video_focus_button)
        das_controls.addLayout(camera_controls)
        das_controls.addLayout(display_controls)
        das_layout.addLayout(das_controls)

        das_status = QGridLayout()
        das_status.setContentsMargins(0, 0, 0, 0)
        das_status.setHorizontalSpacing(12)
        das_status.setVerticalSpacing(2)
        das_status.addWidget(self.video_sequence_status_label, 0, 0)
        das_status.addWidget(self.video_current_das_label, 0, 1, Qt.AlignRight)
        das_status.addWidget(self.video_trajectory_status_label, 1, 0, 1, 2)
        das_status.setColumnStretch(0, 1)
        das_layout.addLayout(das_status)
        das_layout.addWidget(self.video_das_plot_widget, 1)
        das_panel.setMinimumHeight(270)

        root.addWidget(das_panel, 1)

        self.video_load_button.clicked.connect(self.chooseVideoComparisonFile)
        self.video_das_load_button.clicked.connect(self.chooseVideoDasFolder)
        self.video_play_button.clicked.connect(self.toggleVideoPlayback)
        self.video_back_button.clicked.connect(lambda: self.seekVideoByMilliseconds(-1000))
        self.video_forward_button.clicked.connect(lambda: self.seekVideoByMilliseconds(1000))
        self.video_speed_combo.currentIndexChanged.connect(self.setVideoPlaybackRate)
        self.video_fit_combo.currentIndexChanged.connect(self.setVideoFitMode)
        self.video_position_slider.sliderPressed.connect(self._videoSliderPressed)
        self.video_position_slider.sliderReleased.connect(self._videoSliderReleased)
        self.video_position_slider.sliderMoved.connect(self._videoSliderMoved)
        self.video_camera_channel_apply_button.clicked.connect(self.applyVideoCameraChannel)
        self.video_camera_visible_checkbox.toggled.connect(self.setVideoCameraVisible)
        self.video_annotations_visible_checkbox.toggled.connect(self.setVideoAnnotationsVisible)
        self.video_display_mode_combo.currentIndexChanged.connect(
            self._videoDisplayModeChanged
        )
        self.video_window_combo.currentIndexChanged.connect(
            self._videoVisibleWindowChanged
        )
        self.video_filter_button.clicked.connect(self.showVideoFilterDialog)
        self.video_focus_button.toggled.connect(self.setVideoFocusMode)
        self.video_trajectory_dx_spin_box.editingFinished.connect(self._configureVideoTrajectoryAnalysis)
        self.video_das_plot_widget.scene().sigMouseClicked.connect(self._videoDasClicked)

        self._createVideoAnnotationSidebar(video_panel)
        if QVideoWidget is not None:
            self.video_player = QtMultimedia.QMediaPlayer(self)
            self.video_player.setVideoOutput(self.video_surface)
            self.video_player.positionChanged.connect(self._videoPositionChanged)
            self.video_player.durationChanged.connect(self._videoDurationChanged)
            self.video_player.stateChanged.connect(self._videoStateChanged)
            self.video_player.mediaStatusChanged.connect(self._videoMediaStatusChanged)
            self.video_player.error.connect(self._videoPlayerError)
        else:
            self.video_play_button.setEnabled(False)
            self.video_back_button.setEnabled(False)
            self.video_forward_button.setEnabled(False)
            self.video_speed_combo.setEnabled(False)
        self._syncVideoProjectWidgets()
        self.refreshVideoAnnotationTable()

    def _createVideoAnnotationSidebar(self, video_panel):
        """Keep video visible above scrollable synchronization/annotation tools."""

        self.annotation_sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(self.annotation_sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_layout.addWidget(video_panel)

        self.annotation_controls_scroll = QScrollArea()
        self.annotation_controls_scroll.setWidgetResizable(True)
        self.annotation_controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        annotation_content = QWidget()
        self.annotation_controls_scroll.setWidget(annotation_content)
        sidebar_layout.addWidget(self.annotation_controls_scroll, 1)
        layout = QVBoxLayout(annotation_content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        project_group = QGroupBox('标注工程')
        project_form = QFormLayout(project_group)
        project_form.setContentsMargins(8, 8, 8, 8)
        self.annotation_project_label = Label('未保存：标签仅在本次会话保留')
        self.annotation_project_label.setObjectName('secondaryLabel')
        self.annotation_project_label.setWordWrap(True)
        self.annotation_new_button = PushButton('新建')
        self.annotation_open_button = PushButton('打开')
        self.annotation_save_button = PushButton('保存')
        self.annotation_export_button = PushButton('导出 CSV')
        project_buttons = QWidget()
        project_buttons_layout = QGridLayout(project_buttons)
        project_buttons_layout.setContentsMargins(0, 0, 0, 0)
        project_buttons_layout.setSpacing(5)
        project_buttons_layout.addWidget(self.annotation_new_button, 0, 0)
        project_buttons_layout.addWidget(self.annotation_open_button, 0, 1)
        project_buttons_layout.addWidget(self.annotation_save_button, 1, 0)
        project_buttons_layout.addWidget(self.annotation_export_button, 1, 1)
        project_form.addRow(self.annotation_project_label)
        project_form.addRow(project_buttons)
        layout.addWidget(project_group)

        sync_group = QGroupBox('视频对时')
        sync_form = QFormLayout(sync_group)
        self.video_sync_form = sync_form
        sync_form.setContentsMargins(8, 8, 8, 8)
        self.video_start_time_edit = QDateTimeEdit()
        self.video_start_time_edit.setDisplayFormat('yyyy-MM-dd HH:mm:ss.zzz')
        self.video_start_time_edit.setCalendarPopup(True)
        self.video_start_time_edit.setKeyboardTracking(False)
        self.video_start_time_edit.setAccessibleName('视频开始时间')
        self.video_start_time_edit.setToolTip(
            '修改完成后自动应用；也可拖动右侧紫色虚线，用当前视频帧反算开始时间'
        )
        self.video_sync_offset_spin_box = QDoubleSpinBox()
        self.video_sync_offset_spin_box.setRange(-3600.0, 3600.0)
        self.video_sync_offset_spin_box.setDecimals(3)
        self.video_sync_offset_spin_box.setSingleStep(0.01)
        self.video_sync_offset_spin_box.setSuffix(' s')
        self.video_sync_offset_spin_box.setKeyboardTracking(False)
        self.video_sync_rate_spin_box = QDoubleSpinBox()
        self.video_sync_rate_spin_box.setRange(0.900000, 1.100000)
        self.video_sync_rate_spin_box.setDecimals(6)
        self.video_sync_rate_spin_box.setSingleStep(0.000100)
        self.video_sync_rate_spin_box.setValue(1.0)
        self.video_sync_rate_spin_box.setKeyboardTracking(False)
        self.video_sync_apply_button = PushButton('应用对时')
        self.video_sync_apply_button.setObjectName('primaryAction')
        self.video_sync_single_button = PushButton('校正当前时刻')
        self.video_sync_single_button.setCheckable(True)
        self.video_sync_single_button.setToolTip('暂停视频后点击此按钮，再在右侧 DAS 图上点击同一事件时刻')
        self.video_sync_anchor_button = PushButton('添加校准点')
        self.video_sync_anchor_button.setCheckable(True)
        self.video_sync_anchor_button.setToolTip('记录两个相隔较远的同一事件点，同时校正偏移和时钟漂移')
        self.video_sync_undo_button = PushButton('撤销校正')
        self.video_sync_reset_button = PushButton('恢复初始')
        self.video_sync_state_label = Label('等待选择视频')
        self.video_sync_state_label.setObjectName('statusBadge')
        self.video_sync_state_label.setWordWrap(True)
        self.video_sync_hint_label = Label(
            '单点校正固定偏移；两个相隔较远的校准点可同时校正长录像的时钟漂移。'
        )
        self.video_sync_hint_label.setObjectName('secondaryLabel')
        self.video_sync_hint_label.setWordWrap(True)
        sync_form.addRow('视频开始时间', self.video_start_time_edit)
        layout.addWidget(sync_group)

        mark_group = QGroupBox('人工标注')
        mark_form = QFormLayout(mark_group)
        mark_form.setContentsMargins(8, 8, 8, 8)
        self.annotation_kind_combo = ComboBox()
        self.annotation_kind_combo.setEditable(True)
        self.annotation_kind_combo.addItems(['车辆经过', '进入视野', '离开视野', '多车', '异常', '其他'])
        self.annotation_outcome_combo = ComboBox()
        self.annotation_outcome_combo.addItems(['未核对', '确认匹配', '拒绝', '不确定', 'DAS未检测到', '疑似误检'])
        self.annotation_note_edit = LineEdit()
        self.annotation_note_edit.setPlaceholderText('可选备注')
        self.annotation_point_button = PushButton('标记车辆 (T)')
        self.annotation_point_button.setObjectName('primaryAction')
        self.annotation_interval_start_button = PushButton('开始区间 (I)')
        self.annotation_interval_finish_button = PushButton('结束并保存 (O)')
        self.annotation_interval_finish_button.setEnabled(False)
        self.annotation_interval_label = Label('未开始区间标注')
        self.annotation_interval_label.setObjectName('secondaryLabel')
        self.annotation_trajectory_tolerance_spin_box = QDoubleSpinBox()
        self.annotation_trajectory_tolerance_spin_box.setRange(0.0, 120.0)
        self.annotation_trajectory_tolerance_spin_box.setDecimals(3)
        self.annotation_trajectory_tolerance_spin_box.setValue(2.0)
        self.annotation_trajectory_tolerance_spin_box.setSuffix(' s')
        self.annotation_trajectory_combo = ComboBox()
        self.annotation_trajectory_combo.addItem('不关联轨迹', None)
        self.annotation_update_button = PushButton('更新选中标注')
        mark_buttons = QWidget()
        mark_buttons_layout = QHBoxLayout(mark_buttons)
        mark_buttons_layout.setContentsMargins(0, 0, 0, 0)
        mark_buttons_layout.setSpacing(5)
        mark_buttons_layout.addWidget(self.annotation_point_button)
        mark_buttons_layout.addWidget(self.annotation_interval_start_button)
        mark_buttons_layout.addWidget(self.annotation_interval_finish_button)
        mark_form.addRow('类型', self.annotation_kind_combo)
        mark_form.addRow('结论', self.annotation_outcome_combo)
        mark_form.addRow('备注', self.annotation_note_edit)
        mark_form.addRow(mark_buttons)
        mark_form.addRow(self.annotation_interval_label)
        mark_form.addRow('候选窗口', self.annotation_trajectory_tolerance_spin_box)
        mark_form.addRow('关联轨迹', self.annotation_trajectory_combo)
        mark_form.addRow(self.annotation_update_button)
        layout.addWidget(mark_group)

        table_group = QGroupBox('标注列表')
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(8, 8, 8, 8)
        self.annotation_table = QTableWidget(0, 7)
        self.annotation_table.setHorizontalHeaderLabels(
            ['显', '#', '类型', '视频时间', 'DAS 时间', '轨迹', '结论']
        )
        self.annotation_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.annotation_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.annotation_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.annotation_table.verticalHeader().setVisible(False)
        self.annotation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.annotation_table.horizontalHeader().setStretchLastSection(True)
        self.annotation_table.setMinimumHeight(230)
        table_layout.addWidget(self.annotation_table)
        self.annotation_delete_button = PushButton('删除选中')
        self.annotation_delete_button.setObjectName('dangerAction')
        self.annotation_undo_button = PushButton('撤销最后一条')
        table_buttons = QHBoxLayout()
        table_buttons.addWidget(self.annotation_delete_button)
        table_buttons.addWidget(self.annotation_undo_button)
        table_buttons.addStretch(1)
        table_layout.addLayout(table_buttons)
        layout.addWidget(table_group, 1)

        self.annotation_new_button.clicked.connect(self.newVideoAnnotationProject)
        self.annotation_open_button.clicked.connect(self.openVideoAnnotationProject)
        self.annotation_save_button.clicked.connect(self.saveVideoAnnotationProject)
        self.annotation_export_button.clicked.connect(self.exportVideoAnnotationsCsv)
        self.video_start_time_edit.editingFinished.connect(self.applyVideoSync)
        self.video_sync_apply_button.clicked.connect(self.applyVideoSync)
        self.video_sync_single_button.clicked.connect(
            lambda: self._beginVideoSyncPick('single')
        )
        self.video_sync_anchor_button.clicked.connect(
            lambda: self._beginVideoSyncPick('anchor')
        )
        self.video_sync_undo_button.clicked.connect(self.undoVideoSyncCalibration)
        self.video_sync_reset_button.clicked.connect(self.resetVideoSyncCalibration)
        self.annotation_point_button.clicked.connect(self.addVideoPointAnnotation)
        self.annotation_interval_start_button.clicked.connect(self.beginVideoIntervalAnnotation)
        self.annotation_interval_finish_button.clicked.connect(self.finishVideoIntervalAnnotation)
        self.annotation_update_button.clicked.connect(self.updateSelectedVideoAnnotation)
        self.annotation_delete_button.clicked.connect(self.deleteSelectedVideoAnnotation)
        self.annotation_undo_button.clicked.connect(self.undoLastVideoAnnotation)
        self.annotation_table.itemSelectionChanged.connect(self._videoAnnotationTableSelectionChanged)
        self.annotation_table.itemChanged.connect(self._videoAnnotationTableItemChanged)

    # """------------------------------------------------------------------------------------------------------------"""
    """视频对照、同步与人工标注"""

    def _videoDataContext(self):
        """Return the long-recording context when one is active for video work."""

        if self.video_sequence_data_group is not None and self.video_sequence_timeline is not None:
            return self.video_sequence_data_group, self.video_sequence_timeline
        if self.video_das_match_required:
            return None, None
        return self.data_group, self.data_timeline

    def _clearVideoSequenceContext(self):
        """Return video comparison to the normal, full-resolution data context."""

        if self.video_filter_dialog is not None:
            self.video_filter_dialog.close()
            self.video_filter_dialog.deleteLater()
            self.video_filter_dialog = None
        self.video_sequence_data_group = None
        self.video_sequence_timeline = None
        self.video_sequence_source_paths = []
        self.video_sequence_selected_segment_index = None
        self.video_das_match_required = bool(self.video_annotation_project.video_path)
        self.video_trajectory_windows.clear()
        self.video_trajectory_pending.clear()
        self.video_trajectory_current_window = None
        # 清除正在进行的区间标注状态
        self._cancelPendingIntervalAnnotation()
        if hasattr(self, 'video_sequence_status_label'):
            self.video_sequence_status_label.setText('匹配 DAS：未加载')
            self.video_sequence_status_label.setToolTip('')

    def _videoChannelBounds(self):
        group, _timeline = self._videoDataContext()
        if group is not None:
            return 1, int(group.channel_count)
        return 1, 1

    def _annotationTimeline(self):
        _group, timeline = self._videoDataContext()
        if timeline is None or not self.video_annotation_context_matches:
            return None
        return timeline

    def updateVideoAnnotationDataContext(self):
        """Bind an annotation project only to its matching imported DAS source."""

        data_group, timeline = self._videoDataContext()
        if data_group is None or timeline is None:
            self.video_annotation_context_matches = False
            # 上下文无效时清除正在进行的区间标注
            self._cancelPendingIntervalAnnotation()
            self._updateVideoControlEnabledState()
            return False
        matches = self.video_annotation_project.set_das_context(data_group, timeline)
        self.video_annotation_context_matches = bool(matches)
        if matches:
            self.video_annotation_project.reproject_video_annotations(timeline)
        else:
            # 上下文不匹配时清除正在进行的区间标注
            self._cancelPendingIntervalAnnotation()
        self._updateVideoControlEnabledState()
        return matches

    def _updateVideoControlEnabledState(self):
        """Keep media controls usable while withholding data-dependent marking."""

        has_video = bool(self.video_annotation_project.video_path)
        has_timeline = self._annotationTimeline() is not None
        has_sync = has_video and self.video_annotation_project.sync.video_start_time is not None
        can_mark = has_timeline and has_sync
        self.video_das_load_button.setEnabled(has_sync)
        for widget in (
                self.video_camera_channel_spin_box,
                self.video_camera_channel_apply_button,
                self.video_trajectory_dx_spin_box,
                self.video_camera_visible_checkbox,
                self.video_annotations_visible_checkbox,
                self.video_follow_checkbox,
                self.video_filter_button,
        ):
            widget.setEnabled(has_timeline)
        for widget in (
                self.annotation_point_button,
                self.annotation_interval_start_button,
                self.annotation_update_button,
                self.video_sync_single_button,
                self.video_sync_anchor_button,
        ):
            widget.setEnabled(can_mark)
        self.video_start_time_edit.setEnabled(has_video)
        self.video_sync_apply_button.setEnabled(has_video)
        self.annotation_interval_finish_button.setEnabled(
            can_mark and self.video_annotation_interval_start_ms is not None
        )
        self.annotation_export_button.setEnabled(bool(self.video_annotation_project.annotations))
        self.annotation_save_button.setEnabled(True)
        self.annotation_delete_button.setEnabled(self.video_annotation_selected_id is not None)
        self.annotation_undo_button.setEnabled(bool(self.video_annotation_project.annotations))
        if not has_timeline:
            self.video_sync_summary_label.setText('对时：请先导入与视频对应的 DAS 数据')
        elif not self.video_annotation_context_matches:
            self.video_sync_summary_label.setText('对时：当前标注工程不属于这组 DAS 文件，已停止显示标签')
        elif not has_video:
            self.video_sync_summary_label.setText('对时：请选择摄像头视频')
        elif not has_sync:
            self.video_sync_summary_label.setText('对时：请设置视频开始时间')

    def _markVideoAnnotationDirty(self):
        self.video_annotation_dirty = True
        self._updateVideoProjectLabel()

    def _updateVideoProjectLabel(self):
        project_path = self.video_annotation_project.project_path
        if project_path:
            state = '有未保存修改' if self.video_annotation_dirty else '已保存'
            self.annotation_project_label.setText(f'{state}：{project_path}')
            self.annotation_project_label.setToolTip(project_path)
        else:
            self.annotation_project_label.setText('未保存：标签仅在本次会话保留')
            self.annotation_project_label.setToolTip('请使用“保存”创建独立标注工程文件')

    def _syncVideoProjectWidgets(self):
        """Reflect model state in controls without accidentally applying edits."""

        project = self.video_annotation_project
        self.video_camera_channel_spin_box.blockSignals(True)
        self.video_camera_visible_checkbox.blockSignals(True)
        self.video_start_time_edit.blockSignals(True)
        self.video_sync_offset_spin_box.blockSignals(True)
        self.video_sync_rate_spin_box.blockSignals(True)
        try:
            self.video_camera_channel_spin_box.setValue(max(1, project.camera_channel))
            self.video_camera_visible_checkbox.setChecked(project.camera_visible)
            if project.sync.video_start_time is not None:
                self.video_start_time_edit.setDateTime(QDateTime(project.sync.video_start_time))
            self.video_sync_offset_spin_box.setValue(project.sync.manual_offset_seconds)
            self.video_sync_rate_spin_box.setValue(project.sync.rate)
        finally:
            self.video_camera_channel_spin_box.blockSignals(False)
            self.video_camera_visible_checkbox.blockSignals(False)
            self.video_start_time_edit.blockSignals(False)
            self.video_sync_offset_spin_box.blockSignals(False)
            self.video_sync_rate_spin_box.blockSignals(False)
        self._updateVideoProjectLabel()
        self._updateVideoControlEnabledState()
        self._updateVideoSyncState()

    def chooseVideoComparisonFile(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            '选择摄像头视频',
            '',
            '视频文件 (*.mp4 *.mov *.avi *.mkv *.mpeg *.mpg *.m4v);;所有文件 (*.*)',
        )
        if path:
            self.loadVideoComparisonFile(path)

    @staticmethod
    def _videoPeriod(value: datetime) -> str:
        hour = value.hour
        if 4 <= hour < 11:
            return '清晨'
        if 11 <= hour < 18:
            return '下午'
        return '夜间/凌晨'

    def _recommendedDasFolder(self, video_start: datetime):
        """Find a same-date BIN directory near the camera time without loading it."""
        current = getattr(self, 'file_path', '')
        if not current or not os.path.isdir(current):
            return None
        search_root = os.path.dirname(os.path.normpath(current))
        groups = {}
        inspected = 0
        for directory, _subdirs, files in os.walk(search_root):
            for name in files:
                if not name.casefold().endswith('.bin'):
                    continue
                inspected += 1
                if inspected > 20_000:
                    break
                try:
                    value = parse_filename_end_time(name)
                except (TypeError, ValueError):
                    value = None
                if value is None or value.date() != video_start.date():
                    continue
                distance = abs((value - video_start).total_seconds())
                previous = groups.get(directory)
                groups[directory] = (min(distance, previous[0]) if previous else distance, (previous[1] if previous else 0) + 1)
            if inspected > 20_000:
                break
        if not groups:
            return None
        directory, (distance, count) = min(groups.items(), key=lambda item: (item[1][0], -item[1][1], item[0]))
        return directory, count, distance

    def _refreshVideoDasRecommendation(self):
        """Show the likely DAS folder before the user starts time matching."""
        video_start = parse_video_start_time(self.video_annotation_project.video_path)
        _group, timeline = self._videoDataContext()
        if video_start is None:
            return
        period = self._videoPeriod(video_start)
        folder_hint = self._recommendedDasFolder(video_start)
        folder_text = (
            f'文件夹 {os.path.basename(folder_hint[0])}（{folder_hint[1]} 个同日 BIN，最近约 {folder_hint[2]:.0f} s）'
            if folder_hint is not None else '当前数据根目录下未找到同日期 BIN 文件夹'
        )
        if timeline is None:
            self.video_sync_summary_label.setText(
                f'录像时间 {video_start.date()} {period}；{folder_text}。点击“匹配 DAS”按时间范围载入。'
            )
            return
        das_date = timeline.start_time.date()
        if das_date != video_start.date():
            self.video_sync_summary_label.setText(
                f'日期不匹配：录像为 {video_start.date()} {period}，当前 DAS 为 {das_date}。'
                f'推荐 {folder_text}；不会自动把 9 月 4 日数据当作 9 月 5 日对时。'
            )
            return
        self.video_sync_summary_label.setText(
            f'推荐并已核对：{video_start.date()} {period} DAS，{folder_text}；'
            '可拖动右侧紫色虚线校正当前视频帧。'
        )

    def _videoSourceDurationMs(self) -> int:
        if self.video_media_probe is not None and self.video_media_probe.duration_seconds:
            return max(0, int(round(self.video_media_probe.duration_seconds * 1000.0)))
        if self.video_ffmpeg_duration_ms > 0:
            return int(self.video_ffmpeg_duration_ms)
        return max(0, int(self.video_position_slider.maximum()))

    def _videoWallTimeRange(self):
        """Return the calibrated source-video wall-clock interval."""

        sync = self.video_annotation_project.sync
        duration_ms = self._videoSourceDurationMs()
        start = sync.wall_time_for_video_position(0)
        end = sync.wall_time_for_video_position(duration_ms)
        if start is None:
            raise ValueError('无法从录像文件名识别开始时间，请先在标注页填写视频开始时间')
        if duration_ms <= 0 or end is None:
            raise ValueError('尚未取得录像时长，请等待媒体探测完成')
        return min(start, end), max(start, end)

    def _matchingVideoDasPaths(self, folder: str, margin_seconds: float = VIDEO_DAS_MATCH_MARGIN_SECONDS):
        """Match BIN files whose corrected acquisition interval overlaps the video."""

        folder = os.path.realpath(str(folder))
        if not os.path.isdir(folder):
            raise ValueError('DAS 文件夹不存在')
        video_start, video_end = self._videoWallTimeRange()
        margin = timedelta(seconds=max(0.0, float(margin_seconds)))
        wanted_start = video_start - margin
        wanted_end = video_end + margin
        matches = []
        for name in sorted(os.listdir(folder), key=natural_sort_key):
            if not name.casefold().endswith('.bin'):
                continue
            path = os.path.join(folder, name)
            try:
                header, samples, _channels, rate, _endian = read_bin_header(path)
                file_end = recorded_end_time(path, header[:6])[0] + timedelta(
                    seconds=self.time_correction_seconds
                )
                file_start = file_end - timedelta(seconds=float(samples) / float(rate))
            except (OSError, TypeError, ValueError, ZeroDivisionError):
                continue
            if file_end >= wanted_start and file_start <= wanted_end:
                matches.append((file_start, path))
        return [path for _start, path in sorted(matches, key=lambda item: (item[0], natural_sort_key(item[1])))]

    def chooseVideoDasFolder(self):
        """Choose a DAS folder, time-match it to the video, and load metadata only."""

        try:
            video_start, _video_end = self._videoWallTimeRange()
        except ValueError as error:
            printError(str(error))
            return
        current = getattr(self, 'file_path', '')
        hint = self._recommendedDasFolder(video_start)
        default_folder = hint[0] if hint is not None else current
        folder = QFileDialog.getExistingDirectory(
            self, '选择与录像对应的 DAS 文件夹', default_folder or ''
        )
        if not folder:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.video_sequence_status_label.setText('匹配 DAS：正在扫描文件头…')
        QApplication.processEvents()
        try:
            paths = self._matchingVideoDasPaths(folder)
        finally:
            QApplication.restoreOverrideCursor()
        if not paths:
            start, end = self._videoWallTimeRange()
            message = (
                f'所选文件夹中没有与录像 {format_wall_time(start)} 至 '
                f'{format_wall_time(end)} 重叠的 BIN 文件'
            )
            printError(message)
            self.video_sequence_status_label.setText('匹配 DAS：未找到重叠文件')
            return
        self.file_path = folder
        self.updateFile()
        self.loadVideoSequencePaths(paths, source_description='按录像时间匹配')

    def loadVideoComparisonFile(self, path: str, update_project: bool = True):
        """Set source media and use a local truthful-suffix cache only if needed."""

        path = str(path)
        # 加载新视频时清除正在进行的区间标注
        self._cancelPendingIntervalAnnotation()
        self._clearVideoSequenceContext()
        if update_project:
            parsed_start = parse_video_start_time(path)
            self.video_annotation_project.video_path = path
            self.video_annotation_project.sync.update(parsed_start, 0.0, 1.0)
            self.video_annotation_project.calibration_anchors = []
            self.video_sync_calibration_anchors = []
            self._video_sync_undo_stack.clear()
            self._finishVideoSyncPick()
            self._markVideoAnnotationDirty()
            if parsed_start is None:
                self.video_sync_hint_label.setText(
                    '未能从文件名识别开始时间，请手工填写视频开始时间。'
                )
            else:
                self.video_sync_hint_label.setText(
                    '文件名时间作为初始值；可拖动紫色虚线对准同一车辆事件。'
                )
        self.video_das_match_required = True
        if hasattr(self, 'sidebar_tabs'):
            self.sidebar_tabs.setCurrentWidget(self.annotation_sidebar_widget)
        self.video_source_label.setText(f'视频：{os.path.basename(path)}')
        self.video_source_label.setToolTip(path)
        self._stopFfmpegVideoWorker()
        self._video_frame_pixmap = None
        self.video_playback_backend = 'qt'
        self.video_viewport_stack.setCurrentWidget(self.video_surface)
        self.video_media_playback_path = path
        self.video_media_probe = None
        conversion_pending = False
        try:
            probe = probe_video(path)
            self.video_media_probe = probe
            if probe.is_mpeg_program_stream:
                duration = format_video_position(
                    int(round((probe.duration_seconds or 0.0) * 1000))
                )
                codec = probe.video_codec if probe.video_codec != 'unknown' else '视频编码待媒体后端确认'
                completion = {
                    'terminated': '检测到节目流结束码',
                    'truncated_or_unfinalized': '未检测到结束码；固定容量零填充，不能视为完整',
                    'unfinalized': '未检测到节目流结束码，完整性无法确认',
                }.get(probe.completion_state, '完整性未知')
                self.video_media_info_label.setText(
                    f'媒体探测：MPEG-PS · {codec} · PTS 时长 {duration} · {completion}'
                )
                self.video_media_info_label.setToolTip(
                    f'只读源：{path}\n有效负载末尾：{probe.payload_end_offset:,} B；'
                    f'零填充：{probe.trailing_zero_bytes:,} B。播放使用本机独立 .mpg 缓存副本。'
                )
                self._startVideoMediaConversion(path)
                conversion_pending = True
            else:
                duration = format_video_position(int(round((probe.duration_seconds or 0.0) * 1000)))
                self.video_media_info_label.setText(f'媒体：{probe.video_codec} · {duration}')
                self.video_media_info_label.setToolTip('源文件格式由系统媒体后端直接播放。')
        except (OSError, ValueError) as error:
            self.video_media_info_label.setText(f'媒体探测失败：{error}')
        self._refreshVideoDasRecommendation()
        self._syncVideoProjectWidgets()
        if conversion_pending:
            if self.video_player is not None:
                self.video_player.stop()
                self.video_player.setMedia(QtMultimedia.QMediaContent())
            for control in (self.video_play_button, self.video_back_button, self.video_forward_button, self.video_speed_combo):
                control.setEnabled(False)
            self.video_viewport_stack.setCurrentWidget(self.video_frame_surface)
            self.video_frame_surface.setText('正在生成独立播放缓存；源录像不会被修改。')
            self.video_position_slider.setRange(0, 0)
            self.video_time_label.setText('--:--:--.--- / --:--:--.---')
            self._updateVideoPlayhead(0, force=True)
            self.plotVideoComparisonImage()
            return
        if self.video_player is None:
            self.video_sync_summary_label.setText('当前 PyQt 安装没有可用的视频画面组件。')
            return
        self.video_player.stop()
        self.video_player.setMedia(
            QtMultimedia.QMediaContent(QUrl.fromLocalFile(self.video_media_playback_path))
        )
        self.video_position_slider.setRange(0, 0)
        self.video_time_label.setText('--:--:--.--- / --:--:--.---')
        self._updateVideoPlayhead(0, force=True)
        self.plotVideoComparisonImage()

    def _startVideoMediaConversion(self, source_path: str):
        """Transcode incompatible MPEG-PS in background, always into its cache."""
        expected_duration = (
            self.video_media_probe.duration_seconds
            if self.video_media_probe is not None else None
        )
        future = self.video_media_executor.submit(
            cached_playable_video, source_path, None, expected_duration
        )
        future._das_video_source_path = str(source_path)
        self.video_media_future = future
        self.video_media_poll_timer.start()
        self.video_sync_summary_label.setText(
            '正在后台生成 H.264/AAC 播放缓存；录像源保持只读，完成后可匹配 DAS。'
        )

    def _pollVideoMediaConversion(self):
        future = self.video_media_future
        if future is None or not future.done():
            return
        self.video_media_future = None
        self.video_media_poll_timer.stop()
        try:
            playable_path = str(future.result())
        except Exception as error:
            self.video_sync_summary_label.setText(
                f'播放缓存生成失败：{error}；源录像未被修改。'
            )
            return
        if future._das_video_source_path != self.video_annotation_project.video_path:
            return
        self.video_media_playback_path = playable_path
        self._loadFfmpegVideo(playable_path)
        for control in (self.video_play_button, self.video_back_button, self.video_forward_button, self.video_speed_combo):
            control.setEnabled(True)
        source_duration = (
            int(round(self.video_media_probe.duration_seconds * 1000.0))
            if self.video_media_probe is not None and self.video_media_probe.duration_seconds
            else self.video_ffmpeg_duration_ms
        )
        self.video_media_info_label.setText(
            '媒体探测：MPEG-PS 已转换为独立 H.264/AAC 播放缓存；'
            f'时间轴 {format_video_position(source_duration)}，已通过时长校验。'
        )
        self.video_sync_summary_label.setText('播放缓存已就绪；可播放、跳转并与 DAS 同步。')

    def _loadFfmpegVideo(self, path: str):
        """Activate deterministic FFmpeg frame playback after cache conversion."""
        try:
            cache_probe = probe_video(path)
            self.video_ffmpeg_duration_ms = int(round((cache_probe.duration_seconds or 0.0) * 1000.0))
        except (OSError, ValueError):
            self.video_ffmpeg_duration_ms = 0
        self._stopFfmpegVideoWorker()
        self.video_playback_backend = 'ffmpeg'
        self.video_ffmpeg_position_ms = 0
        self.video_position_slider.setRange(0, self.video_ffmpeg_duration_ms)
        self.video_position_slider.setValue(0)
        self.video_time_label.setText(
            f'{format_video_position(0)} / {format_video_position(self.video_ffmpeg_duration_ms)}'
        )
        self.video_viewport_stack.setCurrentWidget(self.video_frame_surface)
        self.video_frame_surface.setText('播放缓存已就绪；点击播放。')
        self._seekFfmpegVideo(0, play_continuously=False)

    def _stopFfmpegVideoWorker(self):
        worker = self.video_ffmpeg_worker
        self.video_ffmpeg_worker = None
        if worker is not None:
            worker.stop()
            worker.wait(500)

    def _seekFfmpegVideo(self, position_ms: int, play_continuously: bool):
        if not self.video_media_playback_path:
            return
        target = min(max(0, int(position_ms)), self.video_ffmpeg_duration_ms)
        self._stopFfmpegVideoWorker()
        self.video_ffmpeg_position_ms = target
        self.video_ffmpeg_playing = bool(play_continuously)
        worker = FfmpegFrameWorker(
            self.video_media_playback_path,
            target,
            playback_rate=float(self.video_speed_combo.currentData() or 1.0),
            play_continuously=bool(play_continuously),
            parent=self,
        )
        worker.frameReady.connect(self._ffmpegVideoFrameReady)
        worker.playbackEnded.connect(self._ffmpegVideoEnded)
        worker.errorRaised.connect(lambda message: self.video_sync_summary_label.setText(message))
        self.video_ffmpeg_worker = worker
        worker.start()

    def _ffmpegVideoFrameReady(self, image, position_ms: int):
        if self.video_playback_backend != 'ffmpeg':
            return
        self.video_ffmpeg_position_ms = min(
            max(0, int(position_ms)), self.video_ffmpeg_duration_ms
        )
        pixmap = QPixmap.fromImage(image)
        if not pixmap.isNull():
            self._video_frame_pixmap = pixmap
            self._renderVideoFrame()
        if not self._video_slider_dragging:
            self.video_position_slider.setValue(self.video_ffmpeg_position_ms)
        self.video_time_label.setText(
            f'{format_video_position(self.video_ffmpeg_position_ms)} / '
            f'{format_video_position(self.video_ffmpeg_duration_ms)}'
        )
        self._updateVideoPlayhead(self.video_ffmpeg_position_ms)

    def _renderVideoFrame(self):
        pixmap = self._video_frame_pixmap
        if pixmap is None or pixmap.isNull() or not hasattr(self, 'video_frame_surface'):
            return
        mode = self.video_fit_combo.currentData() if hasattr(self, 'video_fit_combo') else Qt.KeepAspectRatio
        self.video_frame_surface.setPixmap(
            pixmap.scaled(
                self.video_frame_surface.size(),
                mode,
                Qt.SmoothTransformation,
            )
        )

    def setVideoFitMode(self, _index: int):
        mode = self.video_fit_combo.currentData()
        if QVideoWidget is not None and isinstance(self.video_surface, QVideoWidget):
            self.video_surface.setAspectRatioMode(mode)
        self._renderVideoFrame()

    def eventFilter(self, watched, event):
        if (
            hasattr(self, 'video_frame_surface')
            and watched is self.video_frame_surface
            and event.type() == QEvent.Resize
        ):
            QTimer.singleShot(0, self._renderVideoFrame)
        return super().eventFilter(watched, event)

    def _ffmpegVideoEnded(self):
        if self.video_playback_backend != 'ffmpeg':
            return
        self.video_ffmpeg_playing = False
        self.video_play_button.setText('播放')

    def toggleVideoPlayback(self):
        if self.video_playback_backend == 'ffmpeg':
            if self.video_ffmpeg_playing:
                self.video_ffmpeg_playing = False
                self._stopFfmpegVideoWorker()
                self.video_play_button.setText('播放')
            else:
                self._seekFfmpegVideo(self.video_ffmpeg_position_ms, play_continuously=True)
                self.video_play_button.setText('暂停')
            return
        if self.video_player is None or not self.video_annotation_project.video_path:
            return
        if self.video_player.state() == QtMultimedia.QMediaPlayer.PlayingState:
            self.video_player.pause()
        else:
            self.video_player.play()

    def seekVideoByMilliseconds(self, delta: int):
        if self.video_playback_backend == 'ffmpeg':
            self._seekFfmpegVideo(
                self.video_ffmpeg_position_ms + int(delta), self.video_ffmpeg_playing
            )
            return
        if self.video_player is None:
            return
        maximum = max(0, self.video_player.duration())
        target = min(max(0, self.video_player.position() + int(delta)), maximum)
        self.video_player.setPosition(target)
        self._updateVideoPlayhead(target, force=True)

    def setVideoPlaybackRate(self, _index: int):
        if self.video_playback_backend == 'ffmpeg' and self.video_ffmpeg_playing:
            self._seekFfmpegVideo(self.video_ffmpeg_position_ms, play_continuously=True)
            return
        if self.video_player is not None:
            self.video_player.setPlaybackRate(float(self.video_speed_combo.currentData() or 1.0))

    def _videoSliderPressed(self):
        self._video_slider_dragging = True

    def _videoSliderMoved(self, value: int):
        self.video_time_label.setText(
            f'{format_video_position(value)} / {format_video_position(self.video_position_slider.maximum())}'
        )
        self._updateVideoPlayhead(value, force=True)

    def _videoSliderReleased(self):
        self._video_slider_dragging = False
        if self.video_playback_backend == 'ffmpeg':
            self._seekFfmpegVideo(self.video_position_slider.value(), self.video_ffmpeg_playing)
            self._updateVideoPlayhead(self.video_position_slider.value(), force=True)
            return
        if self.video_player is not None:
            self.video_player.setPosition(self.video_position_slider.value())
        self._updateVideoPlayhead(self.video_position_slider.value(), force=True)

    def _videoDurationChanged(self, duration: int):
        if duration <= 0 and self.video_media_probe is not None and self.video_media_probe.duration_seconds:
            duration = int(round(self.video_media_probe.duration_seconds * 1000.0))
        self.video_position_slider.setRange(0, max(0, int(duration)))
        self.video_time_label.setText(
            f'{format_video_position(self.video_player.position() if self.video_player else 0)} / '
            f'{format_video_position(duration)}'
        )

    def _videoStateChanged(self, state):
        self.video_play_button.setText(
            '暂停' if state == QtMultimedia.QMediaPlayer.PlayingState else '播放'
        )

    def _videoMediaStatusChanged(self, status):
        if status == QtMultimedia.QMediaPlayer.LoadedMedia:
            playback = 'MPEG-PS 缓存副本' if self.video_media_probe and self.video_media_probe.is_mpeg_program_stream else '源文件'
            self.video_sync_summary_label.setText(
                f'视频已载入（{playback}）；当前时间会同步到下方 DAS 竖线。'
            )
        elif status == QtMultimedia.QMediaPlayer.InvalidMedia:
            self.video_sync_summary_label.setText(
                '当前 Windows 媒体后端仍无法播放该编码；源文件未被修改。'
                '请安装可用的 FFmpeg 后端或使用兼容的 H.264/AAC 缓存转码。'
            )

    def _videoPlayerError(self, *_args):
        if self.video_player is not None:
            details = self.video_player.errorString().strip()
            if details:
                self.video_sync_summary_label.setText(f'视频播放失败：{details}')

    def _videoPositionChanged(self, position: int):
        if not self._video_slider_dragging:
            self.video_position_slider.setValue(max(0, int(position)))
        self.video_time_label.setText(
            f'{format_video_position(position)} / {format_video_position(self.video_position_slider.maximum())}'
        )
        self._updateVideoPlayhead(position)

    def _updateVideoPlayhead(self, position_ms: int, force: bool = False):
        """Move the synchronized cursor only; never redraw the data image per frame."""

        if not force and abs(int(position_ms) - self._last_video_playhead_update_ms) < 50:
            return
        self._last_video_playhead_update_ms = int(position_ms)
        timeline = self._annotationTimeline()
        if timeline is None:
            self.video_current_das_label.setText('DAS：等待数据')
            return
        sample = self.video_annotation_project.sync.sample_for_video_position(position_ms, timeline)
        if sample is None:
            self.video_current_das_label.setText('DAS：未设置视频开始时间')
            return
        sampling_rate = float(timeline.sampling_rate)
        seconds = sample / sampling_rate
        wall_time = timeline.absolute_time_for_sample(sample)
        self.video_current_das_label.setText(
            f'DAS {format_wall_time(wall_time)}  |  样点 {sample}'
        )
        if self.video_playhead_line is not None:
            if not self._video_playhead_dragging:
                self.video_playhead_line.setPos(seconds)
                self._setVideoPlayheadTooltip(
                    self.video_playhead_line, sample, wall_time
                )
        if self.video_follow_checkbox.isChecked() and self.video_das_plot_widget is not None:
            view_box = self.video_das_plot_widget.getViewBox()
            maximum = timeline.total_samples / sampling_rate
            width = min(self._videoVisibleWindowSeconds(), maximum)
            width = max(width, 1 / sampling_rate)
            # Keep the playhead at one quarter of the window.  Updating this
            # range on every clock tick produces a continuous stitched scroll
            # instead of the former edge-triggered jumps.
            target_left = min(
                max(seconds - width * 0.25, 0.0),
                max(0.0, maximum - width),
            )
            target_right = min(maximum, target_left + width)
            view_box.setXRange(target_left, target_right, padding=0)
        self._requestVideoTrajectoryForPosition(position_ms)

    def _videoPlayheadTarget(self, line):
        """Return the DAS sample and wall time represented by a cursor line."""

        timeline = self._annotationTimeline()
        if timeline is None:
            return None
        seconds = min(
            max(float(line.value()), 0.0),
            timeline.total_samples / float(timeline.sampling_rate),
        )
        sample = min(
            max(int(round(seconds * float(timeline.sampling_rate))), 0),
            timeline.total_samples,
        )
        return sample, timeline.absolute_time_for_sample(sample)

    @staticmethod
    def _setVideoPlayheadTooltip(line, sample: int, wall_time: datetime):
        line.setToolTip(
            f'DAS 时间：{format_wall_time(wall_time)}\n样点：{sample}\n'
            '拖动紫色虚线并松开，可校正当前视频帧'
        )

    def _videoPlayheadDragged(self, line):
        """Pause playback and preview the DAS time underneath the dragged cursor."""

        if not self._video_playhead_dragging:
            self._video_playhead_dragging = True
            if self.video_playback_backend == 'ffmpeg':
                self.video_ffmpeg_playing = False
                self._stopFfmpegVideoWorker()
                self.video_play_button.setText('播放')
            elif self.video_player is not None:
                self.video_player.pause()
        target = self._videoPlayheadTarget(line)
        if target is None:
            return
        sample, wall_time = target
        self._setVideoPlayheadTooltip(line, sample, wall_time)
        self.video_current_das_label.setText(
            f'DAS {format_wall_time(wall_time)}  |  样点 {sample}'
        )
        self.video_sync_summary_label.setText(
            f'拖动对时：松开后，当前视频帧将对应 DAS {format_wall_time(wall_time)}。'
        )

    def _videoPlayheadMoveFinished(self, line):
        """Commit one drag as a single-start-time video/DAS calibration."""

        if not self._video_playhead_dragging:
            return
        self._video_playhead_dragging = False
        target = self._videoPlayheadTarget(line)
        if target is None:
            return
        sample, _wall_time = target
        self._alignCurrentVideoToDasSample(sample)

    def _beginVideoSyncPick(self, mode: str):
        """Pause playback and let the next DAS click establish correspondence."""

        button = (
            self.video_sync_single_button
            if mode == 'single' else self.video_sync_anchor_button
        )
        if not button.isChecked():
            self._finishVideoSyncPick()
            self.video_sync_summary_label.setText('已取消人工对时取点。')
            return
        if self._annotationTimeline() is None:
            self._finishVideoSyncPick()
            printError('请先自动匹配视频对应的 DAS 数据')
            return
        if self.video_annotation_project.sync.video_start_time is None:
            self._finishVideoSyncPick()
            printError('请先设置视频开始时间')
            return
        if self.video_playback_backend == 'ffmpeg':
            self.video_ffmpeg_playing = False
            self._stopFfmpegVideoWorker()
            self.video_play_button.setText('播放')
        elif self.video_player is not None:
            self.video_player.pause()
        self._video_sync_pick_mode = mode
        other = (
            self.video_sync_anchor_button
            if mode == 'single' else self.video_sync_single_button
        )
        other.blockSignals(True)
        other.setChecked(False)
        other.blockSignals(False)
        action = '单点校正' if mode == 'single' else '校准点'
        self.video_sync_summary_label.setText(
            f'{action}取点中：请在右侧 DAS 图点击与当前视频帧相同的事件时刻；再次点击按钮可取消。'
        )

    def _finishVideoSyncPick(self):
        self._video_sync_pick_mode = None
        for button in (
            self.video_sync_single_button,
            self.video_sync_anchor_button,
        ):
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)

    def _videoSyncSnapshot(self):
        sync = self.video_annotation_project.sync
        return {
            'video_start_time': sync.video_start_time,
            'manual_offset_seconds': float(sync.manual_offset_seconds),
            'rate': float(sync.rate),
            'anchors': [dict(item) for item in self.video_annotation_project.calibration_anchors],
        }

    def _pushVideoSyncUndo(self):
        snapshot = self._videoSyncSnapshot()
        if not self._video_sync_undo_stack or self._video_sync_undo_stack[-1] != snapshot:
            self._video_sync_undo_stack.append(snapshot)
            self._video_sync_undo_stack = self._video_sync_undo_stack[-20:]

    def _restoreVideoSyncSnapshot(self, snapshot, message: str):
        sync = self.video_annotation_project.sync
        sync.update(
            snapshot.get('video_start_time'),
            snapshot.get('manual_offset_seconds', 0.0),
            snapshot.get('rate', 1.0),
        )
        self.video_annotation_project.calibration_anchors = [
            dict(item) for item in snapshot.get('anchors', [])
        ]
        self.video_sync_calibration_anchors = list(
            self.video_annotation_project.calibration_anchors
        )
        timeline = self._annotationTimeline()
        moved = self.video_annotation_project.reproject_video_annotations(timeline) if timeline else 0
        self._markVideoAnnotationDirty()
        self._syncVideoProjectWidgets()
        self.refreshVideoAnnotationTable(select_identifier=self.video_annotation_selected_id)
        self.plotVideoComparisonImage()
        self._updateVideoPlayhead(self._currentVideoPosition(), force=True)
        self.video_sync_summary_label.setText(f'{message}；重新定位 {moved} 条标注。')

    def undoVideoSyncCalibration(self):
        if not self._video_sync_undo_stack:
            return
        self._restoreVideoSyncSnapshot(
            self._video_sync_undo_stack.pop(),
            '已撤销上一次对时修改',
        )

    def resetVideoSyncCalibration(self):
        sync = self.video_annotation_project.sync
        initial_start = parse_video_start_time(self.video_annotation_project.video_path)
        if initial_start is None:
            initial_start = sync.video_start_time
        target = {
            'video_start_time': initial_start,
            'manual_offset_seconds': 0.0,
            'rate': 1.0,
            'anchors': [],
        }
        if self._videoSyncSnapshot() == target:
            return
        self._pushVideoSyncUndo()
        self._restoreVideoSyncSnapshot(target, '已恢复文件名初始对时')

    def _updateVideoSyncState(self):
        if not hasattr(self, 'video_sync_state_label'):
            return
        sync = self.video_annotation_project.sync
        if not self.video_annotation_project.video_path:
            text = '等待选择视频'
            active = False
        elif sync.video_start_time is None:
            text = '未设置视频开始时间'
            active = False
        else:
            parsed = parse_video_start_time(self.video_annotation_project.video_path)
            source = '文件名对时' if parsed == sync.video_start_time else '手工开始时间'
            anchor_count = len(self.video_annotation_project.calibration_anchors)
            text = (
                f'{source} · 偏移 {sync.manual_offset_seconds:+.3f} s · '
                f'倍率 {sync.rate:.6f} · {anchor_count} 个校准点'
            )
            active = self._annotationTimeline() is not None
        self.video_sync_state_label.setText(text)
        self.video_sync_state_label.setProperty('state', 'active' if active else 'inactive')
        self.video_sync_state_label.style().unpolish(self.video_sync_state_label)
        self.video_sync_state_label.style().polish(self.video_sync_state_label)
        self.video_sync_undo_button.setEnabled(bool(self._video_sync_undo_stack))
        reset_needed = bool(
            self.video_annotation_project.calibration_anchors
            or not np.isclose(sync.manual_offset_seconds, 0.0)
            or not np.isclose(sync.rate, 1.0)
        )
        self.video_sync_reset_button.setEnabled(
            bool(self.video_annotation_project.video_path) and reset_needed
        )

    def _videoDasClicked(self, event):
        """Seek, or use Ctrl+Shift to anchor the current video frame to DAS."""

        if event.button() != Qt.LeftButton:
            return
        if getattr(event, 'double', lambda: False)():
            self.video_focus_button.toggle()
            return
        pick_mode = self._video_sync_pick_mode
        if pick_mode is None and not (event.modifiers() & Qt.ControlModifier):
            return
        timeline = self._annotationTimeline()
        if timeline is None:
            return
        view_box = self.video_das_plot_widget.getViewBox()
        point = view_box.mapSceneToView(event.scenePos())
        sample = min(
            max(int(round(point.x() * timeline.sampling_rate)), 0),
            timeline.total_samples,
        )
        if pick_mode == 'anchor' or event.modifiers() & Qt.ShiftModifier:
            self._recordVideoCalibrationAnchor(sample)
            self._finishVideoSyncPick()
            return
        if pick_mode == 'single':
            self._alignCurrentVideoToDasSample(sample)
            self._finishVideoSyncPick()
            return
        position = self.video_annotation_project.sync.video_position_for_sample(sample, timeline)
        if position is None:
            return
        if self.video_playback_backend == 'ffmpeg':
            self._seekFfmpegVideo(position, play_continuously=False)
        elif self.video_player is not None:
            self.video_player.pause()
            self.video_player.setPosition(position)
        self._updateVideoPlayhead(position, force=True)

    def _alignCurrentVideoToDasSample(self, sample: int):
        """Derive the sole video start time from one video-frame/DAS match."""

        timeline = self._annotationTimeline()
        sync = self.video_annotation_project.sync
        if timeline is None or sync.video_start_time is None:
            printError('请先选择视频并设置视频开始时间，再建立手工对时锚点')
            return
        if self.video_playback_backend == 'ffmpeg':
            self._stopFfmpegVideoWorker()
        elif self.video_player is not None:
            self.video_player.pause()
        position_ms = self._currentVideoPosition()
        target_time = timeline.absolute_time_for_sample(sample)
        start_time = target_time - timedelta(seconds=position_ms / 1000.0)
        self._pushVideoSyncUndo()
        sync.update(start_time, 0.0, 1.0)
        self.video_annotation_project.calibration_anchors = []
        self.video_sync_calibration_anchors = []
        moved = self.video_annotation_project.reproject_video_annotations(timeline)
        self._markVideoAnnotationDirty()
        self._syncVideoProjectWidgets()
        self.refreshVideoAnnotationTable(select_identifier=self.video_annotation_selected_id)
        self.plotVideoComparisonImage()
        self._updateVideoPlayhead(position_ms, force=True)
        self.video_sync_summary_label.setText(
            f'拖动对时已应用：视频 {format_video_position(position_ms)} '
            f'→ DAS {format_wall_time(target_time)}；视频开始时间已更新为 '
            f'{format_wall_time(start_time)}，重新定位 {moved} 条标签。'
        )

    def _recordVideoCalibrationAnchor(self, sample: int):
        """Use two operator-confirmed events to solve offset and clock rate."""
        timeline = self._annotationTimeline()
        sync = self.video_annotation_project.sync
        if timeline is None or sync.video_start_time is None:
            printError('请先选择视频、导入匹配 DAS，再记录校准锚点')
            return
        if self.video_playback_backend == 'ffmpeg':
            self._stopFfmpegVideoWorker()
        elif self.video_player is not None:
            self.video_player.pause()
        anchor = {
            'video_position_ms': int(self._currentVideoPosition()),
            'das_sample': int(sample),
        }
        anchors = list(self.video_annotation_project.calibration_anchors)
        if anchors and abs(anchor['video_position_ms'] - anchors[-1]['video_position_ms']) < 100:
            printError('两次校准锚点的视频时刻过近；请使用两次明确且相隔较远的车辆经过事件')
            return
        candidate_anchors = (anchors + [anchor])[-2:]
        if len(candidate_anchors) < 2:
            self._pushVideoSyncUndo()
            self.video_annotation_project.calibration_anchors = candidate_anchors
            self.video_sync_calibration_anchors = list(candidate_anchors)
            self._markVideoAnnotationDirty()
            self._updateVideoSyncState()
            self.video_sync_summary_label.setText(
                '已记录第 1 个校准点。暂停到另一个相隔较远的明确事件，点击“添加校准点”后在 DAS 图选取第 2 点。'
            )
            return
        first, second = candidate_anchors
        video_delta = (second['video_position_ms'] - first['video_position_ms']) / 1000.0
        das_first = timeline.absolute_time_for_sample(first['das_sample'])
        das_second = timeline.absolute_time_for_sample(second['das_sample'])
        das_delta = (das_second - das_first).total_seconds()
        if video_delta <= 0 or das_delta <= 0:
            printError('校准锚点必须按时间先后记录，且两次事件不能是同一时刻')
            return
        rate = das_delta / video_delta
        if not 0.9 <= rate <= 1.1:
            printError(f'两点推得的时钟倍率 {rate:.6f} 超出安全范围；请核对是否点中了同一车辆事件')
            return
        offset = (
            (das_first - sync.video_start_time).total_seconds()
            - first['video_position_ms'] / 1000.0 * rate
        )
        self._pushVideoSyncUndo()
        self.video_annotation_project.calibration_anchors = candidate_anchors
        self.video_sync_calibration_anchors = list(candidate_anchors)
        sync.update(sync.video_start_time, offset, rate)
        moved = self.video_annotation_project.reproject_video_annotations(timeline)
        self._markVideoAnnotationDirty()
        self._syncVideoProjectWidgets()
        self.refreshVideoAnnotationTable(select_identifier=self.video_annotation_selected_id)
        self.plotVideoComparisonImage()
        self.video_sync_summary_label.setText(
            f'两点校准已应用：偏移 {offset:+.3f} s，时钟倍率 {rate:.8f}；重新定位 {moved} 条标注。'
        )

    def applyVideoCameraChannel(self):
        if self._annotationTimeline() is None:
            return
        channel_from, channel_to = self._videoChannelBounds()
        channel = min(max(channel_from, int(self.video_camera_channel_spin_box.value())), channel_to)
        self.video_annotation_project.set_camera_channel(channel)
        self._markVideoAnnotationDirty()
        annotation = self.video_annotation_project.annotation_by_identifier(
            self.video_annotation_selected_id
        )
        if annotation is not None:
            self._refreshAnnotationTrajectoryChoices(annotation)
        self.plotVideoComparisonImage()

    def _videoCameraLineMoved(self, line):
        if self.video_das_plot_widget is None or self._annotationTimeline() is None:
            return
        local_channel = float(line.value())
        channel_from, channel_to = self._videoChannelBounds()
        plot_origin = getattr(self, '_video_plot_channel_from', channel_from)
        global_channel = min(
            max(channel_from, int(round(local_channel - 0.5 + plot_origin))),
            channel_to,
        )
        self.video_annotation_project.set_camera_channel(global_channel)
        self.video_camera_channel_spin_box.blockSignals(True)
        try:
            self.video_camera_channel_spin_box.setValue(global_channel)
        finally:
            self.video_camera_channel_spin_box.blockSignals(False)
        self._markVideoAnnotationDirty()
        annotation = self.video_annotation_project.annotation_by_identifier(
            self.video_annotation_selected_id
        )
        if annotation is not None:
            self._refreshAnnotationTrajectoryChoices(annotation)
        self.plotVideoComparisonImage()

    def setVideoCameraVisible(self, visible: bool):
        self.video_annotation_project.camera_visible = bool(visible)
        self._markVideoAnnotationDirty()
        self.plotVideoComparisonImage()

    def setVideoAnnotationsVisible(self, _visible: bool):
        self.plotVideoComparisonImage()

    def applyVideoSync(self):
        """Apply the only editable sync value: video start time."""

        if not self.video_annotation_project.video_path:
            printError('请先选择摄像头视频')
            return
        start_time = self.video_start_time_edit.dateTime().toPyDateTime()
        previous = self._videoSyncSnapshot()
        anchors_changed = bool(self.video_annotation_project.calibration_anchors)
        try:
            changed = self.video_annotation_project.sync.update(
                start_time,
                0.0,
                1.0,
            )
        except ValueError as error:
            printError(str(error))
            return
        if changed or anchors_changed:
            self._video_sync_undo_stack.append(previous)
            self._video_sync_undo_stack = self._video_sync_undo_stack[-20:]
        self.video_annotation_project.calibration_anchors = []
        self.video_sync_calibration_anchors = []
        timeline = self._annotationTimeline()
        moved = self.video_annotation_project.reproject_video_annotations(timeline) if timeline else 0
        if changed or anchors_changed or moved:
            self._markVideoAnnotationDirty()
        self._syncVideoProjectWidgets()
        self.refreshVideoAnnotationTable(select_identifier=self.video_annotation_selected_id)
        self.plotVideoComparisonImage()
        self._updateVideoPlayhead(
            self._currentVideoPosition(),
            force=True,
        )
        self.video_sync_summary_label.setText(
            f'视频开始时间已应用：{format_wall_time(start_time)}；'
            f'重新定位 {moved} 条视频标注。'
        )

    def newVideoAnnotationProject(self):
        if self.video_annotation_dirty and self.video_annotation_project.annotations:
            reply = QMessageBox.question(
                self,
                '新建标注工程',
                '当前标注尚未保存，仍要新建并清空本次会话标签吗？',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self.video_annotation_project = AnnotationProject()
        self.video_annotation_context_matches = self.data_timeline is not None
        self.video_annotation_selected_id = None
        self.video_annotation_interval_start_ms = None
        self.video_annotation_dirty = False
        self._video_sync_undo_stack.clear()
        self._finishVideoSyncPick()
        self._video_trajectory_candidates = {}
        if self.video_player is not None:
            self.video_player.stop()
            self.video_player.setMedia(QtMultimedia.QMediaContent())
        self.video_source_label.setText('未载入摄像头视频')
        self.video_position_slider.setRange(0, 0)
        self.video_time_label.setText('--:--:--.--- / --:--:--.---')
        if self.data_group is not None and self.data_timeline is not None:
            self.updateVideoAnnotationDataContext()
        self._syncVideoProjectWidgets()
        self.refreshVideoAnnotationTable()
        self.plotVideoComparisonImage()

    def openVideoAnnotationProject(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            '打开标注工程',
            '',
            'DAS 视频标注工程 (*.dasannotations.json *.json);;所有文件 (*.*)',
        )
        if not path:
            return
        try:
            project = AnnotationProject.load(path)
        except ValueError as error:
            QMessageBox.warning(self, '打开标注工程失败', str(error))
            return
        self.video_annotation_project = project
        self.video_annotation_dirty = False
        self.video_annotation_selected_id = None
        self.video_annotation_interval_start_ms = None
        self._video_sync_undo_stack.clear()
        self._finishVideoSyncPick()
        matches = self.updateVideoAnnotationDataContext() if self.data_timeline is not None else False
        self._syncVideoProjectWidgets()
        self.refreshVideoAnnotationTable()
        if project.video_path:
            self.loadVideoComparisonFile(project.video_path, update_project=False)
        else:
            self.plotVideoComparisonImage()
        if not matches and project.annotations:
            QMessageBox.warning(
                self,
                'DAS 数据不匹配',
                '该标注工程绑定的 DAS 文件、采样率或采样数与当前导入数据不一致；'
                '为避免错位，标签暂不显示，也不能新增标注。',
            )

    def saveVideoAnnotationProject(self):
        path = self.video_annotation_project.project_path
        if not path:
            default_name = 'video_annotations.dasannotations.json'
            if self.video_annotation_project.video_path:
                stem = os.path.splitext(os.path.basename(self.video_annotation_project.video_path))[0]
                default_name = f'{stem}.dasannotations.json'
            path, _ = QFileDialog.getSaveFileName(
                self,
                '保存标注工程',
                default_name,
                'DAS 视频标注工程 (*.dasannotations.json);;JSON 文件 (*.json)',
            )
        if not path:
            return
        try:
            self.video_annotation_project.save(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, '保存标注工程失败', str(error))
            return
        self.video_annotation_dirty = False
        self._updateVideoProjectLabel()
        self.statusBar().showMessage(f'标注工程已保存：{path}', 6000)

    def exportVideoAnnotationsCsv(self):
        if not self.video_annotation_project.annotations:
            printError('当前没有可导出的标注')
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            '导出标注 CSV',
            'video_annotations.csv',
            'CSV 文件 (*.csv)',
        )
        if not path:
            return
        try:
            self.video_annotation_project.export_csv(path, self._annotationTimeline())
        except OSError as error:
            QMessageBox.warning(self, '导出 CSV 失败', str(error))
            return
        self.statusBar().showMessage(f'已导出 {len(self.video_annotation_project.annotations)} 条标注：{path}', 6000)

    def refreshVideoAnnotationTable(self, select_identifier=None):
        timeline = self._annotationTimeline()
        selected = self.video_annotation_selected_id if select_identifier is None else select_identifier
        # 断开信号连接以避免触发 itemChanged
        self.annotation_table.itemChanged.disconnect(self._videoAnnotationTableItemChanged)
        self.annotation_table.blockSignals(True)
        try:
            annotations = self.video_annotation_project.annotations
            self.annotation_table.setRowCount(len(annotations))
            target_row = -1
            for row, annotation in enumerate(annotations):
                visible = QTableWidgetItem()
                visible.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                visible.setCheckState(Qt.Checked if annotation.visible else Qt.Unchecked)
                visible.setData(Qt.UserRole, annotation.identifier)
                self.annotation_table.setItem(row, 0, visible)
                identifier = QTableWidgetItem(str(annotation.identifier))
                identifier.setData(Qt.UserRole, annotation.identifier)
                self.annotation_table.setItem(row, 1, identifier)
                self.annotation_table.setItem(row, 2, QTableWidgetItem(annotation.kind))
                self.annotation_table.setItem(row, 3, QTableWidgetItem(
                    format_video_position(annotation.start_video_ms)
                    + (f' – {format_video_position(annotation.end_video_ms)}' if annotation.is_interval else '')
                ))
                das_text = ''
                if timeline is not None:
                    das_text = format_wall_time(timeline.absolute_time_for_sample(annotation.start_sample))
                self.annotation_table.setItem(row, 4, QTableWidgetItem(das_text))
                trajectory_text = ''
                if annotation.trajectory_identifier is not None:
                    trajectory_text = f'#{annotation.trajectory_identifier}'
                    if annotation.time_residual_ms is not None:
                        trajectory_text += f'  {annotation.time_residual_ms:+.0f} ms'
                self.annotation_table.setItem(row, 5, QTableWidgetItem(trajectory_text))
                conclusion = QTableWidgetItem(annotation.outcome)
                conclusion.setToolTip(annotation.note or '无备注')
                self.annotation_table.setItem(row, 6, conclusion)
                if annotation.identifier == selected:
                    target_row = row
            if target_row >= 0:
                self.annotation_table.selectRow(target_row)
        finally:
            self.annotation_table.blockSignals(False)
            # 重新连接信号
            self.annotation_table.itemChanged.connect(self._videoAnnotationTableItemChanged)
        self._updateVideoControlEnabledState()

    def _videoAnnotationTableItemChanged(self, item):
        if item.column() != 0:
            return
        identifier_item = self.annotation_table.item(item.row(), 1)
        if identifier_item is None:
            return
        annotation = self.video_annotation_project.annotation_by_identifier(
            identifier_item.data(Qt.UserRole)
        )
        if annotation is None:
            return
        annotation.visible = item.checkState() == Qt.Checked
        self._markVideoAnnotationDirty()
        self.plotVideoComparisonImage()

    def _videoAnnotationTableSelectionChanged(self):
        rows = self.annotation_table.selectionModel().selectedRows()
        if not rows:
            self.video_annotation_selected_id = None
            self._updateVideoControlEnabledState()
            return
        identifier_item = self.annotation_table.item(rows[0].row(), 1)
        if identifier_item is None:
            return
        identifier = identifier_item.data(Qt.UserRole)
        annotation = self.video_annotation_project.annotation_by_identifier(identifier)
        if annotation is None:
            return
        self.video_annotation_selected_id = annotation.identifier
        self.annotation_kind_combo.setCurrentText(annotation.kind)
        self.annotation_outcome_combo.setCurrentText(annotation.outcome)
        self.annotation_note_edit.setText(annotation.note)
        self._refreshAnnotationTrajectoryChoices(annotation)
        if self.video_playback_backend == 'ffmpeg':
            self._seekFfmpegVideo(annotation.start_video_ms, play_continuously=False)
        elif self.video_player is not None:
            self.video_player.pause()
            self.video_player.setPosition(annotation.start_video_ms)
        else:
            self.video_position_slider.setValue(annotation.start_video_ms)
        self._updateVideoPlayhead(annotation.start_video_ms, force=True)
        self._updateVideoControlEnabledState()

    def _refreshAnnotationTrajectoryChoices(self, annotation):
        self.annotation_trajectory_combo.blockSignals(True)
        try:
            self.annotation_trajectory_combo.clear()
            self.annotation_trajectory_combo.addItem('不关联轨迹', None)
            self._video_trajectory_candidates = {}
            timeline = self._annotationTimeline()
            if timeline is not None:
                candidates = trajectory_candidates(
                    self._activeVideoTrajectories(),
                    self.video_annotation_project.camera_channel,
                    annotation.start_sample / timeline.sampling_rate,
                    self.annotation_trajectory_tolerance_spin_box.value(),
                )
                for candidate in candidates:
                    self._video_trajectory_candidates[candidate.identifier] = candidate
                    self.annotation_trajectory_combo.addItem(
                        f'轨迹 #{candidate.identifier} · {candidate.direction} · '
                        f'可信 {candidate.confidence:.0%} · Δ {candidate.residual_ms:+.1f} ms',
                        candidate.identifier,
                    )
            if annotation.trajectory_identifier is not None:
                index = self.annotation_trajectory_combo.findData(annotation.trajectory_identifier)
                if index < 0:
                    self.annotation_trajectory_combo.addItem(
                        f'轨迹 #{annotation.trajectory_identifier}（已关联，当前不在候选窗）',
                        annotation.trajectory_identifier,
                    )
                    index = self.annotation_trajectory_combo.count() - 1
                self.annotation_trajectory_combo.setCurrentIndex(index)
            else:
                self.annotation_trajectory_combo.setCurrentIndex(0)
        finally:
            self.annotation_trajectory_combo.blockSignals(False)

    def _currentVideoPosition(self):
        if self.video_playback_backend == 'ffmpeg':
            return self.video_ffmpeg_position_ms
        return self.video_player.position() if self.video_player is not None else self.video_position_slider.value()

    def _addVideoAnnotation(self, start_ms: int, end_ms=None):
        timeline = self._annotationTimeline()
        if timeline is None:
            printError('请先导入与标注工程匹配的 DAS 数据')
            return None
        try:
            annotation = self.video_annotation_project.add_video_annotation(
                timeline,
                self.annotation_kind_combo.currentText(),
                self.annotation_outcome_combo.currentText(),
                start_ms,
                self.video_annotation_project.camera_channel,
                end_video_ms=end_ms,
                note=self.annotation_note_edit.text(),
            )
        except ValueError as error:
            printError(str(error))
            return None
        self.video_annotation_selected_id = annotation.identifier
        self._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable(select_identifier=annotation.identifier)
        self._refreshAnnotationTrajectoryChoices(annotation)
        self.plotVideoComparisonImage()
        self.statusBar().showMessage(
            f'已添加标注 #{annotation.identifier}：{annotation.kind}。可在左侧关联候选轨迹。',
            6000,
        )
        return annotation

    def _cancelPendingIntervalAnnotation(self):
        """清除正在进行的区间标注状态（上下文变化或用户取消时调用）"""
        if self.video_annotation_interval_start_ms is not None:
            self.video_annotation_interval_start_ms = None
            if hasattr(self, 'annotation_interval_label'):
                self.annotation_interval_label.setText('未开始区间标注')
            if hasattr(self, 'annotation_interval_finish_button'):
                self._updateVideoControlEnabledState()

    def addVideoPointAnnotation(self):
        self._addVideoAnnotation(self._currentVideoPosition())

    def beginVideoIntervalAnnotation(self):
        if self._annotationTimeline() is None:
            printError('请先完成视频与 DAS 的对时')
            return
        self.video_annotation_interval_start_ms = self._currentVideoPosition()
        self.annotation_interval_label.setText(
            f'区间起点：{format_video_position(self.video_annotation_interval_start_ms)}'
        )
        self._updateVideoControlEnabledState()

    def finishVideoIntervalAnnotation(self):
        if self.video_annotation_interval_start_ms is None:
            return
        # 验证上下文仍然有效
        if self._annotationTimeline() is None:
            printError('DAS 数据上下文已失效，区间标注已取消')
            self._cancelPendingIntervalAnnotation()
            return
        start = self.video_annotation_interval_start_ms
        end = self._currentVideoPosition()
        annotation = self._addVideoAnnotation(start, end)
        if annotation is not None:
            self.video_annotation_interval_start_ms = None
            self.annotation_interval_label.setText('未开始区间标注')
            self._updateVideoControlEnabledState()

    def updateSelectedVideoAnnotation(self):
        annotation = self.video_annotation_project.annotation_by_identifier(self.video_annotation_selected_id)
        if annotation is None:
            printError('请先在标注列表中选择一条记录')
            return
        annotation.kind = self.annotation_kind_combo.currentText().strip() or annotation.kind
        annotation.outcome = self.annotation_outcome_combo.currentText().strip() or annotation.outcome
        annotation.note = self.annotation_note_edit.text().strip()
        selected_trajectory = self.annotation_trajectory_combo.currentData()
        try:
            selected_trajectory = int(selected_trajectory) if selected_trajectory is not None else None
        except (TypeError, ValueError):
            selected_trajectory = None
        annotation.trajectory_identifier = selected_trajectory
        annotation.time_residual_ms = None
        if selected_trajectory is not None:
            trajectory = next(
                (item for item in self._activeVideoTrajectories() if item.identifier == selected_trajectory),
                None,
            )
            crossing = trajectory_crossing_time(
                trajectory, self.video_annotation_project.camera_channel
            ) if trajectory else None
            if crossing is not None:
                timeline = self._annotationTimeline()
                sampling_rate = timeline.sampling_rate if timeline is not None else self.sampling_rate
                annotation.time_residual_ms = (
                    crossing - annotation.start_sample / sampling_rate
                ) * 1000.0
        self._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable(select_identifier=annotation.identifier)
        self.plotVideoComparisonImage()

    def deleteSelectedVideoAnnotation(self):
        if self.video_annotation_selected_id is None:
            return
        removed = self.video_annotation_project.delete_annotation(self.video_annotation_selected_id)
        if removed is None:
            return
        self.video_annotation_selected_id = None
        self._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable()
        self.plotVideoComparisonImage()
        self.statusBar().showMessage(f'已删除标注 #{removed.identifier}。', 5000)

    def undoLastVideoAnnotation(self):
        if not self.video_annotation_project.annotations:
            return
        removed = self.video_annotation_project.annotations.pop()
        self.video_annotation_selected_id = None
        self._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable()
        self.plotVideoComparisonImage()
        self.statusBar().showMessage(f'已撤销最后一条标注 #{removed.identifier}。', 5000)

    def initLocalParams(self):
        """
        初始化局部参数，即适用于单个文件，重新选择文件后更新
        Returns:

        """
        # 播放器默认状态
        self.player = None  # 播放器
        self.playerState = False  # 播放器否在播放
        self.hasWavFile = False  # 当前通道是否已创建了音频文件

        # 数据范围
        self.channel_from_num = 1
        self.channel_to_num = self.channels_num
        self.sampling_times_from_num = 1
        self.sampling_times_to_num = self.sampling_times
        self.event_range_start_sample = 0
        self.event_range_end_sample = self.sampling_times
        self.multi_waves_reset_pending = True

    # """------------------------------------------------------------------------------------------------------------"""
    """继承mainwindow自带函数"""

    def closeEvent(self, event: QEvent):
        """
        退出时的提示
        Args:
            event: 事件

        Returns:

        """
        if self.das_filter_dialog is not None and self.das_filter_dialog.is_busy():
            QMessageBox.warning(self, '滤波处理中', '请等待滤波链计算完成后再退出。')
            event.ignore()
            return
        reply = QMessageBox.question(self, '提示', '是否退出？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        # 判断返回值，如果点击的是Yes按钮，我们就关闭组件和应用，否则就忽略关闭事件
        if reply == QMessageBox.Yes:
            self.video_trajectory_poll_timer.stop()
            self.video_media_poll_timer.stop()
            self.video_trajectory_executor.shutdown(wait=False, cancel_futures=True)
            self.video_media_executor.shutdown(wait=False, cancel_futures=True)
            event.accept()
        else:
            event.ignore()

    def keyPressEvent(self, event):
        """Expose visible video-label shortcuts without hijacking text editors."""

        focus = QApplication.focusWidget()
        if focus is not None and any(
                focus.inherits(name)
                for name in ('QLineEdit', 'QAbstractSpinBox', 'QComboBox', 'QTableWidget')
        ):
            super().keyPressEvent(event)
            return
        if hasattr(self, 'tab_widget') and self.tab_widget.currentWidget() is self.video_compare_container:
            key = event.key()
            if key == Qt.Key_F11:
                self.video_focus_button.toggle()
                event.accept()
                return
            if key == Qt.Key_Escape and self._video_focus_mode:
                self.video_focus_button.setChecked(False)
                event.accept()
                return
            if key == Qt.Key_Space:
                self.toggleVideoPlayback()
                event.accept()
                return
            if key == Qt.Key_T:
                self.addVideoPointAnnotation()
                event.accept()
                return
            if key == Qt.Key_I:
                self.beginVideoIntervalAnnotation()
                event.accept()
                return
            if key == Qt.Key_O:
                self.finishVideoIntervalAnnotation()
                event.accept()
                return
        super().keyPressEvent(event)

    def removeTab(self, index: int):
        """
        关闭对应选项卡
        Args:
            index: 选项卡索引

        Returns:

        """
        self.tab_widget.removeTab(index)

    # """------------------------------------------------------------------------------------------------------------"""
    """播放当前文件调用的函数"""

    def playBtnChangeState(self):
        """
        点击播放按钮改变文字和播放器状态
        Returns:

        """
        if not self.playerState:
            setPicture(self.player_play_button, pause_jpg, 'pause.jpg')
            self.player.play()
            self.playerState = True
        else:
            setPicture(self.player_play_button, play_jpg, 'play.jpg')
            self.player.pause()
            self.playerState = False

    def createWavFile(self):
        """
        创建当前数据的 wav 文件，储存在当前文件夹路径下
        Returns:

        """
        if not self.hasWavFile:
            data = np.array(self.data[self.channel_number - 1])  # 不转array会在重复转换数据类型时发生数据类型错误
            writeWav(self.file_path, data, self.sampling_rate)
            self.hasWavFile = True

    def createPlayer(self):
        """
        创建播放器并赋数据
        Returns:

        """
        if not self.player:
            self.player = QtMultimedia.QMediaPlayer()
            self.player.stateChanged.connect(self.playerStateChanged)
            self.player.setMedia(
                QtMultimedia.QMediaContent(QUrl.fromLocalFile(os.path.join(self.file_path, 'temp.wav'))))

    def playerStateChanged(self, state: QtMultimedia.QMediaPlayer.State):
        """
        播放器停止后删除文件
        Args:
            state: 播放器状态

        Returns:

        """
        if state == QtMultimedia.QMediaPlayer.StoppedState:
            self.resetPlayer()
            os.remove(os.path.join(self.file_path, 'temp.wav'))  # 在播放完成或点击Abort后删除临时文件

    def resetPlayer(self):
        """
        重置播放器
        Returns:

        """
        self.player.stop()
        setPicture(self.player_play_button, play_jpg, 'play.jpg')
        self.playerState = False
        self.hasWavFile = False

    # """------------------------------------------------------------------------------------------------------------"""
    """主绘图区"""

    def plotGrayScaleImage(self):
        """
        绘制灰度图
        Returns:

        """
        self.speed_ruler_roi = None
        self.plot_gray_scale_widget.clear()
        self.plot_gray_scale_widget.setTimeOrigin(
            self.data_timeline.start_time if self.data_timeline is not None else None
        )
        title = '灰度图' if self.image_colormap == '灰度' else f'彩色图 - {self.image_colormap}'
        # The active workspace tab already identifies this view.  Leaving the
        # canvas title empty prevents the same label appearing three times and
        # returns useful vertical space to the data image.
        self.plot_gray_scale_widget.setTitle('')
        self.tab_widget.setTabText(0, title)

        item = pg.ImageItem()
        self.addDataImageItem(self.plot_gray_scale_widget, item, self.data, use_image_controls=True,
                              show_color_bar=True)
        self.drawFileBoundaries(self.plot_gray_scale_widget, 0, self.current_channels)
        self.drawVehicleTrajectories()
        self.drawEventRange(self.plot_gray_scale_widget)
        self.drawSpeedRuler()

    def drawFileBoundaries(self, plot_widget, y_min: float, y_max: float):
        """Draw one clickable source strip per file plus dashed seam lines."""

        if self.data_group is None or len(self.data_group.segments) <= 1:
            plot_widget._file_segment_visuals = []
            return
        visible_start = (self.sampling_times_from_num - 1) / self.sampling_rate
        visible_end = self.sampling_times_to_num / self.sampling_rate
        strip_height = max((float(y_max) - float(y_min)) * 0.075, 0.1)
        strip_y = float(y_max) - strip_height
        visuals = []

        for index, segment in enumerate(self.data_group.segments):
            segment_start = segment.start_sample / self.sampling_rate
            segment_end = segment.end_sample / self.sampling_rate
            if segment_end <= visible_start or segment_start >= visible_end:
                continue

            detail = self.fileSegmentDetails(index)
            bar = FileSegmentBarItem(
                QRectF(segment_start, strip_y, segment_end - segment_start, strip_height),
                index,
                self.selectFileSegment,
            )
            bar.setToolTip(detail)
            plot_widget.addItem(bar)

            label = pg.TextItem(str(index + 1), color='#5b21b6', anchor=(0.5, 0.5))
            label.setZValue(21)
            label.setAcceptedMouseButtons(Qt.NoButton)
            label.setPos((segment_start + segment_end) / 2, strip_y + strip_height / 2)
            label.setToolTip(detail)
            plot_widget.addItem(label)
            visuals.append({
                'index': index,
                'start': segment_start,
                'end': segment_end,
                'label_y': strip_y + strip_height / 2,
                'bar': bar,
                'label': label,
            })

            if index > 0 and visible_start < segment_start < visible_end:
                previous = self.data_group.segments[index - 1]
                line = pg.InfiniteLine(
                    pos=segment_start,
                    angle=90,
                    movable=False,
                    pen=pg.mkPen('#7b2cbf', width=1.5, style=Qt.DashLine),
                )
                line.setZValue(19)
                line.setToolTip(
                    f'文件接缝：{previous.name} → {segment.name}\n'
                    f'全局采样点：{segment.start_sample + 1}'
                )
                plot_widget.addItem(line)

        plot_widget._file_segment_visuals = visuals
        self._registerFileSegmentPlot(plot_widget)
        self.updateFileSegmentLabels(plot_widget)
        self._refreshFileSegmentHighlights()
        QTimer.singleShot(0, lambda widget=plot_widget: self.updateFileSegmentLabels(widget))

    @staticmethod
    def _formatRelativeSeconds(value: float) -> str:
        return f'{float(value):.6f}'.rstrip('0').rstrip('.') or '0'

    @staticmethod
    def _fileNameClock(name: str):
        """Extract HH:MM:SS from the common DAS datetime filename pattern."""

        match = re.search(
            r'(?:19|20)\d{2}[-_]\d{1,2}[-_]\d{1,2}[-_]'
            r'(\d{1,2})[-_](\d{1,2})[-_](\d{1,2})(?:[-_.]|$)',
            os.path.basename(str(name)),
        )
        if match is None:
            return None
        return ':'.join(f'{int(part):02d}' for part in match.groups())

    def fileSegmentLabel(self, index: int, pixel_width: float) -> str:
        """Return a collision-resistant label for a source strip."""

        if self.data_group is None or not (0 <= index < len(self.data_group.segments)):
            return ''
        sequence = str(index + 1)
        if pixel_width < 58:
            return sequence
        segment = self.data_group.segments[index]
        clock = self._fileNameClock(segment.name)
        if clock:
            return f'{sequence}  {clock}'
        if pixel_width >= 180:
            maximum = max(8, int(pixel_width // 8) - len(sequence) - 2)
            name = segment.name
            if len(name) > maximum:
                name = f'{name[:maximum - 1]}…'
            return f'{sequence}  {name}'
        return sequence

    def fileSegmentDetails(self, index: int) -> str:
        """Build the path, sample range and corrected time details."""

        if self.data_group is None or not (0 <= index < len(self.data_group.segments)):
            return ''
        segment = self.data_group.segments[index]
        sampling_rate = float(self.data_group.sampling_rate)
        start_time = segment.start_sample / sampling_rate
        end_time = segment.end_sample / sampling_rate
        duration = segment.sample_count / sampling_rate
        lines = [
            f'第 {index + 1}/{len(self.data_group.segments)} 段\n'
            f'文件：{segment.name}\n'
            f'完整路径：{segment.path}\n'
            f'全局采样范围：{segment.start_sample + 1} - {segment.end_sample} '
            f'（{segment.sample_count} 点）\n'
            f'起止相对时间：{self._formatRelativeSeconds(start_time)} - '
            f'{self._formatRelativeSeconds(end_time)} s\n'
            f'时长：{self._formatRelativeSeconds(duration)} s'
        ]
        if self.data_timeline is not None and index < len(self.data_timeline.segments):
            timeline_segment = self.data_timeline.segments[index]
            source_name = '文件名' if timeline_segment.timestamp_source == 'filename' else '文件头'
            lines.append(
                f'\n记录结束时间（{source_name}）：{format_wall_time(timeline_segment.recorded_end)}'
                f'\n修正后记录结束：{format_wall_time(timeline_segment.corrected_recorded_end)}'
                f'\n连续推算范围：{format_wall_time(timeline_segment.inferred_start)} - '
                f'{format_wall_time(timeline_segment.inferred_end)}'
            )
            if index > 0:
                lines.append(
                    f'\n记录与连续推算偏差：'
                    f'{timeline_segment.end_time_difference_seconds:+.3f} s'
                )
        return ''.join(lines)

    def updateStitchedFilesList(self):
        """Refresh the left-side source list in exact stitching order."""

        if not hasattr(self, 'stitched_files_list'):
            return
        self._refreshing_stitched_files = True
        try:
            self.stitched_files_list.clear()
            segments = self.data_group.segments if self.data_group is not None else []
            self.stitched_files_group.setTitle(f'当前拼接文件（{len(segments)}）')
            digits = max(2, len(str(len(segments))))
            for index, segment in enumerate(segments):
                warning = False
                if self.data_timeline is not None and index < len(self.data_timeline.segments) and index > 0:
                    difference = self.data_timeline.segments[index].end_time_difference_seconds
                    warning = abs(difference) > self.data_timeline.continuity_tolerance_seconds
                prefix = '⚠ ' if warning else ''
                item = QListWidgetItem(f'{prefix}{index + 1:0{digits}d}  {segment.name}')
                item.setData(Qt.UserRole, index)
                item.setToolTip(self.fileSegmentDetails(index))
                self.stitched_files_list.addItem(item)
            if self.selected_file_segment_index is not None and \
                    self.selected_file_segment_index < len(segments):
                self.stitched_files_list.setCurrentRow(self.selected_file_segment_index)
            else:
                self.stitched_files_list.setCurrentRow(-1)
        finally:
            self._refreshing_stitched_files = False

    def _stitchedFileRowChanged(self, index: int):
        if not self._refreshing_stitched_files and index >= 0:
            self.selectFileSegment(index)

    def selectFileSegment(self, index: int):
        """Synchronize segment selection between the source list and all plots."""

        if self.data_group is None or not (0 <= int(index) < len(self.data_group.segments)):
            return
        self.selected_file_segment_index = int(index)
        if hasattr(self, 'stitched_files_list') and self.stitched_files_list.currentRow() != int(index):
            self._refreshing_stitched_files = True
            try:
                self.stitched_files_list.setCurrentRow(int(index))
            finally:
                self._refreshing_stitched_files = False
        self._refreshFileSegmentHighlights()
        self.statusBar().showMessage(self.fileSegmentDetails(int(index)).replace('\n', '  |  '))

    def _registerFileSegmentPlot(self, plot_widget):
        if plot_widget not in self._file_segment_plot_widgets:
            self._file_segment_plot_widgets.append(plot_widget)
        if getattr(plot_widget, '_file_segment_range_tracking', False):
            return
        plot_widget._file_segment_range_tracking = True
        plot_widget.getViewBox().sigXRangeChanged.connect(
            lambda *_args, widget=plot_widget: self.updateFileSegmentLabels(widget)
        )

    def updateFileSegmentLabels(self, plot_widget):
        """Reposition and shorten strip labels after zooming or resizing."""

        visuals = getattr(plot_widget, '_file_segment_visuals', [])
        if not visuals:
            return
        try:
            view_box = plot_widget.getViewBox()
            view_start, view_end = view_box.viewRange()[0]
            view_width = max(float(view_end) - float(view_start), 1e-12)
            pixel_scale = max(float(view_box.width()), 1.0) / view_width
            for visual in visuals:
                clipped_start = max(float(visual['start']), float(view_start))
                clipped_end = min(float(visual['end']), float(view_end))
                is_visible = clipped_end > clipped_start
                visual['label'].setVisible(is_visible)
                if not is_visible:
                    continue
                pixel_width = (clipped_end - clipped_start) * pixel_scale
                visual['label'].setText(self.fileSegmentLabel(visual['index'], pixel_width))
                visual['label'].setPos(
                    (clipped_start + clipped_end) / 2,
                    visual['label_y'],
                )
        except RuntimeError:
            return

    def _refreshFileSegmentHighlights(self):
        selected = self.selected_file_segment_index
        live_widgets = []
        for plot_widget in self._file_segment_plot_widgets:
            try:
                visuals = getattr(plot_widget, '_file_segment_visuals', [])
                for visual in visuals:
                    is_selected = visual['index'] == selected
                    color = QColor(245, 158, 11, 112) if is_selected else QColor(124, 58, 237, 60)
                    outline = QColor('#d97706') if is_selected else QColor(124, 58, 237, 120)
                    pen = QPen(outline, 1.5 if is_selected else 0.8)
                    pen.setCosmetic(True)
                    visual['bar'].setBrush(QBrush(color))
                    visual['bar'].setPen(pen)
                    visual['label'].setColor('#92400e' if is_selected else '#5b21b6')
                live_widgets.append(plot_widget)
            except RuntimeError:
                continue
        self._file_segment_plot_widgets = live_widgets

    def setEventRangeControlsEnabled(self, enabled: bool):
        for widget in (
            self.event_range_from_edit,
            self.event_range_to_edit,
            self.event_range_set_button,
            self.event_range_view_button,
            self.event_range_reset_button,
            self.event_markers_visible_checkbox,
        ):
            widget.setEnabled(bool(enabled))

    def updateEventRangeEditors(self):
        """Synchronize corrected wall times into the event-range controls."""

        if self.data_timeline is None or not hasattr(self, 'event_range_start_sample'):
            self.setEventRangeControlsEnabled(False)
            return
        self.setEventRangeControlsEnabled(True)
        minimum = QDateTime(self.data_timeline.start_time)
        maximum = QDateTime(self.data_timeline.end_time)
        self._syncing_event_range = True
        try:
            for editor in (self.event_range_from_edit, self.event_range_to_edit):
                editor.setDateTimeRange(minimum, maximum)
            self.event_range_from_edit.setDateTime(QDateTime(
                self.data_timeline.absolute_time_for_sample(self.event_range_start_sample)
            ))
            self.event_range_to_edit.setDateTime(QDateTime(
                self.data_timeline.absolute_time_for_sample(self.event_range_end_sample)
            ))
        finally:
            self._syncing_event_range = False

    def setEventRangeFromInputs(self):
        """Move the event markers from corrected absolute-time inputs."""

        if self.data_timeline is None:
            return
        start = self.data_timeline.sample_boundary_for_time(
            self.event_range_from_edit.dateTime().toPyDateTime()
        )
        end = self.data_timeline.sample_boundary_for_time(
            self.event_range_to_edit.dateTime().toPyDateTime()
        )
        self.setEventSampleRange(start, end, show_status=True)

    def setEventSampleRange(self, start: int, end: int, show_status: bool = False):
        """Set a clamped non-empty event interval in zero-based sample boundaries."""

        if not hasattr(self, 'sampling_times') or self.sampling_times <= 0:
            return
        start = min(max(int(start), 0), self.sampling_times)
        end = min(max(int(end), 0), self.sampling_times)
        if start > end:
            start, end = end, start
        if start == end:
            if end < self.sampling_times:
                end += 1
            else:
                start = max(0, start - 1)
        self.event_range_start_sample = start
        self.event_range_end_sample = end
        self.updateEventRangeEditors()
        self._syncEventRangePlots()
        if show_status and self.data_timeline is not None:
            start_text = format_wall_time(self.data_timeline.absolute_time_for_sample(start))
            end_text = format_wall_time(self.data_timeline.absolute_time_for_sample(end))
            self.statusBar().showMessage(
                f'事件范围：{start_text} - {end_text}  |  '
                f'采样边界：{start} - {end}  |  时长 {(end - start) / self.sampling_rate:.3f} s',
                8000,
            )

    def _eventRangeMoved(self, region):
        if self._syncing_event_range:
            return
        start_seconds, end_seconds = sorted(map(float, region.getRegion()))
        self.setEventSampleRange(
            round(start_seconds * self.sampling_rate),
            round(end_seconds * self.sampling_rate),
            show_status=True,
        )

    def _eventLineText(self, sample_boundary: int, prefix: str) -> str:
        if self.data_timeline is None:
            return prefix
        value = self.data_timeline.absolute_time_for_sample(sample_boundary)
        return f'{prefix} {value.strftime("%H:%M:%S.%f")[:-3]}'

    def setEventMarkersVisible(self, visible: bool):
        """Show or hide only the event overlay, without changing the data view."""

        self.show_event_markers = bool(visible)
        live_widgets = []
        for plot_widget in list(self._event_range_plot_widgets):
            try:
                visual = getattr(plot_widget, '_event_range_visual', None)
                if visual is not None:
                    plot_widget.removeItem(visual['region'])
                plot_widget._event_range_visual = None
                if self.show_event_markers and self.data_timeline is not None and \
                        hasattr(self, 'event_range_start_sample'):
                    self.drawEventRange(plot_widget)
                live_widgets.append(plot_widget)
            except RuntimeError:
                continue
        self._event_range_plot_widgets = live_widgets

    def drawEventRange(self, plot_widget):
        """Draw two synchronized draggable time markers without obscuring the data."""

        if not getattr(self, 'show_event_markers', True) or \
                self.data_timeline is None or not hasattr(self, 'event_range_start_sample'):
            plot_widget._event_range_visual = None
            return
        start_seconds = self.event_range_start_sample / self.sampling_rate
        end_seconds = self.event_range_end_sample / self.sampling_rate
        region = pg.LinearRegionItem(
            values=(start_seconds, end_seconds),
            orientation=pg.LinearRegionItem.Vertical,
            brush=pg.mkBrush(0, 0, 0, 0),
            hoverBrush=pg.mkBrush(0, 0, 0, 0),
            movable=True,
            bounds=(0.0, self.sampling_times / self.sampling_rate),
            swapMode='sort',
        )
        # File strips occupy layers 19-21.  Keep event markers and their
        # labels higher so the end marker remains readable at the top edge.
        region.setZValue(30)
        start_pen = pg.mkPen('#16a34a', width=3)
        end_pen = pg.mkPen('#dc2626', width=3)
        region.lines[0].setPen(start_pen)
        region.lines[0].setHoverPen(pg.mkPen('#4ade80', width=5))
        region.lines[1].setPen(end_pen)
        region.lines[1].setHoverPen(pg.mkPen('#fb7185', width=5))
        start_label = pg.InfLineLabel(
            region.lines[0],
            text=self._eventLineText(self.event_range_start_sample, '开始'),
            position=0.86,
            color='#166534',
            fill=pg.mkBrush(255, 255, 255, 205),
            movable=True,
        )
        end_label = pg.InfLineLabel(
            region.lines[1],
            text=self._eventLineText(self.event_range_end_sample, '结束'),
            position=0.72,
            color='#991b1b',
            fill=pg.mkBrush(255, 255, 255, 205),
            movable=True,
        )
        start_label.setZValue(1)
        end_label.setZValue(1)
        region.sigRegionChangeFinished.connect(lambda item=region: self._eventRangeMoved(item))
        plot_widget.addItem(region)
        plot_widget._event_range_visual = {
            'region': region,
            'start_label': start_label,
            'end_label': end_label,
        }
        if plot_widget not in self._event_range_plot_widgets:
            self._event_range_plot_widgets.append(plot_widget)

    def _syncEventRangePlots(self):
        if not hasattr(self, 'event_range_start_sample'):
            return
        start_seconds = self.event_range_start_sample / self.sampling_rate
        end_seconds = self.event_range_end_sample / self.sampling_rate
        self._syncing_event_range = True
        live_widgets = []
        try:
            for plot_widget in self._event_range_plot_widgets:
                try:
                    visual = getattr(plot_widget, '_event_range_visual', None)
                    if visual is not None:
                        visual['region'].setRegion((start_seconds, end_seconds))
                        visual['start_label'].setText(
                            self._eventLineText(self.event_range_start_sample, '开始')
                        )
                        visual['end_label'].setText(
                            self._eventLineText(self.event_range_end_sample, '结束')
                        )
                    live_widgets.append(plot_widget)
                except RuntimeError:
                    continue
        finally:
            self._syncing_event_range = False
        self._event_range_plot_widgets = live_widgets

    def viewEventRange(self):
        """Apply the marker range as the current non-destructive data view."""

        self.setEventRangeFromInputs()
        self.sampling_times_from_num = self.event_range_start_sample + 1
        self.sampling_times_to_num = self.event_range_end_sample
        self.updateDataRange()
        self.updateDataParams()
        self.updateDataGPSTime()
        self.updateImages()
        self.syncDASFilterVisibleRange()

    def restoreFullEventRange(self):
        if not hasattr(self, 'sampling_times'):
            return
        self.setEventSampleRange(0, self.sampling_times)
        self.sampling_times_from_num = 1
        self.sampling_times_to_num = self.sampling_times
        self.updateDataRange()
        self.updateDataParams()
        self.updateDataGPSTime()
        self.updateImages()
        self.syncDASFilterVisibleRange()

    def addDataImageItem(self,
                         plot_widget: MyPlotWidget,
                         item: pg.ImageItem,
                         data: np.array,
                         use_image_controls: bool = False,
                         show_color_bar: bool = False) -> None:
        """
        按当前数据的实际时间长度和通道数绘制二维图，避免自动坐标轴范围过大。
        """
        start_time = (self.sampling_times_from_num - 1) / self.sampling_rate
        duration = self.current_sampling_times / self.sampling_rate
        channel_count = self.current_channels

        levels = self.imageLevels(data) if use_image_controls else None
        color_map = self.imageColorMap() if use_image_controls else None

        item.setImage(data.T, autoLevels=levels is None)
        if levels is not None:
            item.setLevels(levels)
        if color_map is not None:
            item.setColorMap(color_map)
        item.setRect(QRectF(start_time, 0, duration, channel_count))
        plot_widget.addItem(item)
        self.updateGrayScaleColorBar(plot_widget, item, color_map, levels, show_color_bar)

        view_box = plot_widget.getViewBox()
        view_box.setLimits(xMin=start_time, xMax=start_time + duration, yMin=0, yMax=channel_count)
        view_box.setRange(xRange=(start_time, start_time + duration), yRange=(0, channel_count), padding=0)

    def drawVehicleTrajectories(self, plot_widget=None, full_range: bool = False):
        """Draw stored vehicle paths in an image plot's local coordinates."""
        if self._hide_vehicle_trajectories or not self.vehicle_trajectories:
            return
        if not hasattr(self, 'sampling_times_from_num') or not hasattr(self, 'channel_from_num'):
            return
        plot_widget = plot_widget or self.plot_gray_scale_widget

        if full_range:
            start_time = 0.0
            end_time = self.sampling_times / self.sampling_rate
            channel_from = 1
            channel_to = self.channels_num
        else:
            start_time = (self.sampling_times_from_num - 1) / self.sampling_rate
            end_time = self.sampling_times_to_num / self.sampling_rate
            channel_from = self.channel_from_num
            channel_to = self.channel_to_num
        colors = ('#e6194B', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#42d4f4', '#f032e6', '#bfef45')

        for trajectory in self.vehicle_trajectories:
            if not getattr(trajectory, 'visible', True):
                continue
            channels = np.asarray(trajectory.channels)
            times = np.asarray(trajectory.times)
            visible = (
                (channels >= channel_from)
                & (channels <= channel_to)
                & (times >= start_time)
                & (times <= end_time)
            )
            if np.count_nonzero(visible) < 2:
                continue
            color = colors[(int(trajectory.identifier) - 1) % len(colors)]
            local_channels = channels[visible] - channel_from + 0.5
            plot_widget.plot(
                times[visible],
                local_channels,
                pen=pg.mkPen(color=color, width=2),
                connect='finite',
            )
            label = pg.TextItem(str(trajectory.identifier), color=color, anchor=(0, 1))
            label.setPos(float(times[visible][0]), float(local_channels[0]))
            plot_widget.addItem(label)

    @staticmethod
    def _defaultEventFilterPipeline(channel_count: int, sample_count: int):
        """Return the shared full-resolution vehicle-event filter preset."""

        selection = (1, max(1, int(channel_count)), 1, max(1, int(sample_count)))
        return [
            FilterStep(
                'bandpass',
                {
                    'frequency_low': 0.01,
                    'frequency_high': 1.0,
                    'order': 4,
                    'zero_phase': True,
                },
                selection,
                '带通滤波',
            ),
            FilterStep(
                'common_mode',
                {'method': 'median'},
                selection,
                '共模噪声去除',
            ),
            FilterStep(
                'mad_normalize',
                {},
                selection,
                '各通道 MAD 归一化',
            ),
        ]

    @staticmethod
    def _defaultVideoFilterPipeline(channel_count: int, sample_count: int):
        """Compatibility wrapper for the shared default event filter chain."""

        return MainWindow._defaultEventFilterPipeline(channel_count, sample_count)

    def _ensureDefaultVideoFilterPipeline(self, channel_count: int, sample_count: int):
        if self._video_filter_customized:
            return
        self._video_filter_steps = self._defaultVideoFilterPipeline(
            channel_count, sample_count
        )
        self._updateVideoFilterSummary()

    def _videoTrajectoryParameters(self):
        """Return window display settings and optional trajectory geometry."""
        dx = float(self.video_trajectory_dx_spin_box.value())
        parameters = dict(self._vehicle_tracking_settings or {})
        data_group, _timeline = self._videoDataContext()
        data_channel_count = int(data_group.channel_count) if data_group is not None else 0
        detect_trajectories = dx > 0 and data_channel_count >= 8
        display_steps = [
            {
                'algorithm': step.algorithm,
                'parameters': dict(step.parameters),
                'selection': tuple(step.selection),
                'processing_mode': step.processing_mode,
                'label': step.label,
                'enabled': bool(step.enabled),
            }
            for step in self._video_filter_steps
        ]
        display_choice = (
            self.video_display_mode_combo.currentData()
            if hasattr(self, 'video_display_mode_combo') else 'enhanced'
        )
        display_mode = 'raw' if display_choice == 'raw' else 'current'
        parameters.update({
            'channel_spacing': dx if dx > 0 else 4.0,
            'frequency_low': parameters.get('frequency_low', 0.01),
            'frequency_high': parameters.get('frequency_high', 1.0),
            'target_sampling_rate': parameters.get('target_sampling_rate', 50.0),
            'seed_width': parameters.get('seed_width', 8),
            'peak_prominence': parameters.get('peak_prominence', 1.5),
            'minimum_separation': parameters.get('minimum_separation', 0.8),
            'prominence_window': parameters.get('prominence_window', 12.0),
            'minimum_speed': parameters.get('minimum_speed', 2.0),
            'maximum_speed': parameters.get('maximum_speed', 60.0),
            'tracking_tolerance': parameters.get('tracking_tolerance', 0.15),
            'minimum_coverage': parameters.get('minimum_coverage', 0.55),
            'maximum_missed_channels': parameters.get('maximum_missed_channels', 3),
            'direction': parameters.get('direction', 'auto'),
            'polarity': parameters.get('polarity', 'auto'),
            'common_mode_method': 'median',
            'display_mode': display_mode,
            'display_filter_steps': display_steps,
            'detect_trajectories': detect_trajectories,
        })
        return parameters

    def _videoFilterSummary(self) -> str:
        if (
            hasattr(self, 'video_display_mode_combo')
            and self.video_display_mode_combo.currentData() == 'raw'
        ):
            return '原始去趋势'
        if not self._video_filter_customized:
            return '车辆事件增强'
        enabled = [step for step in self._video_filter_steps if step.enabled]
        if not enabled:
            return '原始去趋势'
        return f'{len(enabled)} 步滤波'

    def _updateVideoFilterSummary(self):
        if not hasattr(self, 'video_filter_summary_label'):
            return
        summary = self._videoFilterSummary()
        labels = [step.label for step in self._video_filter_steps if step.enabled]
        self.video_filter_summary_label.setText(summary)
        if not self._video_filter_customized:
            detail = '带通 0.01–1 Hz → 中位数共模抑制 → MAD 归一化；仅影响显示与轨迹分析'
        else:
            detail = ' → '.join(labels) if labels else '当前窗口显示原始去趋势数据'
        self.video_filter_summary_label.setToolTip(detail)

    def _videoVisibleWindowSeconds(self) -> float:
        if hasattr(self, 'video_window_combo'):
            try:
                return max(1.0, float(self.video_window_combo.currentData()))
            except (TypeError, ValueError):
                pass
        return VIDEO_FOLLOW_WINDOW_SECONDS

    def _videoDisplayModeChanged(self, _index: int):
        self._updateVideoFilterSummary()
        self._configureVideoTrajectoryAnalysis()

    def _videoVisibleWindowChanged(self, _index: int):
        self._updateVideoPlayhead(self._currentVideoPosition(), force=True)

    def setVideoFocusMode(self, enabled: bool):
        """Temporarily give the DAS plot all available workspace."""

        enabled = bool(enabled)
        self._video_focus_mode = enabled
        if hasattr(self, 'sidebar_tabs'):
            self.sidebar_tabs.setVisible(not enabled)
        if hasattr(self, 'event_range_widget'):
            self.event_range_widget.setVisible(not enabled)
        if hasattr(self, 'video_focus_button'):
            self.video_focus_button.setText('退出专注' if enabled else '专注模式')
        QTimer.singleShot(
            0,
            lambda: self._updateVideoPlayhead(
                self._currentVideoPosition(), force=True
            ),
        )

    def _videoDisplayWindowSeconds(self) -> float:
        """Give low-frequency display filters enough signal for two periods."""

        if (
            hasattr(self, 'video_display_mode_combo')
            and self.video_display_mode_combo.currentData() == 'raw'
        ):
            return max(VIDEO_DISPLAY_WINDOW_SECONDS, self._videoVisibleWindowSeconds())
        lows = []
        for step in self._video_filter_steps:
            if not step.enabled:
                continue
            value = step.parameters.get('frequency_low')
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(value) and value > 0:
                lows.append(value)
        return max(
            VIDEO_DISPLAY_WINDOW_SECONDS,
            2.0 / min(lows) if lows else VIDEO_DISPLAY_WINDOW_SECONDS,
        )

    def setVideoFilterPipeline(self, steps):
        """Commit the dedicated, read-only video display filter chain."""

        self._video_filter_steps = clone_steps(steps)
        self._video_filter_customized = True
        self._updateVideoFilterSummary()
        self._configureVideoTrajectoryAnalysis()

    def setVideoFilterSettings(self, settings):
        self._video_filter_settings = dict(settings)

    def showVideoFilterDialog(self):
        """Reuse the 2-D filter editor for the rolling video/DAS display."""

        data_group, timeline = self._videoDataContext()
        if data_group is None or timeline is None or self.video_sequence_data_group is None:
            printError('请先选择视频并匹配对应的 DAS 文件')
            return
        current_sample = self.video_annotation_project.sync.sample_for_video_position(
            self._currentVideoPosition(), timeline
        )
        current_sample = 0 if current_sample is None else int(current_sample)
        rate = float(data_group.sampling_rate)
        channel_count = int(data_group.channel_count)
        preview_seconds = min(
            30.0,
            max(5.0, VIDEO_FILTER_PREVIEW_MAX_VALUES / max(1.0, channel_count * rate)),
        )
        preview_count = min(
            data_group.total_samples,
            max(32, int(round(preview_seconds * rate))),
        )
        preview_start = min(
            max(0, current_sample - preview_count // 2),
            max(0, data_group.total_samples - preview_count),
        )
        preview_end = preview_start + preview_count
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage('正在读取当前视频位置附近的二维滤波预览…')
        QApplication.processEvents()
        try:
            preview = read_group_window(
                data_group, preview_start, preview_end, 1, channel_count
            )
        except Exception as error:
            printError(f'无法读取二维滤波预览：{error}')
            return
        finally:
            QApplication.restoreOverrideCursor()

        preview_steps = clone_steps(self._video_filter_steps)
        for step in preview_steps:
            channel_from, channel_to, _sample_from, _sample_to = step.selection
            step.selection = (
                max(1, min(channel_count, channel_from)),
                max(1, min(channel_count, channel_to)),
                1,
                preview.shape[1],
            )
        visible_range = (1, channel_count, 1, preview.shape[1])
        try:
            if self.video_filter_dialog is None:
                dialog = DASFilterDialog(
                    preview,
                    rate,
                    visible_range,
                    settings=self._video_filter_settings,
                    steps=preview_steps,
                    current_data=preview,
                    segment_ranges=[(0, preview.shape[1])],
                    previous_steps=preview_steps,
                    auto_reapply=False,
                    parent=self,
                )
                dialog.setWindowTitle('视频对照 · 二维显示滤波')
                dialog.pipelineChanged.connect(self.setVideoFilterPipeline)
                dialog.settingsChanged.connect(self.setVideoFilterSettings)
                dialog.pipelineConfirmedByUser.connect(self.rememberConfirmedVideoFilterPipeline)
                dialog.savePipelineRequested.connect(self.saveCurrentVideoFilterPipeline)
                dialog.loadPipelineRequested.connect(self.loadSavedVideoFilterPipeline)
                dialog.deletePipelineRequested.connect(self.deleteSavedFilterPipeline)
                dialog.destroyed.connect(lambda: setattr(self, 'video_filter_dialog', None))
                dialog.auto_reapply_checkbox.hide()
                dialog.set_saved_pipelines(self._filter_pipeline_history)
                self.video_filter_dialog = dialog
            else:
                self.video_filter_dialog.set_data(
                    preview,
                    rate,
                    visible_range,
                    current_data=preview,
                    steps=preview_steps,
                    segment_ranges=[(0, preview.shape[1])],
                    previous_steps=preview_steps,
                )
            self.video_filter_dialog.status_label.setText(
                '这里编辑的步骤会按顺序应用到每个播放窗口；时间范围自动扩展为整个窗口。'
            )
            self.video_filter_dialog.show()
            self.video_filter_dialog.raise_()
            self.video_filter_dialog.activateWindow()
        except (RuntimeError, ValueError) as error:
            printError(f'无法打开视频二维滤波：{error}')

    def saveCurrentVideoFilterPipeline(self, name: str):
        dialog = self.video_filter_dialog
        if dialog is None:
            return
        try:
            entry = make_history_entry(
                name,
                'named',
                dialog.pipeline_steps(),
                dialog.raw_data.shape,
                dialog.sampling_rate,
            )
            self._filter_pipeline_history = upsert_named_history(
                self._filter_pipeline_history, entry
            )
        except ValueError as error:
            QMessageBox.warning(self, '无法保存滤波方案', str(error))
            return
        self._persistFilterPipelineHistory()
        self.statusBar().showMessage(f'已保存视频显示滤波方案“{name}”。', 6000)

    def rememberConfirmedVideoFilterPipeline(self, steps):
        dialog = self.video_filter_dialog
        if dialog is None or not steps:
            return
        name = datetime.now().strftime('最近使用 %m-%d %H:%M:%S')
        try:
            entry = make_history_entry(
                name,
                'recent',
                steps,
                dialog.raw_data.shape,
                dialog.sampling_rate,
            )
            self._filter_pipeline_history = add_recent_history(
                self._filter_pipeline_history, entry
            )
        except ValueError as error:
            self.statusBar().showMessage(f'视频滤波链历史未保存：{error}', 8000)
            return
        self._persistFilterPipelineHistory()

    def loadSavedVideoFilterPipeline(self, identifier: str):
        dialog = self.video_filter_dialog
        entry = self._historyEntry(identifier)
        if dialog is None or entry is None:
            return
        try:
            steps = history_entry_steps(entry)
            old_channels, _old_samples = map(int, entry.get('source_shape'))
            new_channels, new_samples = map(int, dialog.raw_data.shape)
            adapted = []
            for step in steps:
                channel_from, channel_to, _sample_from, _sample_to = step.selection
                if channel_from == 1 and channel_to == old_channels:
                    channel_to = new_channels
                if channel_from < 1 or channel_to > new_channels:
                    raise ValueError(
                        f'步骤“{step.label}”的通道范围 {channel_from}-{channel_to} '
                        f'超出当前视频 DAS 的 1-{new_channels}'
                    )
                clone = step.clone(new_identifier=True)
                clone.selection = (channel_from, channel_to, 1, new_samples)
                adapted.append(clone)
        except (TypeError, ValueError) as error:
            QMessageBox.warning(self, '滤波方案与视频 DAS 不兼容', str(error))
            return
        dialog.set_draft_pipeline(
            adapted,
            f'已载入保存方案“{entry.get("name", "")}”',
            new_identifiers=False,
        )

    def _configureVideoTrajectoryAnalysis(self):
        """Validate calibration and reset only derived local-window cache."""
        self.video_trajectory_parameters = self._videoTrajectoryParameters()
        self.video_trajectory_windows.clear()
        self.video_trajectory_pending.clear()
        self.video_trajectory_current_window = None
        self.video_trajectory_generation += 1
        parameters = self.video_trajectory_parameters
        detection_enabled = bool(parameters.get('detect_trajectories'))
        try:
            display_window = self._videoDisplayWindowSeconds()
            if detection_enabled:
                self.video_trajectory_window_seconds = max(
                    display_window,
                    required_window_seconds(parameters, VIDEO_TRAJECTORY_REQUESTED_WINDOW_SECONDS),
                )
            else:
                self.video_trajectory_window_seconds = display_window
        except ValueError as error:
            self.video_trajectory_window_seconds = None
            self.video_trajectory_status_label.setText(f'轨迹：参数无效：{error}')
            return
        filter_note = self._videoFilterSummary()
        if detection_enabled:
            tracking_note = '轨迹检测已启用'
        else:
            tracking_note = '填写 dx 且 DAS 至少包含 8 个通道后启用轨迹检测'
        self.video_trajectory_status_label.setText(
            f'显示：{filter_note}；{tracking_note}；连续滚动窗口 '
            f'{self._videoVisibleWindowSeconds():.0f} s，后台提前预读。'
        )
        self.plotVideoComparisonImage()
        self._requestVideoTrajectoryForPosition(self._currentVideoPosition())

    def _videoTrajectoryKeyForPosition(self, position_ms):
        data_group, timeline = self._videoDataContext()
        parameters = self.video_trajectory_parameters
        if (
            data_group is None or timeline is None or parameters is None
            or self.video_trajectory_window_seconds is None
            or self.video_sequence_data_group is None
        ):
            return None
        camera_start = 1
        camera_end = int(data_group.channel_count)
        sample = self.video_annotation_project.sync.sample_for_video_position(position_ms, timeline)
        if sample is None:
            return None
        sample = min(max(0, int(sample)), max(0, data_group.total_samples - 1))
        count = min(
            data_group.total_samples,
            max(32, int(round(self.video_trajectory_window_seconds * data_group.sampling_rate))),
        )
        stride = max(1, count // 2)
        start = (sample // stride) * stride
        start = min(max(0, start), max(0, data_group.total_samples - count))
        return start, start + count, camera_start, camera_end

    def _requestVideoTrajectoryForPosition(self, position_ms):
        """Queue the visible analysis window followed by one look-ahead window."""
        key = self._videoTrajectoryKeyForPosition(position_ms)
        if key is None:
            return
        self._queueVideoTrajectoryWindow(key, priority=0)
        _group, timeline = self._videoDataContext()
        look_ahead = max(
            VIDEO_TRAJECTORY_PREFETCH_SECONDS,
            self._videoVisibleWindowSeconds() * 0.5,
        )
        next_position = int(position_ms + look_ahead * 1000)
        if timeline is not None:
            self._queueVideoTrajectoryWindow(
                self._videoTrajectoryKeyForPosition(next_position), priority=1
            )
        self._startNextVideoTrajectoryWork()

    def _queueVideoTrajectoryWindow(self, key, priority):
        if key is None or key in self.video_trajectory_windows:
            return
        if self.video_trajectory_future is not None and getattr(self.video_trajectory_future, '_das_video_key', None) == key:
            return
        if any(item[1] == key for item in self.video_trajectory_pending):
            return
        self.video_trajectory_pending.append((int(priority), key))
        self.video_trajectory_pending.sort(key=lambda item: item[0])
        del self.video_trajectory_pending[4:]

    def _startNextVideoTrajectoryWork(self):
        if self.video_trajectory_future is not None or not self.video_trajectory_pending:
            return
        data_group, _timeline = self._videoDataContext()
        if data_group is None or self.video_trajectory_parameters is None:
            self.video_trajectory_pending.clear()
            return
        _priority, key = self.video_trajectory_pending.pop(0)
        start, end, channel_start, channel_end = key
        worker_parameters = dict(self.video_trajectory_parameters)
        worker_parameters['window_channel_from'] = channel_start
        future = self.video_trajectory_executor.submit(
            analyze_group_window,
            data_group,
            start,
            end,
            channel_start,
            channel_end,
            worker_parameters,
        )
        future._das_video_key = key
        future._das_video_generation = self.video_trajectory_generation
        self.video_trajectory_future = future
        mode_text = self._videoFilterSummary()
        self.video_trajectory_status_label.setText(
            f'显示：正在后台预读“{mode_text}”窗口 '
            f'{start / data_group.sampling_rate:.1f}–{end / data_group.sampling_rate:.1f} s；'
            '播放与滚动不会等待到窗口末端再加载。'
        )
        self.video_trajectory_poll_timer.start()

    def _pollVideoTrajectoryWork(self):
        future = self.video_trajectory_future
        if future is None or not future.done():
            return
        self.video_trajectory_future = None
        key = future._das_video_key
        if getattr(future, '_das_video_generation', -1) != self.video_trajectory_generation:
            self._startNextVideoTrajectoryWork()
            return
        try:
            window: VideoTrajectoryWindow = future.result()
            for index, trajectory in enumerate(window.trajectories, start=1):
                # Window-local picker IDs must not collide after annotations are saved.
                trajectory.identifier = int(window.start_sample + index)
            self.video_trajectory_windows[key] = window
            while len(self.video_trajectory_windows) > 3:
                self.video_trajectory_windows.pop(next(iter(self.video_trajectory_windows)))
            self.video_trajectory_current_window = window
            mode_text = self._videoFilterSummary()
            detection_enabled = bool(self.video_trajectory_parameters.get('detect_trajectories'))
            candidate_text = (
                f'{len(window.trajectories)} 条候选'
                if detection_enabled else '轨迹检测未启用'
            )
            self.video_trajectory_status_label.setText(
                f'显示：{mode_text}窗口 '
                f'{window.start_sample / self.video_sequence_data_group.sampling_rate:.1f}–'
                f'{window.end_sample / self.video_sequence_data_group.sampling_rate:.1f} s；'
                f'{candidate_text}。'
            )
            self.plotVideoComparisonImage()
            if self.video_annotation_selected_id is not None:
                annotation = self.video_annotation_project.annotation_by_identifier(self.video_annotation_selected_id)
                if annotation is not None:
                    self._refreshAnnotationTrajectoryChoices(annotation)
        except Exception as error:
            self.video_trajectory_status_label.setText(f'轨迹：窗口处理失败：{error}；未将其视为无车。')
        self._startNextVideoTrajectoryWork()
        if self.video_trajectory_future is None:
            self.video_trajectory_poll_timer.stop()

    def _activeVideoTrajectories(self):
        if self.video_trajectory_current_window is not None:
            return list(self.video_trajectory_current_window.trajectories)
        return list(self.vehicle_trajectories)

    def _drawVideoWindowTrajectories(self, plot_widget, window):
        colors = ('#e6194B', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#42d4f4')
        for index, trajectory in enumerate(window.trajectories):
            channels = np.asarray(trajectory.channels)
            times = np.asarray(trajectory.times)
            visible = (channels >= window.channel_from) & (channels <= window.channel_to)
            if np.count_nonzero(visible) < 2:
                continue
            color = colors[index % len(colors)]
            plot_widget.plot(
                times[visible], channels[visible] - window.channel_from + 0.5,
                pen=pg.mkPen(color=color, width=2), connect='finite',
            )

    def plotVideoComparisonImage(self):
        """Draw only the processed DAS window around the current video time."""

        if not hasattr(self, 'video_das_plot_widget'):
            return
        plot_widget = self.video_das_plot_widget
        plot_widget.clear()
        self._video_annotation_items = []
        self.video_playhead_line = None
        self.video_camera_line = None
        data_group, timeline = self._videoDataContext()
        sequence_active = self.video_sequence_data_group is not None
        display_data = None if sequence_active else getattr(self, 'origin_data', None)
        plot_widget.setTimeOrigin(timeline.start_time if timeline is not None else None)
        plot_widget.setTitle('')
        if timeline is None or data_group is None or (not sequence_active and display_data is None):
            self.video_current_das_label.setText('DAS：请先匹配数据')
            self.video_sequence_status_label.setText('匹配 DAS：未加载')
            return

        channel_from, channel_to = self._videoChannelBounds()
        channel_count = channel_to - channel_from + 1
        if not sequence_active:
            count = len(data_group.segments)
            self.video_sequence_status_label.setText(f'DAS：普通加载 {count} 文件')
            self.video_sequence_status_label.setToolTip(
                '当前显示来自数据页完整加载的数据；长录像请使用“匹配 DAS”按窗口读取。'
            )

        self.video_camera_channel_spin_box.blockSignals(True)
        try:
            self.video_camera_channel_spin_box.setRange(channel_from, channel_to)
            camera_channel = self.video_annotation_project.camera_channel
            self.video_camera_channel_spin_box.setValue(
                min(max(channel_from, camera_channel), channel_to)
            )
        finally:
            self.video_camera_channel_spin_box.blockSignals(False)

        item = pg.ImageItem()
        if sequence_active:
            current_sample = self.video_annotation_project.sync.sample_for_video_position(
                self._currentVideoPosition(), timeline
            )
            current_sample = 0 if current_sample is None else int(current_sample)
            current_seconds = current_sample / timeline.sampling_rate
            candidates = [
                window for window in self.video_trajectory_windows.values()
                if window.start_sample <= current_sample <= window.end_sample
            ]
            active_window = min(
                candidates,
                key=lambda window: abs(
                    (window.start_sample + window.end_sample) // 2 - current_sample
                ),
                default=None,
            )
            self.video_trajectory_current_window = active_window

            plot_channel_count = channel_count
            self._video_plot_channel_from = channel_from
            duration = timeline.total_samples / timeline.sampling_rate
            visible_width = min(duration, self._videoVisibleWindowSeconds())
            visible_width = max(1 / timeline.sampling_rate, visible_width)
            visible_left = min(
                max(current_seconds - visible_width * 0.25, 0.0),
                max(0.0, duration - visible_width),
            )
            view_box = plot_widget.getViewBox()
            view_box.setLimits(
                xMin=0.0,
                xMax=duration,
                yMin=0.0,
                yMax=plot_channel_count,
            )
            view_box.setRange(
                xRange=(visible_left, visible_left + visible_width),
                yRange=(0.0, plot_channel_count),
                padding=0,
            )

            if active_window is not None:
                levels = self.imageLevels(active_window.processed_data)
                cached_windows = sorted(
                    self.video_trajectory_windows.values(),
                    key=lambda window: window.start_sample,
                )
                centers = [
                    (window.start_sample + window.end_sample) / 2.0
                    for window in cached_windows
                ]
                for index, cached_window in enumerate(cached_windows):
                    display_start = cached_window.start_sample
                    display_end = cached_window.end_sample
                    if index > 0:
                        display_start = max(
                            display_start,
                            int(round((centers[index - 1] + centers[index]) / 2.0)),
                        )
                    if index + 1 < len(cached_windows):
                        display_end = min(
                            display_end,
                            int(round((centers[index] + centers[index + 1]) / 2.0)),
                        )
                    if display_end <= display_start:
                        continue
                    data_width = cached_window.processed_data.shape[1]
                    sample_scale = data_width / max(1, cached_window.sample_count)
                    data_start = max(
                        0,
                        int(round(
                            (display_start - cached_window.start_sample) * sample_scale
                        )),
                    )
                    data_end = min(
                        data_width,
                        int(round(
                            (display_end - cached_window.start_sample) * sample_scale
                        )),
                    )
                    if data_end <= data_start:
                        continue
                    cached_item = pg.ImageItem()
                    cached_item.setImage(
                        cached_window.processed_data[:, data_start:data_end].T,
                        autoLevels=levels is None,
                    )
                    if levels is not None:
                        cached_item.setLevels(levels)
                    cached_item.setRect(QRectF(
                        display_start / timeline.sampling_rate,
                        0.0,
                        (display_end - display_start) / timeline.sampling_rate,
                        plot_channel_count,
                    ))
                    plot_widget.addItem(cached_item)
                self._drawVideoWindowTrajectories(plot_widget, active_window)
            else:
                waiting = pg.TextItem('正在预读当前 DAS 连续滚动窗口…', color='#667085', anchor=(0.5, 0.5))
                waiting.setPos(visible_left + visible_width / 2.0, plot_channel_count / 2.0)
                plot_widget.addItem(waiting)
        else:
            self._video_plot_channel_from = channel_from
            levels = self.imageLevels(display_data)
            item.setImage(display_data.T, autoLevels=levels is None)
            if levels is not None:
                item.setLevels(levels)
            duration = display_data.shape[1] / timeline.sampling_rate
            item.setRect(QRectF(0.0, 0.0, duration, channel_count))
            plot_widget.addItem(item)
            view_box = plot_widget.getViewBox()
            view_box.setLimits(xMin=0.0, xMax=duration, yMin=0.0, yMax=channel_count)
            view_box.setRange(xRange=(0.0, duration), yRange=(0.0, channel_count), padding=0)
            self.drawFileBoundaries(plot_widget, 0, channel_count)
            self.drawVehicleTrajectories(plot_widget, full_range=True)
            self.drawEventRange(plot_widget)
        if self.video_annotation_context_matches:
            self._drawVideoCameraLine()
            self._drawVideoAnnotations()
        self._drawVideoPlayhead()
        self._updateVideoPlayhead(self._currentVideoPosition(), force=True)

    def _drawVideoCameraLine(self):
        if not self.video_annotation_project.camera_visible:
            return
        channel = self.video_annotation_project.camera_channel
        channel_from, channel_to = self._videoChannelBounds()
        if not (channel_from <= channel <= channel_to):
            return
        plot_origin = getattr(self, '_video_plot_channel_from', channel_from)
        local_channel = channel - plot_origin + 0.5
        line = pg.InfiniteLine(
            pos=local_channel,
            angle=0,
            movable=True,
            bounds=(0, channel_to - channel_from + 1),
            pen=pg.mkPen('#2563eb', width=3),
            hoverPen=pg.mkPen('#1d4ed8', width=5),
        )
        line.setZValue(28)
        line.setToolTip('拖动此线可修正摄像头对应的全局 DAS 通道；不会修改 DAS 数据。')
        pg.InfLineLabel(
            line,
            text=(f'{self.video_annotation_project.camera_name} · 通道 '
                  f'{self.video_annotation_project.camera_channel}'),
            position=0.97,
            color='#1d4ed8',
            fill=pg.mkBrush(255, 255, 255, 215),
            movable=True,
        )
        line.sigPositionChangeFinished.connect(lambda item=line: self._videoCameraLineMoved(item))
        self.video_das_plot_widget.addItem(line)
        self.video_camera_line = line
        self._video_annotation_items.append(line)

    def _drawVideoAnnotations(self):
        if not self.video_annotations_visible_checkbox.isChecked():
            return
        timeline = self._annotationTimeline()
        if timeline is None:
            return
        sampling_rate = float(timeline.sampling_rate)
        duration = timeline.total_samples / sampling_rate
        channel_from, channel_to = self._videoChannelBounds()
        palette = {
            '确认匹配': ('#13734a', (230, 247, 239, 76), 't'),
            'DAS未检测到': ('#b42318', (254, 243, 242, 76), 'x'),
            '疑似误检': ('#b42318', (254, 243, 242, 76), 'x'),
            '拒绝': ('#b42318', (254, 243, 242, 76), 'x'),
            '不确定': ('#9a5b00', (255, 243, 214, 76), 'o'),
        }
        for index, annotation in enumerate(self.video_annotation_project.annotations):
            if not annotation.visible:
                continue
            color, brush_color, symbol = palette.get(
                annotation.outcome,
                ('#2563eb', (234, 241, 255, 72), 'o'),
            )
            start_seconds = annotation.start_sample / sampling_rate
            selected = annotation.identifier == self.video_annotation_selected_id
            width = 4 if selected else 2
            label_text = f'#{annotation.identifier} {annotation.kind}'
            if annotation.is_interval:
                end_seconds = annotation.end_sample / sampling_rate
                region = pg.LinearRegionItem(
                    values=(start_seconds, end_seconds),
                    orientation=pg.LinearRegionItem.Vertical,
                    movable=False,
                    brush=pg.mkBrush(*brush_color),
                    hoverBrush=pg.mkBrush(*brush_color),
                    bounds=(0.0, duration),
                )
                region.setZValue(34)
                for line in region.lines:
                    line.setPen(pg.mkPen(color, width=width))
                pg.InfLineLabel(
                    region.lines[0],
                    text=label_text,
                    position=0.12 + (index % 5) * 0.13,
                    color=color,
                    fill=pg.mkBrush(255, 255, 255, 215),
                    movable=False,
                )
                self.video_das_plot_widget.addItem(region)
                self._video_annotation_items.append(region)
            else:
                line = pg.InfiniteLine(
                    pos=start_seconds,
                    angle=90,
                    movable=False,
                    pen=pg.mkPen(color, width=width),
                    hoverPen=pg.mkPen(color, width=width + 1),
                )
                line.setZValue(34)
                line.setToolTip(
                    f'标注 #{annotation.identifier}：{annotation.kind}；'
                    f'{format_video_position(annotation.start_video_ms)}'
                )
                pg.InfLineLabel(
                    line,
                    text=label_text,
                    position=0.12 + (index % 5) * 0.13,
                    color=color,
                    fill=pg.mkBrush(255, 255, 255, 215),
                    movable=False,
                )
                self.video_das_plot_widget.addItem(line)
                self._video_annotation_items.append(line)
            if channel_from <= annotation.camera_channel <= channel_to:
                plot_origin = getattr(self, '_video_plot_channel_from', channel_from)
                marker = pg.ScatterPlotItem(
                    [start_seconds],
                    [annotation.camera_channel - plot_origin + 0.5],
                    size=11 if selected else 9,
                    pen=pg.mkPen('#ffffff', width=1),
                    brush=pg.mkBrush(color),
                    symbol=symbol,
                )
                marker.setZValue(36)
                self.video_das_plot_widget.addItem(marker)
                self._video_annotation_items.append(marker)

    def _drawVideoPlayhead(self):
        timeline = self._annotationTimeline()
        can_calibrate = bool(
            timeline is not None
            and self.video_annotation_project.sync.video_start_time is not None
        )
        line = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=can_calibrate,
            pen=pg.mkPen('#7c3aed', width=3, style=Qt.DashLine),
            hoverPen=pg.mkPen('#5b21b6', width=5, style=Qt.DashLine),
        )
        if timeline is not None:
            line.setBounds(
                (0.0, timeline.total_samples / float(timeline.sampling_rate))
            )
        line.setZValue(40)
        if can_calibrate:
            target = self._videoPlayheadTarget(line)
            if target is not None:
                sample, wall_time = target
                self._setVideoPlayheadTooltip(line, sample, wall_time)
            line.sigDragged.connect(self._videoPlayheadDragged)
            line.sigPositionChangeFinished.connect(
                self._videoPlayheadMoveFinished
            )
        else:
            line.setToolTip('请先设置视频开始时间，再拖动紫色虚线进行校正')
        self.video_das_plot_widget.addItem(line)
        self.video_playhead_line = line
        self._video_annotation_items.append(line)

    def defaultSpeedRulerPoints(self):
        """Return a visible diagonal in full-data time/global-channel coordinates."""

        start_time = (self.sampling_times_from_num - 1) / self.sampling_rate
        end_time = self.sampling_times_to_num / self.sampling_rate
        time_span = max(end_time - start_time, 1 / self.sampling_rate)
        channel_span = max(float(self.channel_to_num - self.channel_from_num), 0.0)
        elapsed = time_span * 0.5
        channel_delta = min(
            channel_span * 0.5,
            20.0 * elapsed / self.speed_ruler_channel_spacing,
        )
        if 0 < channel_delta < 20.0 * elapsed / self.speed_ruler_channel_spacing:
            elapsed = channel_delta * self.speed_ruler_channel_spacing / 20.0
        return (
            (start_time + time_span * 0.25, self.channel_from_num + channel_span * 0.25),
            (
                start_time + time_span * 0.25 + elapsed,
                self.channel_from_num + channel_span * 0.25 + channel_delta,
            ),
        )

    def addOrResetSpeedRuler(self):
        """Add one speed ruler, or reset the existing ruler into the current view."""

        if not hasattr(self, 'data') or self.data.size == 0:
            printError('请先导入 DAS 数据')
            return
        self.speed_ruler_active = True
        self.speed_ruler_points = self.defaultSpeedRulerPoints()
        self._removeSpeedRulerGraphics()
        self.drawSpeedRuler()
        self.tab_widget.setCurrentWidget(self.gray_scale_container)
        self.updateSpeedRulerButtons()

    def _setSpeedRulerStatus(self, text: str, detail: str, state: str) -> None:
        """Keep the toolbar status compact while retaining the full measurement."""

        self.speed_ruler_status_label.setText(text)
        self.speed_ruler_status_label.setToolTip(detail)
        self.speed_ruler_status_label.setProperty('state', state)
        self.speed_ruler_status_label.style().unpolish(self.speed_ruler_status_label)
        self.speed_ruler_status_label.style().polish(self.speed_ruler_status_label)

    def removeSpeedRuler(self):
        """Remove only the manual overlay; never modify DAS or trajectory data."""

        self.speed_ruler_active = False
        self.speed_ruler_points = None
        self._removeSpeedRulerGraphics()
        self._setSpeedRulerStatus('未添加', '速度标尺未添加', 'inactive')
        self.updateSpeedRulerButtons()

    def _removeSpeedRulerGraphics(self):
        ruler = self.speed_ruler_roi
        self.speed_ruler_roi = None
        if ruler is None:
            return
        try:
            self.plot_gray_scale_widget.removeItem(ruler)
        except RuntimeError:
            pass

    def drawSpeedRuler(self):
        """Recreate the ruler after plot refresh using stored full-data coordinates."""

        if not self.speed_ruler_active or not hasattr(self, 'data') or self.data.size == 0:
            return
        if self.speed_ruler_points is None:
            self.speed_ruler_points = self.defaultSpeedRulerPoints()
        local_points = [
            (time_value, channel - self.channel_from_num + 0.5)
            for time_value, channel in self.speed_ruler_points
        ]
        ruler = SpeedRulerROI(local_points, self.speed_ruler_channel_spacing)
        self.speed_ruler_roi = ruler
        ruler.sigRegionChanged.connect(self.speedRulerMoved)
        self.plot_gray_scale_widget.addItem(ruler)
        self.speedRulerMoved(ruler)
        self.updateSpeedRulerButtons()

    def speedRulerMoved(self, ruler):
        """Persist ruler endpoints and update speed text during dragging/rotation."""

        if ruler is not self.speed_ruler_roi:
            return
        parent_points = ruler.parentPoints()
        self.speed_ruler_points = tuple(
            (time_value, local_channel + self.channel_from_num - 0.5)
            for time_value, local_channel in parent_points
        )
        measurement = calculate_projected_speed(
            self.speed_ruler_points[0],
            self.speed_ruler_points[1],
            self.speed_ruler_channel_spacing,
        )
        detail = format_speed_measurement(measurement)
        if measurement.valid:
            text = f'{measurement.speed_mps:.2f} m/s · {measurement.direction_text}'
            state = 'active'
        else:
            text = '无法测量'
            state = 'inactive'
        self._setSpeedRulerStatus(text, detail, state)

    def updateSpeedRulerChannelSpacing(self, value: float):
        """Recalculate the active ruler when the real adjacent-channel spacing changes."""

        self.speed_ruler_channel_spacing = float(value)
        if self.speed_ruler_roi is not None:
            self.speed_ruler_roi.setChannelSpacing(self.speed_ruler_channel_spacing)
            self.speedRulerMoved(self.speed_ruler_roi)

    def updateSpeedRulerButtons(self):
        if not hasattr(self, 'speed_ruler_reset_button'):
            return
        has_data = hasattr(self, 'data') and self.data.size > 0
        self.speed_ruler_reset_button.setEnabled(has_data)
        self.speed_ruler_reset_button.setText(
            '重置速度标尺' if self.speed_ruler_active else '添加速度标尺'
        )
        self.speed_ruler_remove_button.setEnabled(self.speed_ruler_active)

    def updateImageColorParams(self, *args):
        self.image_colormap = self.image_colormap_combx.currentText()
        try:
            self.image_level_min = self.parseOptionalFloat(self.image_level_min_line_edit.text())
            self.image_level_max = self.parseOptionalFloat(self.image_level_max_line_edit.text())
            if (self.image_level_min is None) != (self.image_level_max is None):
                raise ValueError('最小值和最大值需要同时填写，或都留空自动计算')
            if self.image_level_min is not None and self.image_level_max is not None:
                if self.image_level_min >= self.image_level_max:
                    raise ValueError('最小值必须小于最大值')
        except ValueError as err:
            printError(err)
            return

        if hasattr(self, 'data'):
            self.plotGrayScaleImage()

    def autoImageLevels(self):
        self.image_level_min_line_edit.clear()
        self.image_level_max_line_edit.clear()
        self.image_level_min = None
        self.image_level_max = None
        if hasattr(self, 'data'):
            self.plotGrayScaleImage()

    @staticmethod
    def parseOptionalFloat(text: str):
        text = text.strip()
        return None if text == '' else float(text)

    def imageLevels(self, data: np.array):
        flat_data = np.asarray(data).reshape(-1)
        if flat_data.size > IMAGE_LEVEL_SAMPLE_LIMIT:
            stride = int(np.ceil(flat_data.size / IMAGE_LEVEL_SAMPLE_LIMIT))
            flat_data = flat_data[::stride]
        finite_data = flat_data[np.isfinite(flat_data)]
        if finite_data.size == 0:
            return None

        if self.image_level_min is not None and self.image_level_max is not None:
            max_abs = float(np.max(np.abs(finite_data)))
            if max_abs == 0:
                max_abs = 1.0
            return [max_abs * self.image_level_min / 100, max_abs * self.image_level_max / 100]

        if self.image_colormap in self.diverging_colormaps:
            limit = float(np.percentile(np.abs(finite_data), 90))
            vmin, vmax = -limit, limit
        else:
            vmin, vmax = np.percentile(finite_data, [2, 98])
            vmin, vmax = float(vmin), float(vmax)

        if vmin == vmax:
            vmin, vmax = vmin - 1, vmax + 1
        return [vmin, vmax]

    def imageColorMap(self):
        if self.image_colormap == '灰度':
            return None

        try:
            return pg.colormap.get(self.image_colormap)
        except Exception:
            values = np.linspace(0.0, 1.0, 256)
            colors = (plt.get_cmap(self.image_colormap)(values) * 255).astype(np.ubyte)
            return pg.ColorMap(values, colors)

    def updateGrayScaleColorBar(self,
                                plot_widget: MyPlotWidget,
                                item: pg.ImageItem,
                                color_map,
                                levels,
                                show_color_bar: bool) -> None:
        if not show_color_bar:
            return

        if color_map is None:
            if self.gray_scale_color_bar is not None:
                self.gray_scale_color_bar.setVisible(False)
            return

        if self.gray_scale_color_bar is None:
            self.gray_scale_color_bar = pg.ColorBarItem(values=levels, width=18, colorMap=color_map,
                                                        label='幅值', interactive=True)
            self.gray_scale_color_bar.setImageItem(item, insert_in=plot_widget.getPlotItem())
        else:
            self.gray_scale_color_bar.setVisible(True)
            self.gray_scale_color_bar.setColorMap(color_map)
            if levels is not None:
                self.gray_scale_color_bar.setLevels(levels)
            self.gray_scale_color_bar.setImageItem(item)

    def plotSingleChannelTime(self):
        """
        绘制单通道时域图
        Returns:

        """
        self.plot_single_channel_time_widget.plot_item.clear()
        self.plot_single_channel_time_widget.setTimeOrigin(
            self.data_timeline.start_time if self.data_timeline is not None else None
        )

        x = xAxis(self.current_sampling_times,
                  self.sampling_times_from_num,
                  self.sampling_times_to_num,
                  self.sampling_rate)
        data = self.data[self.channel_number - 1]
        self.plot_single_channel_time_widget.draw(x, data, pen=QColor('blue'))
        self.drawEventRange(self.plot_single_channel_time_widget)

    def plotAmplitudeFrequency(self):
        """
        绘制幅值图
        Returns:

        """
        self.plot_amplitude_frequency_widget.plot_item.clear()

        data = self.data[self.channel_number - 1]
        data = toAmplitude(data)

        x = xAxis(self.current_sampling_times, sampling_rate=self.sampling_rate, freq=True)
        self.plot_amplitude_frequency_widget.draw(x, data, pen=QColor('blue'))

    # """------------------------------------------------------------------------------------------------------------"""
    """文件路径区和文件列表调用函数"""

    def changeFilePath(self):
        """
        更改显示的文件路径
        Returns:

        """
        file_path = QFileDialog.getExistingDirectory(self, '设置文件路径', '')  # 起始路径
        if file_path != '':
            self.file_path = file_path
            self.updateFile()

    def selectDataFromTable(self):
        """
        确认后按文件表顺序一次性读取、拼接并更新所选文件。
        Returns:

        """
        if self.das_filter_dialog is not None and self.das_filter_dialog.is_busy():
            printError('滤波链正在计算，请等待完成后再切换文件')
            return
        rows = self.selectedFileRows()
        if not rows:
            printError('请先在文件表中选择要加载和拼接的文件')
            return

        self.file_names = [self.files_table_widget.item(row, 0).text() for row in rows]
        self.load_selected_files_button.setEnabled(False)
        self.load_selected_files_button.setText('正在加载…')
        self.statusBar().showMessage(f'正在读取并拼接 {len(self.file_names)} 个文件…')
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            self.readData()
            self.initLocalParams()
            self.updateAll()
            self.syncDASFilterDialog()
            self.statusBar().showMessage(
                f'已加载并拼接 {len(self.data_group.segments)} 个文件。',
                8000,
            )
        except Exception as err:
            printError(err)
            self.statusBar().showMessage(f'文件加载失败：{err}', 10000)
        finally:
            QApplication.restoreOverrideCursor()
            self.load_selected_files_button.setText('确定加载并拼接')
            self.updatePendingFileSelection()

    def _videoSequencePathsFromStartRow(self, start_row: int):
        """Use one selected directory row as the start of a same-format sequence."""

        first = self.files_table_widget.item(int(start_row), 0)
        if first is None:
            return []
        suffix = self.dataFileSuffix(first.text())
        paths = []
        for row in range(int(start_row), self.files_table_widget.rowCount()):
            item = self.files_table_widget.item(row, 0)
            if item is None:
                continue
            if self.dataFileSuffix(item.text()) != suffix:
                continue
            paths.append(self.dataFilePath(item.text()))
        return paths

    @staticmethod
    def _videoSequenceWasCancelled(progress):
        return progress.wasCanceled() if progress is not None else False

    def loadVideoSequenceFromStartRow(self, start_row: int):
        """Compatibility entry point: build metadata from the selected row onward."""

        paths = self._videoSequencePathsFromStartRow(start_row)
        if not paths:
            printError('未找到可连续读取的 DAS 文件')
            return
        self.loadVideoSequencePaths(paths, source_description='从所选文件开始')

    def loadVideoSequencePaths(self, paths, source_description='按录像时间匹配'):
        """Build a continuous video/DAS timeline from headers without reading payloads."""

        paths = [os.path.realpath(str(path)) for path in paths]
        if not paths:
            printError('没有可载入的视频 DAS 文件')
            return
        suffixes = {self.dataFileSuffix(path) for path in paths}
        if len(suffixes) != 1:
            printError('视频 DAS 一次只能处理同一种文件格式')
            return
        suffix = suffixes.pop()
        if suffix != '.bin':
            printError('视频对照的按窗口读取目前仅支持 BIN 文件')
            return
        progress = QProgressDialog('正在读取 DAS 文件头…', '取消', 0, len(paths), self)
        progress.setWindowTitle('匹配视频与 DAS')
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(True)
        progress.setValue(0)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        try:
            headers = []
            sample_counts = []
            channels_num = None
            sampling_rate = None
            for index, path in enumerate(paths):
                if self._videoSequenceWasCancelled(progress):
                    raise RuntimeError('已取消视频 DAS 载入')
                if suffix == '.bin':
                    header, samples, channels, rate, _endian = read_bin_header(path)
                    header = tuple(map(float, header[:6]))
                elif suffix == '.dat':
                    header_data = np.fromfile(path, dtype='<f4')
                    minimum_header = 64 if self.is_scouter else 10
                    if header_data.size <= minimum_header:
                        raise ValueError(f'{path}: DAT 文件过短，无法读取')
                    if self.is_scouter:
                        channels = int(header_data[16])
                        rate = float(header_data[10])
                        samples = (header_data.size - 64) // channels
                    else:
                        channels = int(header_data[9])
                        rate = float(header_data[6])
                        samples = (header_data.size - 10) // channels
                    header = tuple(map(float, header_data[:6]))
                else:
                    raise ValueError(f'不支持的视频 DAS 格式：{suffix}')
                if channels <= 0 or samples <= 0 or rate <= 0:
                    raise ValueError(f'{path}: 通道数、采样点数或采样率无效')
                if channels_num is None:
                    channels_num, sampling_rate = int(channels), float(rate)
                elif channels != channels_num or not np.isclose(rate, sampling_rate):
                    raise ValueError(
                        f'{path}: 通道数或采样率与首个文件不一致，载入已停止'
                    )
                headers.append(header)
                sample_counts.append(int(samples))
                progress.setLabelText(f'正在读取时间轴：{index + 1}/{len(paths)}')
                progress.setValue(index + 1)
                QApplication.processEvents()

            data_group = DataGroup.from_files(paths, sample_counts, channels_num, sampling_rate)
            timeline = DataTimeline.from_data_group(
                data_group,
                headers,
                correction_seconds=self.time_correction_seconds,
            )
            self.video_sequence_data_group = data_group
            self.video_sequence_timeline = timeline
            self.video_sequence_source_paths = list(paths)
            self.video_sequence_selected_segment_index = 0
            self.video_das_match_required = False
            self._ensureDefaultVideoFilterPipeline(
                int(channels_num), int(data_group.total_samples)
            )
            if self.video_annotation_project.camera_channel > channels_num:
                self.video_annotation_project.set_camera_channel(int(channels_num))
            self.updateVideoAnnotationDataContext()
            self._syncVideoProjectWidgets()
            self._refreshVideoDasRecommendation()
            self._configureVideoTrajectoryAnalysis()
            self.refreshVideoAnnotationTable(select_identifier=self.video_annotation_selected_id)
            self.video_sequence_status_label.setText(
                f'匹配 DAS：{len(paths)} 文件 · 播放时按窗口读取'
            )
            self.video_sequence_status_label.setToolTip(
                f'{source_description}：{os.path.basename(paths[0])} 至 {os.path.basename(paths[-1])}；'
                f'仅载入文件头和 {timeline.total_samples} 点时间轴，原始数据随播放位置读取。'
            )
            self.plotVideoComparisonImage()
            self.tab_widget.setCurrentWidget(self.video_compare_container)
            self.statusBar().showMessage(
                f'视频 DAS 已就绪：匹配 {len(paths)} 个文件，播放时按窗口读取。',
                10000,
            )
        except Exception as error:
            printError(error)
            self.statusBar().showMessage(f'视频 DAS 载入失败：{error}', 10000)
        finally:
            progress.close()
            QApplication.restoreOverrideCursor()

    def selectedFileRows(self):
        """Return selected directory-table rows in the visible file order."""

        selection_model = self.files_table_widget.selectionModel()
        if selection_model is None:
            return []
        return sorted({index.row() for index in selection_model.selectedRows(0)})

    def selectedFilePaths(self):
        """Return normalized absolute paths for the pending table selection."""

        paths = []
        for row in self.selectedFileRows():
            item = self.files_table_widget.item(row, 0)
            if item is not None:
                paths.append(os.path.normcase(os.path.realpath(os.path.join(self.file_path, item.text()))))
        return paths

    def updatePendingFileSelection(self):
        """Update only the pending-selection summary; never read data or redraw plots."""

        if not hasattr(self, 'pending_file_selection_label'):
            return
        rows = self.selectedFileRows()
        if not rows:
            self.pending_file_selection_label.setText('待拼接：请选择文件')
            self.load_selected_files_button.setEnabled(False)
            self.load_selected_files_button.setText('确定加载并拼接')
            return

        items = [self.files_table_widget.item(row, 0) for row in rows]
        names = [item.text() for item in items if item is not None]
        loaded_paths = [] if self.data_group is None else [
            os.path.normcase(os.path.realpath(segment.path))
            for segment in self.data_group.segments
        ]
        matches_loaded = bool(names) and self.selectedFilePaths() == loaded_paths
        if matches_loaded:
            self.pending_file_selection_label.setText(f'当前已加载：{len(names)} 个文件')
        elif len(names) == 1:
            self.pending_file_selection_label.setText(f'待加载：{names[0]}')
        else:
            self.pending_file_selection_label.setText(
                f'待拼接：{len(names)} 个文件（{names[0]} → {names[-1]}）'
            )
        self.load_selected_files_button.setText('确定加载并拼接')
        self.load_selected_files_button.setEnabled(not matches_loaded)

    def changeChannelNumber(self):
        """
        更改通道号，默认为 1
        Returns:

        """
        self.channel_number = 1 if self.channel_number_spinbx.value() == '' else self.channel_number_spinbx.value()

    # """------------------------------------------------------------------------------------------------------------"""
    """更新函数"""

    def updateWidgetsState(self):
        """
        更新菜单可操作性状态
        Returns:

        """
        self.export_action.setEnabled(True)
        self.operation_menu.setEnabled(True)
        self.plot_menu.setEnabled(True)
        self.filter_menu.setEnabled(True)
        self.analysis_menu.setEnabled(True)
        self.das_filter_action.setEnabled(True)
        self.reset_das_filter_action.setEnabled(bool(self._das_filter_steps))
        self.updateSpeedRulerButtons()

        setPicture(self.player_play_button, play_jpg, 'play.jpg')
        self.player_play_button.setDisabled(False)
        self.player_stop_button.setDisabled(False)  # 设置播放按钮

    def updateFile(self):
        """
        更新文件列表显示
        Returns:

        """
        self.file_path_line_edit.setText(self.file_path)
        self.file_path_line_edit.setToolTip(os.path.abspath(self.file_path))
        files = sorted(
            (f for f in os.listdir(self.file_path) if f.lower().endswith(DAS_FILE_SUFFIXES)),
            key=natural_sort_key,
        )
        signals_were_blocked = self.files_table_widget.blockSignals(True)
        try:
            self.files_table_widget.setRowCount(len(files))  # 有多少个文件就显示多少行
            for i in range(len(files)):
                table_widget_item = QTableWidgetItem(files[i])
                table_widget_item.setToolTip(os.path.abspath(os.path.join(self.file_path, files[i])))
                self.files_table_widget.setItem(i, 0, table_widget_item)
            self.highlightLoadedFiles()
        finally:
            self.files_table_widget.blockSignals(signals_were_blocked)
        self.updatePendingFileSelection()

    def highlightLoadedFiles(self):
        """Highlight every directory-table row represented by the loaded data group."""

        self.files_table_widget.clearSelection()
        if self.data_group is None:
            return
        loaded_paths = {
            os.path.normcase(os.path.realpath(segment.path))
            for segment in self.data_group.segments
        }
        first_item = None
        for row in range(self.files_table_widget.rowCount()):
            item = self.files_table_widget.item(row, 0)
            if item is None:
                continue
            item_path = os.path.normcase(os.path.realpath(os.path.join(self.file_path, item.text())))
            if item_path in loaded_paths:
                item.setSelected(True)
                if first_item is None:
                    first_item = item
        if first_item is not None:
            self.files_table_widget.scrollToItem(first_item, QAbstractItemView.PositionAtCenter)

    def updateDataRange(self):
        """
        更新数据显示范围
        Returns:

        """
        self.data = self.origin_data[self.channel_from_num - 1:self.channel_to_num,
                    self.sampling_times_from_num - 1:self.sampling_times_to_num]

    def updateDataParams(self):
        """
        更新数据相关参数
        Returns:

        """
        self.current_channels = self.channel_to_num - self.channel_from_num + 1
        self.current_sampling_times = self.sampling_times_to_num - self.sampling_times_from_num + 1

        self.channel_number_spinbx.setRange(1, self.current_channels)
        self.channel_number_spinbx.setValue(self.channel_number)
        self.sampling_rate_line_edit.setText(f'{self.sampling_rate:g}')
        self.current_sampling_times_line_edit.setText(str(self.current_sampling_times))
        self.current_channels_line_edit.setText(str(self.current_channels))

    def _syncTimeCorrectionSpinBox(self):
        """Reflect the saved correction in the editable sidebar control."""

        if not hasattr(self, 'time_correction_spin_box'):
            return
        self.time_correction_spin_box.blockSignals(True)
        try:
            self.time_correction_spin_box.setValue(self.time_correction_seconds)
        finally:
            self.time_correction_spin_box.blockSignals(False)

    def updateDataGPSTime(self):
        """Update corrected inferred times for the current visible sample range."""

        self._syncTimeCorrectionSpinBox()
        if self.data_timeline is None:
            self.gps_from_line_edit.clear()
            self.gps_to_line_edit.clear()
            self.setEventRangeControlsEnabled(False)
            return
        start_sample = 0
        end_sample = self.data_timeline.total_samples
        if hasattr(self, 'sampling_times_from_num') and hasattr(self, 'sampling_times_to_num'):
            start_sample = self.sampling_times_from_num - 1
            end_sample = self.sampling_times_to_num
        visible_start = self.data_timeline.absolute_time_for_sample(start_sample)
        visible_end = self.data_timeline.absolute_time_for_sample(end_sample)
        self.gps_from_line_edit.setText(format_wall_time(visible_start))
        self.gps_to_line_edit.setText(format_wall_time(visible_end))
        self.plot_gray_scale_widget.setTimeOrigin(self.data_timeline.start_time)
        self.plot_single_channel_time_widget.setTimeOrigin(self.data_timeline.start_time)
        self.multi_waves_time_axis.setOrigin(self.data_timeline.start_time)
        if hasattr(self, 'video_das_plot_widget'):
            self.video_das_plot_widget.setTimeOrigin(self.data_timeline.start_time)
        self.updateEventRangeEditors()
        if self.data_timeline.discontinuities:
            self.statusBar().showMessage(
                f'时间连续性提示：{len(self.data_timeline.discontinuities)} 个文件的记录结束时间'
                f'与连续推算偏差超过 {self.data_timeline.continuity_tolerance_seconds:g} s；'
                f'拼接数据仍按采样率连续显示。',
                12000,
            )

    def rebuildDataTimeline(self):
        """Recalculate the continuous wall-clock mapping after loading or correction changes."""

        if self.data_group is None or not self._source_time_headers:
            self.data_timeline = None
            return
        self.data_timeline = DataTimeline.from_data_group(
            self.data_group,
            self._source_time_headers,
            correction_seconds=self.time_correction_seconds,
        )
        self.acquisition_params['时间口径'] = '文件名/文件头为采集结束时间；按采样率连续推算'
        self.acquisition_params['设备时间修正'] = f'记录时间 {self.time_correction_seconds:+.3f} s'
        self.acquisition_params['推算实际时间'] = (
            f'{format_wall_time(self.data_timeline.start_time)} 至 '
            f'{format_wall_time(self.data_timeline.end_time)}'
        )
        self.acquisition_params['时间连续性警告'] = str(len(self.data_timeline.discontinuities))

    def updateImages(self):
        """
        更新4个随时更新的图像显示
        Returns:

        """
        self.plotGrayScaleImage()
        self.plotSingleChannelTime()
        self.plotAmplitudeFrequency()
        self.plotMultiWavesImage()
        self.plotVideoComparisonImage()

    def updateAll(self):
        """
        总更新函数
        Returns:

        """
        self.updateWidgetsState()
        self.updateFile()
        self.updateStitchedFilesList()
        self.updateDataRange()
        self.updateDataParams()
        self.updateDataGPSTime()
        self.updateVideoAnnotationDataContext()
        self.refreshVideoAnnotationTable(select_identifier=self.video_annotation_selected_id)
        self.updateImages()

    # """------------------------------------------------------------------------------------------------------------"""
    """文件菜单调用函数"""

    def importData(self):
        """
        导入（多个）数据文件后更新参数和绘图等
        Returns:

        """
        if self.das_filter_dialog is not None and self.das_filter_dialog.is_busy():
            printError('滤波链正在计算，请等待完成后再导入文件')
            return
        file_names = QFileDialog.getOpenFileNames(self, '导入', '', DAS_FILE_FILTER)[0]  # 打开多个数据文件
        if file_names:
            self.file_names = sorted(file_names, key=lambda value: natural_sort_key(os.path.basename(value)))
            self.file_path = os.path.dirname(self.file_names[0])

            self.readData()
            self.initLocalParams()
            self.updateAll()
            self.syncDASFilterDialog()

    def readData(self):
        """
        读取数据，更新参数
        Returns:

        """

        def f(s):
            return list(map(str, map(int, s[:5]))) + [str(s[5])]

        time, data = [], []
        previous_filter_shape = tuple(self.raw_data.shape) if self.raw_data is not None else None
        self._clearVideoSequenceContext()
        self.file_names = sorted(
            self.file_names,
            key=lambda value: natural_sort_key(os.path.basename(str(value))),
        )
        suffixes = {self.dataFileSuffix(file) for file in self.file_names}
        if len(suffixes) != 1:
            raise ValueError('一次只能读取同一种格式的数据文件。')

        suffix = suffixes.pop()
        first_file_path = self.dataFilePath(self.file_names[0])
        if suffix == '.bin':
            _first_header, sampling_time, channels_num, sampling_rate, _ = read_bin_header(first_file_path)
            metadata = []
            file_sampling_times = []
            for file in self.file_names:
                file_path = self.dataFilePath(file)
                header, file_sampling_time, file_channels_num, file_sampling_rate, _ = read_bin_header(file_path)
                if file_channels_num != channels_num:
                    raise ValueError(f'{file_path}: 通道数不一致，期望 {channels_num}，实际 {file_channels_num}')
                if not np.isclose(file_sampling_rate, sampling_rate):
                    raise ValueError(f'{file_path}: 采样率不一致，期望 {sampling_rate:g}Hz，'
                                     f'实际 {file_sampling_rate:g}Hz')
                metadata.append((file_path, header, file_sampling_time))
                file_sampling_times.append(file_sampling_time)

            ensure_memory_budget(
                channels_num,
                sum(file_sampling_times),
                4.5,
                'BIN 多文件拼接加载',
            )
            for file_path, header, _file_sampling_time in metadata:
                time.append(header[:6])  # 文件记录的采集结束时间
                data.append(bin2numpy(file_path, 0, channels_num))

            sampling_times_text = str(sampling_time) if len(set(file_sampling_times)) == 1 \
                else '、'.join(map(str, file_sampling_times))

            self.acquisition_params = {
                '文件记录结束时间': f'{"-".join(f(time[0]))} 至 {"-".join(f(time[-1]))}',
                '文件格式': '.bin',
                '采样频率': f'{sampling_rate:g}Hz',
                '传感点数（通道数）': f'{channels_num}',
                '单个文件采样点数': sampling_times_text,
            }

        elif suffix == '.dat':
            raw_data = np.fromfile(first_file_path, dtype='<f4')
            if self.is_scouter:
                channels_num = int(raw_data[16])  # 传感点数
                for file in self.file_names:
                    raw_data = np.fromfile(self.dataFilePath(file), dtype='<f4')
                    time.append(raw_data[:6])  # 文件记录的采集结束时间
                    data.append(raw_data[64:].reshape(channels_num, -1, order='F'))
                acquisition_modes = {
                    1.: 'CNTE 连续模式',
                    2.: 'PTRI 预触发模式',
                    3.: 'WTRI 等待触发模式'
                }

                fiber_types = {
                    1.: 'SMF 单模光纤',
                    2.: 'MMF 多模光纤',
                    3.: 'MSF 微结构光纤'
                }
                acquisition_mode = raw_data[6]  # 采集模式
                fiber_type = raw_data[7]  # 光纤类型
                physical_fiber_length = raw_data[8]  # 光纤长度，m
                refractive_index = raw_data[9]  # 反射率
                sampling_rate = int(raw_data[10])  # 采样率
                pulse_width = raw_data[11]  # 脉冲宽度，ns
                gauge_length = raw_data[12]  # 道间距，m
                spatial_resolution = raw_data[13]  # 空间分辨率，m
                start_distance = raw_data[14]  # 开始位置，m
                stop_distance = raw_data[15]  # 结束位置，m
                sampling_time = int(raw_data[17])  # 连续采集时间，即一个文件时长，s
                p = raw_data[18]  # P 系数
                time_decimation = raw_data[19]  # 时间系数
                number = raw_data[20]  # 滑动系数
                window = raw_data[21]  # 窗类型
                cutoff = raw_data[22]  # 截止阈值
                gain1 = raw_data[23]  # 增益 1
                gain2 = raw_data[24]  # 增益 2
                optical_power = raw_data[25]  # 光功率
                scan_threshold = raw_data[26]  # 扫描阈值
                trigger_level = raw_data[27]  # 触发脉宽阈值，ns
                acquisition_time = raw_data[28]  # 触发采集时间，s
                trigger_interval = raw_data[29]  # 触发间隔，s

                self.acquisition_params = {
                    '文件记录结束时间': f'{"-".join(f(time[0]))} 至 {"-".join(f(time[-1]))}',
                    '采集模式': f'{acquisition_modes[acquisition_mode]}',
                    '光纤类型': f'{fiber_types[fiber_type]}',
                    '光纤长度': f'{physical_fiber_length:.3f}m',
                    '反射率': f'{refractive_index:.3f}',
                    '采样频率': f'{sampling_rate}Hz',
                    '脉冲宽度': f'{pulse_width}ns',
                    '道间距': f'{gauge_length}m',
                    '空间分辨率': f'{spatial_resolution:.3f}m',
                    '测量开始位置': f'{start_distance:.3f}m',
                    '测量结束位置': f'{stop_distance:.3f}m',
                    '传感点数（通道数）': f'{channels_num}',
                    '单个文件采样点数': f'{sampling_time * sampling_rate}',
                    '计算系数 P': f'{p}',
                    '降采样时间系数': f'{time_decimation}',
                    '窗口滑动平均系数': f'{number}',
                    '窗类型': f'{window}',
                    '截止阈值': f'{cutoff:.3f}',
                    '接受增益 1': f'{gain1}',
                    '接受增益 2': f'{gain2}',
                    '输出光功率': f'{optical_power}',
                    '微结构扫描阈值': f'{scan_threshold}',
                    '触发采集模式脉冲阈值': f'{trigger_level}ns',
                    '触发采集模式采集间隔': f'{trigger_interval:.3f}s',
                    '等待出发采集模式采集时间': f'{acquisition_time}s'
                }

            else:
                sampling_rate, channels_num = int(raw_data[6]), int(raw_data[9])  # 采样率，通道数
                sampling_time = (len(raw_data) - 10) // channels_num
                for file in self.file_names:
                    raw_data = np.fromfile(self.dataFilePath(file), dtype='<f4')
                    time.append(raw_data[:6])  # 文件记录的采集结束时间
                    data.append(raw_data[10:].reshape(channels_num, -1))

                self.acquisition_params = {
                    '文件记录结束时间': f'{"-".join(f(time[0]))} 至 {"-".join(f(time[-1]))}',
                    '采样频率': f'{sampling_rate}Hz',
                    '传感点数（通道数）': f'{channels_num}',
                    '单个文件采样点数': f'{sampling_time}',
                }

        else:
            raise ValueError(f'不支持的数据格式：{suffix}')

        sample_counts = [int(array.shape[1]) for array in data]
        total_samples = sum(sample_counts)
        ensure_memory_budget(
            channels_num,
            total_samples,
            4.5,
            '多文件拼接加载',
        )
        source_paths = [self.dataFilePath(file) for file in self.file_names]
        self.data_group = DataGroup.from_files(
            source_paths,
            sample_counts,
            channels_num,
            sampling_rate,
        )
        self.selected_file_segment_index = None
        self.time = time
        self._source_time_headers = [tuple(map(float, values[:6])) for values in time]
        self.rebuildDataTimeline()
        self.data = detrendData(np.concatenate(data, axis=1))  # （通道数，采样次数）
        # Keep an immutable baseline so the new two-dimensional filter dialog
        # can preview, undo, and restore results without rereading the files.
        self.raw_data = np.asarray(self.data, dtype=np.float32).copy()
        self.raw_data.setflags(write=False)
        self.origin_data = self.raw_data.copy()
        # Parameter presets live across data groups, while the applied chain is
        # local to the group. Keep the most recent non-empty chain for explicit reuse.
        if self._das_filter_steps:
            self._last_das_filter_steps = clone_steps(self._das_filter_steps)
            self._last_das_filter_shape = previous_filter_shape
        self._das_filter_steps = []
        self._vehicle_tracking_settings = None
        self.vehicle_trajectories = []
        self._hide_vehicle_trajectories = False
        self.speed_ruler_points = None
        self.sampling_rate = sampling_rate
        self.channels_num = channels_num
        self.sampling_times = self.data.shape[1]
        self.acquisition_params['总采样点数'] = f'{self.sampling_times}'
        self.acquisition_params['拼接文件数'] = f'{len(self.data_group.segments)}'
        self.acquisition_params['拼接顺序'] = ' → '.join(
            segment.name for segment in self.data_group.segments
        )
        self.updateStitchedFilesList()

    def dataFilePath(self, file_name):
        """
        获取数据文件绝对路径。
        """
        file_name = str(file_name)
        return file_name if os.path.isabs(file_name) else os.path.join(self.file_path, file_name)

    @staticmethod
    def dataFileSuffix(file_name):
        """
        获取数据文件后缀。
        """
        return os.path.splitext(str(file_name))[1].lower()

    def exportData(self):
        """
        导出数据
        Returns:

        """
        fpath, ftype = QFileDialog.getSaveFileName(self, '导出', '', 'csv(*.csv);;json(*.json);;pickle(*.pickle);;'
                                                                     'txt(*.txt);;xls(*.xls *.xlsx)')

        data = pd.DataFrame(self.data)  # 保存为df

        if ftype.find('*.txt') > 0:  # txt以空格分隔
            data.to_csv(fpath, sep=' ', index=False, header=False)
        elif ftype.find('*.csv') > 0:  # csv以逗号分隔
            data.to_csv(fpath, sep=',', index=False, header=False)
        elif ftype.find('*.xls') > 0:  # xls以制表符分隔
            data.to_csv(fpath, sep='\t', index=False, header=False)
        elif ftype.find('*.json') > 0:
            data.to_json(fpath, orient='values')
        elif ftype.find('*.pickle') > 0:
            data.to_pickle(fpath)

    def showDASPyConverterDialog(self):
        """Open the standalone BIN-to-DASPy export dialog."""
        DASPyConverterDialog(self).exec_()

    def changeReadMode(self):
        """
        修改读取模式
        Returns:

        """
        self.read_mode_action.setText(f'读取模式：{"普通采集" if self.is_scouter else "scouter 采集"}')
        self.is_scouter = ~self.is_scouter

    def showAcquisitionParams(self):
        """
        打印采集参数
        Returns:

        """
        dialog = Dialog()
        dialog.setWindowTitle('采集参数')
        dialog.resize(450, 650)
        text_edit = TextEdit()
        for k, v in self.acquisition_params.items():
            text_edit.append(f'{k}: {v}')

        vbox = QVBoxLayout()
        vbox.addWidget(text_edit)

        dialog.setLayout(vbox)
        dialog.exec_()

    # """------------------------------------------------------------------------------------------------------------"""
    """计算信噪比调用函数"""

    def calculateSNR(self):
        """
        计算信噪比
        Returns:

        """
        if not self.snr_calculator:
            self.snr_calculator = SNRCalculator()
        self.snr_calculator.run(self.data, self.sampling_rate)

    # """------------------------------------------------------------------------------------------------------------"""
    """操作-查看数据（时间）调用函数"""

    def applyTimeCorrectionFromSidebar(self):
        """Persist the sidebar value only after its explicit Apply action."""

        self.setTimeCorrectionSeconds(self.time_correction_spin_box.value())

    def setTimeCorrectionSeconds(self, correction_seconds: float):
        """Persist a correction and refresh all corrected-time dependent views."""

        self.time_correction_seconds = float(correction_seconds)
        self.preferences.set_time_correction_seconds(self.time_correction_seconds)
        self.rebuildDataTimeline()
        self.updateDataGPSTime()
        self.updateStitchedFilesList()
        self.updateVideoAnnotationDataContext()
        self.refreshVideoAnnotationTable(select_identifier=self.video_annotation_selected_id)
        if hasattr(self, 'data'):
            self.updateImages()
        self.statusBar().showMessage(
            f'时间修正已保存：记录时间 {self.time_correction_seconds:+.3f} s。',
            8000,
        )

    def showTimeCorrectionDialog(self):
        """Edit and persist the correction added to device-recorded end times."""

        dialog = Dialog()
        dialog.setWindowTitle('时间校正设置')
        dialog.setMinimumWidth(520)
        correction = QDoubleSpinBox()
        correction.setRange(-86400.0, 86400.0)
        correction.setDecimals(3)
        correction.setSingleStep(0.1)
        correction.setSuffix(' s')
        correction.setValue(self.time_correction_seconds)
        correction.setToolTip('设备时间落后真实时间时填正数；例如落后 12 秒填写 12')

        formula = Label('计算公式：推算实际时间 = 文件名/文件头记录时间 + 修正秒数')
        formula.setWordWrap(True)
        example = Label('例如手机为 01:00:12、设备为 01:00:00，应填写 +12.000 s。')
        example.setWordWrap(True)
        example.setStyleSheet('color: #555;')
        save_button = PushButton('保存并应用')
        cancel_button = PushButton('取消')

        def save():
            self.setTimeCorrectionSeconds(correction.value())
            dialog.accept()

        save_button.clicked.connect(save)
        cancel_button.clicked.connect(dialog.reject)
        form = QFormLayout()
        form.addRow('设备记录时间修正', correction)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(formula)
        layout.addWidget(example)
        layout.addLayout(buttons)
        dialog.setLayout(layout)
        dialog.exec_()

    def setTimeRangeDialog(self):
        """
        调用按时间查看数据范围的对话框
        Returns:

        """
        dialog = Dialog()
        dialog.setWindowTitle('查看数据（时间）')

        from_label = Label('始')
        self.time_range_from_line_edit = LineEditWithReg(digit=True)
        self.time_range_from_line_edit.setText(str((self.sampling_times_from_num - 1) / self.sampling_rate))
        to_label = Label('止')
        self.time_range_to_line_edit = LineEditWithReg(digit=True)
        self.time_range_to_line_edit.setText(str(self.sampling_times_to_num / self.sampling_rate))

        btn = PushButton('确定')
        btn.clicked.connect(self.setTimeRange)
        btn.clicked.connect(self.updateDataRange)
        btn.clicked.connect(self.updateDataParams)
        btn.clicked.connect(self.updateDataGPSTime)
        btn.clicked.connect(self.updateImages)
        btn.clicked.connect(dialog.close)

        hbox = QHBoxLayout()
        vbox = QVBoxLayout()
        hbox.addWidget(from_label)
        hbox.addWidget(self.time_range_from_line_edit)
        hbox.addStretch(1)
        hbox.addWidget(to_label)
        hbox.addWidget(self.time_range_to_line_edit)
        vbox.addLayout(hbox)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def setTimeRange(self):
        """
        根据设置时间截取数据
        Returns:

        """
        from_num = int(float(self.time_range_from_line_edit.text()) * self.sampling_rate)
        to_num = int(float(self.time_range_to_line_edit.text()) * self.sampling_rate)

        if 0 <= from_num < self.origin_data.shape[1] and 1 < to_num <= self.origin_data.shape[1]:
            if from_num > to_num:
                from_num, to_num = to_num, from_num
        else:
            from_num, to_num = 0, self.origin_data.shape[1]

        self.sampling_times_from_num, self.sampling_times_to_num = from_num + 1, to_num
        self.setEventSampleRange(from_num, to_num)
        self.syncDASFilterVisibleRange()

    # """------------------------------------------------------------------------------------------------------------"""
    """查看数据（通道）调用函数"""

    def setChannelRangeDialog(self):
        """
        按通道截取数据的对话框
        Returns:

        """
        dialog = Dialog()
        dialog.setWindowTitle('查看数据（通道）')

        from_label = Label('始')
        self.channel_from = LineEditWithReg()
        self.channel_from.setText(str(self.channel_from_num))
        to_label = Label('止')
        self.channel_to = LineEditWithReg()
        self.channel_to.setText(str(self.channel_to_num))

        btn = PushButton('确定')
        btn.clicked.connect(self.setChannelRange)
        btn.clicked.connect(self.updateDataRange)
        btn.clicked.connect(self.updateDataParams)
        btn.clicked.connect(self.updateImages)
        btn.clicked.connect(dialog.close)

        vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        hbox.addWidget(from_label)
        hbox.addWidget(self.channel_from)
        hbox.addStretch(1)
        hbox.addWidget(to_label)
        hbox.addWidget(self.channel_to)

        vbox.addLayout(hbox)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def setChannelRange(self):
        """
        以通道数截取
        Returns:

        """
        from_num, to_num = int(self.channel_from.text()), int(self.channel_to.text())

        if 1 <= from_num < self.origin_data.shape[0] and 1 < to_num <= self.origin_data.shape[0]:
            if from_num > to_num:
                from_num, to_num = to_num, from_num
        elif from_num == 0 and 1 < to_num <= self.origin_data.shape[0]:
            from_num = 1
        else:
            from_num, to_num = 1, self.origin_data.shape[0]

        self.channel_from_num, self.channel_to_num = from_num, to_num

    # """------------------------------------------------------------------------------------------------------------"""
    """更改读取通道号步长、读取文件数调用的函数"""

    def changeChannelNumberStep(self):
        """
        改变通道号的步长
        Returns:

        """
        dialog = Dialog()
        dialog.setFixedWidth(400)
        dialog.setWindowTitle('设置通道切换步长')

        channel_number_step_label = Label('步长')
        self.channel_number_step_line_edit = LineEditWithReg()
        self.channel_number_step_line_edit.setToolTip('切换通道时的步长')
        self.channel_number_step_line_edit.setText(str(self.channel_number_step))

        btn = PushButton('确定')
        btn.clicked.connect(self.updateChannelNumberStep)
        btn.clicked.connect(dialog.close)

        vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        hbox.addWidget(channel_number_step_label)
        hbox.addWidget(self.channel_number_step_line_edit)
        vbox.addLayout(hbox)
        vbox.addSpacing(5)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def updateChannelNumberStep(self):
        """
        更新读取通道号的步长
        Returns:

        """
        self.channel_number_step = int(self.channel_number_step_line_edit.text())

        self.channel_number_spinbx.setSingleStep(self.channel_number_step)

    # """------------------------------------------------------------------------------------------------------------"""
    """绘制热力图调用函数"""

    def plotHeatMapImage(self):
        """
        绘制伪颜色图
        Returns:

        """
        plot_widget = MyPlotWidget('热力图', '推算时间', '通道', check_mouse=False, time_axis=True)
        plot_widget.setTimeOrigin(self.data_timeline.start_time if self.data_timeline is not None else None)
        self.tab_widget.addTab(plot_widget, '热力图')

        item = pg.ImageItem()
        item.setColorMap('viridis')
        self.addDataImageItem(plot_widget, item, self.data)
        self.drawFileBoundaries(plot_widget, 0, self.current_channels)
        self.drawEventRange(plot_widget)

    # """------------------------------------------------------------------------------------------------------------"""
    """绘制二值图调用函数"""

    def ployBinaryImage(self):
        """
        二值图设置组件
        Returns:

        """
        if not self.binary_image:
            self.binary_image = BinaryImageHandler()
        data = self.binary_image.run(self.data)

        if data is not None:
            plot_widget = MyPlotWidget('二值图', '推算时间', '通道', check_mouse=False, time_axis=True)
            plot_widget.setTimeOrigin(self.data_timeline.start_time if self.data_timeline is not None else None)
            self.tab_widget.addTab(plot_widget, f'二值图 - 阈值={self.binary_image.threshold}')

            item = pg.ImageItem()
            self.addDataImageItem(plot_widget, item, data)
            self.drawFileBoundaries(plot_widget, 0, self.current_channels)
            self.drawEventRange(plot_widget)

    # """------------------------------------------------------------------------------------------------------------"""
    """计算数据特征调用的函数"""

    def plotFeature(self):
        """
        获取要计算的数据特征名字和值
        Returns:

        """
        feature_name = self.plot_menu.sender().text()
        feature = FeatureCalculator(feature_name, self.data, self.sampling_rate).run()

        plot_widget = MyPlotWidget(feature_name + '图', '通道', '')
        x = xAxis(self.current_channels, 1, self.current_channels)
        plot_widget.draw(x, feature, pen=QColor('blue'))
        self.tab_widget.addTab(plot_widget, f'{feature_name}图')

    # """------------------------------------------------------------------------------------------------------------"""
    """绘制多通道云图调用函数"""

    def showMultiWavesTab(self):
        """定位到固定云图页；菜单入口不再创建临时 Tab。"""
        self.tab_widget.setCurrentWidget(self.multi_waves_container)
        self.plotMultiWavesImage()

    def plotMultiWavesImage(self):
        """按当前数据刷新固定的多通道云图页。"""
        if not hasattr(self, 'data') or self.data.size == 0:
            self.plot_multi_waves_widget.clear()
            return

        self.multi_waves_time_axis.setOrigin(
            self.data_timeline.start_time if self.data_timeline is not None else None
        )

        self.multi_waves_x = xAxis(self.current_sampling_times,
                                   self.sampling_times_from_num,
                                   self.sampling_times_to_num,
                                   self.sampling_rate)
        self.multi_waves_x_min = float(self.multi_waves_x[0])
        self.multi_waves_x_max = float(self.multi_waves_x[-1])
        if self.multi_waves_x_max <= self.multi_waves_x_min:
            self.multi_waves_x_max = self.multi_waves_x_min + 1 / self.sampling_rate

        self.multi_waves_channel_min = self.channel_from_num
        self.multi_waves_channel_max = self.channel_to_num
        full_time_width = self.multi_waves_x_max - self.multi_waves_x_min
        min_time_window_width = min(1 / self.sampling_rate, full_time_width)
        default_time_window_width = min(max(full_time_width / 5, min_time_window_width), full_time_width)

        previous_channel_from = self.multi_waves_channel_from_spin_box.value()
        previous_channel_to = self.multi_waves_channel_to_spin_box.value()
        should_reset = self.multi_waves_reset_pending or previous_channel_from < self.multi_waves_channel_min \
            or previous_channel_to > self.multi_waves_channel_max or previous_channel_from > previous_channel_to
        if should_reset:
            channel_from = self.multi_waves_channel_min
            channel_to = min(channel_from + 19, self.multi_waves_channel_max)
            self.multi_waves_time_from = self.multi_waves_x_min
            self.multi_waves_time_window_width = default_time_window_width
        else:
            channel_from = max(self.multi_waves_channel_min, previous_channel_from)
            channel_to = min(self.multi_waves_channel_max, previous_channel_to)
            self.multi_waves_time_window_width = min(
                max(getattr(self, 'multi_waves_time_window_width', default_time_window_width),
                    min_time_window_width), full_time_width)
            max_time_from = self.multi_waves_x_max - self.multi_waves_time_window_width
            self.multi_waves_time_from = min(max(getattr(self, 'multi_waves_time_from', self.multi_waves_x_min),
                                                  self.multi_waves_x_min), max_time_from)

        self.multi_waves_channel_from_spin_box.blockSignals(True)
        self.multi_waves_channel_to_spin_box.blockSignals(True)
        self.multi_waves_channel_from_spin_box.setRange(self.multi_waves_channel_min, self.multi_waves_channel_max)
        self.multi_waves_channel_to_spin_box.setRange(self.multi_waves_channel_min, self.multi_waves_channel_max)
        self.multi_waves_channel_from_spin_box.setValue(channel_from)
        self.multi_waves_channel_to_spin_box.setValue(channel_to)
        self.multi_waves_channel_from_spin_box.blockSignals(False)
        self.multi_waves_channel_to_spin_box.blockSignals(False)

        time_decimals = min(9, max(3, int(np.ceil(np.log10(max(self.sampling_rate, 1)))) + 1))
        for spin_box in (self.multi_waves_time_from_spin_box, self.multi_waves_time_to_spin_box):
            spin_box.blockSignals(True)
            spin_box.setDecimals(time_decimals)
            spin_box.setRange(self.multi_waves_x_min, self.multi_waves_x_max)
            spin_box.setSingleStep(min_time_window_width)
            spin_box.blockSignals(False)

        self.multi_waves_view_box.setLimits(
            xMin=self.multi_waves_x_min, xMax=self.multi_waves_x_max,
            yMin=self.multi_waves_channel_min - 0.5, yMax=self.multi_waves_channel_max + 0.5,
            minXRange=min_time_window_width, maxXRange=full_time_width,
            minYRange=1, maxYRange=self.current_channels)
        self.multi_waves_reset_pending = False
        self.drawMultiWavesVisibleChannels()

    def drawMultiWavesVisibleChannels(self):
        """重绘当前选定的云图通道，并保持视图范围在新数据边界内。"""
        if not hasattr(self, 'multi_waves_x'):
            return
        channel_from = self.multi_waves_channel_from_spin_box.value()
        channel_to = self.multi_waves_channel_to_spin_box.value()
        self.plot_multi_waves_widget.clear()
        for channel_number in range(channel_from, channel_to + 1):
            self.plot_multi_waves_widget.plot(
                self.multi_waves_x,
                self.data[channel_number - self.multi_waves_channel_min] + channel_number,
                pen=QColor(self.multi_waves_colors[(channel_number - 1) % len(self.multi_waves_colors)]))
        self.drawFileBoundaries(
            self.plot_multi_waves_widget,
            channel_from - 0.5,
            channel_to + 0.5,
        )
        self.drawEventRange(self.plot_multi_waves_widget)
        self.updateMultiWavesViewRange()

    def updateMultiWavesViewRange(self):
        """同步云图的按钮导航状态、标签和 ViewBox 范围。"""
        channel_from = self.multi_waves_channel_from_spin_box.value()
        channel_to = self.multi_waves_channel_to_spin_box.value()
        max_time_from = self.multi_waves_x_max - self.multi_waves_time_window_width
        self.multi_waves_time_from = min(max(self.multi_waves_time_from, self.multi_waves_x_min), max_time_from)
        self.multi_waves_view_box.setRange(
            xRange=(self.multi_waves_time_from,
                    self.multi_waves_time_from + self.multi_waves_time_window_width),
            yRange=(channel_from - 0.5, channel_to + 0.5), padding=0)
        self.multi_waves_channel_range_label.setText(f'通道：{channel_from} - {channel_to}')
        self.updateMultiWavesTimeDisplay()

    def updateMultiWavesTimeDisplay(self):
        """把当前时间窗口同步到输入框和提示文字。"""
        time_to = self.multi_waves_time_from + self.multi_waves_time_window_width
        self.multi_waves_time_from_spin_box.blockSignals(True)
        self.multi_waves_time_to_spin_box.blockSignals(True)
        self.multi_waves_time_from_spin_box.setValue(self.multi_waves_time_from)
        self.multi_waves_time_to_spin_box.setValue(time_to)
        self.multi_waves_time_from_spin_box.blockSignals(False)
        self.multi_waves_time_to_spin_box.blockSignals(False)
        if self.data_timeline is not None:
            absolute_from = self.data_timeline.absolute_time_for_sample(
                self.multi_waves_time_from * self.sampling_rate
            )
            absolute_to = self.data_timeline.absolute_time_for_sample(
                time_to * self.sampling_rate
            )
            self.multi_waves_time_range_label.setText(
                f'推算时间：{format_wall_time(absolute_from)} - {format_wall_time(absolute_to)}'
            )
        else:
            self.multi_waves_time_range_label.setText(
                f'时间：{self.multi_waves_time_from:.3f} - {time_to:.3f} s'
            )

    def syncMultiWavesTimeRange(self, _view_box, view_range):
        """鼠标平移或缩放后，同步云图的时间窗口状态和输入框。"""
        if not hasattr(self, 'multi_waves_x'):
            return
        time_from, time_to = view_range[0]
        if time_to <= time_from:
            return
        self.multi_waves_time_from = max(time_from, self.multi_waves_x_min)
        self.multi_waves_time_window_width = min(time_to - time_from,
                                                  self.multi_waves_x_max - self.multi_waves_x_min)
        self.updateMultiWavesTimeDisplay()

    def setMultiWavesChannelRange(self, channel_from: int, channel_to: int):
        """限制通道范围、同步输入框并重绘固定云图。"""
        channel_from = min(max(channel_from, self.multi_waves_channel_min), self.multi_waves_channel_max)
        channel_to = min(max(channel_to, channel_from), self.multi_waves_channel_max)
        self.multi_waves_channel_from_spin_box.blockSignals(True)
        self.multi_waves_channel_to_spin_box.blockSignals(True)
        self.multi_waves_channel_from_spin_box.setValue(channel_from)
        self.multi_waves_channel_to_spin_box.setValue(channel_to)
        self.multi_waves_channel_from_spin_box.blockSignals(False)
        self.multi_waves_channel_to_spin_box.blockSignals(False)
        self.drawMultiWavesVisibleChannels()

    def confirmMultiWavesChannelRange(self):
        """提交完整的多位通道输入，并防止起止通道颠倒。"""
        self.multi_waves_channel_from_spin_box.interpretText()
        self.multi_waves_channel_to_spin_box.interpretText()
        channel_from = self.multi_waves_channel_from_spin_box.value()
        channel_to = self.multi_waves_channel_to_spin_box.value()
        if channel_from > channel_to:
            printError('起始通道不能大于结束通道')
            return
        self.drawMultiWavesVisibleChannels()

    def confirmMultiWavesTimeRange(self):
        """提交输入的时间起止范围，并在该范围内显示云图。"""
        if not hasattr(self, 'multi_waves_x'):
            return
        self.multi_waves_time_from_spin_box.interpretText()
        self.multi_waves_time_to_spin_box.interpretText()
        time_from = self.multi_waves_time_from_spin_box.value()
        time_to = self.multi_waves_time_to_spin_box.value()
        minimum_width = min(1 / self.sampling_rate, self.multi_waves_x_max - self.multi_waves_x_min)
        if time_to - time_from < minimum_width:
            printError('结束时间必须至少比起始时间大一个采样间隔')
            return
        self.multi_waves_time_from = time_from
        self.multi_waves_time_window_width = time_to - time_from
        self.updateMultiWavesViewRange()

    def moveMultiWavesTime(self, direction: int):
        """按当前时间窗口宽度平移固定云图。"""
        if not hasattr(self, 'multi_waves_x'):
            return
        step = max(self.multi_waves_time_window_width * 0.8, 1 / self.sampling_rate)
        self.multi_waves_time_from += direction * step
        self.updateMultiWavesViewRange()

    def moveMultiWavesChannels(self, direction: int):
        """保持当前通道窗口宽度，向上或向下浏览云图。"""
        if not hasattr(self, 'multi_waves_x'):
            return
        channel_from = self.multi_waves_channel_from_spin_box.value()
        channel_to = self.multi_waves_channel_to_spin_box.value()
        width = channel_to - channel_from + 1
        step = max(1, width // 2)
        new_channel_from = min(max(channel_from + direction * step, self.multi_waves_channel_min),
                               self.multi_waves_channel_max - width + 1)
        self.setMultiWavesChannelRange(new_channel_from, new_channel_from + width - 1)

    # """------------------------------------------------------------------------------------------------------------"""
    """绘制应变图调用函数"""

    def plotStrain(self):
        """
        将相位差转为应变率再积分
        Returns:

        """
        data = self.data[self.channel_number - 1]
        x = xAxis(self.current_sampling_times,
                  self.sampling_times_from_num,
                  self.sampling_times_to_num,
                  self.sampling_rate)
        data = cumulative_trapezoid(data, x, initial=0) * 1e6
        plot_widget = MyPlotWidget('应变图', '推算时间', '应变（με）', grid=True, time_axis=True)
        plot_widget.setTimeOrigin(self.data_timeline.start_time if self.data_timeline is not None else None)
        plot_widget.draw(x, data, pen=QColor('blue'))
        self.drawEventRange(plot_widget)
        self.tab_widget.addTab(plot_widget, f'应变图 - 通道号={self.channel_number}')

    # """------------------------------------------------------------------------------------------------------------"""
    """绘制谱调用函数"""

    def plotSpectrum(self):
        """
        绘制各种谱
        Returns:

        """
        data = self.data[self.channel_number - 1]
        if not self.spectrum:
            self.spectrum = SpectrumHandler()
        ret = self.spectrum.run(data, self.sampling_times_from_num, self.sampling_times_to_num, self.sampling_rate)

        if ret is not None:
            self.tab_widget.addTab(ret, f'{self.spectrum.feature} - 通道号={self.channel_number}' + (
                f'\t窗口类型={self.spectrum.window_text}\t'
                f'帧长={self.spectrum.frame_length}\t'
                f'帧移={self.spectrum.frame_shift}'
                if self.spectrum.dimension != '1d' else ''))

    # """------------------------------------------------------------------------------------------------------------"""
    """Filter更新数据调用函数"""

    def updateUpdateDataMenu(self):
        """
        变更更新数据菜单
        Returns:

        """
        self.update_data_action.setText(f'更新数据（{"否" if self.update_data else "是"}）')
        self.update_data = ~self.update_data

    def updateData(self, data: np.array):
        """
        判断是否在滤波之后根据当前通道更新数据
        Args:
            data: 新数据

        Returns:

        """
        if self.update_data:
            self.clearVehicleTrajectories(update=False)
            self.origin_data[self.channel_number - 1] = data
            self.data = self.origin_data
            self.updateImages()

    def showVehicleTrackingDialog(self):
        """Open the non-destructive vehicle trajectory picker."""
        if self.raw_data is None or not hasattr(self, 'origin_data'):
            printError('请先导入 DAS 数据')
            return
        visible_range = (
            self.channel_from_num,
            self.channel_to_num,
            self.sampling_times_from_num,
            self.sampling_times_to_num,
        )
        dialog = VehicleTrackingDialog(
            self.origin_data,
            self.sampling_rate,
            visible_range=visible_range,
            settings=self._vehicle_tracking_settings,
            trajectories=self.vehicle_trajectories,
            parent=self,
        )
        self.vehicle_tracking_dialog = dialog
        dialog.trajectoriesChanged.connect(self.setVehicleTrajectories)
        dialog.exec_()
        self._vehicle_tracking_settings = dialog.settings()
        self.vehicle_tracking_dialog = None

    def setVehicleTrajectories(self, trajectories):
        """Persist analysis-only trajectories and refresh their image overlay."""
        self.vehicle_trajectories = list(trajectories)
        self._hide_vehicle_trajectories = False
        self.updateImages()
        count = len(self.vehicle_trajectories)
        self.statusBar().showMessage(
            f'车辆轨迹拾取结果已更新：{count} 条。结果仅叠加显示，不会修改数据。',
            6000,
        )

    def clearVehicleTrajectories(self, update: bool = True):
        """Discard paths whose source data have been replaced."""
        self.vehicle_trajectories = []
        self._hide_vehicle_trajectories = False
        if update and hasattr(self, 'origin_data'):
            self.updateImages()

    def showDASFilterDialog(self):
        """Select the persistent two-dimensional filter panel in the left sidebar."""
        if self.raw_data is None or not hasattr(self, 'origin_data'):
            printError('请先导入 DAS 数据')
            return

        visible_range = (
            self.channel_from_num,
            self.channel_to_num,
            self.sampling_times_from_num,
            self.sampling_times_to_num,
        )
        if self.das_filter_dialog is not None:
            self.das_filter_dialog.set_visible_range(visible_range)
            self.das_filter_dialog.set_saved_pipelines(self._filter_pipeline_history)
            self.sidebar_tabs.setCurrentWidget(self.filter_sidebar_widget)
            return

        dialog = DASFilterDialog(
            self.raw_data,
            self.sampling_rate,
            visible_range=visible_range,
            settings=self._das_filter_settings,
            steps=self._das_filter_steps,
            current_data=self.origin_data,
            segment_ranges=self.data_group.segment_ranges if self.data_group else None,
            previous_steps=self._last_das_filter_steps,
            auto_reapply=self.auto_reapply_filter_pipeline,
            embedded=True,
            parent=self.filter_sidebar_widget,
        )
        self.das_filter_dialog = dialog
        self.filter_sidebar_placeholder.hide()
        self.filter_sidebar_layout.addWidget(dialog)
        dialog.previewReady.connect(self.previewDASFilterData)
        dialog.committed.connect(self.commitDASFilterData)
        dialog.pipelineChanged.connect(self.setDASFilterPipeline)
        dialog.settingsChanged.connect(self.setDASFilterSettings)
        dialog.autoReapplyChanged.connect(self.setAutoReapplyFilter)
        dialog.pipelineConfirmedByUser.connect(self.rememberConfirmedFilterPipeline)
        dialog.savePipelineRequested.connect(self.saveCurrentFilterPipeline)
        dialog.loadPipelineRequested.connect(self.loadSavedFilterPipeline)
        dialog.deletePipelineRequested.connect(self.deleteSavedFilterPipeline)
        dialog.backRequested.connect(
            lambda: self.sidebar_tabs.setCurrentWidget(self.data_sidebar_widget)
        )
        dialog.set_saved_pipelines(self._filter_pipeline_history)
        if not self._das_filter_steps:
            dialog.set_draft_pipeline(
                self._defaultEventFilterPipeline(*self.raw_data.shape),
                '已载入默认车辆事件增强滤波链',
                new_identifiers=False,
            )
        dialog.show()
        self.sidebar_tabs.setCurrentWidget(self.filter_sidebar_widget)

    def _sidebarTabChanged(self, index: int):
        """Lazily initialize filtering when the user clicks the sidebar tab."""

        if self.sidebar_tabs.widget(index) is not self.filter_sidebar_widget:
            return
        if self.raw_data is None or not hasattr(self, 'origin_data'):
            self.filter_sidebar_placeholder.setText('请先在“数据”页导入 DAS 数据。')
            return
        if self.das_filter_dialog is None:
            QTimer.singleShot(0, self.showDASFilterDialog)

    def _workspaceTabChanged(self, _index: int):
        """Pair the video workspace with its visible video/annotation sidebar."""

        if self.tab_widget.currentWidget() is self.video_compare_container:
            if not self._video_focus_mode:
                self.sidebar_tabs.setVisible(True)
                self.sidebar_tabs.setCurrentWidget(self.annotation_sidebar_widget)
            return
        if self._video_focus_mode:
            self.video_focus_button.setChecked(False)

    def _rememberSidebarWidth(self, _position: int, _index: int):
        if not self.sidebar_tabs.isVisible():
            return
        sizes = self.main_splitter.sizes()
        if sizes and sizes[0] >= 380:
            self._preferred_sidebar_width = int(sizes[0])
            self.preferences.set_sidebar_width(self._preferred_sidebar_width)

    def syncDASFilterDialog(self):
        """Retarget an existing tool window after a successful data switch."""

        if self.das_filter_dialog is None or self.raw_data is None:
            return
        self._das_filter_settings = self.das_filter_dialog.filter_settings()
        visible_range = (
            self.channel_from_num,
            self.channel_to_num,
            self.sampling_times_from_num,
            self.sampling_times_to_num,
        )
        self.das_filter_dialog.set_data(
            self.raw_data,
            self.sampling_rate,
            visible_range,
            current_data=self.origin_data,
            steps=self._das_filter_steps,
            segment_ranges=self.data_group.segment_ranges if self.data_group else None,
            previous_steps=self._last_das_filter_steps,
        )
        self.das_filter_dialog.setAutoReapply(self.auto_reapply_filter_pipeline)
        replay_started = False
        if self.auto_reapply_filter_pipeline and self._last_das_filter_steps and not self._das_filter_steps:
            try:
                steps = self.adaptPreviousFilterSteps()
            except ValueError as error:
                self.das_filter_dialog.status_label.setText(f'未自动应用最近一次成功滤波链：{error}')
                self.statusBar().showMessage(f'未自动应用最近一次成功滤波链：{error}', 12000)
            else:
                replay_started = self.das_filter_dialog.replayExternalPipeline(
                    steps,
                    '切换文件后自动应用最近一次成功滤波链',
                    commit_after=True,
                )
                if replay_started:
                    self.statusBar().showMessage('正在从新文件原始数据自动应用最近一次成功滤波链……')
        if not replay_started and not self._das_filter_steps:
            self.das_filter_dialog.set_draft_pipeline(
                self._defaultEventFilterPipeline(*self.raw_data.shape),
                '已载入默认车辆事件增强滤波链',
                new_identifiers=False,
            )

    def setDASFilterPipeline(self, steps):
        self._das_filter_steps = clone_steps(steps)
        if self._das_filter_steps and self.raw_data is not None:
            self._last_das_filter_steps = clone_steps(self._das_filter_steps)
            self._last_das_filter_shape = tuple(self.raw_data.shape)
        self.reset_das_filter_action.setEnabled(bool(self._das_filter_steps))

    def setDASFilterSettings(self, settings):
        self._das_filter_settings = dict(settings)

    def setAutoReapplyFilter(self, enabled: bool):
        """Persist the cross-file filter replay preference."""

        self.auto_reapply_filter_pipeline = bool(enabled)
        self.preferences.set_auto_reapply_filter(self.auto_reapply_filter_pipeline)
        if self.das_filter_dialog is not None:
            self.das_filter_dialog.setAutoReapply(self.auto_reapply_filter_pipeline)

    def _persistFilterPipelineHistory(self):
        self._filter_pipeline_history = normalize_history(self._filter_pipeline_history)
        self.preferences.set_filter_pipeline_history(self._filter_pipeline_history)
        if self.das_filter_dialog is not None:
            self.das_filter_dialog.set_saved_pipelines(self._filter_pipeline_history)
        if self.video_filter_dialog is not None:
            self.video_filter_dialog.set_saved_pipelines(self._filter_pipeline_history)

    def saveCurrentFilterPipeline(self, name: str):
        """Save the visible working chain as a named cross-restart scheme."""

        if self.das_filter_dialog is None or self.raw_data is None:
            return
        steps = self.das_filter_dialog.pipeline_steps()
        try:
            entry = make_history_entry(
                name,
                'named',
                steps,
                self.raw_data.shape,
                self.sampling_rate,
            )
            self._filter_pipeline_history = upsert_named_history(
                self._filter_pipeline_history,
                entry,
            )
        except ValueError as error:
            QMessageBox.warning(self, '无法保存滤波方案', str(error))
            return
        self._persistFilterPipelineHistory()
        self.statusBar().showMessage(f'已保存滤波方案“{name}”，下次启动仍可载入。', 8000)

    def rememberConfirmedFilterPipeline(self, steps):
        """Store a deduplicated recent entry only after explicit user confirmation."""

        if self.raw_data is None or not steps:
            return
        name = datetime.now().strftime('最近使用 %m-%d %H:%M:%S')
        try:
            entry = make_history_entry(
                name,
                'recent',
                steps,
                self.raw_data.shape,
                self.sampling_rate,
            )
            self._filter_pipeline_history = add_recent_history(
                self._filter_pipeline_history,
                entry,
            )
        except ValueError as error:
            self.statusBar().showMessage(f'滤波链历史未保存：{error}', 8000)
            return
        self._persistFilterPipelineHistory()

    def deleteSavedFilterPipeline(self, identifier: str):
        previous_count = len(self._filter_pipeline_history)
        self._filter_pipeline_history = [
            entry for entry in self._filter_pipeline_history
            if str(entry.get('identifier')) != str(identifier)
        ]
        if len(self._filter_pipeline_history) == previous_count:
            return
        self._persistFilterPipelineHistory()
        self.statusBar().showMessage('已删除保存的滤波方案。', 5000)

    def _historyEntry(self, identifier: str):
        return next((
            entry for entry in self._filter_pipeline_history
            if str(entry.get('identifier')) == str(identifier)
        ), None)

    def loadSavedFilterPipeline(self, identifier: str):
        """Validate and load a saved chain into the editor without processing data."""

        if self.raw_data is None or self.das_filter_dialog is None:
            return
        entry = self._historyEntry(identifier)
        if entry is None:
            QMessageBox.warning(self, '无法载入滤波方案', '找不到所选滤波方案。')
            return
        try:
            steps = history_entry_steps(entry)
            adapted = self.adaptFilterStepsToCurrentData(
                steps,
                entry.get('source_shape'),
            )
            self.validateFilterStepsForCurrentData(adapted)
        except (TypeError, ValueError) as error:
            QMessageBox.warning(self, '滤波方案与当前数据不兼容', str(error))
            return
        if self.das_filter_dialog.set_draft_pipeline(
            adapted,
            f'已载入保存方案“{entry.get("name", "")}”',
        ):
            self.statusBar().showMessage(
                f'已载入滤波方案“{entry.get("name", "")}”；主图未改变，点击“应用滤波”后统一计算。',
                8000,
            )

    def adaptFilterStepsToCurrentData(self, steps, source_shape):
        """Adapt only source-wide bounds; keep custom ranges strict."""

        if self.raw_data is None:
            raise ValueError('当前没有可处理的新数据')
        new_channels, new_samples = map(int, self.raw_data.shape)
        try:
            old_channels, old_samples = map(int, source_shape)
        except (TypeError, ValueError):
            raise ValueError('保存的滤波方案缺少有效的源数据尺寸')
        if min(old_channels, old_samples) <= 0:
            raise ValueError('保存的滤波方案源数据尺寸无效')
        adapted = []
        for step in steps:
            channel_from, channel_to, sample_from, sample_to = step.selection
            if channel_from == 1 and channel_to == old_channels:
                channel_to = new_channels
            elif channel_to > new_channels:
                raise ValueError(
                    f'步骤“{step.label}”的通道范围 {channel_from}-{channel_to} '
                    f'超出当前数据 1-{new_channels}'
                )
            if sample_from == 1 and sample_to == old_samples:
                sample_to = new_samples
            elif sample_to > new_samples:
                raise ValueError(
                    f'步骤“{step.label}”的采样范围 {sample_from}-{sample_to} '
                    f'超出当前数据 1-{new_samples}'
                )
            adapted.append(FilterStep(
                algorithm=step.algorithm,
                parameters=step.parameters,
                selection=(channel_from, channel_to, sample_from, sample_to),
                label=step.label,
                enabled=step.enabled,
                processing_mode=step.processing_mode,
            ))
        return adapted

    def validateFilterStepsForCurrentData(self, steps):
        """Reject incompatible saved frequencies before starting a worker."""

        nyquist = self.sampling_rate / 2.0
        supported_algorithms = {algorithm for algorithm, _label in ALGORITHM_LABELS}
        for step in steps:
            if step.algorithm not in supported_algorithms:
                raise ValueError(
                    f'步骤“{step.label}”使用了未知滤波算法：{step.algorithm}'
                )
            parameters = step.parameters
            if step.algorithm in {'bandpass', 'bandstop'}:
                low = float(parameters.get('frequency_low', 0.0))
                high = float(parameters.get('frequency_high', 0.0))
                if not 0 < low < high < nyquist:
                    raise ValueError(
                        f'步骤“{step.label}”的频率 {low:g}-{high:g} Hz '
                        f'不适用于当前采样率 {self.sampling_rate:g} Hz'
                    )
            elif step.algorithm in {'lowpass', 'highpass'}:
                frequency = float(parameters.get('frequency', 0.0))
                if not 0 < frequency < nyquist:
                    raise ValueError(
                        f'步骤“{step.label}”的截止频率 {frequency:g} Hz '
                        f'不适用于当前采样率 {self.sampling_rate:g} Hz'
                    )
            elif step.algorithm == 'fk':
                high = float(parameters.get('fk_frequency_high', 0.0))
                spacing = float(parameters.get('channel_spacing', 0.0))
                if high and not 0 < high < nyquist:
                    raise ValueError(
                        f'步骤“{step.label}”的 F-K 频率上限 {high:g} Hz '
                        f'不适用于当前采样率 {self.sampling_rate:g} Hz'
                    )
                if spacing <= 0:
                    raise ValueError(f'步骤“{step.label}”的相邻通道距离 dx 必须大于 0')

    def adaptPreviousFilterSteps(self):
        """Retarget full-data steps and strictly validate custom ranges for new data."""

        if not self._last_das_filter_steps:
            return []
        if self._last_das_filter_shape is None:
            source_shape = self.raw_data.shape if self.raw_data is not None else (0, 0)
        else:
            source_shape = self._last_das_filter_shape
        return self.adaptFilterStepsToCurrentData(
            self._last_das_filter_steps,
            source_shape,
        )

    def syncDASFilterVisibleRange(self):
        if self.das_filter_dialog is None or self.das_filter_dialog.is_busy():
            return
        self.das_filter_dialog.set_visible_range((
            self.channel_from_num,
            self.channel_to_num,
            self.sampling_times_from_num,
            self.sampling_times_to_num,
        ))

    def previewDASFilterData(self, data: np.ndarray, description: str = ''):
        """Refresh all plots with a dialog preview without changing the baseline."""
        self._hide_vehicle_trajectories = True
        self.origin_data = np.asarray(data, dtype=np.float32).copy()
        self.updateDataRange()
        self.updateImages()
        if description:
            self.statusBar().showMessage(f'预览：{description}', 8000)

    def commitDASFilterData(self, data: np.ndarray):
        """Commit the dialog result as the current working data."""
        self.clearVehicleTrajectories(update=False)
        self.origin_data = np.asarray(data, dtype=np.float32).copy()
        self.updateDataRange()
        self.updateImages()
        self.reset_das_filter_action.setEnabled(bool(self._das_filter_steps))
        self.statusBar().showMessage('二维滤波结果已应用；可从“滤波”菜单恢复原始数据。', 8000)

    def resetDASFilterData(self):
        """Restore the detrended data loaded from disk."""
        if self.raw_data is None:
            return
        if self.das_filter_dialog is not None and self.das_filter_dialog.is_busy():
            printError('滤波链正在计算，请等待完成后再恢复原始数据')
            return
        if self.das_filter_dialog is not None:
            self.das_filter_dialog.restore_original()
            return
        self.clearVehicleTrajectories(update=False)
        self._das_filter_steps = []
        self.origin_data = np.asarray(self.raw_data, dtype=np.float32).copy()
        self.updateDataRange()
        self.updateImages()
        self.reset_das_filter_action.setEnabled(False)
        if self.das_filter_dialog is not None:
            self.syncDASFilterDialog()
        self.statusBar().showMessage('已恢复导入后的原始数据（包含现有去趋势步骤）。', 8000)

    # """------------------------------------------------------------------------------------------------------------"""
    """滤波-EMD调用函数"""

    def plotEMD(self):
        """
        EMD
        Returns:

        """
        data = self.data[self.channel_number - 1]
        if not self.emd:
            self.emd = EMDHandler()
        ret = self.emd.run(data, self.sampling_times_from_num, self.sampling_times_to_num, self.sampling_rate)

        if ret is not None:
            if self.emd.emd_options_flag:
                ret.widget().setFixedWidth(self.tab_widget.width())
                self.tab_widget.addTab(ret, f'{self.emd.emd_method} - 分解: 通道号={self.channel_number}\t'
                                            f'IMF数量={self.emd.imfs_res_num - 1}')
                self.emd_plot_ins_fre_action.setEnabled(True)
            else:
                reconstruct_imf = [int(i) for i in re.findall(r'\d+', self.emd.reconstruct_nums)]
                self.tab_widget.addTab(ret, f'{self.emd.emd_method} - 重构: 通道号={self.channel_number}\t'
                                            f'重构IMF={reconstruct_imf}')

                self.updateData(self.emd.data)

    def plotEMDInstantaneousFrequency(self):
        """
        绘制瞬时频率
        Returns:

        """
        ret = self.emd.calculateInstantaneousFrequency()
        ret.widget().setFixedWidth(self.tab_widget.width())
        self.tab_widget.addTab(ret, f'{self.emd.emd_method} - 瞬时频率: 通道号={self.channel_number}')

    # """------------------------------------------------------------------------------------------------------------"""
    """滤波-IIR滤波器调用函数"""

    def designIIRFilter(self):
        """
        设计iir滤波器
        Returns:

        """
        data = self.data[self.channel_number - 1]
        if not self.filter:
            self.filter = FilterHandler()
        ret = self.filter.run(self.filter_menu.sender().text(),
                              data,
                              self.sampling_times_from_num,
                              self.sampling_times_to_num,
                              self.sampling_rate)

        if ret is not None:
            if self.filter.method is not None:
                self.tab_widget.addTab(ret, f'IIR滤波器 - 通道号={self.channel_number}\t'
                                            f'滤波器={self.filter.filter_name}\t'
                                            f'滤波器类型={self.filter.method}')
            else:
                self.tab_widget.addTab(ret, f'IIR滤波器 - 通道号={self.channel_number}\t'
                                            f'滤波器={self.filter.filter_name}')

            self.updateData(self.filter.data)

    # """------------------------------------------------------------------------------------------------------------"""
    """小波菜单调用函数"""

    def plotCWT(self):
        """
        连续小波变换
        Returns:

        """
        data = self.data[self.channel_number - 1]
        if not self.cwt:
            self.cwt = CWTHandler()
        ret = self.cwt.run(data, self.sampling_times_from_num, self.sampling_times_to_num, self.sampling_rate)

        if ret is not None:
            self.tab_widget.addTab(ret, f'连续小波变换 - 通道号={self.channel_number}\t'
                                        f'小波={self.cwt.wavelet}\t'
                                        f'分解尺度数量={self.cwt.total_scales}')

    def plotDWT(self):
        """
        离散小波分解
        Returns:

        """
        data = self.data[self.channel_number - 1]
        if not self.dwt:
            self.dwt = DWTHandler()
        ret = self.dwt.run(data, self.sampling_times_from_num, self.sampling_times_to_num, self.sampling_rate)

        if ret is not None:
            if self.dwt.flag:
                ret.widget().setFixedWidth(self.tab_widget.width())
                self.tab_widget.addTab(ret, f'离散小波变换 - 分解: 通道号={self.channel_number}\t'
                                            f'小波={self.dwt.wavelet}\t'
                                            f'分解层数={self.dwt.decompose_level}')
            else:
                self.tab_widget.addTab(ret, f'离散小波变换 - 重构: 通道号={self.channel_number}\t'
                                            f'小波={self.dwt.wavelet}\t'
                                            f'系数={self.dwt.reconstruct}')

                self.updateData(self.dwt.data)

    def plotDWPT(self):
        """
        小波包变换
        Returns:

        """
        data = self.data[self.channel_number - 1]
        if not self.dwpt:
            self.dwpt = DWPTHandler()
        ret = self.dwpt.run(data, self.sampling_times_from_num, self.sampling_times_to_num, self.sampling_rate)

        if ret is not None:
            if self.dwpt.flag:
                ret.setFixedWidth(self.tab_widget.width())
                self.tab_widget.addTab(ret, f'小波包 - 分解: 通道号={self.channel_number}\t'
                                            f'小波={self.dwpt.wavelet}\t'
                                            f'分解层数={self.dwpt.decompose_level}')
            else:
                self.tab_widget.addTab(ret, f'小波包 - 重构: 通道号={self.channel_number}\t'
                                            f'小波={self.dwpt.wavelet}\t'
                                            f'子节点={self.dwpt.reconstruct}')
                self.updateData(self.dwpt.data)

    # """------------------------------------------------------------------------------------------------------------"""
    """其他-筛选数据"""

    def dataSiftingDialog(self):
        """
        信号检测
        Returns:

        """
        if not self.data_sift:
            self.data_sift = DataSifting(self)
        self.data_sift.runDialog()

    # """------------------------------------------------------------------------------------------------------------"""
