# -*- coding: utf-8 -*-
"""
@Time    : 2024/9/30 下午2:26
@Author  : zxy
@File    : emd.py
"""
import re
from typing import Optional

import numpy as np
from PyEMD import EMD, EEMD, CEEMDAN
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea
from scipy.signal import hilbert

from utils.function import xAxis, initCombinedPlotWidget
from ui.widgets.custom_widgets import MyPlotWidget, Dialog, LineEditWithReg, Label, RadioButton, LineEdit, ComboBox, PushButton


class EMDHandler:
    emd_methods = ['emd', 'eemd', 'ceemdan']

    def __init__(self):
        self.data = None
        self.sampling_times = 0
        self.sampling_times_from = 0
        self.sampling_times_to = 0
        self.sampling_rate = 0
        self.ret = None

        self.emd_method = 'emd'
        self.imfs_res_num = 5  # 所有模态加残余模态的数量
        self.reconstruct_nums = str(list(range(1, 5)))  # 重构模态号
        self.emd_options_flag = True  # 默认操作为分解
        self.eemd_trials = 100  # 添加噪声点数量？
        self.eemd_noise_width = 0.05  # 添加的高斯噪声的标准差
        self.ceemdan_trials = 100  # 添加噪声点数量？
        self.ceemdan_epsilon = 0.005  # 添加噪声大小与标准差的乘积
        self.ceemdan_noise_kind = 'normal'  # 噪声种类
        self.ceemdan_noise_scale = 1.0  # 添加噪声的大小
        self.ceemdan_range_thr = 0.01  # 范围阈值，小于则不再分解
        self.ceemdan_total_power_thr = 0.05  # 总功率阈值，小于则不再分解

    def runEMD(self) -> None:
        """
        运行 emd，并绘制 emd 分解图和重构图
        Returns:

        """
        if self.emd_method == 'emd':
            emd = EMD()
            self.imfs_res = emd.emd(self.data, max_imf=self.imfs_res_num - 1)
        elif self.emd_method == 'eemd':
            emd = EEMD(trials=self.eemd_trials, noise_width=self.eemd_noise_width)
            self.imfs_res = emd.eemd(self.data, max_imf=self.imfs_res_num - 1)
        elif self.emd_method == 'ceemdan':
            if not hasattr(self, 'ceemdan_noise_kind_combx'):
                noise_kind = 'normal'
            else:
                noise_kind = self.ceemdan_noise_kind_combx.currentText()
            emd = CEEMDAN(trials=self.ceemdan_trials, epsilon=self.ceemdan_epsilon,
                          noise_scale=self.ceemdan_noise_scale,
                          noise_kind=noise_kind, range_thr=self.ceemdan_range_thr,
                          total_power_thr=self.ceemdan_total_power_thr)
            self.imfs_res = emd.ceemdan(self.data, max_imf=self.imfs_res_num - 1)

        if self.emd_options_flag:
            scroll_area = QScrollArea()
            wgt = QWidget()
            vbox1 = QVBoxLayout()
            vbox2 = QVBoxLayout()
            hbox = QHBoxLayout()

            pw_time_list, pw_fre_list = [], []
            x_time = xAxis(self.sampling_times,
                           self.sampling_times_from,
                           self.sampling_times_to,
                           self.sampling_rate)
            x_fre = xAxis(self.sampling_times, self.sampling_rate, freq=True)
            for i, x in enumerate(self.imfs_res):
                if i == 0:
                    pw_time = MyPlotWidget(f'{self.emd_method}分解 - 时域', '', 'IMF1（rad）')
                    pw_fre = MyPlotWidget(f'{self.emd_method}分解 - 频域', '', 'IMF1')
                elif i == len(self.imfs_res) - 1:
                    pw_time = MyPlotWidget('', '时间（s）', f'Residual（rad）')
                    pw_fre = MyPlotWidget('', '频率（Hz）', f'Residual')
                else:
                    pw_time = MyPlotWidget('', '', f'IMF{i + 1}（rad）')
                    pw_fre = MyPlotWidget('', '', f'IMF{i + 1}')

                pw_time.setFixedHeight(150)
                pw_time.draw(x_time, x, pen=QColor('blue'))
                pw_time_list.append(pw_time)
                pw_time_list[i].setXLink(pw_time_list[0])  # 设置时域x轴对应

                data = np.abs(np.fft.fft(x))[:self.sampling_times // 2] * 2.0 / self.sampling_times
                pw_fre.setFixedHeight(150)
                pw_fre.draw(x_fre, data, pen=QColor('blue'))
                pw_fre_list.append(pw_fre)
                pw_fre_list[i].setXLink(pw_fre_list[0])  # 设置频域x轴对应

                vbox1.addWidget(pw_time)
                vbox2.addWidget(pw_fre)

            hbox.addLayout(vbox1)
            hbox.addLayout(vbox2)
            wgt.setLayout(hbox)
            scroll_area.setWidget(wgt)
            self.ret = scroll_area

        else:
            reconstruct_imf = [int(i) for i in re.findall(r'\d+', self.reconstruct_nums)]  # 映射为整数类型
            data = np.zeros_like(self.imfs_res[0])
            for i in range(len(reconstruct_imf) - 1):
                imf_num = reconstruct_imf[i]
                data += self.imfs_res[imf_num]  # 重构数据

            self.ret = initCombinedPlotWidget(data,
                                              self.emd_method + '重构',
                                              self.sampling_times_from,
                                              self.sampling_times_to,
                                              self.sampling_times,
                                              self.sampling_rate)

    def runDialog(self) -> None:
        """
        运行对话框
        Returns:

        """
        dialog = Dialog()
        dialog.resize(600, 200)
        dialog.setWindowTitle('EMD设置')

        shared_options_label = Label('共享设置')
        shared_options_label.setAlignment(Qt.AlignHCenter)
        emd_method_label = Label('分解方式')
        self.emd_method_combx = ComboBox()
        self.emd_method_combx.addItems(self.emd_methods)
        self.emd_method_combx.setCurrentText(self.emd_method)
        self.emd_decompose_radio_btn = RadioButton('分解')
        self.emd_decompose_radio_btn.setChecked(self.emd_options_flag)
        imf_num_label = Label('IMF数量')
        self.emd_decompose_line_edit = LineEditWithReg()
        self.emd_decompose_line_edit.setToolTip('IMF数量，最大为9')
        self.emd_decompose_line_edit.setText(str(self.imfs_res_num - 1))

        self.emd_reconstruct_radio_btn = RadioButton('重构')
        self.emd_reconstruct_radio_btn.setChecked(not self.emd_options_flag)
        reconstruct_imf_number_label = Label('重构的IMF')
        self.emd_reconstruct_line_edit = LineEdit()
        self.emd_reconstruct_line_edit.setToolTip('重构的IMF号，应用逗号或空格分隔')
        self.emd_reconstruct_line_edit.setText(self.reconstruct_nums)

        if not hasattr(self, 'imfs_res'):
            self.emd_reconstruct_radio_btn.setEnabled(False)
            reconstruct_imf_number_label.setEnabled(False)
            self.emd_reconstruct_line_edit.setEnabled(False)

        eemd_options_label = Label('EEMD设置')
        eemd_options_label.setAlignment(Qt.AlignHCenter)
        eemd_trials_label = Label('试验点')
        self.eemd_trials_line_edit = LineEditWithReg()
        self.eemd_trials_line_edit.setText(str(self.eemd_trials))
        self.eemd_trials_line_edit.setToolTip('添加噪声的试验点或施加EMD点的数量')
        eemd_noise_width_label = Label('噪声宽度')
        self.eemd_noise_width_line_edit = LineEditWithReg(digit=True)
        self.eemd_noise_width_line_edit.setText(str(self.eemd_noise_width))
        self.eemd_noise_width_line_edit.setToolTip('高斯噪声的标准差，与信号的幅值有关')

        ceemdan_options_label = Label('CEEMDAN设置')
        ceemdan_options_label.setAlignment(Qt.AlignHCenter)
        ceemdan_trials_label = Label('试验点')
        self.ceemdan_trials_line_edit = LineEditWithReg()
        self.ceemdan_trials_line_edit.setText(str(self.ceemdan_trials))
        self.ceemdan_trials_line_edit.setToolTip('添加噪声的试验点或施加EMD点的数量')
        ceemdan_epsilon_label = Label('Epsilon')
        self.ceemdan_epsilon_line_edit = LineEditWithReg(digit=True)
        self.ceemdan_epsilon_line_edit.setText(str(self.ceemdan_epsilon))
        self.ceemdan_epsilon_line_edit.setToolTip('添加噪声乘标准差后的大小')
        ceemdan_noise_scale_label = Label('噪声大小')
        self.ceemdan_noise_scale_line_edit = LineEditWithReg(digit=True)
        self.ceemdan_noise_scale_line_edit.setText(str(self.ceemdan_noise_scale))
        self.ceemdan_noise_scale_line_edit.setToolTip('添加噪声的振幅')
        ceemdan_noise_kind_label = Label('噪声种类')
        self.ceemdan_noise_kind_combx = ComboBox()
        self.ceemdan_noise_kind_combx.addItems(['normal', 'uniform'])
        self.ceemdan_noise_kind_combx.setCurrentText(self.ceemdan_noise_kind)
        ceemdan_range_thr_label = Label('振幅范围阈值')
        self.ceemdan_range_thr_line_edit = LineEditWithReg(digit=True)
        self.ceemdan_range_thr_line_edit.setText(str(self.ceemdan_range_thr))
        self.ceemdan_range_thr_line_edit.setToolTip('用于IMF分解检查，其值等于与初始信号振幅之比的百分数，如果绝对振幅小于振幅范围阈值，'
                                                    '则认为分解完成')
        ceemdan_total_power_thr_label = Label('总功率阈值')
        self.ceemdan_total_power_thr_line_edit = LineEditWithReg(digit=True)
        self.ceemdan_total_power_thr_line_edit.setText(str(self.ceemdan_total_power_thr))
        self.ceemdan_total_power_thr_line_edit.setToolTip('用于IMF分解检查，如果信号总功率小于总功率阈值，则认为分解完成')

        btn = PushButton('确定')
        btn.clicked.connect(self.updateParams)
        btn.clicked.connect(self.runEMD)
        btn.clicked.connect(dialog.close)

        hbox = QHBoxLayout()
        hbox1 = QHBoxLayout()
        hbox2 = QHBoxLayout()
        shared_options_vbox = QVBoxLayout()

        hbox3 = QHBoxLayout()
        eemd_options_vbox = QVBoxLayout()

        hbox4 = QHBoxLayout()
        hbox5 = QHBoxLayout()
        hbox6 = QHBoxLayout()
        ceemdan_options_vbox = QVBoxLayout()

        vbox = QVBoxLayout()
        hbox.addWidget(emd_method_label)
        hbox.addSpacing(5)
        hbox.addWidget(self.emd_method_combx)
        hbox.addStretch(1)
        hbox1.addWidget(self.emd_decompose_radio_btn)
        hbox1.addStretch(1)
        hbox1.addWidget(imf_num_label)
        hbox1.addWidget(self.emd_decompose_line_edit)
        hbox2.addWidget(self.emd_reconstruct_radio_btn)
        hbox2.addStretch(1)
        hbox2.addWidget(reconstruct_imf_number_label)
        hbox2.addWidget(self.emd_reconstruct_line_edit)
        shared_options_vbox.addWidget(shared_options_label)
        shared_options_vbox.addSpacing(10)
        shared_options_vbox.addLayout(hbox)
        shared_options_vbox.addLayout(hbox1)
        shared_options_vbox.addLayout(hbox2)

        hbox3.addWidget(eemd_trials_label)
        hbox3.addWidget(self.eemd_trials_line_edit)
        hbox3.addStretch(1)
        hbox3.addWidget(eemd_noise_width_label)
        hbox3.addWidget(self.eemd_noise_width_line_edit)
        eemd_options_vbox.addWidget(eemd_options_label)
        eemd_options_vbox.addSpacing(10)
        eemd_options_vbox.addLayout(hbox3)

        hbox4.addWidget(ceemdan_trials_label)
        hbox4.addWidget(self.ceemdan_trials_line_edit)
        hbox4.addStretch(1)
        hbox4.addWidget(ceemdan_epsilon_label)
        hbox4.addWidget(self.ceemdan_epsilon_line_edit)
        hbox5.addWidget(ceemdan_noise_scale_label)
        hbox5.addWidget(self.ceemdan_noise_scale_line_edit)
        hbox5.addStretch(1)
        hbox5.addWidget(ceemdan_noise_kind_label)
        hbox5.addWidget(self.ceemdan_noise_kind_combx)
        hbox6.addWidget(ceemdan_range_thr_label)
        hbox6.addWidget(self.ceemdan_range_thr_line_edit)
        hbox6.addStretch(1)
        hbox6.addWidget(ceemdan_total_power_thr_label)
        hbox6.addWidget(self.ceemdan_total_power_thr_line_edit)
        ceemdan_options_vbox.addWidget(ceemdan_options_label)
        ceemdan_options_vbox.addSpacing(10)
        ceemdan_options_vbox.addLayout(hbox4)
        ceemdan_options_vbox.addLayout(hbox5)
        ceemdan_options_vbox.addLayout(hbox6)

        vbox.addLayout(shared_options_vbox)
        vbox.addSpacing(30)
        vbox.addLayout(eemd_options_vbox)
        vbox.addSpacing(30)
        vbox.addLayout(ceemdan_options_vbox)
        vbox.addSpacing(20)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def updateParams(self) -> None:
        """
        更新分解数和重构数
        Returns:

        """
        self.emd_method = self.emd_method_combx.currentText()
        self.emd_options_flag = self.emd_decompose_radio_btn.isChecked()

        if self.emd_options_flag:
            if int(self.emd_decompose_line_edit.text()) == 0:
                self.imfs_res_num = 2
            elif int(self.emd_decompose_line_edit.text()) >= 10:
                self.imfs_res_num = 10
            else:
                self.imfs_res_num = int(self.emd_decompose_line_edit.text()) + 1
            self.reconstruct_nums = str(list(range(1, self.imfs_res_num)))
        else:
            self.reconstruct_nums = self.emd_reconstruct_line_edit.text()

        self.eemd_trials = int(self.eemd_trials_line_edit.text())
        self.eemd_noise_width = float(self.eemd_noise_width_line_edit.text())

        self.ceemdan_trials = int(self.ceemdan_trials_line_edit.text())
        self.ceemdan_epsilon = float(self.ceemdan_epsilon_line_edit.text())
        self.ceemdan_noise_scale = float(self.ceemdan_noise_scale_line_edit.text())
        self.ceemdan_noise_kind = self.ceemdan_noise_kind_combx.currentText()
        self.ceemdan_range_thr = float(self.ceemdan_range_thr_line_edit.text())
        self.ceemdan_total_power_thr = float(self.ceemdan_total_power_thr_line_edit.text())

    def calculateInstantaneousFrequency(self) -> np.array:
        """
        计算瞬时频率
        Returns:

        """
        x_time = xAxis(self.sampling_times,
                       self.sampling_times_from,
                       self.sampling_times_to,
                       self.sampling_rate)
        analytic_signal = hilbert(self.imfs_res)
        inst_phase = np.unwrap(np.angle(analytic_signal))
        inst_freqs = np.diff(inst_phase) / (2 * np.pi * (x_time[1] - x_time[0]))
        inst_freqs = np.concatenate((inst_freqs, inst_freqs[:, -1].reshape(inst_freqs[:, -1].shape[0], 1)), axis=1)

        wgt = QWidget()
        vbox = QVBoxLayout()
        scroll_area = QScrollArea()

        pw_list = []
        for i, x in enumerate(inst_freqs):
            if i == 0:
                pw_list.append(MyPlotWidget('瞬时频率图', '', 'IMF1（Hz）'))
            elif i == len(inst_freqs) - 1:
                pw_list.append(MyPlotWidget('', '时间（s）', f'Residual'))
            else:
                pw_list.append(MyPlotWidget('', '', f'IMF{i + 1}（Hz）'))

            pw_list[i].setXLink(pw_list[0])
            pw_list[i].draw(x_time, x, pen=QColor('blue'))
            pw_list[i].setFixedHeight(150)
            vbox.addWidget(pw_list[i])
        wgt.setLayout(vbox)
        scroll_area.setWidget(wgt)
        return scroll_area

    def run(self,
            data: np.array,
            sampling_times_from: int,
            sampling_times_to: int,
            sampling_rate: int) -> Optional[QWidget]:
        """
        运行 emd，返回绘制图的组件
        Args:
            data: 数据
            sampling_times_from: 数据 x 轴起始
            sampling_times_to: 数据 x 轴终止
            sampling_rate: 采样率

        Returns: 含有 emd 结果的绘图组件

        """
        self.ret = None
        self.data = data
        self.sampling_times = len(data)
        self.sampling_times_from = sampling_times_from
        self.sampling_times_to = sampling_times_to
        self.sampling_rate = sampling_rate
        self.runDialog()
        return self.ret
