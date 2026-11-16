# -*- coding: utf-8 -*-
"""
@Time    : 2024/10/1 下午3:53
@Author  : zxy
@File    : wavelet_packet.py
"""
import re
from typing import Optional

import numpy as np
import pywt
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QScrollArea

from utils.function import initCombinedPlotWidget, xAxis, toAmplitude
from ui.widgets.custom_widgets import ComboBox, Label, LineEditWithReg, PushButton, Dialog, RadioButton, LineEdit, MyPlotWidget


class DWPTHandler:
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
        # self.reconstruct = ['a', 'd']  # 重构节点名称
        self.family = 'bior'  # 小波族索引
        self.wavelet = 'bior1.1'  # 小波
        self.decompose_level = 3  # 分解层数
        self.decompose_max_level = None  # 显示的最大分解层数
        self.padding_mode = 'zero'  # 数据填充模式

    def runDialog(self):
        """
        小波包分解对话框
        Returns:

        """
        dialog = Dialog()
        dialog.setWindowTitle('小波包')

        self.decompose_radiobtn = RadioButton('分解')
        self.decompose_radiobtn.setChecked(self.flag)

        # reconstruct_radiobtn = RadioButton('重构')
        # reconstruct_radiobtn.setChecked(not self.flag)

        # reconstruct_label = Label('重构子节点')
        # self.reconstruct_line_edit = LineEdit()
        # self.reconstruct_line_edit.setFixedWidth(500)
        # self.reconstruct_line_edit.setToolTip('选择重构的子节点，a为近似节点路径分支，d为细节节点路径分支，'
        #                                       '多个a或d相连代表了子节点路径')
        #
        # self.reconstruct_line_edit.setText(str(self.reconstruct))

        # if not hasattr(self, 'subnodes'):
        #     reconstruct_radiobtn.setEnabled(False)
        #     reconstruct_label.setEnabled(False)
        #     self.reconstruct_line_edit.setEnabled(False)

        label = Label('选择小波：')

        family_label = Label('小波族')
        self.family_combx = ComboBox()
        self.family_combx.addItems(self.wavelet_families.keys())
        self.family_combx.setCurrentText(self.family)
        self.family_combx.currentIndexChanged.connect(self.waveletPacketsChangeNameComboBox)

        name_label = Label('小波名称')
        self.name_combx = ComboBox()
        self.name_combx.setFixedWidth(75)
        self.name_combx.addItems(self.wavelet_families[self.family])
        self.name_combx.setCurrentText(self.wavelet)
        self.name_combx.currentIndexChanged.connect(self.waveletPacketsCalculateDecomposeMaxLevel)

        decompose_level_label = Label('分解层数')
        self.decompose_level_line_edit = LineEditWithReg()
        self.decompose_level_line_edit.setToolTip('分解层数')
        self.decompose_level_line_edit.setText(str(self.decompose_level))

        decompose_max_level_label = Label('最大分解层数')
        self.decompose_max_level_line_edit = LineEditWithReg(focus=False)
        self.decompose_max_level_line_edit.setToolTip('数据的最大分解层数，与数据长度和选择的小波有关')
        self.decompose_max_level = pywt.dwt_max_level(self.sampling_times, self.wavelet)
        self.decompose_max_level_line_edit.setText(str(self.decompose_max_level))

        padding_mode_label = Label('填充模式')
        self.padding_mode_combx = ComboBox()
        self.padding_mode_combx.setToolTip('信号延长模式')
        self.padding_mode_combx.addItems(self.padding_modes)
        self.padding_mode_combx.setCurrentText(self.padding_mode)

        btn = PushButton('确定')
        btn.clicked.connect(self.updateParams)
        btn.clicked.connect(self.runWaveletPackets)
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
        hbox3.addWidget(decompose_max_level_label)
        hbox3.addWidget(self.decompose_max_level_line_edit)
        hbox3.addStretch(1)
        hbox3.addWidget(padding_mode_label)
        hbox3.addWidget(self.padding_mode_combx)

        vbox.addLayout(hbox1)
        vbox.addSpacing(10)
        vbox.addLayout(hbox3)
        # vbox.addSpacing(10)
        # vbox.addLayout(hbox2)
        vbox.addSpacing(10)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def waveletPacketsChangeNameComboBox(self) -> None:
        """
        根据选择的小波族更改小波的名字
        Returns:

        """
        self.family = self.family_combx.currentText()
        self.name_combx.clear()
        self.name_combx.addItems(self.wavelet_families[self.family])
        self.name_combx.setCurrentIndex(0)

    def waveletPacketsCalculateDecomposeMaxLevel(self):
        """
        根据选择的小波计算最大分解层数
        Returns:

        """
        if self.name_combx.currentText():
            self.wavelet = self.name_combx.currentText()
            self.decompose_max_level = pywt.dwt_max_level(self.sampling_times, self.wavelet)  # 最大分解层数
            self.decompose_max_level_line_edit.setText(str(self.decompose_max_level))

    def updateParams(self):
        """
        更新小波包分解系数
        Returns:

        """
        # self.flag = self.decompose_radiobtn.isChecked()
        # self.reconstruct = self.reconstruct_line_edit.text()
        self.decompose_level = int(self.decompose_level_line_edit.text())
        self.decompose_max_level = int(self.decompose_max_level_line_edit.text())
        self.padding_mode = self.padding_mode_combx.currentText()

    def runWaveletPackets(self):
        """
        运行小波包分解或重构
        Returns:

        """
        if self.flag:
            self.wp = pywt.WaveletPacket(self.data,
                                         wavelet=self.wavelet,
                                         mode=self.padding_mode)  # 创建一个小波包
            self.subnodes = self.wp.get_level(level=self.decompose_level, order='natural',
                                              decompose=True)  # 获得当前分解层数下的各节点
            self.reconstruct = [i.path for i in self.subnodes]

        # else:
        #     total_paths = [i.path for i in self.subnodes]
        #     self.reconstruct = str(self.reconstruct).split("','")
        #     self.reconstruct = re.findall('\w+', self.reconstruct[0])
        #
        #     for i in total_paths:
        #         if i not in self.reconstruct:
        #             del self.wp[i]

        if self.flag:
            wgt = QWidget()
            vbox1 = QVBoxLayout()
            vbox2 = QVBoxLayout()
            hbox = QHBoxLayout()
            scroll_area = QScrollArea()

            pw_time_list, pw_fre_list = [], []
            n = len(self.subnodes)
            for i, x in enumerate(self.subnodes):
                cur_n = len(x.data)
                if i == 0:
                    pw_time = MyPlotWidget('小波包分解 - 时域', '', f'{x.path}（rad）')
                    pw_fre = MyPlotWidget('小波包分解 - 频域', '', f'{x.path}')
                elif i == n - 1:
                    pw_time = MyPlotWidget('', '时间（s）', f'{x.path}（rad）')
                    pw_fre = MyPlotWidget('', '频率（Hz）', f'{x.path}')
                else:
                    pw_time = MyPlotWidget('', '', f'{x.path}（rad）')
                    pw_fre = MyPlotWidget('', '', f'{x.path}')

                x_time = xAxis(num=cur_n,
                               begin=self.sampling_times_from,
                               end=self.sampling_times_from + cur_n,
                               sampling_rate=self.sampling_rate)
                pw_time.setFixedHeight(150)
                pw_time.draw(x_time, x.data, pen=QColor('blue'))
                pw_time_list.append(pw_time)
                pw_time_list[i].setXLink(pw_time_list[0])

                data = toAmplitude(x.data)
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
        #     self.data = self.wp.reconstruct()  # 重构信号
        #     combined_widget = initCombinedPlotWidget(self.data,
        #                                              '小波包重构',
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
        计算 dwpt、返回绘制图的组件
        Args:
            data: 数据
            sampling_times_from: 数据 x 轴起始
            sampling_times_to: 数据 x 轴终止
            sampling_rate: 采样率

        Returns: 含有 dwpt 谱的绘图组件

        """
        self.ret = None
        self.data = data
        self.sampling_times = len(data)
        self.sampling_times_from = sampling_times_from
        self.sampling_times_to = sampling_times_to
        self.sampling_rate = sampling_rate
        self.runDialog()
        return self.ret
