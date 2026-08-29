import os
import numpy as np

HEADER_FLOATS = 20
HEADER_BYTES = HEADER_FLOATS * 4
HEADER_FRAMES_INDEX = 7
HEADER_CHANNELS_INDEX = 8
HEADER_SAMPLING_RATE_INDEX = 9


def bin_header_metadata(header):
    """解析 notebook 定义的 BIN 头字段。"""
    if len(header) < HEADER_FLOATS:
        raise ValueError(f"BIN 文件头长度不足，期望 {HEADER_FLOATS} 个 float32。")

    def integer_field(index, name):
        value = float(header[index])
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"BIN 文件头 {name} 无效: {value}")
        integer_value = int(value)
        if value != integer_value:
            raise ValueError(f"BIN 文件头 {name} 必须是正整数: {value}")
        return integer_value

    sampling_times = integer_field(HEADER_FRAMES_INDEX, "帧数(header[7])")
    channels_num = integer_field(HEADER_CHANNELS_INDEX, "通道数(header[8])")
    sampling_rate = float(header[HEADER_SAMPLING_RATE_INDEX])
    if not np.isfinite(sampling_rate) or sampling_rate <= 0:
        raise ValueError(f"BIN 文件头采样率(header[9])无效: {sampling_rate}")
    return sampling_times, channels_num, sampling_rate


def read_bin_header(file_path):
    """
    读取 20 位头(80字节)的 .bin 格式 DAS 数据头。

    Returns:
        tuple: (header, sampling_times, channels_num, sampling_rate, endian)
    """
    file_size = os.path.getsize(file_path)

    if file_size <= HEADER_BYTES:
        raise ValueError(f"{file_path}: 文件太短，无法读取。")

    with open(file_path, "rb") as f:
        head_bytes = f.read(HEADER_BYTES)

    # 同时按小端 / 大端解析，根据年月日判断字节序
    hdr_le = np.frombuffer(head_bytes, dtype="<f4", count=HEADER_FLOATS)
    hdr_be = np.frombuffer(head_bytes, dtype=">f4", count=HEADER_FLOATS)

    def looks_like_date(h):
        try:
            y, m, d = int(round(float(h[0]))), int(round(float(h[1]))), int(round(float(h[2])))
            return (2000 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31)
        except:
            return False

    if looks_like_date(hdr_le):
        endian = "<"
        hdr = hdr_le
    elif looks_like_date(hdr_be):
        endian = ">"
        hdr = hdr_be
    else:
        endian = "<"
        hdr = hdr_le

    sampling_times, channels_num, sampling_rate = bin_header_metadata(hdr)

    # 利用文件总长度做交叉验证 (Cross-check)
    body_bytes = file_size - HEADER_BYTES
    if body_bytes % 4 != 0:
        raise ValueError(f"{file_path}: 数据体字节数不是 float32 的整数倍。")
    total_floats = body_bytes // 4

    expected_floats = sampling_times * channels_num
    if expected_floats != total_floats:
        raise ValueError(
            f"{file_path}: 头部帧数={sampling_times}、通道数={channels_num}，"
            f"预期数据量={expected_floats}，实际数据量={total_floats}")

    return hdr, sampling_times, channels_num, sampling_rate, endian


def bin2numpy(file_path, ch1=0, ch2=None):
    """
    直接读取 20 位头(80字节)的 .bin 格式 DAS 数据。

    返回与 bin.ipynb 一致的 (通道数, 采样次数) 形状。
    """
    _header, sampling_times, channels_num, _sampling_rate, endian = read_bin_header(file_path)
    if ch2 is None:
        ch2 = channels_num
    if ch1 < 0 or ch2 > channels_num or ch1 >= ch2:
        raise ValueError(f"{file_path}: 通道范围无效，ch1={ch1}, ch2={ch2}, channels={channels_num}")

    # 一次性读取数据体
    with open(file_path, "rb") as f:
        f.seek(HEADER_BYTES)
        data_bytes = f.read()

    # 按照对应的大小端格式将字节流转为 float32 数组
    dtype_str = endian + "f4"
    data_arr = np.frombuffer(data_bytes, dtype=dtype_str)

    # 原始数据按通道逐帧连续存储，和 notebook 的 reshape 方式保持一致。
    data_matrix = data_arr.reshape((channels_num, sampling_times))

    # 截取你需要的道数范围并返回（加上 astype 确保内存连续性，保护后续 pytorch 运算不报错）
    return data_matrix[ch1:ch2].astype(np.float32, copy=False)
