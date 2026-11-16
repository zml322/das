# -*- coding: utf-8 -*-
"""
@Time    : 2024/6/12 上午9:29
@Author  : zxy
@File    : filter.py
"""
from typing import Optional

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout
from scipy.signal import iircomb, iirnotch, iirpeak, cheby2, bessel, ellip, cheby1, butter, buttord, cheb1ord, cheb2ord, \
    ellipord, filtfilt

from utils.function import initCombinedPlotWidget
from ui.widgets.custom_widgets import LineEditWithReg, Label, PushButton, ComboBox, Dialog, CheckBox


class FilterI:
    """一类滤波器"""
    filter_names = {
        'Butterworth': butter,
        'Chebyshev type I': cheby1,
        'Chebyshev type II': cheby2,
        'Elliptic (Cauer)': ellip,
        'Bessel/Thomson': bessel
    }
    btype = ['lowpass', 'highpass', 'bandpass', 'bandstop']
    cal_names = {butter: buttord, cheby1: cheb1ord, cheby2: cheb2ord, ellip: ellipord}
    norms = ['phase', 'delay', 'mag']

    def __init__(self, filter_name: str, data: np.array, sampling_rate: int):
        """
        初始化各种参数
        Args:
            filter_name: 滤波器名
            data: 数据
            sampling_rate: 采样率
            
        """
        self.data = data
        self.filter_name = filter_name
        self.filter = self.filter_names[filter_name]
        self.sampling_rate = sampling_rate
        self.order = 4
        self.Wn = int(0.1 * sampling_rate)
        self.cal_order = None
        self.cal_Wn = None
        self.method = 'lowpass'
        self.wp = str(int(0.2 * sampling_rate))
        self.ws = str(int(0.3 * sampling_rate))
        self.rp = 5.
        self.rs = 40.
        self.gpass = 3.
        self.gstop = 40.
        self.analog = False
        self.norm = 'phase'
        self.flag = True

        self.b = None
        self.a = None

        self.draw = False

    def runDialog(self):
        """
        对话框初始化布局
        Returns:

        """
        dialog = Dialog()
        dialog.setWindowTitle(f'设计{self.filter_name}滤波器')

        combx_label = Label('滤波器类型')
        self.combx = ComboBox()
        self.combx.setToolTip('滤波器的类型')
        self.combx.addItems(self.btype)
        self.combx.setCurrentText(self.method)
        self.combx.currentTextChanged.connect(self.resetCalculateParams)

        self.checkbx = CheckBox('模拟滤波器')
        self.checkbx.setToolTip('勾选时返回模拟滤波器，否则返回数字滤波器')
        self.checkbx.setChecked(self.analog)
        self.checkbx.stateChanged.connect(self.resetCalculateParams)

        # 计算区域组件
        cal_label = Label('计算滤波器阶数和自然频率')
        cal_label.setAlignment(Qt.AlignHCenter)

        wp_label = Label('通带频率（wp）')
        self.wp_le = LineEditWithReg(space=True)
        self.wp_le.setToolTip('选择带通或带阻滤波器时应以空格分隔截止频率（Hz）\n'
                              '例如：\n'
                              'lowpass: wp = 200, ws = 300\n'
                              'highpass: wp = 300, ws = 200\n'
                              'bandpass: wp = 200 500, ws = 100 600\n'
                              'bandstop: wp = 100 600, ws = 200 500')
        self.wp_le.setText(str(self.wp))
        self.wp_le.textChanged.connect(self.resetCalculateParams)

        ws_label = Label('阻带频率（ws）')
        self.ws_le = LineEditWithReg(space=True)
        self.ws_le.setToolTip('选择带通或带阻滤波器时应以空格分隔截止频率（Hz）\n'
                              '例如：\n'
                              'lowpass: wp = 200, ws = 300\n'
                              'highpass: wp = 300, ws = 200\n'
                              'bandpass: wp = 200 500, ws = 100 600\n'
                              'bandstop: wp = 100 600, ws = 200 500')
        self.ws_le.setText(str(self.ws))
        self.ws_le.textChanged.connect(self.resetCalculateParams)

        gpass_label = Label('通带损失（gpass）')
        self.gpass_le = LineEditWithReg(digit=True)
        self.gpass_le.setToolTip('通带的最大损失（dB）')
        self.gpass_le.setText(str(self.gpass))
        self.gpass_le.textChanged.connect(self.resetCalculateParams)

        gstop_label = Label('阻带衰减（gstop）')
        self.gstop_le = LineEditWithReg(digit=True)
        self.gstop_le.setToolTip('阻带最小衰减（dB）')
        self.gstop_le.setText(str(self.gstop))
        self.gstop_le.textChanged.connect(self.resetCalculateParams)

        cal_order_label = Label('阶数（N）')
        self.cal_order_le = LineEditWithReg(focus=False)

        cal_Wn_label = Label('自然频率（Wn）')
        self.cal_Wn_le = LineEditWithReg(focus=False)

        self.cal_btn = PushButton('计算')
        self.cal_btn.clicked.connect(self.calculateParams)

        if not self.flag:
            self.cal_order_le.setText(str(self.cal_order))
            self.cal_Wn_le.setText(str(self.cal_Wn))
            self.cal_btn.setText('输入阶数和自然频率')

        hbox1 = QHBoxLayout()
        hbox2 = QHBoxLayout()
        hbox3 = QHBoxLayout()
        hbox4 = QHBoxLayout()
        cal_vbox = QVBoxLayout()

        hbox1.addWidget(combx_label)
        hbox1.addWidget(self.combx)
        hbox1.addStretch(1)
        hbox1.addWidget(self.checkbx)

        hbox2.addWidget(wp_label)
        hbox2.addWidget(self.wp_le)
        hbox2.addStretch(1)
        hbox2.addWidget(ws_label)
        hbox2.addWidget(self.ws_le)

        hbox3.addWidget(gpass_label)
        hbox3.addWidget(self.gpass_le)
        hbox3.addStretch(1)
        hbox3.addWidget(gstop_label)
        hbox3.addWidget(self.gstop_le)

        hbox4.addWidget(cal_order_label)
        hbox4.addWidget(self.cal_order_le)
        hbox4.addStretch(1)
        hbox4.addWidget(cal_Wn_label)
        hbox4.addWidget(self.cal_Wn_le)

        cal_vbox.addWidget(cal_label)
        cal_vbox.addSpacing(10)
        cal_vbox.addLayout(hbox1)
        cal_vbox.addSpacing(10)
        cal_vbox.addLayout(hbox2)
        cal_vbox.addSpacing(10)
        cal_vbox.addLayout(hbox3)
        cal_vbox.addSpacing(10)
        cal_vbox.addLayout(hbox4)
        cal_vbox.addSpacing(10)
        cal_vbox.addWidget(self.cal_btn)

        # 滤波器系数组件
        filter_params_label = Label('滤波器系数')
        filter_params_label.setAlignment(Qt.AlignHCenter)

        rp_label = Label('最大纹波（rp）')
        self.rp_le = LineEditWithReg(digit=True)
        self.rp_le.setToolTip('通带最大纹波（dB）')
        self.rp_le.setText(str(self.rp))

        rs_label = Label('最小衰减（rs）')
        self.rs_le = LineEditWithReg(digit=True)
        self.rs_le.setToolTip('阻带所需最小衰减（dB）')
        self.rs_le.setText(str(self.rs))

        order_label = Label('阶数（N）')
        self.order_le = LineEditWithReg()
        self.order_le.setToolTip('滤波器的阶数')
        self.order_le.setText(str(self.order))

        Wn_label = Label('自然频率（Wn）')
        self.Wn_le = LineEditWithReg(space=True)
        self.Wn_le.setToolTip('截止频率')
        self.Wn_le.setText(str(self.Wn))

        btn = PushButton('确定')
        btn.clicked.connect(self.updateParams)
        btn.clicked.connect(self.design)

        hbox5 = QHBoxLayout()
        hbox6 = QHBoxLayout()
        vbox = QVBoxLayout()

        hbox5.addWidget(rp_label)
        hbox5.addWidget(self.rp_le)
        hbox5.addStretch(1)
        hbox5.addWidget(rs_label)
        hbox5.addWidget(self.rs_le)

        hbox6.addWidget(order_label)
        hbox6.addWidget(self.order_le)
        hbox6.addStretch(1)
        hbox6.addWidget(Wn_label)
        hbox6.addWidget(self.Wn_le)

        vbox.addSpacing(10)
        vbox.addWidget(filter_params_label)
        vbox.addSpacing(10)
        vbox.addLayout(hbox5)
        vbox.addSpacing(10)
        vbox.addLayout(hbox6)

        norm_label = Label('标准化')
        self.norm_combx = ComboBox()
        self.norm_combx.setToolTip('截止频率标准化')
        self.norm_combx.addItems(self.norms)
        self.norm_combx.setCurrentText(self.norm)

        if self.filter == butter:
            rp_label.setEnabled(False)
            self.rp_le.setEnabled(False)
            rs_label.setEnabled(False)
            self.rs_le.setEnabled(False)
        elif self.filter == cheby1:
            rs_label.setEnabled(False)
            self.rs_le.setEnabled(False)
        elif self.filter == cheby2:
            rp_label.setEnabled(False)
            self.rp_le.setEnabled(False)

        if self.filter == bessel:
            vbox = QVBoxLayout()
            hbox1 = QHBoxLayout()
            hbox2 = QHBoxLayout()

            hbox1.addWidget(combx_label)
            hbox1.addWidget(self.combx)
            hbox1.addStretch(1)
            hbox1.addWidget(norm_label)
            hbox1.addWidget(self.norm_combx)
            hbox1.addStretch(1)
            hbox1.addWidget(self.checkbx)
            hbox2.addWidget(order_label)
            hbox2.addWidget(self.order_le)
            hbox2.addStretch(1)
            hbox2.addWidget(Wn_label)
            hbox2.addWidget(self.Wn_le)

            vbox.addSpacing(5)
            vbox.addWidget(filter_params_label)
            vbox.addLayout(hbox1)
            vbox.addSpacing(5)
            vbox.addLayout(hbox2)
            vbox.addSpacing(5)
            vbox.addWidget(btn)
            dialog.setLayout(vbox)
        else:
            dialog_layout = QVBoxLayout()
            dialog_layout.addLayout(cal_vbox)
            dialog_layout.addSpacing(10)
            dialog_layout.addLayout(vbox)
            dialog_layout.addSpacing(10)
            dialog_layout.addWidget(btn)
            dialog.setLayout(dialog_layout)

        btn.clicked.connect(self.filterData)
        btn.clicked.connect(dialog.close)
        dialog.exec_()

    def updateParams(self):
        """
        更新滤波器参数
        Returns:

        """
        self.method = self.combx.currentText()
        self.wp = self.wp_le.text()
        self.ws = self.ws_le.text()
        self.rp = float(self.rp_le.text())
        self.rs = float(self.rs_le.text())
        self.gpass = float(self.gpass_le.text())
        self.gstop = float(self.gstop_le.text())
        self.analog = self.checkbx.isChecked()
        self.norm = self.norm_combx.currentText()
        self.order = int(self.order_le.text())
        self.Wn = list(map(int, self.Wn_le.text().split(' ')))
        if self.method == 'lowpass' or self.method == 'highpass':
            self.Wn = self.Wn[0]

    def calculateParams(self):
        """
        使用函数计算滤波器的阶数和自然频率并填入滤波器参数中
        Returns:

        """
        self.wp = self.wp_le.text()
        self.ws = self.ws_le.text()
        self.analog = self.checkbx.isChecked()
        self.method = self.combx.currentText()

        if self.flag:
            wp = list(map(int, self.wp.split(' ')))
            ws = list(map(int, self.ws.split(' ')))
            if self.method in ['lowpass', 'highpass']:
                wp, ws = wp[0], ws[0]

            self.cal_order, self.cal_Wn = self.cal_names[self.filter](wp=wp,
                                                                      ws=ws,
                                                                      gpass=self.gpass,
                                                                      gstop=self.gstop,
                                                                      analog=self.analog,
                                                                      fs=self.sampling_rate)
            if self.method in ['lowpass', 'highpass']:
                self.cal_Wn = [int(self.cal_Wn)]
            else:
                self.cal_Wn = list(map(int, self.cal_Wn))

            self.cal_order_le.setText(str(self.cal_order))
            self.cal_Wn_le.setText(' '.join(map(str, self.cal_Wn)))
            self.cal_btn.setText('输入阶数与自然频率')
            self.flag = False

        else:
            self.order_le.setText(str(self.cal_order))
            self.Wn_le.setText(' '.join(map(str, self.cal_Wn)))

    def resetCalculateParams(self):
        """
        每次参数改动后重置计算按钮
        Returns:

        """
        self.flag = True
        if hasattr(self, 'cal_order_le'):
            self.cal_order_le.setText('')
            self.cal_Wn_le.setText('')
            self.cal_btn.setText('计算')

    def design(self):
        """
        设计滤波器
        Returns:

        """
        if self.filter == butter:
            self.b, self.a = self.filter(N=self.order,
                                         Wn=self.Wn,
                                         btype=self.method,
                                         analog=self.analog,
                                         fs=self.sampling_rate)
        elif self.filter == cheby1:
            self.b, self.a = self.filter(N=self.order,
                                         rp=self.rp,
                                         Wn=self.Wn,
                                         btype=self.method,
                                         analog=self.analog,
                                         fs=self.sampling_rate)
        elif self.filter == cheby2:
            self.b, self.a = self.filter(N=self.order,
                                         rs=self.rs,
                                         Wn=self.Wn,
                                         btype=self.method,
                                         analog=self.analog,
                                         fs=self.sampling_rate)
        elif self.filter == ellip:
            self.b, self.a = self.filter(N=self.order,
                                         rp=self.rp,
                                         rs=self.rs,
                                         Wn=self.Wn,
                                         btype=self.method,
                                         analog=self.analog,
                                         fs=self.sampling_rate)
        elif self.filter == bessel:
            self.b, self.a = self.filter(N=self.order,
                                         Wn=self.Wn,
                                         btype=self.method,
                                         analog=self.analog,
                                         norm=self.norm,
                                         fs=self.sampling_rate)

    def filterData(self):
        """
        滤波数据
        Returns:

        """
        self.draw = True
        self.data = filtfilt(self.b, self.a, self.data)  # 滤波


class FilterII:
    """二类滤波器"""
    filter_names = {
        'Notch Digital Filter': iirnotch,
        'Peak (Resonant) Digital Filter': iirpeak,
        'Notching or Peaking Digital Comb Filter': iircomb
    }
    ftypes = ['notch', 'peak']

    def __init__(self, filter_name: str, data: np.array, sampling_rate: int):
        """
        初始化各种参数
        Args:
            filter_name: 滤波器名称
            data: 数据
            sampling_rate: 采样率
            
        """
        self.data = data
        self.filter_name = filter_name
        self.filter = self.filter_names[filter_name]
        self.method = None
        self.sampling_rate = sampling_rate
        self.w0 = int(0.2 * sampling_rate)
        self.Q = 30.
        self.ftype = 'notch'
        self.pass_zero = False

        self.b = None
        self.a = None

        self.draw = False

    def filterData(self):
        """
        滤波数据
        Returns:

        """
        self.draw = True
        self.data = filtfilt(self.b, self.a, self.data)  # 滤波

    def runDialog(self):
        """
        初始化对话框布局
        Returns:

        """
        dialog = Dialog()
        dialog.setWindowTitle(f'设计{self.filter_name}滤波器')

        filter_params_label = Label('滤波器参数')
        filter_params_label.setAlignment(Qt.AlignHCenter)

        W0_label = Label('移除频率（Hz）')
        self.W0_le = LineEditWithReg()
        self.W0_le.setToolTip('从信号中移除的频率')
        self.W0_le.setText(str(self.w0))

        Q_label = Label('品质因数')
        self.Q_le = LineEditWithReg(digit=True)
        self.Q_le.setToolTip('表征 notch 类滤波器 -3dB 带宽的无量纲系数，与中心频率有关')
        self.Q_le.setText(str(self.Q))

        btn = PushButton('确定')
        btn.clicked.connect(self.updateParams)
        btn.clicked.connect(self.design)

        hbox = QHBoxLayout()
        vbox = QVBoxLayout()

        hbox.addWidget(W0_label)
        hbox.addWidget(self.W0_le)
        hbox.addStretch(1)
        hbox.addWidget(Q_label)
        hbox.addWidget(self.Q_le)

        vbox.addSpacing(5)
        vbox.addWidget(filter_params_label)
        vbox.addSpacing(10)
        vbox.addLayout(hbox)
        vbox.addSpacing(5)

        if self.filter == iircomb:
            ftype_label = Label('梳式滤波器类型')
            self.ftype_combx = ComboBox()
            self.ftype_combx.setToolTip(
                '生成的梳式滤波器类型，如果为notch，品质因子应用于波谷，如果为peak，品质因子应用与波峰')
            self.ftype_combx.addItems(self.ftypes)
            self.ftype_combx.setCurrentText(self.ftype)

            self.pass_zero_checkbx = CheckBox('非零')
            self.pass_zero_checkbx.setToolTip('默认为否，滤波器波谷集中于频率[0, w0, 2*w0, …]，'
                                              '波峰集中于中点[w0/2, 3*w0/2, 5*w0/2, …]；\n'
                                              '如果为是，波谷集中于[w0/2, 3*w0/2, 5*w0/2, …]，'
                                              '波峰集中于[0, w0, 2*w0, …]')
            self.pass_zero_checkbx.setChecked(self.pass_zero)

            hbox1 = QHBoxLayout()
            hbox1.addWidget(ftype_label)
            hbox1.addWidget(self.ftype_combx)
            hbox1.addStretch(1)
            hbox1.addWidget(self.pass_zero_checkbx)
            vbox.addLayout(hbox1)
            vbox.addSpacing(10)

        vbox.addWidget(btn)
        dialog.setLayout(vbox)
        btn.clicked.connect(self.filterData)
        btn.clicked.connect(dialog.close)
        dialog.exec_()

    def updateParams(self):
        """
        更新滤波器参数
        Returns:

        """
        self.draw = False
        self.w0 = int(self.W0_le.text())
        self.Q = float(self.Q_le.text())
        if self.filter == iircomb:
            self.ftype = self.ftype_combx.currentText()
            self.pass_zero = self.pass_zero_checkbx.isChecked()

    def design(self):
        """
        设计comb类滤波器
        Returns:

        """
        if self.filter == iircomb:
            self.b, self.a = self.filter(w0=self.w0,
                                         Q=self.Q,
                                         ftype=self.ftype,
                                         pass_zero=self.pass_zero,
                                         fs=self.sampling_rate)
        else:
            self.b, self.a = self.filter(w0=self.w0,
                                         Q=self.Q,
                                         fs=self.sampling_rate)


class FilterHandler:
    def __init__(self):
        """根据滤波器名创建滤波器类"""
        self.data = None
        self.method = None
        self.filter_name = None
        self.obj = None

    def run(self,
            name: str,
            data: np.array,
            sampling_times_from: int,
            sampling_times_to: int,
            sampling_rate: int) -> Optional[np.array]:
        """
        运行滤波器
        Args:
            name: 滤波器名称
            data: 数据
            sampling_times_from: 数据 x 轴起始
            sampling_times_to: 数据 x 轴终止
            sampling_rate: 采样率

        Returns: 滤波后的数据

        """
        if name != self.filter_name:
            self.filter_name = name
            if self.filter_name in {'Butterworth', 'Chebyshev type I', 'Chebyshev type II',
                                    'Elliptic (Cauer)', 'Bessel/Thomson'}:
                self.obj = FilterI(self.filter_name, data, sampling_rate)
            else:
                self.obj = FilterII(self.filter_name, data, sampling_rate)
        self.obj.draw = False
        self.obj.sampling_rate = sampling_rate
        self.obj.data = data
        self.obj.runDialog()
        self.method = self.obj.method

        if self.obj.draw:
            self.data = self.obj.data
            combined_widget = initCombinedPlotWidget(self.data,
                                                     'IIR滤波器',
                                                     sampling_times_from,
                                                     sampling_times_to,
                                                     len(data),
                                                     sampling_rate)

            return combined_widget
