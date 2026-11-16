# -*- coding: utf-8 -*-
"""
@Time    : 2024/9/30 下午2:03
@Author  : zxy
@File    : snr.py
"""
import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout

from ui.widgets.custom_widgets import Dialog, Label, LineEditWithReg, PushButton


class SNRCalculator:
    def __init__(self):
        self.data = None
        self.sampling_rate = 1

        self.signal_channel_number = 1
        self.noise_channel_number = 1
        self.signal_start_time = 1.
        self.signal_stop_time = 2.
        self.noise_start_time = 1.
        self.noise_stop_time = 2.

    def runDialog(self) -> None:
        """
        计算信噪比对话框
        Returns:

        """
        dialog = Dialog()
        dialog.setFixedWidth(800)
        dialog.setWindowTitle('计算信噪比')

        signal_channel_number_label = Label('信号所在通道号')
        self.signal_channel_number_line_edit = LineEditWithReg()
        self.signal_channel_number_line_edit.setText(str(self.signal_channel_number))
        signal_start_time_label = Label('起始时间（秒）')
        self.signal_start_time_line_edit = LineEditWithReg(digit=True)
        self.signal_start_time_line_edit.setText(str(self.signal_start_time))
        signal_stop_time_label = Label('终止时间（秒）')
        self.signal_stop_time_line_edit = LineEditWithReg(digit=True)
        self.signal_stop_time_line_edit.setText(str(self.signal_stop_time))

        noise_channel_number_label = Label('噪声所在通道号')
        self.noise_channel_number_line_edit = LineEditWithReg()
        self.noise_channel_number_line_edit.setText(str(self.noise_channel_number))
        noise_start_time_label = Label('起始时间（秒）')
        self.noise_start_time_line_edit = LineEditWithReg(digit=True)
        self.noise_start_time_line_edit.setText(str(self.noise_start_time))
        noise_stop_time_label = Label('终止时间（秒）')
        self.noise_stop_time_line_edit = LineEditWithReg(digit=True)
        self.noise_stop_time_line_edit.setText(str(self.noise_stop_time))

        snr_label = Label('SNR = ')
        self.snr_line_edit = LineEditWithReg(focus=False)
        self.snr_line_edit.setFixedWidth(100)
        snr_unit_label = Label('dB')

        btn = PushButton('计算')
        btn.clicked.connect(self.updateParams)
        btn.clicked.connect(self.calculateSNR)

        vbox = QVBoxLayout()
        hbox1 = QHBoxLayout()
        hbox2 = QHBoxLayout()
        hbox3 = QHBoxLayout()

        hbox1.addWidget(signal_channel_number_label)
        hbox1.addWidget(self.signal_channel_number_line_edit)
        hbox1.addSpacing(50)
        hbox1.addWidget(signal_start_time_label)
        hbox1.addWidget(self.signal_start_time_line_edit)
        hbox1.addSpacing(5)
        hbox1.addWidget(signal_stop_time_label)
        hbox1.addWidget(self.signal_stop_time_line_edit)

        hbox2.addWidget(noise_channel_number_label)
        hbox2.addWidget(self.noise_channel_number_line_edit)
        hbox2.addSpacing(50)
        hbox2.addWidget(noise_start_time_label)
        hbox2.addWidget(self.noise_start_time_line_edit)
        hbox2.addSpacing(5)
        hbox2.addWidget(noise_stop_time_label)
        hbox2.addWidget(self.noise_stop_time_line_edit)

        hbox3.addStretch(1)
        hbox3.addWidget(snr_label)
        hbox3.addWidget(self.snr_line_edit)
        hbox3.addWidget(snr_unit_label)
        hbox3.addStretch(1)

        vbox.addLayout(hbox1)
        vbox.addSpacing(5)
        vbox.addLayout(hbox2)
        vbox.addSpacing(5)
        vbox.addLayout(hbox3)
        vbox.addSpacing(5)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def updateParams(self) -> None:
        """
        更新参数
        Returns:

        """
        self.signal_channel_number = int(self.signal_channel_number_line_edit.text())
        self.noise_channel_number = int(self.noise_channel_number_line_edit.text())
        self.signal_start_time = float(self.signal_start_time_line_edit.text())
        self.signal_stop_time = float(self.signal_stop_time_line_edit.text())
        self.noise_start_time = float(self.noise_start_time_line_edit.text())
        self.noise_stop_time = float(self.noise_stop_time_line_edit.text())

    def calculateSNR(self) -> None:
        """
        计算信噪比
        Returns:

        """
        signal_data = self.data[self.signal_channel_number - 1,
                      int(self.signal_start_time * self.sampling_rate):
                      int((self.signal_stop_time + 1) * self.sampling_rate)]
        noise_data = self.data[self.noise_channel_number - 1,
                     int(self.noise_start_time * self.sampling_rate):
                     int((self.noise_stop_time + 1) * self.sampling_rate)]

        snr = 10.0 * np.log10(np.sum(signal_data ** 2) / np.sum(noise_data ** 2))
        self.snr_line_edit.setText(f'{snr:.5f}')

    def run(self, data: np.array, sampling_rate: int) -> None:
        """
        运行组件
        Args:
            data: 数据
            sampling_rate: 采样率

        Returns:

        """
        self.data = data
        self.sampling_rate = sampling_rate
        self.runDialog()
