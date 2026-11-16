# -*- coding: utf-8 -*-
"""
信号分析模块

- spectrum: FFT频谱分析（幅度谱、功率谱、相位谱）
- wavelet: 小波变换（DWT、CWT）
- wavelet_packet: 小波包分解（DWPT）
- emd: 经验模态分解（EMD、EEMD、CEEMDAN）
- snr: 信噪比计算
- feature: 特征提取（能量、方差、过零率）
- binary_image: 阈值二值化（Otsu、双峰法）
"""
from .spectrum import SpectrumHandler
from .wavelet import DWTHandler, CWTHandler
from .wavelet_packet import DWPTHandler
from .emd import EMDHandler
from .snr import SNRCalculator
from .feature import FeatureCalculator
from .binary_image import BinaryImageHandler

__all__ = [
    'SpectrumHandler', 'DWTHandler', 'CWTHandler', 'DWPTHandler',
    'EMDHandler', 'SNRCalculator', 'FeatureCalculator', 'BinaryImageHandler'
]
