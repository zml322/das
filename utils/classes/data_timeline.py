"""Corrected, continuous wall-clock timeline for stitched DAS files."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Tuple

from .data_group import DataGroup


_DAS_FILENAME_TIME = re.compile(
    r"(?<!\d)((?:19|20)\d{2})[-_](\d{1,2})[-_](\d{1,2})"
    r"[-_](\d{1,2})[-_](\d{1,2})[-_](\d{1,2})(?!\d)"
)


def parse_filename_end_time(path: str) -> Optional[datetime]:
    """Parse the recorded acquisition-end time from a common DAS filename."""

    match = _DAS_FILENAME_TIME.search(os.path.basename(str(path)))
    if match is None:
        return None
    try:
        return datetime(*map(int, match.groups()))
    except ValueError:
        return None


def datetime_from_header(header: Sequence[float]) -> Optional[datetime]:
    """Build a naive local datetime from the first six numeric header fields."""

    if len(header) < 6:
        return None
    try:
        year, month, day, hour, minute = (int(round(float(value))) for value in header[:5])
        second_value = float(header[5])
        return datetime(year, month, day, hour, minute) + timedelta(seconds=second_value)
    except (TypeError, ValueError, OverflowError):
        return None


def recorded_end_time(path: str, header: Sequence[float]) -> Tuple[datetime, str]:
    """Prefer the filename end time and fall back to the BIN/DAT header."""

    filename_time = parse_filename_end_time(path)
    if filename_time is not None:
        return filename_time, "filename"
    header_time = datetime_from_header(header)
    if header_time is not None:
        return header_time, "header"
    raise ValueError(f"{path}: 文件名和文件头都没有可识别的采集结束时间")


@dataclass(frozen=True)
class TimelineSegment:
    """Time metadata for one source segment in a continuous stitched timeline."""

    path: str
    start_sample: int
    sample_count: int
    recorded_end: datetime
    timestamp_source: str
    corrected_recorded_end: datetime
    inferred_start: datetime
    inferred_end: datetime
    end_time_difference_seconds: float

    @property
    def end_sample(self) -> int:
        return int(self.start_sample) + int(self.sample_count)


@dataclass(frozen=True)
class DataTimeline:
    """Continuous time mapping anchored by the corrected first-file end time."""

    start_time: datetime
    end_time: datetime
    sampling_rate: float
    total_samples: int
    correction_seconds: float
    continuity_tolerance_seconds: float
    segments: Tuple[TimelineSegment, ...]

    @classmethod
    def from_data_group(
        cls,
        data_group: DataGroup,
        headers: Sequence[Sequence[float]],
        correction_seconds: float = 12.0,
        continuity_tolerance_seconds: float = 1.0,
    ) -> "DataTimeline":
        if not data_group.segments:
            raise ValueError("时间轴需要至少一个文件分段")
        if len(headers) != len(data_group.segments):
            raise ValueError("时间头数量必须与文件分段数量一致")
        sampling_rate = float(data_group.sampling_rate)
        correction = float(correction_seconds)
        recorded = [
            recorded_end_time(segment.path, header)
            for segment, header in zip(data_group.segments, headers)
        ]
        first_segment = data_group.segments[0]
        first_corrected_end = recorded[0][0] + timedelta(seconds=correction)
        start_time = first_corrected_end - timedelta(
            seconds=first_segment.sample_count / sampling_rate
        )
        end_time = start_time + timedelta(
            seconds=data_group.total_samples / sampling_rate
        )

        timeline_segments: List[TimelineSegment] = []
        for segment, (source_end, source_name) in zip(data_group.segments, recorded):
            inferred_start = start_time + timedelta(
                seconds=segment.start_sample / sampling_rate
            )
            inferred_end = start_time + timedelta(
                seconds=segment.end_sample / sampling_rate
            )
            corrected_end = source_end + timedelta(seconds=correction)
            difference = (corrected_end - inferred_end).total_seconds()
            timeline_segments.append(
                TimelineSegment(
                    path=segment.path,
                    start_sample=segment.start_sample,
                    sample_count=segment.sample_count,
                    recorded_end=source_end,
                    timestamp_source=source_name,
                    corrected_recorded_end=corrected_end,
                    inferred_start=inferred_start,
                    inferred_end=inferred_end,
                    end_time_difference_seconds=difference,
                )
            )

        return cls(
            start_time=start_time,
            end_time=end_time,
            sampling_rate=sampling_rate,
            total_samples=data_group.total_samples,
            correction_seconds=correction,
            continuity_tolerance_seconds=float(continuity_tolerance_seconds),
            segments=tuple(timeline_segments),
        )

    def absolute_time_for_sample(self, sample_boundary: float) -> datetime:
        """Map a zero-based sample boundary to corrected wall-clock time."""

        sample_boundary = min(max(float(sample_boundary), 0.0), float(self.total_samples))
        return self.start_time + timedelta(seconds=sample_boundary / self.sampling_rate)

    def sample_boundary_for_time(self, value: datetime) -> int:
        """Map corrected wall-clock time to the nearest valid sample boundary."""

        seconds = (value - self.start_time).total_seconds()
        return min(max(int(round(seconds * self.sampling_rate)), 0), self.total_samples)

    @property
    def discontinuities(self) -> Tuple[TimelineSegment, ...]:
        tolerance = abs(float(self.continuity_tolerance_seconds))
        return tuple(
            segment
            for index, segment in enumerate(self.segments)
            if index > 0 and abs(segment.end_time_difference_seconds) > tolerance
        )


def format_wall_time(value: datetime, milliseconds: bool = True) -> str:
    """Format a local acquisition time without implying GPS/UTC semantics."""

    text = value.strftime("%Y-%m-%d %H:%M:%S.%f")
    return text[:-3] if milliseconds else text[:-7]
