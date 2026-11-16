# -*- coding: utf-8 -*-
"""
@Time    : 2024/9/30 下午0:25
@Author  : zxy
@File    : binary_image.py
"""
from typing import Optional

import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout

from ui.widgets.custom_widgets import PushButton, ComboBox, RadioButton, LineEditWithReg, Dialog


class BinaryImageHandler:
    threshold_methods = {
        '双峰法': 'twoPeaks',
        '大津法': 'ostu'
    }

    def __init__(self):
        self.data = None
        self.flag = True  # 是否使用简单阈值
        self.threshold = 120  # 阈值
        self.threshold_method = '双峰法'  # 计算阈值方法

        self.draw = False

    @staticmethod
    def normalizeToGrayScale(data: np.array) -> np.array:
        """
        将数据范围缩放到 0-255
        Args:
            data: 数据

        Returns:

        """
        mx, mn = np.max(data), np.min(data)
        data = (data - mn) / (mx - mn)
        return data * 255

    def binarizeData(self) -> None:
        """
        二值化数据
        Returns:

        """
        self.draw = True
        self.data[self.data >= self.threshold] = 255
        self.data[self.data < self.threshold] = 0

    def runDialog(self) -> None:
        """
        二值图设置组件
        Returns:

        """
        dialog = Dialog()
        dialog.setWindowTitle('二值图')

        self.input_radiobtn = RadioButton('阈值')
        self.input_radiobtn.setChecked(self.flag)

        self.threshold_line_edit = LineEditWithReg()
        self.threshold_line_edit.setText(str(self.threshold))

        self.method_radiobtn = RadioButton('计算方法')
        self.method_radiobtn.setChecked(not self.flag)

        self.method_combx = ComboBox()
        self.method_combx.addItems(self.threshold_methods.keys())
        self.method_combx.setCurrentText(self.threshold_method)

        btn = PushButton('确定')
        btn.clicked.connect(self.updateParams)
        btn.clicked.connect(self.binarizeData)
        btn.clicked.connect(dialog.close)

        vbox = QVBoxLayout()
        hbox1 = QHBoxLayout()
        hbox1.addWidget(self.input_radiobtn)
        hbox1.addWidget(self.threshold_line_edit)
        hbox1.addStretch(0)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(self.method_radiobtn)
        hbox2.addSpacing(20)
        hbox2.addWidget(self.method_combx)
        hbox2.addStretch(0)

        vbox.addLayout(hbox1)
        vbox.addSpacing(30)
        vbox.addLayout(hbox2)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def updateParams(self) -> None:
        """
        检查选择那种求阈值方法
        Returns:

        """
        self.flag = self.input_radiobtn.isChecked()

        if self.flag:
            threshold = float(self.threshold_line_edit.text())
            if threshold > 255:
                threshold = 255
        else:
            threshold = getattr(self,
                                self.threshold_methods[self.method_combx.currentText()])()

        self.threshold_method = self.method_combx.currentText()
        self.threshold = threshold

    def twoPeaks(self) -> int:
        """
        双峰法求阈值
        Returns:

        """
        # 存储灰度直方图
        gray_scale_hist = [0] * 256
        for i, x in enumerate(self.data):
            for j, y in enumerate(x):
                gray_scale_hist[int(y)] += 1

        # 寻找灰度直方图的最大峰值对应的灰度值
        first_peak = gray_scale_hist.index(max(gray_scale_hist))

        # 寻找灰度直方图的第二个峰值对应的灰度值
        distance = [(i - first_peak) ** 2 * gray_scale_hist[i] for i in range(256)]  # 综合考虑 两峰距离与峰值
        second_peak = distance.index(max(distance))

        # 找到两个峰值之间的最小值对应的灰度值，作为阈值
        if first_peak > second_peak:
            first_peak, second_peak = second_peak, first_peak

        temp_val = gray_scale_hist[first_peak:second_peak]
        min_gray_scale_location = temp_val.index(min(temp_val))
        return first_peak + min_gray_scale_location + 1

    def ostu(self) -> int:
        """
        OSTU（大津）法
        Returns:

        """
        height, width = self.data.shape
        sq = height * width
        max_gray_scale = threshold = 0
        # 遍历每一个灰度层
        for i in range(256):
            smaller_px = self.data[np.where(self.data < i)]
            bigger_px = self.data[np.where(self.data >= i)]
            smaller_ratio = len(smaller_px) / sq
            bigger_ratio = len(bigger_px) / sq
            average_gray_scale_smaller = np.mean(smaller_px) if len(smaller_px) > 0 else 0
            average_gray_scale_bigger = np.mean(bigger_px) if len(bigger_px) > 0 else 0
            cur = smaller_ratio * bigger_ratio * (average_gray_scale_smaller - average_gray_scale_bigger) ** 2
            if cur > max_gray_scale:
                max_gray_scale = cur
                threshold = i
        return threshold

    def run(self, data: np.array) -> Optional[np.array]:
        """
        求二值图阈值
        Args:
            data: 数据

        Returns: 二值图数据

        """
        self.draw = False
        self.data = self.normalizeToGrayScale(data)
        self.runDialog()
        return self.data if self.draw else None
