# -*- coding: utf-8 -*-
"""
@Time    : 2024/6/12 上午8:52
@Author  : zxy
@File    : data_sifting.py
"""
import pickle
from pathlib import Path
from typing import List, Callable

import numpy as np
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout
from image.image import folder_jpg, import_jpg
from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from numpy import correlate
from scipy.signal import medfilt, medfilt2d, detrend
from scipy.signal.windows import *

from ..bin_reader import bin2numpy, read_bin_header
from ..function import DAS_FILE_FILTER, printError, setPicture
from ..theme import ui_font_family
from ..widget import Dialog, Label, TextEdit, PushButton, LineEditWithReg, ComboBox, CheckBox


def save_pickle(file: Path, data: np.array) -> None:
    """
    @description: 将数据保存为pickle格式文件
    @param {Path} file 保存的pickle文件路径
    @param {np} data 要保存的数据
    @return {*}
    """
    f = open(file, "wb")
    pickle.dump(data, f)
    f.close()


class Base:
    """双门限法信号筛选基类"""

    def __init__(self,
                 noise: Path,
                 file_path: List,
                 signal_threshold_ratio: float,
                 endpoint_threshold_ratio: float,
                 minimal_signal_length: float = 1.,
                 signal_interval: float = 0.5,
                 window_func: Callable = hamming,
                 frame_length: int = 128,
                 frame_shift: int = 96) -> None:
        """
        初始化参数
        Args:
            noise: 包含分段噪声信号的字典，时长需为一个文件长，键为噪声文件路径，格式为 pathlib.PosixPath，
                   值为包含与当前噪声文件对应的起止通道（包含）的List，且每段通道数之和应与数据文件总通道数一致，
                   各噪声文件其他参数应于数据文件一致
            file_path: 由 pathlib.PosixPath 组成的列表，每一个都是以.dat或.bin为结尾的数据文件
            signal_threshold_ratio: 信号特征阈值与噪声段特征的比
            endpoint_threshold_ratio: 信号端点特征阈值与噪声段特征的比
            minimal_signal_length: 信号最短长度，信号长度小于该值会被舍去
            signal_interval: 信号间的间隔，两段信号间间隔小于该值会将两端信号与之间的间隔合成为一段信号
            window_func: 窗函数
            frame_length: 帧长
            frame_shift: 帧移
        """
        self.file_path = file_path
        self.file_path.sort()
        self.file_name = [file.stem for file in self.file_path]  # 所有的文件名

        self.sampling_rate = 0
        self.sampling_times = 0
        self.channels_num = 0
        self.data = self._filter_data(data=self._read_data())

        self.noise = noise
        self.noise_data = self._filter_data(data=self._read_noise())
        self._concat_data()

        self.time_length = self.sampling_times // self.sampling_rate
        self.total_sampling_times = (len(self.file_path) + 1) * self.sampling_times

        self.minimal_signal_length = minimal_signal_length
        self.signal_interval = signal_interval
        self.window_func = window_func
        self.frame_length = frame_length
        self.frame_shift = frame_shift
        self.signal_threshold_ratio = signal_threshold_ratio
        self.endpoint_threshold_ratio = endpoint_threshold_ratio

        self.frames = []  # 经分帧后的帧
        self.frame_indices = []  # 包含每一帧起始索引对
        self.frames_num = 0  # 分帧后的总帧数
        self.no_signal_frames_num = self._get_no_signal_frames_num()

        self.feature = {}  # 各帧对应的特征值
        self.signal_threshold = {}  # 各通道信号特征值阈值
        self.endpoint_threshold = {}  # 各通道信号端点特征值阈值
        self.compare_mode = ""  # 特征阈值与特征的比较方法，more代表>=，less代表<=

        self.signals = {}  # 信号字典，key为通道号，value为包含对应通道信号的List
        self.signal_nums = 0  # 信号总数量
        self.signal_indices = {}  # 信号索引字典，key为通道号，value为包含对应同号信号索引的List
        self.search_channels = []  # 所有要搜索的通道号
        self.signal_channels = []  # 满足搜索条件，有信号的通道号
        self.saving_names = {}  # 保存数据名的字典，key为通道号，value为包含对应所保存信号起始及时间str的List

        self._init_rc_params()

        print("Initialization completed")

    @staticmethod
    def _init_rc_params() -> None:
        """
        初始化rc.Params
        Returns:
        """
        plt.rcParams["font.sans-serif"] = [ui_font_family(), "Microsoft YaHei", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False  # 显示负号
        plt.rcParams["axes.labelsize"] = 10
        plt.rcParams["axes.titlesize"] = 12
        plt.rcParams["xtick.labelsize"] = 9
        plt.rcParams["ytick.labelsize"] = 9
        plt.rcParams["legend.fontsize"] = 10

    @staticmethod
    def _detrend_data(data: np.array) -> np.array:
        """
        对数据去均值、线性趋势
        Args:
            data: 数据

        Returns: 数据

        """
        data = detrend(data, axis=1, type="constant")
        data = detrend(data, axis=1, type="linear")
        return data

    @staticmethod
    def _multimedfilt(data: np.array, kernel_size: int = 5, times: int = 10) -> np.array:
        """
        对数据进行多次中值滤波，须为一或二维
        Args:
            data: 输入数据
            kernel_size: 中值滤波核大小
            times: 滤波次数

        Returns: 中值滤波后的数据

        """
        if len(data.shape) == 1:
            for _ in range(times):
                data = medfilt(data, kernel_size=kernel_size)
        else:
            for _ in range(times):
                data = medfilt2d(data, kernel_size=(1, kernel_size))
        return data

    def _filter_data(self, data: np.array) -> np.array:
        """
        数据滤波
        Args:
            data:  输入数据

        Returns: 滤波后的数据

        """
        data = self._detrend_data(data=data)
        data = self._multimedfilt(data=data, kernel_size=3, times=1)
        return data

    def _read_data(self) -> np.array:
        """
        读取数据
        Returns: 数据

        """
        suffixes = {file.suffix.lower() for file in self.file_path}
        if len(suffixes) != 1:
            raise ValueError("一次只能读取同一种格式的数据文件。")

        first_file = self.file_path[0]
        if first_file.suffix.lower() == ".bin":
            _header, self.sampling_times, self.channels_num, self.sampling_rate, _ = read_bin_header(first_file)
        else:
            raw_data = np.fromfile(first_file, dtype="<f4")
            self.sampling_rate = int(raw_data[6])
            self.sampling_times = int(raw_data[7])
            self.channels_num = int(raw_data[9])

        data = []
        for file in self.file_path:
            if file.suffix.lower() == ".bin":
                _header, sampling_times, channels_num, sampling_rate, _ = read_bin_header(file)
                if not np.isclose(sampling_rate, self.sampling_rate):
                    printError(
                        f"data file {file} has sampling rate: {sampling_rate}, while first data file has {self.sampling_rate}"
                    )
                if sampling_times != self.sampling_times:
                    printError(
                        f"data file {file} has sampling times: {sampling_times}, while first data file has {self.sampling_times}"
                    )
                if channels_num != self.channels_num:
                    printError(
                        f"data file {file} has channels: {channels_num}, while first data file has {self.channels_num}"
                    )
                data.append(bin2numpy(file, 0, self.channels_num))
            else:
                raw_data = np.fromfile(file, dtype="<f4")
                data.append(raw_data[10:].reshape(self.channels_num, self.sampling_times))
        return np.concatenate(data, axis=1)

    def _read_noise(self) -> np.array:
        """
        读取分段噪声文件的数据，检测采样频率和单次采样点数是否相同
        Returns:

        """
        if self.noise.suffix.lower() == ".bin":
            _header, sampling_times, channels_num, sampling_rate, _ = read_bin_header(self.noise)
            noise_data = bin2numpy(self.noise, 0, channels_num)
        else:
            raw_data = np.fromfile(self.noise, dtype="<f4")
            sampling_rate = int(raw_data[6])
            sampling_times = int(raw_data[7])
            channels_num = int(raw_data[9])
            noise_data = raw_data[10:].reshape(channels_num, sampling_times)

        if sampling_rate != self.sampling_rate:
            printError(
                f"noise file {self.noise} has sampling rate: {sampling_rate}, while data files have {self.sampling_rate}"
            )
        if sampling_times != self.sampling_times:
            printError(
                f"noise file {self.noise} has sampling times: {sampling_times}, while data files have {self.sampling_times}"
            )
        if channels_num != self.channels_num:
            printError(
                f"noise file {self.noise} has sampling times: {channels_num}, while data files have {self.channels_num}"
            )
        return noise_data

    def _concat_data(self) -> None:
        """
        合并噪声段和待检测信号段
        Returns:

        """
        self.data = np.concatenate([self.noise_data, self.data], axis=1)

    def _windows(self) -> np.array:
        """
        加窗
        Returns: 窗长为帧长的窗

        """
        return self.window_func(self.frame_length)

    def _get_no_signal_frames_num(self) -> int:
        """
        计算前置噪声帧数
        Returns: 前置噪声段的帧数

        """
        return (self.sampling_times - self.frame_length) // self.frame_shift

    def _enframe(self, channel_number: int) -> None:
        """
        将单道信号分帧加窗
        Args:
            channel_number: 通道号

        Returns:

        """
        data = self.data[channel_number - 1]
        frames_num = (self.total_sampling_times - self.frame_length + self.frame_shift) // self.frame_shift
        pad_length = int(frames_num * self.frame_shift + self.frame_length) - self.total_sampling_times  # 计算填充数据长度
        data = np.pad(data, (0, pad_length), "constant")  # 填充数据
        frames = np.zeros((frames_num, self.frame_length))  # 创造返回的帧矩阵
        self.frame_indices = self.frame_shift * np.array([i for i in range(frames_num)])  # 计算每帧的索引
        for i in range(frames_num):
            frames[i, :] = data[self.frame_indices[i]:self.frame_indices[i] + self.frame_length]
        self.frames = frames * self._windows()

    def _get_feature(self, *args, **kwargs) -> None:
        """
        计算数据的特征值，更新self.feature以及两个阈值
        Args:
            *args: 
            **kwargs: 

        Returns:

        """
        ...

    def _search_signal_frame_indices(self, feature: np.array, channel_number: int) -> np.array:
        """
        搜索信号帧索引
        Args:
            feature: 各帧对应的特征值
            channel_number: 通道号

        Returns: 信号帧索引

        """
        frame_of_signal_indices = []
        begin, ptr = 0, self.no_signal_frames_num
        signal_threshold = self.signal_threshold[channel_number]
        while ptr < len(self.frames):
            if feature[ptr] >= signal_threshold:
                begin = ptr
                while ptr < len(self.frames) and feature[ptr] >= signal_threshold:
                    ptr += 1
                if ptr == len(self.frames) or feature[ptr] < signal_threshold:
                    frame_of_signal_indices.append([begin, ptr - 1])
            ptr += 1
        return frame_of_signal_indices

    def _search_endpoint_frame_indices(self, feature: np.array, indices: np.array, channel_number: int) -> np.array:
        """
        搜索信号端点帧索引，扩充信号帧索引
        Args:
            feature: 各帧对应的特征值
            indices: 信号帧索引
            channel_number: 通道号

        Returns: 信号端点帧索引

        """
        endpoint_threshold = self.endpoint_threshold[channel_number]
        for start, end in indices:
            while start > self.no_signal_frames_num and feature[start] >= endpoint_threshold:
                start -= 1
            while end < self.frames_num - 1 and feature[end] >= endpoint_threshold:
                end += 1
        return indices

    @staticmethod
    def _combine_indices(indices: List) -> List:
        """
        对于两段索引，如果第一段索引的开始与第二段索引的结束之前对应的索引长度小于信号间隔，
        则只保存第一段索引的开始与第二段索引的结束，以减少信号的数量
        Args:
            indices: 包含零、一或多组索引对的List，每一个索引对记录了信号的开始和结束索引

        Returns: 包含合并后信号索引对的List，每一个索引对记录了信号的开始和结束索引

        """
        combined_indices = []
        for index in indices:
            if not combined_indices or combined_indices[-1][1] < index[0]:
                combined_indices.append(index)
            else:
                combined_indices[-1][1] = combined_indices[-1][1] if combined_indices[-1][1] > index[1] else index[1]
        return combined_indices

    def _check_signal_length(self, indices: List) -> List:
        """
        检查信号长度是否满足最小长度要求，不满足则删除
        Args:
            indices: 包含表示信号索引对的List

        Returns:

        """
        res = []
        for index in indices:
            if index[1] - index[0] >= self.minimal_signal_length * self.sampling_rate:
                res.append(index)
        return res

    def _process_signal_frame_indices(self, signal_frame_indices: np.array) -> np.array:
        """
        处理搜索到的信号端点帧索引
        Args:
            signal_frame_indices: 信号帧索引

        Returns: 处理后的信号帧索引

        """
        indices = []
        if signal_frame_indices:
            for start, end in signal_frame_indices:
                begin, end = self.frame_indices[start], self.frame_indices[end] + self.frame_length
                if begin <= self.sampling_times:
                    begin = self.sampling_times
                if end >= self.total_sampling_times:
                    end = self.total_sampling_times - 1
                indices.append([begin, end])
        if indices:
            indices = self._check_signal_length(indices=indices)
            indices = self._combine_indices(indices=indices)
        return indices

    def _update_search_channels(self, channel_number: str) -> None:
        """
        更新要搜索的所有通道号
        Args:
            channel_number: 指定的通道，可传参单个通道号，或一个表示通道范围的列表，或None表示所有通道

        Returns:

        """
        channel_number = [int(x) for x in channel_number.split(' ') if x]
        if not channel_number:
            channel_number = [*range(1, self.channels_num + 1)]
        elif len(channel_number) > 1:
            channel_number = [*range(channel_number[0], channel_number[-1] + 1)]
        self.search_channels = channel_number

    def _update_signals(self, data: np.array, channel_number: int, indices: List) -> None:
        """
        更新搜索到的单通道信号及信号索引
        Args:
            data: 单通道原始信号
            channel_number: 单通道号
            indices: 包含表示信号索引对的List

        Returns:

        """
        if indices:
            self.signals[channel_number] = []
            self.signal_indices[channel_number] = []
            for index in indices:
                self.signals[channel_number].append(data[index[0]:index[1]])
                self.signal_indices[channel_number].append(index)

    def _update_signals_num(self) -> None:
        """
        更新存在满足搜索条件信号的通道号和搜索到的信号总数量
        Returns:

        """
        self.signal_channels = list(self.signals.keys())
        self.signals_num = sum(len(self.signals[x]) for x in self.signal_channels)

    def _search(self, channel_number: int) -> None:
        """
        搜索单道信号对应的帧索引，并转为时域信号索引，更新信号
        Args:
            channel_number: 通道号

        Returns:

        """
        data = self.data[channel_number - 1]
        signal_frame_indices = self._search_signal_frame_indices(feature=self.feature[channel_number],
                                                                 channel_number=channel_number)
        signal_frame_indices = self._search_endpoint_frame_indices(feature=self.feature[channel_number],
                                                                   indices=signal_frame_indices,
                                                                   channel_number=channel_number)
        signal_frame_indices = self._combine_indices(indices=signal_frame_indices)
        indices = self._process_signal_frame_indices(signal_frame_indices=signal_frame_indices)
        self._update_signals(data=data, channel_number=channel_number, indices=indices)

    def search(self, channel_number: str) -> None:
        """
        分帧、计算各帧特征值、搜索信号、更新信号数量
        Args:
            channel_number: 要搜索的通道

        Returns:

        """
        self._update_search_channels(channel_number=channel_number)
        for channel in self.search_channels:
            self._enframe(channel_number=channel)
            self._get_feature(channel_number=channel)
            self._search(channel_number=channel)
        self._update_signals_num()

    def _get_index_saving_name(self, index: List, channel_number: int) -> str:
        """
        获取单对信号索引的储存名称，包含所在文件起始、时间以及通道号
        Args:
            index: 单个信号索引对
            channel_number: 信号所在通道号

        Returns: 单个信号对应的储存名称

        """
        l, r = index
        l -= self.sampling_times
        r -= self.sampling_times
        fstart = l // self.sampling_times
        fend = r // self.sampling_times
        tbegin = l / self.sampling_rate - fstart * self.time_length
        tend = r / self.sampling_rate - fstart * self.time_length

        if fstart == fend:  # 处于一个文件
            saving_name = f"{self.file_name[fstart]}_time={tbegin:.3f}s_to_{tend:.3f}s_channel={channel_number}"
        else:
            saving_name = f"{self.file_name[fstart]}_to_{self.file_name[fend]}_time={tbegin:.3f}s_to_{tend:.3f}s_channel={channel_number}"
        return saving_name

    def _get_saving_name(self, channel_number: int, indices: List) -> List:
        """
        获取单通道所有信号的储存文件名
        Args:
            channel_number: 通道号
            indices: 包含表示信号索引对的List

        Returns: 该通道所有信号的储存文件名

        """
        saving_name = []
        for index in indices:
            saving_name.append(self._get_index_saving_name(index=index, channel_number=channel_number))
        return saving_name

    def _get_saving_names(self) -> None:
        """
        获取所有信号的存储名字
        Returns:

        """
        for key, value in self.signal_indices.items():
            self.saving_names[key] = self._get_saving_name(channel_number=key, indices=value)

    def _save(self, save_path: str) -> None:
        """
        保存指定或所有通道搜索到的信号，格式为.pickle
        Args:
            save_path: 保存文件夹路径

        Returns:

        """
        save_path = Path(save_path)
        for channel in self.signal_channels:
            for i in range(len(self.signals[channel])):
                saving_name, data = self.saving_names[channel][i], self.signals[channel][i]
                save_pickle(save_path / f"{saving_name}.pickle", data)

    def save(self, save_path: str) -> None:
        """
        获取保存名字、在save_path路径下新建一个class_name的文件夹，在其中保存选择通道的信号
        Args:
            save_path: 保存文件夹路径

        Returns:

        """
        self._get_saving_names()
        self._save(save_path=save_path)

    def plot_single_channel(self) -> FigureCanvas:
        """
        绘制某一通道的信号
        Args:

        Returns:

        """
        figure = plt.figure()
        figure_widget = FigureCanvas(figure)

        ch = self.signal_channels[0]
        signals = self.signals[ch]
        indices = self.signal_indices[ch]
        for i in range(len(signals)):
            x = np.linspace(indices[i][0], indices[i][1] - 1, len(signals[i])) / self.sampling_rate
            plt.plot(x, signals[i], label=f"信号 {i + 1}", zorder=2)

        source_data = self.data[ch - 1]
        x = np.linspace(1, self.total_sampling_times, self.total_sampling_times) / self.sampling_rate
        plt.plot(x, source_data, label="原始信号", alpha=0.3, zorder=1)
        plt.title(f"通道 {ch}")
        plt.xlabel("时间（秒）")
        plt.ylabel("相位差（弧度）")
        plt.legend()
        return figure_widget

    def plot_heatmap(self) -> FigureCanvas:
        """
        绘制搜索到的信号热力图
        Returns:

        """
        figure = plt.figure()
        figure_widget = FigureCanvas(figure)
        ax = plt.gca()
        ax.imshow(self.data, cmap="viridis", aspect="auto", vmin=0, vmax=1)
        ax.invert_yaxis()
        hd = []
        for channel in self.signal_channels:
            points_x = np.array(self.signal_indices[channel]).flatten() + 1
            n = len(points_x)
            hd.append(ax.scatter(x=points_x, y=[channel] * n, s=10, c="g"))
            hd.append(ax.hlines(y=[channel] * (n // 2), xmin=points_x[::2], xmax=points_x[1::2], colors="r", alpha=0.3))
        ax.set_xlim(0, self.total_sampling_times)
        ax.set_xticks(ticks=plt.xticks()[0], labels=plt.xticks()[0] / self.sampling_rate)
        ax.set_xlabel("时间（秒）")
        ax.set_ylim(0, self.channels_num)
        ax.set_ylabel("通道")
        ax.legend(handles=hd, labels=["信号端点", "信号"], loc="lower right")
        ax.set_title(f"信号数量 {self.signals_num}")
        return figure_widget


class Energy(Base):
    """基于短时能量"""

    def __init__(self,
                 signal_threshold_ratio: float = 5.,
                 endpoint_threshold_ratio: float = 3.,
                 *args,
                 **kwargs) -> None:
        """

        Args:
            signal_threshold_ratio:  信号短时能量与噪声段短时能量均值的比，短时能量大于于该值时认为是信号
            endpoint_threshold_ratio:  信号端点短时能量与噪声段短时能量均值的比，短时能量小于该值时认为是信号端点
            *args:
            **kwargs:
        """
        super().__init__(signal_threshold_ratio=signal_threshold_ratio,
                         endpoint_threshold_ratio=endpoint_threshold_ratio,
                         *args,
                         **kwargs)

    def _get_feature(self, channel_number: int) -> None:
        """
        计算分帧后数据的短时能量
        Args:
            channel_number: 通道号

        Returns:

        """
        short_time_energy = []
        for frame in self.frames:
            short_time_energy.append(np.sum(frame ** 2))

        self.feature[channel_number] = self._multimedfilt(np.array(short_time_energy))
        self.signal_threshold[channel_number] = np.mean(
            self.feature[channel_number][:self.no_signal_frames_num]) * self.signal_threshold_ratio
        self.endpoint_threshold[channel_number] = np.mean(
            self.feature[channel_number][:self.no_signal_frames_num]) * self.endpoint_threshold_ratio


class AutoCorrelationMaximum(Base):
    """基于自相关函数"""

    def __init__(self,
                 signal_threshold_ratio: float = 1.5,
                 endpoint_threshold_ratio: float = 1.2,
                 *args,
                 **kwargs) -> None:
        """

        Args:
            signal_threshold_ratio:  信号自相关系数阈值与噪声段自相关系数最大值的比，自相关系数大于该值时认为是信号
            endpoint_threshold_ratio:  信号端点自相关系数阈值与噪声段自相关系数最大值的比，自相关系数小于该值时认为是信号端点
            *args:
            **kwargs:
        """
        super().__init__(signal_threshold_ratio=signal_threshold_ratio,
                         endpoint_threshold_ratio=endpoint_threshold_ratio,
                         *args,
                         **kwargs)

    def _get_feature(self, channel_number: int) -> None:
        """
        计算分帧后的自相关函数
        Args:
            channel_number:

        Returns:

        """
        corr = []
        for frame in self.frames:
            corr.append(np.max(correlate(frame, frame, mode="full")))

        self.feature[channel_number] = self._multimedfilt(np.array(corr))
        self.signal_threshold[channel_number] = np.max(
            self.feature[channel_number][:self.no_signal_frames_num]) * self.signal_threshold_ratio
        self.endpoint_threshold[channel_number] = np.max(
            self.feature[channel_number][:self.no_signal_frames_num]) * self.endpoint_threshold_ratio


class CrossCorrelationMaximum(Base):
    """基于互相关函数"""

    def __init__(self,
                 signal_threshold_ratio: float = 1.5,
                 endpoint_threshold_ratio: float = 1.2,
                 *args,
                 **kwargs) -> None:
        """

        Args:
            signal_threshold_ratio:  信号互相关系数阈值与噪声段自相关系数最大值的比，互相关系数大于该值时认为是信号
            endpoint_threshold_ratio:  信号端点互相关系数阈值与噪声段自相关系数最大值的比，互相关系数小于该值时认为是信号端点
            *args:
            **kwargs:
        """
        super().__init__(signal_threshold_ratio=signal_threshold_ratio,
                         endpoint_threshold_ratio=endpoint_threshold_ratio,
                         *args,
                         **kwargs)

    def _get_feature(self, channel_number: int) -> None:
        """
        计算分帧后的互相关函数
        Args:
            channel_number: 通道号

        Returns:

        """
        corr = [0]
        for i in range(1, len(self.frames)):
            corr.append(np.max(correlate(self.frames[i - 1], self.frames[i], mode="full")))

        self.feature[channel_number] = self._multimedfilt(np.array(corr))
        self.signal_threshold[channel_number] = np.max(
            self.feature[channel_number][:self.no_signal_frames_num]) * self.signal_threshold_ratio
        self.endpoint_threshold[channel_number] = np.max(
            self.feature[channel_number][:self.no_signal_frames_num]) * self.endpoint_threshold_ratio


class DataSifting:
    """双门限法滤波"""

    def __init__(self, parent):
        """
        初始化
        Args:
            parent: 父级，为主窗口，为显示结果用
        """
        self.parent = parent
        self.methods = {
            '能量（均值）': Energy,
            '自相关函数（最大值）': AutoCorrelationMaximum,
            '互相关函数（最大值）': CrossCorrelationMaximum,
        }
        self.noise = None
        self.data_list = []

        self.save_path = str(Path.cwd())
        self.save_signals = True
        self.show_result = True

        self.feature_index = 0
        self.signal_threshold = 5.
        self.endpoint_threshold = 3.

        self.search_channels = ''
        self.minimal_signal_length = 1.
        self.signal_interval = 0.5

        self.window_index = 6
        self.window = hamming
        self.windows = {'Bartlett': bartlett, 'Blackman': blackman, 'Blackman-Harris': blackmanharris,
                        'Bohman': bohman, 'Cosine': cosine, 'Flat Top': flattop,
                        'Hamming': hamming, 'Hann': hann, 'Lanczos / Sinc': lanczos,
                        'Modified Barrtlett-Hann': barthann, 'Nuttall': nuttall, 'Parzen': parzen,
                        'Rectangular / Dirichlet': boxcar, 'Taylor': taylor, 'Triangular': triang,
                        'Tukey / Tapered Cosine': tukey}
        self.frame_length = 128
        self.frame_shift = 96

        self.dialog = None

        self.initDialogLayout()

    def selectNoiseData(self):
        """
        添加噪声文件，更新噪声文件文本框显示
        Returns:

        """
        file_name = QFileDialog.getOpenFileName(self.dialog, '选择噪声文件', '', DAS_FILE_FILTER)[0]
        if file_name:
            self.noise = Path(file_name)
            self.dialog.noise_text_edit.setText(file_name)

    def selectData(self):
        """
        添加数据文件，更新数据文件文本框显示
        Returns:

        """
        file_names = QFileDialog.getOpenFileNames(self.dialog, '选择数据文件', '', DAS_FILE_FILTER)[0]
        if file_names:
            self.dialog.data_text_edit.clear()
            self.data_list = [Path(x) for x in file_names]
            for name in file_names:
                self.dialog.data_text_edit.append(name)

    def selectSavePath(self):
        """
        选择保存路径
        Returns:

        """
        file_path = QFileDialog.getExistingDirectory(self.dialog, '设置文件路径', '')  # 起始路径
        if file_path != '':
            self.save_path = file_path
            self.dialog.save_path_line_edit.setText(file_path)

    def dataSifting(self):
        """
        创建数据筛选类，根据输入更新其参数，筛选数据、保存数据并显示结果
        Returns:

        """
        method = self.dialog.feature_combobox.currentText()
        obj = self.methods[method](
            noise=Path(self.noise),
            file_path=self.data_list,
            signal_threshold_ratio=self.signal_threshold,
            endpoint_threshold_ratio=self.endpoint_threshold,
            minimal_signal_length=self.minimal_signal_length,
            signal_interval=self.signal_interval,
            window_func=self.windows[self.window],
            frame_length=self.frame_length,
            frame_shift=self.frame_shift
        )
        obj.search(self.search_channels)

        if not obj.signals_num:
            printError('未搜索到信号！')
        else:
            msg = f'共搜索到 {obj.signals_num} 个信号\n'
            if self.save_signals:
                obj.save(self.save_path)
                msg += f'已保存至 {self.save_path}'
            printError(msg)

            if self.show_result:
                if len(obj.signal_channels) == 1:
                    figure_widget = obj.plot_single_channel()
                else:
                    figure_widget = obj.plot_heatmap()
                self.parent.tab_widget.addTab(figure_widget, f'{method}筛选结果：'
                                                             f'信号阈值={self.signal_threshold}\t'
                                                             f'信号端点阈值={self.endpoint_threshold}')

    def initDialogLayout(self):
        """
        初始化对话框布局
        Returns:

        """
        self.dialog = Dialog()
        self.dialog.resize(500, 300)
        self.dialog.setWindowTitle('数据筛选')

        noise_data_label = Label('噪声文件')
        self.dialog.noise_text_edit = TextEdit()
        select_noise_data_button = PushButton()
        setPicture(select_noise_data_button, import_jpg, 'import.jpg', )
        select_noise_data_button.clicked.connect(self.selectNoiseData)

        data_label = Label('数据文件')
        self.dialog.data_text_edit = TextEdit()
        select_data_button = PushButton()
        setPicture(select_data_button, import_jpg, 'import.jpg', )
        select_data_button.clicked.connect(self.selectData)

        save_path_label = Label('保存路径')
        self.dialog.save_path_line_edit = LineEditWithReg(focus=False)
        self.dialog.save_path_line_edit.setStyleSheet('min-width: 300px')
        select_save_path_button = PushButton()
        setPicture(select_save_path_button, folder_jpg, 'folder.jpg', )
        select_save_path_button.clicked.connect(self.selectSavePath)
        self.dialog.save_signals_checkbox = CheckBox('保存结果')

        self.dialog.show_result_checkbox = CheckBox('显示结果')

        feature_label = Label('特征值')
        self.dialog.feature_combobox = ComboBox()
        self.dialog.feature_combobox.addItems(['能量（均值）', '自相关函数（最大值）', '互相关函数（最大值）'])

        signal_threshold_label = Label('信号阈值')
        self.dialog.signal_threshold_line_edit = LineEditWithReg(digit=True)
        self.dialog.signal_threshold_line_edit.setToolTip('信号特征阈值与噪声段特征的比')

        endpoint_threshold_label = Label('信号端点阈值')
        self.dialog.endpoint_threshold_line_edit = LineEditWithReg(digit=True)
        self.dialog.endpoint_threshold_line_edit.setToolTip('信号端点特征阈值与噪声段特征的比')

        search_channels_label = Label('搜索通道')
        search_channels_label.setToolTip('')
        self.dialog.search_channels_line_edit = LineEditWithReg(space=True)
        self.dialog.search_channels_line_edit.setToolTip(
            '要搜索的通道号，不填表示搜索全部；单个通道号表示指定通道；两个通道号表示搜索介于二者区间的所有通道，应以空格分隔')

        minimal_signal_length_label = Label('最小信号长度（秒）')
        self.dialog.minimal_signal_length_line_edit = LineEditWithReg(digit=True)
        self.dialog.minimal_signal_length_line_edit.setToolTip('信号最短长度，信号长度小于该值会被舍去')

        signal_interval_label = Label('信号间隔（秒）')
        self.dialog.signal_interval_line_edit = LineEditWithReg(digit=True)
        self.dialog.signal_interval_line_edit.setToolTip(
            '信号间的间隔，两段信号间间隔小于该值会将两端信号与之间的间隔合成为一段信号')

        window_label = Label('窗函数')
        self.dialog.window_combobox = ComboBox()
        self.dialog.window_combobox.addItems(self.windows.keys())

        frame_length_label = Label('帧长')
        self.dialog.frame_length_line_edit = LineEditWithReg()

        frame_shift_label = Label('帧移')
        self.dialog.frame_shift_line_edit = LineEditWithReg()

        btn = PushButton('确定')
        btn.clicked.connect(self.updateParams)
        btn.clicked.connect(self.dataSifting)
        btn.clicked.connect(self.dialog.close)

        vbox = QVBoxLayout()
        top_box = QVBoxLayout()
        select_hbox = QHBoxLayout()
        path_hbox = QHBoxLayout()
        noise_vbox = QVBoxLayout()
        noise_hbox = QHBoxLayout()
        data_vbox = QVBoxLayout()
        data_hbox = QHBoxLayout()
        bottom_vbox = QVBoxLayout()
        threshold_hbox = QHBoxLayout()
        params_hbox = QHBoxLayout()

        noise_hbox.addWidget(noise_data_label)
        noise_hbox.addWidget(select_noise_data_button)
        noise_hbox.addStretch(1)
        noise_vbox.addLayout(noise_hbox)
        noise_vbox.addWidget(self.dialog.noise_text_edit)

        data_hbox.addWidget(data_label)
        data_hbox.addWidget(select_data_button)
        data_hbox.addStretch(1)
        data_vbox.addLayout(data_hbox)
        data_vbox.addWidget(self.dialog.data_text_edit)

        select_hbox.addLayout(noise_vbox)
        select_hbox.addLayout(data_vbox)

        path_hbox.addWidget(save_path_label)
        path_hbox.addWidget(self.dialog.save_path_line_edit)
        path_hbox.addWidget(select_save_path_button)
        path_hbox.addSpacing(5)
        path_hbox.addWidget(self.dialog.save_signals_checkbox)
        path_hbox.addStretch(1)
        path_hbox.addWidget(self.dialog.show_result_checkbox)

        top_box.addLayout(select_hbox)
        top_box.addSpacing(10)
        top_box.addLayout(path_hbox)

        threshold_hbox.addWidget(feature_label)
        threshold_hbox.addWidget(self.dialog.feature_combobox)
        threshold_hbox.addSpacing(5)
        threshold_hbox.addWidget(signal_threshold_label)
        threshold_hbox.addWidget(self.dialog.signal_threshold_line_edit)
        threshold_hbox.addSpacing(5)
        threshold_hbox.addWidget(endpoint_threshold_label)
        threshold_hbox.addWidget(self.dialog.endpoint_threshold_line_edit)
        threshold_hbox.addSpacing(5)
        threshold_hbox.addWidget(search_channels_label)
        threshold_hbox.addWidget(self.dialog.search_channels_line_edit)

        params_hbox.addWidget(minimal_signal_length_label)
        params_hbox.addWidget(self.dialog.minimal_signal_length_line_edit)
        params_hbox.addSpacing(5)
        params_hbox.addWidget(signal_interval_label)
        params_hbox.addWidget(self.dialog.signal_interval_line_edit)
        params_hbox.addSpacing(5)
        params_hbox.addWidget(window_label)
        params_hbox.addWidget(self.dialog.window_combobox)
        params_hbox.addSpacing(5)
        params_hbox.addWidget(frame_length_label)
        params_hbox.addWidget(self.dialog.frame_length_line_edit)
        params_hbox.addSpacing(5)
        params_hbox.addWidget(frame_shift_label)
        params_hbox.addWidget(self.dialog.frame_shift_line_edit)

        bottom_vbox.addLayout(threshold_hbox)
        bottom_vbox.addSpacing(10)
        bottom_vbox.addLayout(params_hbox)

        vbox.addLayout(top_box)
        vbox.addSpacing(10)
        vbox.addLayout(bottom_vbox)
        vbox.addSpacing(10)
        vbox.addWidget(btn)

        self.dialog.setLayout(vbox)

    def updateParams(self):
        """
        更新参数
        Returns:

        """
        self.save_path = self.dialog.save_path_line_edit.text()
        self.save_signals = self.dialog.save_signals_checkbox.isChecked()
        self.show_result = self.dialog.show_result_checkbox.isChecked()
        self.feature_index = self.dialog.feature_combobox.currentIndex()
        self.signal_threshold = float(self.dialog.signal_threshold_line_edit.text())
        self.endpoint_threshold = float(self.dialog.endpoint_threshold_line_edit.text())
        self.search_channels = self.dialog.search_channels_line_edit.text()
        self.minimal_signal_length = float(self.dialog.minimal_signal_length_line_edit.text())
        self.signal_interval = float(self.dialog.signal_interval_line_edit.text())
        self.window_index = self.dialog.window_combobox.currentIndex()
        self.window = self.dialog.window_combobox.currentText()
        self.frame_length = int(self.dialog.frame_length_line_edit.text())
        self.frame_shift = int(self.dialog.frame_shift_line_edit.text())

    def runDialog(self):
        """
        更新对话框组件显示并运行对话框
        Returns:

        """
        self.dialog.save_path_line_edit.setText(self.save_path)
        self.dialog.save_signals_checkbox.setChecked(self.save_signals)
        self.dialog.show_result_checkbox.setChecked(self.show_result)
        self.dialog.feature_combobox.setCurrentIndex(self.feature_index)
        self.dialog.signal_threshold_line_edit.setText(str(self.signal_threshold))
        self.dialog.endpoint_threshold_line_edit.setText(str(self.endpoint_threshold))
        self.dialog.search_channels_line_edit.setText(self.search_channels)
        self.dialog.minimal_signal_length_line_edit.setText(str(self.minimal_signal_length))
        self.dialog.signal_interval_line_edit.setText(str(self.signal_interval))
        self.dialog.window_combobox.setCurrentIndex(self.window_index)
        self.dialog.frame_length_line_edit.setText(str(self.frame_length))
        self.dialog.frame_shift_line_edit.setText(str(self.frame_shift))
        self.dialog.exec_()
