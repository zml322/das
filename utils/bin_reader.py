import os
import numpy as np

HEADER_FLOATS = 20
HEADER_BYTES = HEADER_FLOATS * 4


def read_bin_header(file_path):
    """
    读取 20 位头(80字节)的 .bin 格式 DAS 数据头。

    Returns:
        tuple: (header, sampling_times, channels_num, endian)
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

    # 获取维度 N(每道点数) 和 M(道数)
    n_hdr = int(round(float(hdr[7])))
    m_hdr = int(round(float(hdr[8])))

    # 利用文件总长度做交叉验证 (Cross-check)
    body_bytes = file_size - HEADER_BYTES
    if body_bytes % 4 != 0:
        raise ValueError(f"{file_path}: 数据体字节数不是 float32 的整数倍。")
    total_floats = body_bytes // 4

    if n_hdr > 0 and m_hdr > 0 and n_hdr * m_hdr == total_floats:
        N, M = n_hdr, m_hdr
    elif n_hdr > 0 and total_floats % n_hdr == 0:
        N, M = n_hdr, total_floats // n_hdr
    elif m_hdr > 0 and total_floats % m_hdr == 0:
        M, N = m_hdr, total_floats // m_hdr
    else:
        raise ValueError(f"{file_path}: 无法推断维度，n_hdr={n_hdr}, m_hdr={m_hdr}, 实际数据量={total_floats}")

    return hdr, N, M, endian


def bin2numpy(file_path, ch1=0, ch2=None):
    """
    直接读取 20 位头(80字节)的 .bin 格式 DAS 数据。

    返回形状为 (采样次数, 通道数)；主程序内部使用时需要转置为 (通道数, 采样次数)。
    """
    _header, N, M, endian = read_bin_header(file_path)
    if ch2 is None:
        ch2 = M
    if ch1 < 0 or ch2 > M or ch1 >= ch2:
        raise ValueError(f"{file_path}: 通道范围无效，ch1={ch1}, ch2={ch2}, channels={M}")

    # 一次性读取数据体
    with open(file_path, "rb") as f:
        f.seek(HEADER_BYTES)
        data_bytes = f.read()

    # 按照对应的大小端格式将字节流转为 float32 数组
    dtype_str = endian + "f4"
    data_arr = np.frombuffer(data_bytes, dtype=dtype_str)

    # 按照列优先（Fortran order）重塑为 (nt, nchan) 矩阵
    data_matrix = data_arr.reshape((N, M), order='F')

    # 截取你需要的道数范围并返回（加上 astype 确保内存连续性，保护后续 pytorch 运算不报错）
    return data_matrix[:, ch1:ch2].astype(np.float32, copy=False)
