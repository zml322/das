# -*- coding: utf-8 -*-
"""
@Time    : 2024/10/1 下午3:00
@Author  : zxy
@File    : wavelet.py
"""
import re
from typing import Optional

import numpy as np
import pywt
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QScrollArea
from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from utils.function import xAxis, toAmplitude, initCombinedPlotWidget
from ui.widgets.custom_widgets import ComboBox, Label, LineEdit, RadioButton, CheckBox, LineEditWithReg, PushButton, Dialog, \
    MyPlotWidget


class CWTHandler:
    wavelet_families = pywt.families()
    wavelet_families = {x: [y for y in pywt.wavelist(kind='continuous') if y.startswith(x)] for x in wavelet_families}
    wavelet_families = {k: v for k, v in wavelet_families.items() if v}

    methods = ['conv', 'fft', 'auto']

    def __init__(self):
        self.data = None
        self.ret = None
        self.sampling_times = 0
        self.sampling_times_from = 0
        self.sampling_times_to = 0
        self.sampling_rate = 0

        self.family = 'cgau'  # 小波族
        self.wavelet = 'cgau1'  # 小波
        self.total_scales = 128  # 总分解尺度数量
        self.method = 'conv'  # 计算方式

    def runDialog(self):
        """
        设置选择的小波、总分解尺度数量和计算方式
        Returns:

        """
        dialog = Dialog()
        dialog.setWindowTitle('连续小波变换')

        label = Label('选择小波：')

        family_label = Label('小波族')
        self.family_combx = ComboBox()
        self.family_combx.addItems(self.wavelet_families.keys())
        self.family_combx.setCurrentText(self.family)
        self.family_combx.currentIndexChanged.connect(self.changeNameComboBox)

        name_label = Label('小波名称')
        self.name_combx = ComboBox()
        self.name_combx.setFixedWidth(75)
        self.name_combx.addItems(self.wavelet_families[self.family])
        self.name_combx.setCurrentText(self.wavelet)

        scale_label = Label('分解尺度数量')
        self.scale_line_edit = LineEditWithReg()
        self.scale_line_edit.setText(str(self.total_scales))
        self.scale_line_edit.setToolTip('分解尺度数量，通常为 2 的幂')

        method_label = Label('计算方式')
        self.method_combx = ComboBox()
        self.method_combx.addItems(self.methods)
        self.method_combx.setCurrentText(self.method)

        btn = PushButton('确定')
        btn.clicked.connect(self.updateParams)
        btn.clicked.connect(self.runCWT)
        btn.clicked.connect(dialog.close)

        vbox = QVBoxLayout()
        hbox1 = QHBoxLayout()
        hbox2 = QHBoxLayout()

        hbox1.addWidget(label)
        hbox1.addWidget(family_label)
        hbox1.addWidget(self.family_combx)
        hbox1.addStretch(1)
        hbox1.addWidget(name_label)
        hbox1.addWidget(self.name_combx)

        hbox2.addWidget(scale_label)
        hbox2.addWidget(self.scale_line_edit)
        hbox2.addStretch(1)
        hbox2.addWidget(method_label)
        hbox2.addWidget(self.method_combx)

        vbox.addSpacing(10)
        vbox.addLayout(hbox1)
        vbox.addSpacing(10)
        vbox.addLayout(hbox2)
        vbox.addSpacing(10)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def changeNameComboBox(self) -> None:
        """
        根据选择的小波族更改小波的名字
        Returns:

        """
        self.family = self.family_combx.currentText()
        self.name_combx.clear()
        self.name_combx.addItems(self.wavelet_families[self.family])
        self.name_combx.setCurrentIndex(0)

    def updateParams(self) -> None:
        """
        更新参数
        Returns:

        """
        self.total_scales = int(self.scale_line_edit.text())
        self.wavelet = self.name_combx.currentText()
        self.method = self.method_combx.currentText()

    def runCWT(self) -> None:
        """
        运行 cwt
        Returns:

        """
        cf = pywt.central_frequency(self.wavelet)
        scales = 2. * cf * self.total_scales / np.arange(1, self.total_scales + 1)
        t = xAxis(self.sampling_times, self.sampling_times_from, self.sampling_times_to, self.sampling_rate)
        coeff, fs = pywt.cwt(self.data, scales, self.wavelet, sampling_period=1. / self.sampling_rate)

        figure = plt.figure()
        plot_widget = FigureCanvas(figure)
        ax = plt.gca()
        ax.tick_params(axis='both', which='both', direction='in')
        im = ax.pcolormesh(t, fs, np.abs(coeff), shading='gouraud')
        ax.set_title('连续小波变换')
        ax.set_xlabel('时间（s）')
        ax.set_ylabel('频率（Hz）')
        plt.colorbar(im, ax=ax, pad=0.2)
        plt.xlim(self.sampling_times_from / self.sampling_rate, self.sampling_times_to / self.sampling_rate)
        plt.ylim(0, self.sampling_rate / 2)
        self.ret = plot_widget

    def run(self,
            data: np.array,
            sampling_times_from: int,
            sampling_times_to: int,
            sampling_rate: int) -> Optional[QWidget]:
        """
        计算 cwt、返回绘制图的组件
        Args:
            data: 数据
            sampling_times_from: 数据 x 轴起始
            sampling_times_to: 数据 x 轴终止
            sampling_rate: 采样率

        Returns: 含有 cwt 谱的绘图组件

        """
        self.ret = None
        self.data = data
        self.sampling_times = len(data)
        self.sampling_times_from = sampling_times_from
        self.sampling_times_to = sampling_times_to
        self.sampling_rate = sampling_rate
        self.runDialog()
        return self.ret


class DWTHandler:
    wavelet_families = pywt.families()
    wavelet_families = {x: [y for y in pywt.wavelist(kind='discrete') if y.startswith(x)] for x in wavelet_families}
    wavelet_families = {k: v for k, v in wavelet_families.items() if v}

    padding_modes = pywt.Modes.modes

    def __init__(self):
        self.data = None
        self.ret = None
        self.sampling_times = 0
        self.sampling_times_from = 0
        self.sampling_times_to = 0
        self.sampling_rate = 0

        self.flag = True  # 默认操作为分解
        # self.reconstruct = ['cA1', 'cD1']  # 重构系数名称
        self.family = 'bior'  # 小波族索引
        self.wavelet = 'bior1.1'  # 小波
        self.decompose_level = 3  # 分解层数
        self.decompose_level_calculated = False  # 是否使用函数计算最大分解层数
        self.padding_mode = 'zero'  # 数据填充模式

    def runDialog(self):
        """
        设置选择的小波、分解层数、填充模式
        Returns:

        """
        dialog = Dialog()
        dialog.setWindowTitle('离散小波变换')

        self.decompose_radiobtn = RadioButton('分解')
        self.decompose_radiobtn.setChecked(self.flag)

        reconstruct_radiobtn = RadioButton('重构')
        reconstruct_radiobtn.setChecked(not self.flag)

        # reconstruct_label = Label('重构系数')
        # self.reconstruct_line_edit = LineEdit()
        # self.reconstruct_line_edit.setFixedWidth(500)
        # self.reconstruct_line_edit.setToolTip('选择cAn和cDn系数进行重构，cAn为近似系数，cDn-cD1为细节系数')
        # self.reconstruct_line_edit.setText(str(self.reconstruct))

        # if not hasattr(self, 'coeffs'):
        #     reconstruct_radiobtn.setEnabled(False)
        #     reconstruct_label.setEnabled(False)
        #     self.reconstruct_line_edit.setEnabled(False)

        label = Label('选择小波：')

        family_label = Label('小波族')
        self.family_combx = ComboBox()
        self.family_combx.addItems(self.wavelet_families)
        self.family_combx.setCurrentText(self.family)
        self.family_combx.currentIndexChanged[int].connect(self.changeNameComboBox)

        name_label = Label('小波名称')
        self.name_combx = ComboBox()
        self.name_combx.setFixedWidth(75)
        self.name_combx.addItems(self.wavelet_families[self.family])
        self.name_combx.setCurrentText(self.wavelet)

        decompose_level_label = Label('分解层数')
        self.decompose_level_line_edit = LineEditWithReg()
        self.decompose_level_line_edit.setToolTip('分解层数')
        self.decompose_level_line_edit.setText(str(self.decompose_level))

        self.decompose_level_checkbx = CheckBox('使用计算的分解层数')
        self.decompose_level_checkbx.setToolTip('使用根据数据长度和选择的小波计算得到的分解层数')
        self.decompose_level_checkbx.setChecked(self.decompose_level_calculated)

        padding_mode_label = Label('填充模式')
        self.padding_mode_combx = ComboBox()
        self.padding_mode_combx.setToolTip('数据延长模式')
        self.padding_mode_combx.addItems(self.padding_modes)
        self.padding_mode_combx.setCurrentText(self.padding_mode)

        btn = PushButton('确定')
        btn.clicked.connect(self.updateParams)
        btn.clicked.connect(self.runDWT)
        btn.clicked.connect(dialog.close)

        vbox = QVBoxLayout()
        hbox1 = QHBoxLayout()
        # hbox2 = QHBoxLayout()
        hbox3 = QHBoxLayout()

        hbox1.addWidget(self.decompose_radiobtn)
        hbox1.addStretch(1)
        hbox1.addWidget(label)
        hbox1.addWidget(family_label)
        hbox1.addWidget(self.family_combx)
        hbox1.addWidget(name_label)
        hbox1.addWidget(self.name_combx)

        # hbox2.addWidget(reconstruct_radiobtn)
        # hbox2.addStretch(1)
        # hbox2.addWidget(reconstruct_label)
        # hbox2.addWidget(self.reconstruct_line_edit)

        hbox3.addWidget(decompose_level_label)
        hbox3.addWidget(self.decompose_level_line_edit)
        hbox3.addWidget(self.decompose_level_checkbx)
        hbox3.addStretch(1)
        hbox3.addWidget(padding_mode_label)
        hbox3.addWidget(self.padding_mode_combx)

        vbox.addSpacing(10)
        vbox.addLayout(hbox1)
        vbox.addSpacing(10)
        vbox.addLayout(hbox3)
        # vbox.addSpacing(10)
        # vbox.addLayout(hbox2)
        vbox.addSpacing(10)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def changeNameComboBox(self) -> None:
        """
        根据选择的小波族更改小波的名字
        Returns:

        """
        self.family = self.family_combx.currentText()
        self.name_combx.clear()
        self.name_combx.addItems(self.wavelet_families[self.family])
        self.name_combx.setCurrentIndex(0)

    def updateParams(self):
        """
        更新参数
        Returns:

        """
        # self.flag = self.decompose_radiobtn.isChecked()
        # self.reconstruct = self.reconstruct_line_edit.text()
        self.wavelet = self.name_combx.currentText()
        self.decompose_level = int(self.decompose_level_line_edit.text())
        self.decompose_level_calculated = self.decompose_level_checkbx.isChecked()
        self.padding_mode = self.padding_mode_combx.currentText()

    def runDWT(self):
        """
        分解或重构
        Returns:

        """
        if self.decompose_level_calculated:
            self.decompose_level = pywt.dwt_max_level(self.sampling_times, self.wavelet)  # 求最大分解层数

        if self.flag:
            self.coeffs = pywt.wavedec(self.data, wavelet=self.wavelet,
                                       mode=self.padding_mode,
                                       level=self.decompose_level)  # 求分解系数
            # self.reconstruct = []
            # self.reconstruct.append(f'cA{self.decompose_level}')
            # for i in range(len(self.coeffs) - 1, 0, -1):
            #     self.reconstruct.append(f'cD{i}')
            # self.former_reconstruct = self.reconstruct

        # else:
        #     rec_coeffs_split = str(self.reconstruct).split("'")
        #     rec_coeffs = []
        #     for i in rec_coeffs_split:
        #         coeff = re.match('^\w{2}\d+$', i)
        #         if coeff is not None:
        #             rec_coeffs.append(coeff.group())
        #     self.reconstruct = rec_coeffs  # 更新规范的重构系数显示
        #
        #     for i in self.former_reconstruct:
        #         if i not in rec_coeffs:  # 删除的系数置0
        #             if i == f'cA{self.decompose_level}':
        #                 self.coeffs[0] = np.zeros_like(self.coeffs[0])
        #             else:
        #                 number = int(re.match('^cD(\d+)$', i).group(1))
        #                 self.coeffs[-number] = np.zeros_like(self.coeffs[-number])

        if self.flag:
            wgt = QWidget()
            vbox1 = QVBoxLayout()
            vbox2 = QVBoxLayout()
            hbox = QHBoxLayout()
            scroll_area = QScrollArea()

            pw_time_list, pw_fre_list = [], []
            n = len(self.coeffs)
            for i, x in enumerate(self.coeffs):
                cur_n = len(x)
                if i == 0:
                    pw_time = MyPlotWidget('离散小波变换分解 - 时域', '', f'cA{self.decompose_level}（rad）')
                    pw_fre = MyPlotWidget('离散小波变换分解 - 频域', '', f'cA{self.decompose_level}')
                elif i == n - 1:
                    pw_time = MyPlotWidget('', '时间（s）', f'cD1（rad）')
                    pw_fre = MyPlotWidget('', '频率（Hz）', f'cD1')
                else:
                    pw_time = MyPlotWidget('', '', f'cD{n - i}（rad）')
                    pw_fre = MyPlotWidget('', '', f'cD{n - i}')

                x_time = xAxis(num=cur_n,
                               begin=self.sampling_times_from,
                               end=self.sampling_times_from + cur_n,
                               sampling_rate=self.sampling_rate)
                pw_time.setFixedHeight(150)
                pw_time.draw(x_time, x, pen=QColor('blue'))
                pw_time_list.append(pw_time)
                pw_time_list[i].setXLink(pw_time_list[0])

                data = toAmplitude(x)
                x_fre = xAxis(num=cur_n, sampling_rate=self.sampling_rate, freq=True)
                pw_fre.setFixedHeight(150)
                pw_fre.draw(x_fre, data, pen=QColor('blue'))
                pw_fre_list.append(pw_fre)
                pw_fre_list[i].setXLink(pw_fre_list[0])

                vbox1.addWidget(pw_time)
                vbox2.addWidget(pw_fre)

            hbox.addLayout(vbox1)
            hbox.addLayout(vbox2)
            wgt.setLayout(hbox)
            scroll_area.setWidget(wgt)
            self.ret = scroll_area

        # else:
        #     self.data = pywt.waverec(self.coeffs, wavelet=self.wavelet, mode=self.padding_mode)[:self.sampling_times]  # 重构信号
        #     combined_widget = initCombinedPlotWidget(self.data,
        #                                              '离散小波变换重构',
        #                                              self.sampling_times_from,
        #                                              self.sampling_times_to,
        #                                              self.sampling_times,
        #                                              self.sampling_rate)
        #     self.ret = combined_widget

    def run(self,
            data: np.array,
            sampling_times_from: int,
            sampling_times_to: int,
            sampling_rate: int) -> Optional[QWidget]:
        """
        计算 dwt、返回绘制图的组件
        Args:
            data: 数据
            sampling_times_from: 数据 x 轴起始
            sampling_times_to: 数据 x 轴终止
            sampling_rate: 采样率

        Returns: 含有 dwt 谱的绘图组件

        """
        self.ret = None
        self.data = data
        self.sampling_times = len(data)
        self.sampling_times_from = sampling_times_from
        self.sampling_times_to = sampling_times_to
        self.sampling_rate = sampling_rate
        self.runDialog()
        return self.ret

    # 滤波-小波-小波去噪
    # self.wavelet_threshold_action = Action(self.wavelet_menu, '小波去噪', '小波去噪', self.waveletThresholdDialog)
    #
    # self.wavelet_menu.addSeparator()

    # 小波去噪
    # self.wavelet_threshold = 1.0  # 阈值
    # self.wavelet_threshold_sub = 0.0  # 替换值
    # self.wavelet_threshold_modes = ['soft', 'hard', 'garrote', 'greater', 'less']  # 阈值种类
    # self.wavelet_threshold_mode_index = 0  # 阈值种类索引

    # def waveletThresholdDialog(self):
    #     """小波去噪"""
    #     dialog = Dialog()
    #     dialog.setWindowTitle('小波去噪')
    #
    #     wavelet_threshold_label = Label('阈值')
    #     self.wavelet_threshold_line_edit = LineEditWithReg(digit=True)
    #     self.wavelet_threshold_line_edit.setToolTip('去噪阈值')
    #     self.wavelet_threshold_line_edit.setText(str(self.wavelet_threshold))
    #
    #     wavelet_threshold_sub_label = Label('替换值')
    #     self.wavelet_threshold_sub_line_edit = LineEditWithReg(digit=True)
    #     self.wavelet_threshold_sub_line_edit.setToolTip('数据中筛除的值替换为该值')
    #     self.wavelet_threshold_sub_line_edit.setText(str(self.wavelet_threshold_sub))
    #
    #     wavelet_threshold_mode_label = Label('阈值类型')
    #     self.wavelet_threshold_mode_combx = ComboBox()
    #     self.wavelet_threshold_mode_combx.setToolTip('设置阈值类型')
    #     self.wavelet_threshold_mode_combx.addItems(self.wavelet_threshold_modes)
    #     self.wavelet_threshold_mode_combx.setCurrentIndex(self.wavelet_threshold_mode_index)
    #
    #     btn = PushButton('确定')
    #     btn.clicked.connect(self.updateWaveletThresholdParams)
    #     btn.clicked.connect(self.plotWaveletThreshold)
    #     btn.clicked.connect(dialog.close)
    #
    #     vbox = QVBoxLayout()
    #     hbox = QHBoxLayout()
    #     hbox.addWidget(wavelet_threshold_label)
    #     hbox.addWidget(self.wavelet_threshold_line_edit)
    #     hbox.addWidget(wavelet_threshold_sub_label)
    #     hbox.addWidget(self.wavelet_threshold_sub_line_edit)
    #     hbox.addStretch(1)
    #     hbox.addWidget(wavelet_threshold_mode_label)
    #     hbox.addWidget(self.wavelet_threshold_mode_combx)
    #
    #     vbox.addSpacing(5)
    #     vbox.addLayout(hbox)
    #     vbox.addSpacing(5)
    #     vbox.addWidget(btn)
    #
    #     dialog.setLayout(vbox)
    #     dialog.exec_()
    #
    # def updateWaveletThresholdParams(self):
    #     """更新小波阈值"""
    #     self.wavelet_threshold = float(self.wavelet_threshold_line_edit.text())
    #     self.wavelet_threshold_sub = float(self.wavelet_threshold_sub_line_edit.text())
    #     self.wavelet_threshold_mode_index = self.wavelet_threshold_mode_combx.currentIndex()
    #
    # def plotWaveletThreshold(self):
    #     """绘制滤波后的图像"""
    #     data = self.data[self.channel_number - 1]
    #
    #     try:
    #         data = pywt.threshold(data, value=self.wavelet_threshold,
    #                               mode=self.wavelet_threshold_mode_combx.currentText(),
    #                               substitute=self.wavelet_threshold_sub)  # 阈值滤波
    #         combined_widget = initCombinedPlotWidget(data,
    #                                                  '小波去噪',
    #                                                  self.sampling_times_from_num,
    #                                                  self.sampling_times_to_num,
    #                                                  self.current_sampling_times,
    #                                                  self.sampling_rate
    #                                                  )
    #
    #         self.tab_widget.addTab(combined_widget, f'小波去噪 - 阈值={self.wavelet_threshold}\t'
    #                                                 f'阈值类型={self.wavelet_threshold_mode_combx.currentText()}\t'
    #                                                 f'通道号={self.channel_number}')
    #
    #         self.updateData(data)
    #     except Exception as err:
    #         printError(err)
