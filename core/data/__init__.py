# -*- coding: utf-8 -*-
"""
数据管理模块

- bin_reader: BIN格式文件读取（20浮点头+数据体）
- data_group: 多文件拼接与内存预算管理
- data_timeline: 时间轴元数据与文件-时间映射
"""
from .bin_reader import bin2numpy, read_bin_header, bin_window
from .data_group import DataGroup, ensure_memory_budget, natural_sort_key, format_bytes
from .data_timeline import DataTimeline, format_wall_time

__all__ = [
    'bin2numpy', 'read_bin_header', 'bin_window',
    'DataGroup', 'ensure_memory_budget', 'natural_sort_key', 'format_bytes',
    'DataTimeline', 'format_wall_time'
]
