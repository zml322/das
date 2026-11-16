# -*- coding: utf-8 -*-
"""
@Time    : 2024/10/2 上午10:31
@Author  : zxy
@File    : spectrum.py
"""
from typing import Optional, Union, Tuple

import numpy as np
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from matplotlib import pyplot as plt
from scipy.signal.windows import *
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from utils.function import xAxis
from ui.widgets.custom_widgets import PushButton, LineEditWithReg, Label, ComboBox, Dialog, MyPlotWidget


class SpectrumHandler:
    features = {
        '幅度谱': ['Magnitude', '幅度（dB）'],
        '功率谱密度谱': ['PSD', '功率/频率（dB/Hz）'],
        '角度谱': ['Angle', '角度（rad）'],
        '相位谱': ['Phase', '相位（rad）'],
    }
    dimensions = ['1d', '2d', '3d']
    # 默认窗口名称及对应的窗口
    window_methods = {
        'Bartlett': bartlett,
        'Blackman': blackman,
        'Blackman-Harris': blackmanharris,
        'Bohman': bohman,
        'Cosine': cosine,
        'Flat Top': flattop,
        'Hamming': hamming,
        'Hann': hann,
        'Lanczos / Sinc': lanczos,
        'Modified Barrtlett-Hann': barthann,
        'Nuttall': nuttall,
        'Parzen': parzen,
        'Rectangular / Dirichlet': boxcar,
        'Taylor': taylor,
        'Triangular': triang,
        'Tukey / Tapered Cosine': tukey
    }
    offset = 1e-9

    def __init__(self):
        self.data = None
        self.ret = None
        self.sampling_times = 0
        self.sampling_times_from = 0
        self.sampling_times_to = 0
        self.sampling_rate = 0

        self.feature = '幅度谱'  # 当前绘制特征
        self.dimension = '1d'  # 绘制维度
        self.window_text = 'Rectangular / Dirichlet'  # 加窗名称
        self.frame_length = 256  # 帧长
        self.frame_shift = 128  # 帧移

    def runDialog(self):
        """
        绘制谱设置调用窗口
        Returns:

        """
        dialog = Dialog()
        dialog.setWindowTitle('绘图设置')
        dialog.resize(200, 100)

        feature_label = Label('绘制特征')
        self.feature_combx = ComboBox()
        self.feature_combx.addItems(self.features.keys())
        self.feature_combx.setCurrentText(self.feature)

        dimension_label = Label('绘制维度')
        self.dimension_combx = ComboBox()
        self.dimension_combx.addItems(self.dimensions)
        self.dimension_combx.setCurrentText(self.dimension)

        window_method_label = Label('窗口类型')
        self.window_method_combx = ComboBox()
        self.window_method_combx.addItems(self.window_methods.keys())
        self.window_method_combx.setCurrentText(self.window_text)

        frame_length_label = Label('帧长')
        self.frame_length_line_edit = LineEditWithReg()
        self.frame_length_line_edit.setText(str(self.frame_length))
        self.frame_length_line_edit.setToolTip('每帧长度，通常为 2 的幂')

        frame_shift_label = Label('帧移')
        self.frame_shift_line_edit = LineEditWithReg()
        self.frame_shift_line_edit.setText(str(self.frame_shift))
        self.frame_shift_line_edit.setToolTip('帧每次移动的长度')

        btn = PushButton('确定')
        btn.clicked.connect(self.updateParams)
        btn.clicked.connect(self.plotSpectrum)
        btn.clicked.connect(dialog.close)

        hbox = QHBoxLayout()
        hbox1 = QHBoxLayout()
        hbox2 = QHBoxLayout()
        hbox3 = QHBoxLayout()
        vbox = QVBoxLayout()

        hbox.addWidget(feature_label)
        hbox.addWidget(self.feature_combx)
        hbox.addStretch(1)
        hbox.addWidget(dimension_label)
        hbox.addWidget(self.dimension_combx)
        hbox1.addWidget(window_method_label)
        hbox1.addStretch(1)
        hbox1.addWidget(self.window_method_combx)
        hbox2.addWidget(frame_length_label)
        hbox2.addStretch(1)
        hbox2.addWidget(self.frame_length_line_edit)
        hbox3.addWidget(frame_shift_label)
        hbox3.addStretch(1)
        hbox3.addWidget(self.frame_shift_line_edit)

        vbox.addLayout(hbox)
        vbox.addLayout(hbox1)
        vbox.addLayout(hbox2)
        vbox.addLayout(hbox3)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def updateParams(self):
        """
        更新加窗设置
        Returns:

        """
        self.feature = self.feature_combx.currentText()
        self.dimension = self.dimension_combx.currentText()
        self.window_text = self.window_method_combx.currentText()
        self.frame_length = int(self.frame_length_line_edit.text())
        self.frame_shift = int(self.frame_shift_line_edit.text())

    @staticmethod
    def fft(data: np.array) -> np.array:
        """
        计算数据的 fft
        Args:
            data: 数据

        Returns: fft 半谱

        """
        return np.fft.fft(data)[:len(data) // 2]

    def todB(self, data: np.array) -> np.array:
        """
        线性单位转分贝
        Args:
            data: 线性单位数据

        Returns: 分贝单位数据

        """
        return 20.0 * np.log10(data + self.offset)

    def getAngle(self, data: np.array) -> np.array:
        """
        计算角度谱
        Args:
            data: 数据

        Returns: 数据角度谱

        """
        return np.angle(self.fft(data))

    def getPhase(self, data: np.array) -> np.array:
        """
        计算相位谱
        Args:
            data: 数据

        Returns: 数据相位谱

        """
        return np.unwrap(self.getAngle(data))

    def getMagnitude(self, data: np.array, linear: bool = False) -> np.array:
        """
        计算幅度谱
        Args:
            data: 数据
            linear: 是否返回线性单位，否则返回数据单位为分贝

        Returns: 数据幅度谱

        """
        mag = np.abs(self.fft(data))
        if linear:
            return mag
        return self.todB(mag)

    def getPSD(self, data: np.array) -> np.array:
        """
        计算功率密度谱
        Args:
            data: 数据

        Returns: 数据功率谱密度

        """
        return self.todB(self.getMagnitude(data, linear=True) ** 2 / len(data) / self.sampling_rate)

    def calculateFeature(self) -> Union[np.array, Tuple]:
        """
        计算数据对应特征
        Returns: 如果绘制维度是 1d，返回数据特征，否则返回绘图所需的时间、频率轴与分帧后的数据特征

        """
        func = getattr(self, f'get{self.features[self.feature][0]}')
        if self.dimension == '1d':
            return func(self.data)

        frames_num = (self.sampling_times - self.frame_length + self.frame_shift) // self.frame_shift
        frames = []  # 创造返回的帧矩阵
        for i in range(frames_num):
            frames.append(self.data[i * self.frame_shift:i * self.frame_shift + self.frame_length])
        frames = np.multiply(frames, self.window_methods[self.window_text](self.frame_length))
        frames = np.array([func(x) for x in frames]).T

        t = xAxis(frames_num, self.sampling_times_from, self.sampling_times_to, self.sampling_rate)
        fs = xAxis(self.frame_length, sampling_rate=self.sampling_rate, freq=True)
        return t, fs, frames

    def plotSpectrum(self) -> None:
        """
        绘制谱
        Returns:

        """
        ret = self.calculateFeature()
        title, unit = self.feature, self.features[self.feature][1]
        if self.dimension == '1d':
            plot_widget = MyPlotWidget(title, '频率（Hz）', unit, grid=True)
            x = xAxis(self.sampling_times, sampling_rate=self.sampling_rate, freq=True)
            plot_widget.draw(x, ret, pen=QColor('blue'))
        else:
            t, fs, frames = ret
            figure = plt.figure()
            plot_widget = FigureCanvas(figure)
            if self.dimension == '2d':
                ax = plt.gca()
                ax.tick_params(axis='both', which='both', direction='in')
                im = ax.pcolormesh(t, fs, frames, shading='gouraud')
            else:
                ax = figure.add_subplot(projection='3d')
                ax.tick_params(axis='both', which='both', direction='in')
                im = ax.plot_surface(t[None, :], fs[:, None], frames, cmap='viridis')
                ax.set_zlabel(unit)

            ax.set_title(title)
            ax.set_xlabel('时间（s）')
            ax.set_ylabel('频率（Hz）')
            plt.colorbar(im, ax=ax, label=unit, pad=0.2)
            plt.xlim(self.sampling_times_from / self.sampling_rate, self.sampling_times_to / self.sampling_rate)
            plt.ylim(0, self.sampling_rate / 2)
        self.ret = plot_widget

    def run(self,
            data: np.array,
            sampling_times_from: int,
            sampling_times_to: int,
            sampling_rate: int) -> Optional[QWidget]:
        """
        计算数据特征、返回绘制图的组件
        Args:
            data: 数据
            sampling_times_from: 数据 x 轴起始
            sampling_times_to: 数据 x 轴终止
            sampling_rate: 采样率

        Returns: 含有数据谱的绘图组件

        """
        self.ret = None
        self.data = data
        self.sampling_times = len(data)
        self.sampling_times_from = sampling_times_from
        self.sampling_times_to = sampling_times_to
        self.sampling_rate = sampling_rate
        self.runDialog()
        return self.ret
