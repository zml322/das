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

import pandas as pd
from PyQt5 import QtMultimedia
from PyQt5.QtCore import QUrl, QEvent, QRectF
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, qApp, QTabWidget, QTableWidget, QAbstractItemView, \
    QTableWidgetItem, QHeaderView, QTabBar, QScrollBar, QHBoxLayout
from matplotlib import pyplot as plt
from scipy.integrate import cumulative_trapezoid

from image.image import *
from .classes.binary_image import BinaryImageHandler
from .classes.data_sifting import DataSifting
from .classes.emd import EMDHandler
from .classes.feature import FeatureCalculator
from .classes.filter import FilterHandler
from .classes.snr import SNRCalculator
from .classes.spectrum import SpectrumHandler
from .classes.wavelet import DWTHandler, CWTHandler
from .classes.wavelet_packet import DWPTHandler
from .bin_reader import bin2numpy, read_bin_header
from .function import *
from .widget import *


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        """
        初始化界面
        Returns:

        """
        super().__init__()
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
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Times New Roman']
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['axes.labelsize'] = 12
        plt.rcParams['axes.titlesize'] = 18
        plt.rcParams['xtick.labelsize'] = 10
        plt.rcParams['ytick.labelsize'] = 10

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
        self.files_read_number = 1  # 表格连续读取文件数

        # 滤波器是否更新数据
        self.update_data = False

        # 计算信噪比
        self.snr_calculator = None

        # 滤波器
        self.filter = None

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
        self.statusBar().setStyleSheet('font-size: 15px; font-family: "Times New Roman", "SimHei";')  # 状态栏
        self.menu_bar = self.menuBar()  # 菜单栏
        self.menu_bar.setStyleSheet('font-size: 17px; font-family: "Times New Roman", "SimHei";')
        self.setWindowTitle('DAS数据查看')
        setPicture(self, icon_jpg, 'icon.jpg', window_icon=True)

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('myappid')  # 设置任务栏图标

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
                                            '查看范围（时间）',
                                            '按时间设置数据查看范围',
                                            self.setTimeRangeDialog)

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

        # 操作-设置文件读取数量
        self.change_files_read_number_action = Action(self.operation_menu,
                                                      '设置文件读取数量',
                                                      '设置从表格选中文件时的读取数量，从选中的文件开始算起',
                                                      self.changeFilesReadNumberDialog)

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
                                                     self.plotMultiWavesImage)

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

        self.filter_menu.addSeparator()

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
        # 设置主窗口layout
        main_window_widget = QWidget()
        main_window_vbox = QVBoxLayout()
        main_window_hbox = QHBoxLayout()

        # 左侧
        # 文件区
        file_hbox = QHBoxLayout()
        file_area_vbox = QVBoxLayout()
        file_path_label = Label('文件路径')
        self.file_path_line_edit = LineEdit(focus=False)

        change_file_path_button = PushButton()
        setPicture(change_file_path_button, folder_jpg, 'folder.jpg', )
        change_file_path_button.clicked.connect(self.changeFilePath)

        file_table_scrollbar = QScrollBar(Qt.Vertical)
        file_table_scrollbar.setStyleSheet('min-height: 100')  # 设置滚动滑块的最小高度
        self.files_table_widget = QTableWidget(30, 1)
        self.files_table_widget.setVerticalScrollBar(file_table_scrollbar)
        self.files_table_widget.setStyleSheet('font-size: 17px; font-family: "Times New Roman", "Microsoft YaHei";')
        self.files_table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)  # 设置表格不可编辑
        self.files_table_widget.setHorizontalHeaderLabels(['文件'])  # 设置表头
        self.files_table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        QTableWidget.resizeRowsToContents(self.files_table_widget)
        QTableWidget.resizeColumnsToContents(self.files_table_widget)  # 设置表格排与列的宽度随内容改变
        self.files_table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)  # 设置一次选中一排内容
        self.files_table_widget.itemClicked.connect(self.selectDataFromTable)

        # 文件区布局
        file_hbox.addWidget(self.file_path_line_edit)
        file_hbox.addWidget(change_file_path_button)
        file_area_vbox.addWidget(file_path_label)
        file_area_vbox.addLayout(file_hbox)
        file_area_vbox.addWidget(self.files_table_widget)

        # 右侧
        # 参数
        sampling_rate_label = Label('采样率')
        self.sampling_rate_line_edit = LineEditWithReg(focus=False)

        sampling_times_label = Label('采样次数')
        self.current_sampling_times_line_edit = LineEditWithReg(focus=False)

        number_of_channels_label = Label('通道数')
        self.current_channels_line_edit = LineEditWithReg(focus=False)

        channel_number_label = Label('通道号')
        self.channel_number_spinbx = SpinBox()
        self.channel_number_spinbx.setValue(1)
        self.channel_number_spinbx.setMinimumWidth(100)
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

        # 数据参数布局
        data_params_hbox = QHBoxLayout()
        data_params_hbox.addWidget(channel_number_label)
        data_params_hbox.addWidget(self.channel_number_spinbx)
        data_params_hbox.addSpacing(20)
        data_params_hbox.addWidget(self.player_play_button)
        data_params_hbox.addSpacing(5)
        data_params_hbox.addWidget(self.player_stop_button)
        data_params_hbox.addSpacing(20)
        data_params_hbox.addWidget(sampling_rate_label)
        data_params_hbox.addWidget(self.sampling_rate_line_edit)
        data_params_hbox.addSpacing(5)
        data_params_hbox.addWidget(sampling_times_label)
        data_params_hbox.addWidget(self.current_sampling_times_line_edit)
        data_params_hbox.addSpacing(5)
        data_params_hbox.addWidget(number_of_channels_label)
        data_params_hbox.addWidget(self.current_channels_line_edit)

        # 图像颜色控制
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

        # 绘制灰度图
        self.plot_gray_scale_widget = MyPlotWidget('灰度图', '时间（s）', '通道', check_mouse=False)

        # 绘制单通道相位差-时间图
        self.plot_single_channel_time_widget = MyPlotWidget('相位差图', '时间（s）', '相位差（rad）', grid=True)

        # 绘制频谱图
        self.plot_amplitude_frequency_widget = MyPlotWidget('幅值图', '频率（Hz）', '幅值', grid=True)

        combine_image_widget = QWidget()
        image_vbox = QVBoxLayout()
        image_vbox.addWidget(self.plot_single_channel_time_widget)
        image_vbox.addWidget(self.plot_amplitude_frequency_widget)
        combine_image_widget.setLayout(image_vbox)

        self.tab_widget = QTabWidget()
        self.tab_widget.setMovable(True)  # 设置tab可移动
        self.tab_widget.setStyleSheet('font-size: 15px; font-family: "Times New Roman", "Microsoft YaHei";')
        self.tab_widget.setTabsClosable(True)  # 设置tab可关闭
        self.tab_widget.tabCloseRequested[int].connect(self.removeTab)
        self.tab_widget.addTab(self.plot_gray_scale_widget, '灰度图')
        self.tab_widget.addTab(combine_image_widget, '单通道')
        self.tab_widget.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.tab_widget.tabBar().setTabButton(1, QTabBar.RightSide, None)  # 设置删除按钮消失

        # GPS时间组件
        gps_from_label = Label('始')
        gps_to_label = Label('止')
        self.gps_from_line_edit = LineEdit(focus=False)
        self.gps_to_line_edit = LineEdit(focus=False)

        # GPS时间布局
        gps_hbox = QHBoxLayout()
        gps_hbox.addWidget(gps_from_label)
        gps_hbox.addWidget(self.gps_from_line_edit)
        gps_hbox.addSpacing(50)
        gps_hbox.addWidget(gps_to_label)
        gps_hbox.addWidget(self.gps_to_line_edit)

        # 右侧布局
        main_window_vbox.addSpacing(10)
        main_window_vbox.addLayout(data_params_hbox)
        main_window_vbox.addSpacing(6)
        main_window_vbox.addLayout(image_controls_hbox)
        main_window_vbox.addSpacing(10)
        main_window_vbox.addWidget(self.tab_widget)
        main_window_vbox.addSpacing(10)
        main_window_vbox.addLayout(gps_hbox)

        # 主页面
        main_window_hbox.addSpacing(10)
        main_window_hbox.addLayout(file_area_vbox)
        main_window_hbox.addSpacing(20)
        main_window_hbox.addLayout(main_window_vbox)
        main_window_hbox.addSpacing(10)
        main_window_hbox.setStretchFactor(file_area_vbox, 1)
        main_window_hbox.setStretchFactor(main_window_vbox, 4)  # 设置各部分所占比例
        main_window_widget.setLayout(main_window_hbox)
        self.setCentralWidget(main_window_widget)

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

    # """------------------------------------------------------------------------------------------------------------"""
    """继承mainwindow自带函数"""

    def closeEvent(self, event: QEvent):
        """
        退出时的提示
        Args:
            event: 事件

        Returns:

        """
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
        self.plot_gray_scale_widget.clear()
        title = '灰度图' if self.image_colormap == '灰度' else f'彩色图 - {self.image_colormap}'
        self.plot_gray_scale_widget.setTitle(f'<font face="Microsoft YaHei" size="5">{title}</font>')
        self.tab_widget.setTabText(0, title)

        item = pg.ImageItem()
        self.addDataImageItem(self.plot_gray_scale_widget, item, self.data, use_image_controls=True,
                              show_color_bar=True)

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

        x = xAxis(self.current_sampling_times,
                  self.sampling_times_from_num,
                  self.sampling_times_to_num,
                  self.sampling_rate)
        data = self.data[self.channel_number - 1]
        self.plot_single_channel_time_widget.draw(x, data, pen=QColor('blue'))

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
        当从文件列表中选择文件时更新图像等
        Returns:

        """
        self.file_names = []
        item_index = self.files_table_widget.currentIndex().row()  # 获取当前点击的文件行索引
        for i in range(self.files_read_number):
            if item_index + i + 1 > self.files_table_widget.rowCount():  # 如果读取文件数大于该文件下面剩余的文件数就只读到最后一个文件
                break
            self.file_names.append(self.files_table_widget.item(item_index + i, 0).text())

        self.readData()
        self.initLocalParams()
        self.updateAll()

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

        setPicture(self.player_play_button, play_jpg, 'play.jpg')
        self.player_play_button.setDisabled(False)
        self.player_stop_button.setDisabled(False)  # 设置播放按钮

    def updateFile(self):
        """
        更新文件列表显示
        Returns:

        """
        self.file_path_line_edit.setText(self.file_path)
        files = [f for f in os.listdir(self.file_path) if f.lower().endswith(DAS_FILE_SUFFIXES)]
        self.files_table_widget.setRowCount(len(files))  # 有多少个文件就显示多少行
        for i in range(len(files)):
            table_widget_item = QTableWidgetItem(files[i])
            self.files_table_widget.setItem(i, 0, table_widget_item)

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
        self.sampling_rate_line_edit.setText(str(self.sampling_rate))
        self.current_sampling_times_line_edit.setText(str(self.current_sampling_times))
        self.current_channels_line_edit.setText(str(self.current_channels))

    def updateDataGPSTime(self):
        """
        更新数据时间显示
        Returns:

        """

        def f(s):
            return list(map(str, map(int, s[:5]))) + [str(s[5])]

        from_time, to_time = f(self.time[0]), f(self.time[-1])
        from_time = ' - '.join(from_time)
        to_time = ' - '.join(to_time)

        self.gps_from_line_edit.setText(from_time)  # 更新开头文件GPS时间
        self.gps_to_line_edit.setText(to_time)  # 更新末尾文件GPS时间

    def updateImages(self):
        """
        更新4个随时更新的图像显示
        Returns:

        """
        self.plotGrayScaleImage()
        self.plotSingleChannelTime()
        self.plotAmplitudeFrequency()

    def updateAll(self):
        """
        总更新函数
        Returns:

        """
        self.updateWidgetsState()
        self.updateFile()
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
        file_names = QFileDialog.getOpenFileNames(self, '导入', '', DAS_FILE_FILTER)[0]  # 打开多个数据文件
        if file_names:
            self.file_names = file_names
            self.file_path = os.path.dirname(self.file_names[0])

            self.readData()
            self.initLocalParams()
            self.updateAll()

    def readData(self):
        """
        读取数据，更新参数
        Returns:

        """

        def f(s):
            return list(map(str, map(int, s[:5]))) + [str(s[5])]

        time, data = [], []
        suffixes = {self.dataFileSuffix(file) for file in self.file_names}
        if len(suffixes) != 1:
            raise ValueError('一次只能读取同一种格式的数据文件。')

        suffix = suffixes.pop()
        first_file_path = self.dataFilePath(self.file_names[0])
        if suffix == '.bin':
            first_header, sampling_time, channels_num, _ = read_bin_header(first_file_path)
            sampling_rate = self.binSamplingRate(first_header)
            for file in self.file_names:
                file_path = self.dataFilePath(file)
                header, file_sampling_time, file_channels_num, _ = read_bin_header(file_path)
                if file_channels_num != channels_num:
                    raise ValueError(f'{file_path}: 通道数不一致，期望 {channels_num}，实际 {file_channels_num}')
                time.append(header[:6])  # GPS时间
                data.append(bin2numpy(file_path, 0, channels_num).T)

            self.acquisition_params = {
                'GPS时间': f'{"-".join(f(time[0]))} 至 {"-".join(f(time[-1]))}',
                '文件格式': '.bin',
                '采样频率': f'{sampling_rate}Hz',
                '传感点数（通道数）': f'{channels_num}',
                '单个文件采样点数': f'{sampling_time}',
            }

        elif suffix == '.dat':
            raw_data = np.fromfile(first_file_path, dtype='<f4')
            if self.is_scouter:
                channels_num = int(raw_data[16])  # 传感点数
                for file in self.file_names:
                    raw_data = np.fromfile(self.dataFilePath(file), dtype='<f4')
                    time.append(raw_data[:6])  # GPS时间
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
                    'GPS时间': f'{"-".join(f(time[0]))} 至 {"-".join(f(time[-1]))}',
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
                    time.append(raw_data[:6])  # GPS时间
                    data.append(raw_data[10:].reshape(channels_num, -1))

                self.acquisition_params = {
                    'GPS时间': f'{"-".join(f(time[0]))} 至 {"-".join(f(time[-1]))}',
                    '采样频率': f'{sampling_rate}Hz',
                    '传感点数（通道数）': f'{channels_num}',
                    '单个文件采样点数': f'{sampling_time}',
                }

        else:
            raise ValueError(f'不支持的数据格式：{suffix}')

        self.time = time
        self.data = detrendData(np.concatenate(data, axis=1))  # （通道数，采样次数）
        self.origin_data = self.data
        self.sampling_rate = sampling_rate
        self.channels_num = channels_num
        self.sampling_times = self.data.shape[1]
        self.acquisition_params['总采样点数'] = f'{self.sampling_times}'

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

    def binSamplingRate(self, header):
        """
        从 .bin 头里读取采样率；缺失时沿用界面已有值，仍缺失则使用 1Hz。
        """
        sampling_rate = int(round(float(header[6]))) if len(header) > 6 and header[6] > 0 else 0
        if sampling_rate > 0:
            return sampling_rate
        if self.sampling_rate_line_edit.text():
            return int(self.sampling_rate_line_edit.text())
        return 1

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

    def changeFilesReadNumberDialog(self):
        """
        从表格选择文件时读取的文件数
        Returns:

        """
        dialog = Dialog()
        dialog.setFixedWidth(400)
        dialog.setWindowTitle('设置文件读取数量')

        files_read_number_label = Label('文件读取数量')
        self.files_read_number_line_edit = LineEditWithReg()
        self.files_read_number_line_edit.setToolTip('设置从表格选中文件时的读取数量，从选中的文件开始算起')
        self.files_read_number_line_edit.setText(str(self.files_read_number))

        btn = PushButton('确定')
        btn.clicked.connect(self.updateFilesReadNumber)
        btn.clicked.connect(self.updateImages)
        btn.clicked.connect(dialog.close)

        vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        hbox.addWidget(files_read_number_label)
        hbox.addWidget(self.files_read_number_line_edit)
        vbox.addLayout(hbox)
        vbox.addSpacing(5)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def updateFilesReadNumber(self):
        """
        更新读取文件数量
        Returns:

        """
        self.files_read_number = int(self.files_read_number_line_edit.text())

    # """------------------------------------------------------------------------------------------------------------"""
    """绘制热力图调用函数"""

    def plotHeatMapImage(self):
        """
        绘制伪颜色图
        Returns:

        """
        plot_widget = MyPlotWidget('热力图', '时间（s）', '通道', check_mouse=False)
        self.tab_widget.addTab(plot_widget, '热力图')

        item = pg.ImageItem()
        item.setColorMap('viridis')
        self.addDataImageItem(plot_widget, item, self.data)

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
            plot_widget = MyPlotWidget('二值图', '时间（s）', '通道', check_mouse=False)
            self.tab_widget.addTab(plot_widget, f'二值图 - 阈值={self.binary_image.threshold}')

            item = pg.ImageItem()
            self.addDataImageItem(plot_widget, item, data)

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

    def plotMultiWavesImage(self):
        """
        绘制带边界和按钮导航的多通道云图。
        Returns:

        """
        x = xAxis(self.current_sampling_times,
                  self.sampling_times_from_num,
                  self.sampling_times_to_num,
                  self.sampling_rate)
        x_min, x_max = float(x[0]), float(x[-1])
        if x_max <= x_min:
            x_max = x_min + 1 / self.sampling_rate

        # 鼠标用于精细平移和缩放；下方按钮用于按固定步长快速浏览。
        view_box = pg.ViewBox(enableMenu=False)
        plot_widget = pg.PlotWidget(viewBox=view_box)
        plot_widget.setTitle('<font face="Microsoft YaHei" size="5">多通道云图</font>')
        plot_widget.setLabel('bottom', '<font face="Microsoft YaHei" size="3">时间（s）</font>')
        plot_widget.setLabel('left', '<font face="Microsoft YaHei" size="3">通道</font>')
        plot_widget.getAxis('bottom').setTickFont(QFont('Times New Roman'))
        plot_widget.getAxis('left').setTickFont(QFont('Times New Roman'))
        plot_widget.getAxis('left').setWidth(50)
        plot_widget.showGrid(x=True, y=True, alpha=0.2)

        channel_min = self.channel_from_num
        channel_max = self.channel_to_num
        channel_from_spin_box = SpinBox()
        channel_to_spin_box = SpinBox()
        for spin_box in (channel_from_spin_box, channel_to_spin_box):
            spin_box.setRange(channel_min, channel_max)
            spin_box.setFixedWidth(90)
            # 输入多位通道号时不要在每个字符后立即触发重绘。
            spin_box.setKeyboardTracking(False)
        channel_from_spin_box.setValue(channel_min)
        channel_to_spin_box.setValue(min(channel_min + 19, channel_max))
        confirm_channel_button = PushButton('确认')

        channel_range_label = Label('')
        time_range_label = Label('')
        left_button = PushButton('←')
        right_button = PushButton('→')
        up_button = PushButton('↑')
        down_button = PushButton('↓')
        for button in (left_button, right_button, up_button, down_button):
            button.setFixedWidth(45)
        left_button.setToolTip('向前移动时间范围')
        right_button.setToolTip('向后移动时间范围')
        up_button.setToolTip('向更大通道号移动范围')
        down_button.setToolTip('向更小通道号移动范围')

        full_time_width = x_max - x_min
        time_window_width = max(full_time_width / 5, 1 / self.sampling_rate)
        time_window_width = min(time_window_width, full_time_width)
        state = {'time_from': x_min}
        colors = ['red', 'lime', 'deepskyblue', 'yellow', 'plum', 'gold', 'blue', 'fuchsia', 'aqua', 'orange']

        # 视图永远被限制在当前已选择的数据区域内。
        view_box.setLimits(xMin=x_min, xMax=x_max,
                           yMin=channel_min - 0.5, yMax=channel_max + 0.5,
                           minXRange=min(time_window_width, full_time_width), maxXRange=full_time_width,
                           minYRange=1, maxYRange=self.current_channels)

        def update_time_label():
            time_to = state['time_from'] + time_window_width
            time_range_label.setText(f'时间：{state["time_from"]:.3f} - {time_to:.3f} s')

        def update_view_range():
            channel_from = channel_from_spin_box.value()
            channel_to = channel_to_spin_box.value()

            view_box.setRange(xRange=(state['time_from'], state['time_from'] + time_window_width),
                              yRange=(channel_from - 0.5, channel_to + 0.5),
                              padding=0)
            channel_range_label.setText(f'通道：{channel_from} - {channel_to}')
            update_time_label()

        def draw_visible_channels():
            channel_from = channel_from_spin_box.value()
            channel_to = channel_to_spin_box.value()

            plot_widget.clear()
            for channel_number in range(channel_from, channel_to + 1):
                plot_widget.plot(x,
                                 self.data[channel_number - channel_min] + channel_number,
                                 pen=QColor(colors[(channel_number - 1) % len(colors)]))
            update_view_range()

        def set_channel_range(channel_from: int, channel_to: int):
            channel_from = max(channel_min, channel_from)
            channel_to = min(channel_max, channel_to)
            channel_from_spin_box.blockSignals(True)
            channel_to_spin_box.blockSignals(True)
            channel_from_spin_box.setValue(channel_from)
            channel_to_spin_box.setValue(channel_to)
            channel_from_spin_box.blockSignals(False)
            channel_to_spin_box.blockSignals(False)
            draw_visible_channels()

        def confirm_channel_range():
            # 提交编辑框中的完整文本，避免只读取到输入中的首位数字。
            channel_from_spin_box.interpretText()
            channel_to_spin_box.interpretText()
            if channel_from_spin_box.value() > channel_to_spin_box.value():
                printError('起始通道不能大于结束通道')
                return
            draw_visible_channels()

        def move_time(direction: int):
            step = max(time_window_width * 0.8, 1 / self.sampling_rate)
            max_time_from = x_max - time_window_width
            state['time_from'] = min(max(state['time_from'] + direction * step, x_min), max_time_from)
            update_view_range()

        def move_channels(direction: int):
            channel_from = channel_from_spin_box.value()
            channel_to = channel_to_spin_box.value()
            width = channel_to - channel_from + 1
            step = max(1, width // 2)
            new_channel_from = min(max(channel_from + direction * step, channel_min),
                                   channel_max - width + 1)
            set_channel_range(new_channel_from, new_channel_from + width - 1)

        confirm_channel_button.clicked.connect(confirm_channel_range)
        left_button.clicked.connect(lambda: move_time(-1))
        right_button.clicked.connect(lambda: move_time(1))
        up_button.clicked.connect(lambda: move_channels(1))
        down_button.clicked.connect(lambda: move_channels(-1))
        draw_visible_channels()

        controls_hbox = QHBoxLayout()
        controls_hbox.addWidget(Label('显示通道'))
        controls_hbox.addWidget(channel_from_spin_box)
        controls_hbox.addWidget(Label('至'))
        controls_hbox.addWidget(channel_to_spin_box)
        controls_hbox.addWidget(confirm_channel_button)
        controls_hbox.addSpacing(15)
        controls_hbox.addWidget(left_button)
        controls_hbox.addWidget(right_button)
        controls_hbox.addWidget(up_button)
        controls_hbox.addWidget(down_button)
        controls_hbox.addSpacing(15)
        controls_hbox.addWidget(channel_range_label)
        controls_hbox.addSpacing(15)
        controls_hbox.addWidget(time_range_label)
        controls_hbox.addStretch(1)

        container = QWidget()
        vbox = QVBoxLayout()
        vbox.addWidget(plot_widget)
        vbox.addLayout(controls_hbox)
        container.setLayout(vbox)
        self.tab_widget.addTab(container, '多通道云图')

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
        plot_widget = MyPlotWidget('应变图', '时间（s）', '应变（με）', grid=True)
        plot_widget.draw(x, data, pen=QColor('blue'))
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
            self.origin_data[self.channel_number - 1] = data
            self.data = self.origin_data
            self.updateImages()

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
