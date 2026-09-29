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
from datetime import datetime

import pandas as pd
from PyQt5 import QtMultimedia
from PyQt5.QtCore import Qt, QUrl, QEvent, QRectF, QTimer, QDateTime
from PyQt5.QtGui import QBrush, QColor, QPen
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, qApp, QTabWidget, QTableWidget, QAbstractItemView, \
    QTableWidgetItem, QHeaderView, QTabBar, QScrollBar, QHBoxLayout, QDoubleSpinBox, QSplitter, QVBoxLayout, QWidget, \
    QFormLayout, QGroupBox, QListWidget, QListWidgetItem, QGraphicsRectItem, QDateTimeEdit
from matplotlib import pyplot as plt
from scipy.integrate import cumulative_trapezoid

from image.image import *
from .classes.binary_image import BinaryImageHandler
from .classes.data_group import DataGroup, ensure_memory_budget, natural_sort_key
from .classes.data_timeline import DataTimeline, format_wall_time
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
from .classes.wavelet import DWTHandler, CWTHandler
from .classes.wavelet_packet import DWPTHandler
from .bin_reader import bin2numpy, read_bin_header
from .function import *
from .preferences import AppPreferences
from .theme import PLOT_LABEL_POINT_SIZE, PLOT_TICK_POINT_SIZE, PLOT_TITLE_POINT_SIZE, plot_font, plot_html, ui_font_family
from .widget import *
from .version import __version__


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
        self.raw_data = None
        self._das_filter_settings = None
        self._das_filter_steps = []
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
        setPicture(self, icon_jpg, 'icon.jpg', window_icon=True)

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
        file_area_vbox.setSpacing(8)

        self.file_path_line_edit = LineEdit(focus=False)
        self.file_path_line_edit.setPlaceholderText('选择数据文件夹')

        change_file_path_button = PushButton()
        setPicture(change_file_path_button, folder_jpg, 'folder.jpg', )
        change_file_path_button.setToolTip('选择数据文件夹')
        change_file_path_button.setAccessibleName('选择数据文件夹')
        change_file_path_button.clicked.connect(self.changeFilePath)

        file_table_scrollbar = QScrollBar(Qt.Vertical)
        file_table_scrollbar.setStyleSheet('min-height: 100')  # 设置滚动滑块的最小高度
        self.files_table_widget = QTableWidget(30, 1)
        self.files_table_widget.setVerticalScrollBar(file_table_scrollbar)
        self.files_table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)  # 设置表格不可编辑
        self.files_table_widget.setHorizontalHeaderLabels(['文件'])  # 设置表头
        self.files_table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.files_table_widget.verticalHeader().setVisible(False)
        self.files_table_widget.setWordWrap(False)
        self.files_table_widget.setAlternatingRowColors(True)
        self.files_table_widget.setToolTip(
            '鼠标悬停可查看完整路径；使用 Ctrl 或 Shift 选择多个文件，选择完成后点击确定加载'
        )
        QTableWidget.resizeRowsToContents(self.files_table_widget)
        self.files_table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)  # 设置一次选中一排内容
        self.files_table_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.files_table_widget.itemSelectionChanged.connect(self.updatePendingFileSelection)

        self.pending_file_selection_label = Label('待拼接：请选择文件')
        self.pending_file_selection_label.setWordWrap(True)
        self.pending_file_selection_label.setStyleSheet('color: #555;')
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
        self.stitched_files_list.setMinimumHeight(104)
        self.stitched_files_list.setMaximumHeight(220)
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
        self.time_correction_line_edit = LineEdit(focus=False)
        for field in (
                self.sampling_rate_line_edit,
                self.current_sampling_times_line_edit,
                self.current_channels_line_edit,
                self.gps_from_line_edit,
                self.gps_to_line_edit,
                self.time_correction_line_edit,
        ):
            field.setReadOnly(True)
            field.setFixedHeight(28)
            field.setStyleSheet('QLineEdit { min-height: 0; padding: 1px 4px; }')

        self.overview_group = QGroupBox('数据概览')
        self.overview_form = QFormLayout()
        self.overview_form.setContentsMargins(6, 4, 6, 4)
        self.overview_form.setHorizontalSpacing(6)
        self.overview_form.setVerticalSpacing(2)
        self.overview_form.addRow('采样率', self.sampling_rate_line_edit)
        self.overview_form.addRow('采样次数', self.current_sampling_times_line_edit)
        self.overview_form.addRow('通道数', self.current_channels_line_edit)
        self.overview_form.addRow('当前推算开始时间', self.gps_from_line_edit)
        self.overview_form.addRow('当前推算结束时间', self.gps_to_line_edit)
        self.overview_form.addRow('设备时间修正', self.time_correction_line_edit)
        self.overview_group.setLayout(self.overview_form)
        self.overview_group.setStyleSheet('QGroupBox { margin-top: 6px; padding-top: 4px; }')
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
        self.image_colormap_combx.currentTextChanged.connect(self.updateImageColorParams)

        image_level_min_label = Label('最小值(%)')
        self.image_level_min_line_edit = LineEdit()
        self.image_level_min_line_edit.setFixedWidth(90)
        self.image_level_min_line_edit.setPlaceholderText('自动')
        self.image_level_min_line_edit.setToolTip('相对于当前图像最大绝对值的百分比，例如 -80')

        image_level_max_label = Label('最大值(%)')
        self.image_level_max_line_edit = LineEdit()
        self.image_level_max_line_edit.setFixedWidth(90)
        self.image_level_max_line_edit.setPlaceholderText('自动')
        self.image_level_max_line_edit.setToolTip('相对于当前图像最大绝对值的百分比，例如 80')

        image_auto_button = PushButton('自动')
        image_auto_button.clicked.connect(self.autoImageLevels)

        image_apply_button = PushButton('应用')
        image_apply_button.clicked.connect(self.updateImageColorParams)

        image_controls_hbox = QHBoxLayout()
        image_controls_hbox.addWidget(image_colormap_label)
        image_controls_hbox.addWidget(self.image_colormap_combx)
        image_controls_hbox.addSpacing(10)
        image_controls_hbox.addWidget(image_level_min_label)
        image_controls_hbox.addWidget(self.image_level_min_line_edit)
        image_controls_hbox.addSpacing(5)
        image_controls_hbox.addWidget(image_level_max_label)
        image_controls_hbox.addWidget(self.image_level_max_line_edit)
        image_controls_hbox.addSpacing(10)
        image_controls_hbox.addWidget(image_auto_button)
        image_controls_hbox.addWidget(image_apply_button)
        image_controls_hbox.addStretch(1)

        speed_ruler_controls_hbox = QHBoxLayout()
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
        self.speed_ruler_status_label = Label('速度标尺未添加')
        self.speed_ruler_status_label.setStyleSheet('color: #555;')
        self.speed_ruler_status_label.setWordWrap(True)
        speed_ruler_controls_hbox.addWidget(Label('车辆速度标尺  dx'))
        speed_ruler_controls_hbox.addWidget(self.speed_ruler_spacing_spin_box)
        speed_ruler_controls_hbox.addWidget(self.speed_ruler_reset_button)
        speed_ruler_controls_hbox.addWidget(self.speed_ruler_remove_button)
        speed_ruler_controls_hbox.addWidget(self.speed_ruler_status_label, 1)

        # 绘制灰度图
        self.plot_gray_scale_widget = MyPlotWidget(
            '灰度图', '推算时间', '通道', check_mouse=False, time_axis=True
        )
        self.gray_scale_container = QWidget()
        gray_scale_vbox = QVBoxLayout()
        gray_scale_vbox.setContentsMargins(6, 6, 6, 6)
        gray_scale_vbox.setSpacing(6)
        gray_scale_vbox.addLayout(image_controls_hbox)
        gray_scale_vbox.addLayout(speed_ruler_controls_hbox)
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
        self.tab_widget.setMovable(True)  # 设置tab可移动
        self.tab_widget.setTabsClosable(True)  # 设置tab可关闭
        self.tab_widget.tabCloseRequested[int].connect(self.removeTab)
        self.tab_widget.addTab(self.gray_scale_container, '灰度图')
        self.tab_widget.addTab(combine_image_widget, '单通道')
        self.initMultiWavesTab()
        self.tab_widget.addTab(self.multi_waves_container, '多通道云图')
        self.tab_widget.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.tab_widget.tabBar().setTabButton(1, QTabBar.RightSide, None)  # 设置删除按钮消失
        self.tab_widget.tabBar().setTabButton(2, QTabBar.RightSide, None)

        self.event_range_widget = QWidget()
        event_range_hbox = QHBoxLayout()
        event_range_hbox.setContentsMargins(6, 4, 6, 4)
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
        self.event_range_set_button.setToolTip('移动图中的开始/结束竖线，不改变数据查看范围')
        self.event_range_view_button.setToolTip('按竖线范围更新当前视图，不修改导入原始数据')
        self.event_range_reset_button.setToolTip('恢复完整时间视图并把竖线重置到数据两端')
        self.event_range_set_button.clicked.connect(self.setEventRangeFromInputs)
        self.event_range_view_button.clicked.connect(self.viewEventRange)
        self.event_range_reset_button.clicked.connect(self.restoreFullEventRange)
        event_range_hbox.addWidget(Label('事件开始'))
        event_range_hbox.addWidget(self.event_range_from_edit)
        event_range_hbox.addWidget(Label('事件结束'))
        event_range_hbox.addWidget(self.event_range_to_edit)
        event_range_hbox.addWidget(self.event_range_set_button)
        event_range_hbox.addWidget(self.event_range_view_button)
        event_range_hbox.addWidget(self.event_range_reset_button)
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
        self.filter_sidebar_placeholder.setStyleSheet('color: #666; padding: 16px;')
        self.filter_sidebar_layout.addWidget(self.filter_sidebar_placeholder)

        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setMinimumWidth(420)
        self.sidebar_tabs.addTab(self.data_sidebar_widget, '数据')
        self.sidebar_tabs.addTab(self.filter_sidebar_widget, '二维滤波')
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
        self.main_splitter.setSizes([460, 1000])

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
        event.accept() if reply == QMessageBox.Yes else event.ignore()

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
        self.plot_gray_scale_widget.setTitle(plot_html(title, PLOT_TITLE_POINT_SIZE))
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

    def drawEventRange(self, plot_widget):
        """Draw two synchronized draggable time markers without obscuring the data."""

        if self.data_timeline is None or not hasattr(self, 'event_range_start_sample'):
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
        region.setZValue(16)
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

    def drawVehicleTrajectories(self):
        """Draw stored vehicle paths in the current image's local coordinates."""
        if self._hide_vehicle_trajectories or not self.vehicle_trajectories:
            return
        if not hasattr(self, 'sampling_times_from_num') or not hasattr(self, 'channel_from_num'):
            return

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
            self.plot_gray_scale_widget.plot(
                times[visible],
                local_channels,
                pen=pg.mkPen(color=color, width=2),
                connect='finite',
            )
            label = pg.TextItem(str(trajectory.identifier), color=color, anchor=(0, 1))
            label.setPos(float(times[visible][0]), float(local_channels[0]))
            self.plot_gray_scale_widget.addItem(label)

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

    def removeSpeedRuler(self):
        """Remove only the manual overlay; never modify DAS or trajectory data."""

        self.speed_ruler_active = False
        self.speed_ruler_points = None
        self._removeSpeedRulerGraphics()
        self.speed_ruler_status_label.setText('速度标尺未添加')
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
        self.speed_ruler_status_label.setText(
            format_speed_measurement(measurement).replace('\n', '  |  ')
        )

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
        finite_data = np.asarray(data)[np.isfinite(data)]
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

    def updateDataGPSTime(self):
        """Update corrected inferred times for the current visible sample range."""

        if self.data_timeline is None:
            self.gps_from_line_edit.clear()
            self.gps_to_line_edit.clear()
            self.time_correction_line_edit.setText(f'{self.time_correction_seconds:+.3f} s')
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
        self.time_correction_line_edit.setText(
            f'{self.time_correction_seconds:+.3f} s（记录时间 + 修正）'
        )
        self.plot_gray_scale_widget.setTimeOrigin(self.data_timeline.start_time)
        self.plot_single_channel_time_widget.setTimeOrigin(self.data_timeline.start_time)
        self.multi_waves_time_axis.setOrigin(self.data_timeline.start_time)
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
            self.time_correction_seconds = float(correction.value())
            self.preferences.set_time_correction_seconds(self.time_correction_seconds)
            self.rebuildDataTimeline()
            self.updateDataGPSTime()
            self.updateStitchedFilesList()
            if hasattr(self, 'data'):
                self.updateImages()
            self.statusBar().showMessage(
                f'时间修正已保存：记录时间 {self.time_correction_seconds:+.3f} s。',
                8000,
            )
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
        if self.auto_reapply_filter_pipeline and self._last_das_filter_steps and not self._das_filter_steps:
            try:
                steps = self.adaptPreviousFilterSteps()
            except ValueError as error:
                self.das_filter_dialog.status_label.setText(f'未自动应用最近一次成功滤波链：{error}')
                self.statusBar().showMessage(f'未自动应用最近一次成功滤波链：{error}', 12000)
            else:
                if self.das_filter_dialog.replayExternalPipeline(
                    steps,
                    '切换文件后自动应用最近一次成功滤波链',
                    commit_after=True,
                ):
                    self.statusBar().showMessage('正在从新文件原始数据自动应用最近一次成功滤波链……')

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
                reconstruct_imf = [int(i) for i in re.findall('\d+', self.emd.reconstruct_nums)]
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
