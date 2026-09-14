"""Convert this viewer's 20-float-header BIN files into DASPy sections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from uuid import uuid4

import numpy as np

from daspy import DASDateTime, Section

from ..bin_reader import bin2numpy, read_bin_header


OUTPUT_FORMATS: Tuple[Tuple[str, str, str], ...] = (
    ("pkl", "DASPy PKL（推荐，保留元数据）", ".pkl"),
    ("h5", "DASPy HDF5（.h5）", ".h5"),
    ("sgy", "DASPy SEG-Y（.sgy）", ".sgy"),
)

FORMAT_EXTENSIONS: Dict[str, str] = {
    name: extension for name, _label, extension in OUTPUT_FORMATS
}


@dataclass(frozen=True)
class BinMetadata:
    """Validated metadata available in the project-specific BIN header."""

    source: Path
    header: np.ndarray
    sampling_times: int
    channel_count: int
    sampling_rate: float
    endianness: str
    start_time: Optional[datetime]


def _header_start_time(header: np.ndarray) -> Optional[datetime]:
    """Return the six date fields in the BIN header when they form a date."""

    try:
        year, month, day, hour, minute, second = (
            int(round(float(value))) for value in header[:6]
        )
        return datetime(year, month, day, hour, minute, second)
    except (TypeError, ValueError, OverflowError):
        return None


def read_bin_metadata(source: str | Path) -> BinMetadata:
    """Read the source header without loading the full DAS array."""

    source_path = Path(source).expanduser()
    header, sampling_times, channel_count, sampling_rate, endianness = read_bin_header(
        source_path
    )
    return BinMetadata(
        source=source_path,
        header=np.asarray(header, dtype=np.float32).copy(),
        sampling_times=int(sampling_times),
        channel_count=int(channel_count),
        sampling_rate=float(sampling_rate),
        endianness=str(endianness),
        start_time=_header_start_time(header),
    )


def normalize_output_path(output: str | Path, output_format: str) -> Path:
    """Apply the extension required by the selected DASPy writer."""

    try:
        extension = FORMAT_EXTENSIONS[output_format]
    except KeyError as error:
        available = ", ".join(FORMAT_EXTENSIONS)
        raise ValueError(f"不支持的 DASPy 输出格式：{output_format}（可选：{available}）") from error
    return Path(output).expanduser().with_suffix(extension)


def _as_daspy_datetime(value: Optional[datetime]) -> int | DASDateTime:
    """DASPy writers require its datetime subtype for formatted timestamps."""

    if value is None:
        return 0
    return DASDateTime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
    )


def build_section_from_bin(
    source: str | Path,
    *,
    channel_spacing: float,
    sampling_rate: Optional[float] = None,
    start_channel: int = 0,
    start_distance: float = 0.0,
    gauge_length: Optional[float] = None,
    start_time: Optional[datetime] = None,
    data_type: str = "",
    scale: float = 1.0,
) -> tuple[Section, BinMetadata]:
    """Load a BIN file and construct an in-memory DASPy ``Section``.

    ``channel_spacing`` is the true adjacent-channel spacing ``dx``.  It is
    intentionally separate from ``gauge_length`` because those two acquisition
    parameters describe different physical quantities.
    """

    metadata = read_bin_metadata(source)
    dx = float(channel_spacing)
    fs = metadata.sampling_rate if sampling_rate is None else float(sampling_rate)
    scale_value = float(scale)
    if not np.isfinite(dx) or dx <= 0:
        raise ValueError("相邻通道间距 dx 必须是大于 0 的有限数值")
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError("采样率必须是大于 0 的有限数值")
    if not np.isfinite(scale_value) or scale_value <= 0:
        raise ValueError("数据比例 scale 必须是大于 0 的有限数值")

    gauge_value: Optional[float]
    if gauge_length is None:
        gauge_value = None
    else:
        gauge_value = float(gauge_length)
        if not np.isfinite(gauge_value) or gauge_value <= 0:
            raise ValueError("Gauge length 为空或必须是大于 0 的有限数值")

    # ``bin2numpy`` is backed by the immutable bytes returned from the file.
    # Make an owned, writable array because DASPy's readers may update the
    # array in-place while normalizing missing values after a later reload.
    data = np.array(bin2numpy(metadata.source), dtype=np.float32, copy=True, order="C")
    if data.shape != (metadata.channel_count, metadata.sampling_times):
        raise ValueError(
            "BIN 数据尺寸与头部不一致："
            f"读取到 {data.shape}，头部为 "
            f"({metadata.channel_count}, {metadata.sampling_times})"
        )
    if not np.all(np.isfinite(data)):
        raise ValueError("BIN 数据包含 NaN 或无穷值，拒绝导出不完整的 DASPy 文件")

    section_kwargs = {
        "headers": {
            "project_bin_header": metadata.header.tolist(),
            "bin_endianness": metadata.endianness,
            "bin_sampling_times": metadata.sampling_times,
            "bin_channel_count": metadata.channel_count,
        },
        "source": str(metadata.source),
        "source_type": "bin",
        "scale": scale_value,
    }
    if gauge_value is not None:
        section_kwargs["gauge_length"] = gauge_value
    if data_type.strip():
        section_kwargs["data_type"] = data_type.strip()

    section = Section(
        data,
        dx=dx,
        fs=fs,
        start_channel=int(start_channel),
        start_distance=float(start_distance),
        start_time=_as_daspy_datetime(start_time or metadata.start_time),
        **section_kwargs,
    )
    return section, metadata


def convert_bin_to_daspy(
    source: str | Path,
    output: str | Path,
    output_format: str,
    *,
    channel_spacing: float,
    sampling_rate: Optional[float] = None,
    start_channel: int = 0,
    start_distance: float = 0.0,
    gauge_length: Optional[float] = None,
    start_time: Optional[datetime] = None,
    data_type: str = "",
    scale: float = 1.0,
    overwrite: bool = False,
) -> tuple[Path, BinMetadata]:
    """Convert a BIN file atomically and return the final output path.

    A temporary sibling file is written first, so failed exports do not leave a
    truncated result at the requested path.  The source file is read only.
    """

    output_path = normalize_output_path(output, output_format)
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"找不到 BIN 源文件：{source_path}")
    if source_path == output_path.resolve():
        raise ValueError("输出文件不能覆盖 BIN 源文件")
    if not output_path.parent.is_dir():
        raise FileNotFoundError(f"输出目录不存在：{output_path.parent}")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"输出文件已存在：{output_path}")

    section, metadata = build_section_from_bin(
        source_path,
        channel_spacing=channel_spacing,
        sampling_rate=sampling_rate,
        start_channel=start_channel,
        start_distance=start_distance,
        gauge_length=gauge_length,
        start_time=start_time,
        data_type=data_type,
        scale=scale,
    )
    temporary_path = output_path.with_name(
        f".{output_path.stem}.{uuid4().hex}.tmp{output_path.suffix}"
    )
    try:
        section.save(str(temporary_path), ftype=output_format)
        if not temporary_path.is_file() or temporary_path.stat().st_size == 0:
            raise RuntimeError("DASPy 未生成有效的输出文件")
        temporary_path.replace(output_path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return output_path, metadata
