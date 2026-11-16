"""Data-group metadata and memory guards for stitched DAS files."""

from __future__ import annotations

import ctypes
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


def natural_sort_key(value: str) -> Tuple[Tuple[int, object], ...]:
    """Return a case-insensitive key that keeps numeric filename parts ordered."""

    text = str(value)
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in re.split(r"(\d+)", text)
        if part
    )


@dataclass(frozen=True)
class FileSegment:
    """The sample interval occupied by one source file in a stitched array."""

    path: str
    start_sample: int
    sample_count: int

    def __post_init__(self) -> None:
        if int(self.start_sample) < 0:
            raise ValueError("文件分段起始采样点不能小于 0")
        if int(self.sample_count) <= 0:
            raise ValueError("文件分段采样点数必须大于 0")

    @property
    def end_sample(self) -> int:
        """Exclusive global sample end."""

        return int(self.start_sample) + int(self.sample_count)

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def sample_range(self) -> Tuple[int, int]:
        return int(self.start_sample), self.end_sample


@dataclass
class DataGroup:
    """Description of the source files represented by one viewer data array."""

    channel_count: int
    sampling_rate: float
    segments: List[FileSegment] = field(default_factory=list)

    def __post_init__(self) -> None:
        if int(self.channel_count) <= 0:
            raise ValueError("数据组通道数必须大于 0")
        if float(self.sampling_rate) <= 0:
            raise ValueError("数据组采样率必须大于 0")
        expected_start = 0
        for segment in self.segments:
            if segment.start_sample != expected_start:
                raise ValueError("数据组文件分段必须连续且不能重叠")
            expected_start = segment.end_sample

    @classmethod
    def from_files(
        cls,
        file_paths: Sequence[str],
        sample_counts: Sequence[int],
        channel_count: int,
        sampling_rate: float,
    ) -> "DataGroup":
        if len(file_paths) != len(sample_counts) or not file_paths:
            raise ValueError("文件路径和采样点数必须一一对应且不能为空")
        start = 0
        segments: List[FileSegment] = []
        for path, count in zip(file_paths, sample_counts):
            segment = FileSegment(str(path), start, int(count))
            segments.append(segment)
            start = segment.end_sample
        return cls(int(channel_count), float(sampling_rate), segments)

    @property
    def total_samples(self) -> int:
        return self.segments[-1].end_sample if self.segments else 0

    @property
    def segment_ranges(self) -> List[Tuple[int, int]]:
        return [segment.sample_range for segment in self.segments]

    @property
    def boundaries(self) -> List[int]:
        return [segment.start_sample for segment in self.segments[1:]]


def available_memory_bytes() -> Optional[int]:
    """Return currently available physical memory when the platform exposes it."""

    if sys.platform == "win32":
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except (AttributeError, OSError):
            return None

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return None
    return page_size * available_pages


def estimate_array_bytes(
    channel_count: int,
    sample_count: int,
    copies: float = 1.0,
) -> int:
    """Estimate float32 array memory for a workflow with multiple live copies."""

    return int(int(channel_count) * int(sample_count) * 4 * float(copies))


def ensure_memory_budget(
    channel_count: int,
    sample_count: int,
    copies: float,
    operation: str,
    maximum_fraction: float = 0.75,
) -> Tuple[int, Optional[int]]:
    """Reject work that is likely to exhaust currently available memory."""

    required = estimate_array_bytes(channel_count, sample_count, copies)
    available = available_memory_bytes()
    if available is not None and required > int(available * maximum_fraction):
        raise MemoryError(
            f"{operation}预计至少需要 {format_bytes(required)} 内存，"
            f"当前可用约 {format_bytes(available)}；请减少文件数、通道或时间范围。"
        )
    return required, available


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TiB"
