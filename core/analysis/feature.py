# -*- coding: utf-8 -*-
"""
@Time    : 2024/9/30 上午9:52
@Author  : zxy
@File    : feature.py
"""
import numpy as np
from scipy import stats


class FeatureCalculator:
    features = {
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
        '峭度因子': 'kurtosis_factor',
        '重心频率': 'centroid_frequency',
        '平均频率': 'mean_frequency',
        '均方根频率': 'root_mean_square_frequency',
        '均方频率': 'mean_square_frequency',
        '频率方差': 'frequency_variance',
        '频率标准差': 'frequency_standard_deviation'
    }

    def __init__(self, feature_name: str, data: np.array, sampling_rate: int):
        """
        Args:
            feature_name: 特征名称
            data: 数据
            sampling_rate: 采样率

        """
        self.feature_name = feature_name
        self.data = data
        self.sampling_rate = sampling_rate

        self.channels_num, self.sampling_times = data.shape

    def max_value(self) -> np.array:
        """最大值"""
        return np.max(self.data, axis=1)

    def peak_value(self) -> np.array:
        """最大绝对值"""
        return np.max(np.abs(self.data), axis=1)

    def min_value(self) -> np.array:
        """最小值"""
        return np.min(self.data, axis=1)

    def mean(self) -> np.array:
        """均值"""
        return np.mean(self.data, axis=1)

    def peak_peak_value(self) -> np.array:
        """峰峰值"""
        return self.max_value() - self.min_value()

    def mean_absolute_value(self) -> np.array:
        """绝对平均值"""
        return np.mean(np.abs(self.data), axis=1)

    def root_mean_square(self) -> np.array:
        """均方根值"""
        return np.sqrt(np.sum(self.data ** 2, axis=1) / self.sampling_times)

    def square_root_amplitude(self) -> np.array:
        """方根幅值"""
        return (np.sum(np.sqrt(np.abs(self.data)), axis=1) / self.sampling_times) ** 2

    def variance(self) -> np.array:
        """方差"""
        return np.var(self.data, axis=1)

    def standard_deviation(self) -> np.array:
        """标准差"""
        return np.std(self.data, axis=1)

    def kurtosis(self) -> np.array:
        """峭度"""
        return stats.kurtosis(self.data, axis=1, fisher=False)

    def skewness(self) -> np.array:
        """偏度"""
        return stats.skew(self.data, axis=1)

    def clearance_factor(self) -> np.array:
        """裕度指标"""
        return self.peak_value() / self.square_root_amplitude()

    def shape_factor(self) -> np.array:
        """波形指标"""
        return self.root_mean_square() / self.mean_absolute_value()

    def impulse_factor(self) -> np.array:
        """脉冲指标"""
        return self.peak_value() / self.mean_absolute_value()

    def crest_factor(self) -> np.array:
        """峰值指标"""
        return self.peak_value() / self.root_mean_square()

    def kurtosis_factor(self) -> np.array:
        """峭度指标"""
        return self.kurtosis() / (self.root_mean_square() ** 4)

    def fft(self) -> np.array:
        """fft 结果"""
        return np.fft.fft(self.data, axis=1)[:, :self.sampling_times // 2]

    def magnitude(self) -> np.array:
        """信号幅值"""
        return np.abs(self.fft())

    def frequency(self) -> np.array:
        """频率轴"""
        return np.fft.fftfreq(self.sampling_times, 1 / self.sampling_rate)[:self.sampling_times // 2]

    def power(self) -> np.array:
        """功率谱"""
        return self.magnitude() ** 2 / self.sampling_times

    def centroid_frequency(self) -> np.array:
        """重心频率"""
        return np.sum(self.frequency() * self.power(), axis=1) / np.sum(self.power(), axis=1)

    def mean_frequency(self) -> np.array:
        """平均频率"""
        return np.mean(self.power(), axis=1)

    def mean_square_frequency(self) -> np.array:
        """均方频率"""
        return np.sum(self.power() * np.square(self.frequency()), axis=1) / np.sum(self.power(), axis=1)

    def root_mean_square_frequency(self) -> np.array:
        """均方根频率"""
        return np.sqrt(self.mean_square_frequency())

    def frequency_variance(self) -> np.array:
        """频率方差"""
        ps = self.power()
        freq = np.tile(self.frequency(), (self.channels_num, 1))
        cf = np.tile(self.centroid_frequency().reshape(-1, 1), (1, self.sampling_times // 2))
        return np.sum(ps * (freq - cf) ** 2, axis=1) / np.sum(ps, axis=1)

    def frequency_standard_deviation(self) -> np.array:
        """频率标准差"""
        return np.sqrt(self.frequency_variance())

    def run(self) -> np.array:
        """计算所选特征"""
        return getattr(self, self.features[self.feature_name])()
