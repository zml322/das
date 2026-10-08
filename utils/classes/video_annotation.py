"""Persistent video-to-DAS synchronization and manual annotation models.

The module deliberately contains no Qt widgets.  Keeping the annotation
contract independent from the UI makes it possible to test the time mapping,
project persistence, and vehicle-trajectory comparison without a media
backend or an on-screen window.
"""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

from .data_timeline import DataTimeline, format_wall_time


PROJECT_SCHEMA_VERSION = 1
VIDEO_FILENAME_TIME = re.compile(
    r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})(?!\d)"
)


def parse_video_start_time(path: str) -> Optional[datetime]:
    """Parse ``YYYYMMDD_HHMMSS`` camera start times from a video filename."""

    match = VIDEO_FILENAME_TIME.search(os.path.basename(str(path)))
    if match is None:
        return None
    try:
        return datetime(*map(int, match.groups()))
    except ValueError:
        return None


def format_video_position(milliseconds: Optional[int]) -> str:
    """Format a non-negative media position without implying frame accuracy."""

    if milliseconds is None:
        return "--:--:--.---"
    total = max(0, int(round(milliseconds)))
    hours, remainder = divmod(total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _datetime_from_text(value: object) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _normalized_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


@dataclass
class VideoSync:
    """Affine video-clock to corrected DAS wall-clock mapping.

    ``video_start_time`` comes from the camera filename in the normal case.
    The manual offset permits landmark alignment without discarding that
    provenance; ``rate`` permits a later two-landmark drift correction.
    """

    video_start_time: Optional[datetime] = None
    manual_offset_seconds: float = 0.0
    rate: float = 1.0
    revision: int = 0

    def wall_time_for_video_position(self, position_ms: int) -> Optional[datetime]:
        if self.video_start_time is None:
            return None
        elapsed = max(0, int(position_ms)) / 1000.0 * float(self.rate)
        return self.video_start_time + timedelta(
            seconds=elapsed + float(self.manual_offset_seconds)
        )

    def sample_for_video_position(
        self, position_ms: int, timeline: DataTimeline
    ) -> Optional[int]:
        wall_time = self.wall_time_for_video_position(position_ms)
        if wall_time is None:
            return None
        return timeline.sample_boundary_for_time(wall_time)

    def video_position_for_sample(
        self, sample: int, timeline: DataTimeline
    ) -> Optional[int]:
        if self.video_start_time is None or abs(float(self.rate)) < 1e-12:
            return None
        wall_time = timeline.absolute_time_for_sample(sample)
        elapsed = (wall_time - self.video_start_time).total_seconds()
        position = (elapsed - float(self.manual_offset_seconds)) / float(self.rate)
        return max(0, int(round(position * 1000)))

    def update(
        self,
        video_start_time: Optional[datetime],
        manual_offset_seconds: float,
        rate: float,
    ) -> bool:
        rate = float(rate)
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError("视频时钟倍率必须为正数")
        manual_offset_seconds = float(manual_offset_seconds)
        if not np.isfinite(manual_offset_seconds):
            raise ValueError("视频时间偏移必须是有限数值")
        changed = (
            self.video_start_time != video_start_time
            or not np.isclose(self.manual_offset_seconds, manual_offset_seconds)
            or not np.isclose(self.rate, rate)
        )
        self.video_start_time = video_start_time
        self.manual_offset_seconds = manual_offset_seconds
        self.rate = rate
        if changed:
            self.revision += 1
        return changed

    def to_dict(self) -> Dict[str, object]:
        return {
            "video_start_time": self.video_start_time.isoformat()
            if self.video_start_time is not None
            else None,
            "manual_offset_seconds": float(self.manual_offset_seconds),
            "rate": float(self.rate),
            "revision": int(self.revision),
        }

    @classmethod
    def from_dict(cls, value: object) -> "VideoSync":
        payload = value if isinstance(value, dict) else {}
        try:
            rate = float(payload.get("rate", 1.0))
        except (TypeError, ValueError):
            rate = 1.0
        try:
            offset = float(payload.get("manual_offset_seconds", 0.0))
        except (TypeError, ValueError):
            offset = 0.0
        try:
            revision = max(0, int(payload.get("revision", 0)))
        except (TypeError, ValueError):
            revision = 0
        if not np.isfinite(rate) or rate <= 0:
            rate = 1.0
        if not np.isfinite(offset):
            offset = 0.0
        return cls(_datetime_from_text(payload.get("video_start_time")), offset, rate, revision)


@dataclass
class VideoAnnotation:
    """One manual point or interval observation in both time domains."""

    identifier: int
    kind: str
    outcome: str
    start_video_ms: int
    start_sample: int
    camera_channel: int
    end_video_ms: Optional[int] = None
    end_sample: Optional[int] = None
    trajectory_identifier: Optional[int] = None
    time_residual_ms: Optional[float] = None
    note: str = ""
    source_domain: str = "video"
    sync_revision: int = 0
    visible: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def is_interval(self) -> bool:
        return self.end_video_ms is not None and self.end_sample is not None

    def to_dict(self) -> Dict[str, object]:
        return {
            "identifier": int(self.identifier),
            "kind": str(self.kind),
            "outcome": str(self.outcome),
            "start_video_ms": int(self.start_video_ms),
            "end_video_ms": int(self.end_video_ms) if self.end_video_ms is not None else None,
            "start_sample": int(self.start_sample),
            "end_sample": int(self.end_sample) if self.end_sample is not None else None,
            "camera_channel": int(self.camera_channel),
            "trajectory_identifier": int(self.trajectory_identifier)
            if self.trajectory_identifier is not None
            else None,
            "time_residual_ms": float(self.time_residual_ms)
            if self.time_residual_ms is not None
            else None,
            "note": str(self.note),
            "source_domain": str(self.source_domain),
            "sync_revision": int(self.sync_revision),
            "visible": bool(self.visible),
            "created_at": self.created_at.isoformat(timespec="seconds"),
        }

    @classmethod
    def from_dict(cls, value: object) -> "VideoAnnotation":
        if not isinstance(value, dict):
            raise ValueError("标注条目必须是对象")
        try:
            identifier = max(1, int(value["identifier"]))
            start_video_ms = max(0, int(value["start_video_ms"]))
            start_sample = max(0, int(value["start_sample"]))
            channel = max(1, int(value["camera_channel"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("标注条目缺少有效的编号、视频时间、采样点或通道") from error
        end_video = value.get("end_video_ms")
        end_sample = value.get("end_sample")
        try:
            end_video = max(start_video_ms, int(end_video)) if end_video is not None else None
            end_sample = max(start_sample, int(end_sample)) if end_sample is not None else None
        except (TypeError, ValueError):
            end_video, end_sample = None, None
        try:
            trajectory = int(value["trajectory_identifier"])
        except (TypeError, ValueError, KeyError):
            trajectory = None
        try:
            residual = float(value["time_residual_ms"])
            residual = residual if np.isfinite(residual) else None
        except (TypeError, ValueError, KeyError):
            residual = None
        try:
            revision = max(0, int(value.get("sync_revision", 0)))
        except (TypeError, ValueError):
            revision = 0
        return cls(
            identifier=identifier,
            kind=str(value.get("kind") or "车辆经过"),
            outcome=str(value.get("outcome") or "未核对"),
            start_video_ms=start_video_ms,
            start_sample=start_sample,
            camera_channel=channel,
            end_video_ms=end_video,
            end_sample=end_sample,
            trajectory_identifier=trajectory,
            time_residual_ms=residual,
            note=str(value.get("note") or ""),
            source_domain=str(value.get("source_domain") or "video"),
            sync_revision=revision,
            visible=bool(value.get("visible", True)),
            created_at=_datetime_from_text(value.get("created_at")) or datetime.now(),
        )


@dataclass(frozen=True)
class TrajectoryCandidate:
    identifier: int
    crossing_seconds: float
    residual_ms: float
    direction: str = "未知"
    confidence: float = 0.0


def trajectory_crossing_time(trajectory: object, camera_channel: int) -> Optional[float]:
    """Interpolate a picked trajectory's crossing time at a global channel."""

    try:
        channels = np.asarray(getattr(trajectory, "channels"), dtype=float)
        times = np.asarray(getattr(trajectory, "times"), dtype=float)
    except (TypeError, ValueError):
        return None
    if channels.ndim != 1 or times.ndim != 1 or channels.size != times.size or channels.size < 2:
        return None
    finite = np.isfinite(channels) & np.isfinite(times)
    channels, times = channels[finite], times[finite]
    if channels.size < 2 or camera_channel < np.min(channels) or camera_channel > np.max(channels):
        return None
    order = np.argsort(channels)
    sorted_channels, sorted_times = channels[order], times[order]
    unique_channels, unique_indices = np.unique(sorted_channels, return_index=True)
    if unique_channels.size < 2:
        return None
    return float(np.interp(float(camera_channel), unique_channels, sorted_times[unique_indices]))


def trajectory_candidates(
    trajectories: Iterable[object],
    camera_channel: int | Sequence[int],
    target_seconds: float,
    tolerance_seconds: float = 2.0,
) -> List[TrajectoryCandidate]:
    """Return visible picked tracks which cross the camera near an annotation."""

    candidates: List[TrajectoryCandidate] = []
    tolerance = max(0.0, float(tolerance_seconds))
    if isinstance(camera_channel, Sequence) and not isinstance(camera_channel, (str, bytes)):
        bounds = tuple(int(value) for value in camera_channel)
        if len(bounds) != 2:
            raise ValueError("摄像头通道范围必须包含起止两个通道")
        camera_start, camera_end = sorted(bounds)
        target_channel = (camera_start + camera_end) / 2.0
    else:
        camera_start = camera_end = int(camera_channel)
        target_channel = float(camera_start)
    for trajectory in trajectories:
        if not getattr(trajectory, "visible", True):
            continue
        channels = np.asarray(getattr(trajectory, "channels", ()), dtype=float)
        times = np.asarray(getattr(trajectory, "times", ()), dtype=float)
        if channels.size < 2 or np.nanmax(channels) < camera_start or np.nanmin(channels) > camera_end:
            continue
        crossing = trajectory_crossing_time(trajectory, target_channel)
        if crossing is None:
            continue
        residual_ms = (crossing - float(target_seconds)) * 1000.0
        if abs(residual_ms) <= tolerance * 1000.0:
            try:
                identifier = int(getattr(trajectory, "identifier"))
            except (TypeError, ValueError):
                continue
            order = np.argsort(channels)
            direction = "向通道增大" if np.nanmean(np.diff(times[order])) >= 0 else "向通道减小"
            quality = float(getattr(trajectory, "quality", 0.0))
            coverage = float(getattr(trajectory, "coverage", 0.0))
            confidence = min(1.0, max(0.0, quality * coverage))
            candidates.append(TrajectoryCandidate(identifier, crossing, residual_ms, direction, confidence))
    return sorted(candidates, key=lambda item: (abs(item.residual_ms), item.identifier))


@dataclass
class AnnotationProject:
    """A sidecar project; it never writes to a DAS or video source file."""

    video_path: str = ""
    camera_name: str = "摄像头 A"
    camera_channel: int = 1
    camera_channel_start: Optional[int] = None
    camera_channel_end: Optional[int] = None
    camera_visible: bool = True
    sync: VideoSync = field(default_factory=VideoSync)
    annotations: List[VideoAnnotation] = field(default_factory=list)
    calibration_anchors: List[Dict[str, int]] = field(default_factory=list)
    das_context: Dict[str, object] = field(default_factory=dict)
    project_path: str = ""

    @property
    def camera_channel_range(self) -> tuple[int, int]:
        """Deprecated range view retained for old callers and project files."""
        channel = max(1, int(self.camera_channel))
        return channel, channel

    def set_camera_channel(self, channel: int) -> None:
        """Set the single DAS channel represented by the camera overlay."""
        channel = max(1, int(channel))
        self.camera_channel = channel
        self.camera_channel_start = channel
        self.camera_channel_end = channel

    def set_camera_channel_range(self, start: int, end: int) -> None:
        """Import a legacy range as its centre single camera channel."""
        start, end = sorted((max(1, int(start)), max(1, int(end))))
        self.set_camera_channel(int(round((start + end) / 2)))

    def next_identifier(self) -> int:
        return max((annotation.identifier for annotation in self.annotations), default=0) + 1

    def set_video(self, path: str, start_time: Optional[datetime] = None) -> None:
        self.video_path = str(path)
        if start_time is not None:
            self.sync.update(start_time, self.sync.manual_offset_seconds, self.sync.rate)

    def set_das_context(self, data_group: object, timeline: DataTimeline) -> bool:
        paths = [
            _normalized_path(getattr(segment, "path", ""))
            for segment in getattr(data_group, "segments", ())
        ]
        candidate = {
            "source_paths": paths,
            "sampling_rate": float(timeline.sampling_rate),
            "total_samples": int(timeline.total_samples),
        }
        existing = self.das_context
        compatible = not existing or (
            existing.get("source_paths") == candidate["source_paths"]
            and np.isclose(float(existing.get("sampling_rate", -1)), candidate["sampling_rate"])
            and int(existing.get("total_samples", -1)) == candidate["total_samples"]
        )
        if compatible or not self.annotations:
            self.das_context = candidate
            return True
        return False

    def reproject_video_annotations(self, timeline: DataTimeline) -> int:
        """Move video-origin annotations after a synchronization adjustment."""

        changed = 0
        for annotation in self.annotations:
            if annotation.source_domain != "video":
                continue
            start = self.sync.sample_for_video_position(annotation.start_video_ms, timeline)
            end = (
                self.sync.sample_for_video_position(annotation.end_video_ms, timeline)
                if annotation.end_video_ms is not None
                else None
            )
            if start is None:
                continue
            if annotation.start_sample != start or annotation.end_sample != end:
                annotation.start_sample = start
                annotation.end_sample = end
                annotation.sync_revision = self.sync.revision
                changed += 1
        return changed

    def add_video_annotation(
        self,
        timeline: DataTimeline,
        kind: str,
        outcome: str,
        start_video_ms: int,
        camera_channel: Optional[int] = None,
        end_video_ms: Optional[int] = None,
        note: str = "",
    ) -> VideoAnnotation:
        start_sample = self.sync.sample_for_video_position(start_video_ms, timeline)
        if start_sample is None:
            raise ValueError("请先设置摄像头视频开始时间")
        end_sample = (
            self.sync.sample_for_video_position(end_video_ms, timeline)
            if end_video_ms is not None
            else None
        )
        if end_video_ms is not None and end_sample is None:
            raise ValueError("区间结束时间无法映射到 DAS")
        annotation = VideoAnnotation(
            identifier=self.next_identifier(),
            kind=str(kind).strip() or "车辆经过",
            outcome=str(outcome).strip() or "未核对",
            start_video_ms=max(0, int(start_video_ms)),
            end_video_ms=max(0, int(end_video_ms)) if end_video_ms is not None else None,
            start_sample=int(start_sample),
            end_sample=int(end_sample) if end_sample is not None else None,
            camera_channel=max(1, int(camera_channel or self.camera_channel)),
            note=str(note).strip(),
            source_domain="video",
            sync_revision=self.sync.revision,
        )
        if annotation.end_video_ms is not None and annotation.end_video_ms < annotation.start_video_ms:
            annotation.start_video_ms, annotation.end_video_ms = (
                annotation.end_video_ms,
                annotation.start_video_ms,
            )
            annotation.start_sample, annotation.end_sample = annotation.end_sample, annotation.start_sample
        self.annotations.append(annotation)
        return annotation

    def annotation_by_identifier(self, identifier: int) -> Optional[VideoAnnotation]:
        return next((item for item in self.annotations if item.identifier == int(identifier)), None)

    def delete_annotation(self, identifier: int) -> Optional[VideoAnnotation]:
        for index, annotation in enumerate(self.annotations):
            if annotation.identifier == int(identifier):
                return self.annotations.pop(index)
        return None

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "video": {
                "path": self.video_path,
                "camera_name": self.camera_name,
                "camera_channel": int(self.camera_channel),
                "camera_channel_start": int(self.camera_channel_range[0]),
                "camera_channel_end": int(self.camera_channel_range[1]),
                "camera_visible": bool(self.camera_visible),
            },
            "sync": self.sync.to_dict(),
            "das_context": self.das_context,
            "calibration_anchors": [
                {"video_position_ms": int(item["video_position_ms"]), "das_sample": int(item["das_sample"])}
                for item in self.calibration_anchors
                if isinstance(item, dict) and "video_position_ms" in item and "das_sample" in item
            ],
            "annotations": [annotation.to_dict() for annotation in self.annotations],
        }

    @classmethod
    def from_dict(cls, value: object) -> "AnnotationProject":
        if not isinstance(value, dict):
            raise ValueError("标注工程根节点必须是对象")
        if int(value.get("schema_version", 0)) != PROJECT_SCHEMA_VERSION:
            raise ValueError("不支持的标注工程版本")
        video = value.get("video") if isinstance(value.get("video"), dict) else {}
        try:
            channel = max(1, int(video.get("camera_channel", 1)))
            channel_start = max(1, int(video.get("camera_channel_start", channel)))
            channel_end = max(1, int(video.get("camera_channel_end", channel)))
        except (TypeError, ValueError):
            channel = 1
            channel_start = 1
            channel_end = 1
        items = value.get("annotations") if isinstance(value.get("annotations"), list) else []
        annotations = [VideoAnnotation.from_dict(item) for item in items]
        identifiers = [item.identifier for item in annotations]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("标注工程包含重复编号")
        context = value.get("das_context") if isinstance(value.get("das_context"), dict) else {}
        anchor_values = value.get("calibration_anchors")
        anchors: List[Dict[str, int]] = []
        if isinstance(anchor_values, list):
            for item in anchor_values[-2:]:
                if not isinstance(item, dict):
                    continue
                try:
                    anchors.append({
                        "video_position_ms": max(0, int(item["video_position_ms"])),
                        "das_sample": max(0, int(item["das_sample"])),
                    })
                except (KeyError, TypeError, ValueError):
                    continue
        return cls(
            video_path=str(video.get("path") or ""),
            camera_name=str(video.get("camera_name") or "摄像头 A"),
            camera_channel=channel,
            camera_channel_start=channel,
            camera_channel_end=channel,
            camera_visible=bool(video.get("camera_visible", True)),
            sync=VideoSync.from_dict(value.get("sync")),
            annotations=annotations,
            calibration_anchors=anchors,
            das_context=context,
        )

    def save(self, path: str) -> None:
        target = Path(path)
        if not target.name:
            raise ValueError("请选择标注工程文件")
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        temporary = target.with_name(f"{target.name}.tmp")
        try:
            temporary.write_text(payload + "\n", encoding="utf-8")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
        self.project_path = str(target)

    @classmethod
    def load(cls, path: str) -> "AnnotationProject":
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"无法读取标注工程：{error}") from error
        project = cls.from_dict(payload)
        project.project_path = str(source)
        return project

    def export_csv(self, path: str, timeline: Optional[DataTimeline] = None) -> None:
        target = Path(path)
        with target.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=(
                    "annotation_id", "kind", "outcome", "video_start", "video_end",
                    "das_start_sample", "das_end_sample", "das_start_time", "das_end_time",
                    "camera_name", "camera_channel", "trajectory_id", "time_residual_ms",
                    "source_domain", "sync_revision", "visible", "note",
                ),
            )
            writer.writeheader()
            for annotation in self.annotations:
                writer.writerow({
                    "annotation_id": annotation.identifier,
                    "kind": annotation.kind,
                    "outcome": annotation.outcome,
                    "video_start": format_video_position(annotation.start_video_ms),
                    "video_end": format_video_position(annotation.end_video_ms),
                    "das_start_sample": annotation.start_sample,
                    "das_end_sample": annotation.end_sample if annotation.end_sample is not None else "",
                    "das_start_time": format_wall_time(
                        timeline.absolute_time_for_sample(annotation.start_sample)
                    ) if timeline is not None else "",
                    "das_end_time": format_wall_time(
                        timeline.absolute_time_for_sample(annotation.end_sample)
                    ) if timeline is not None and annotation.end_sample is not None else "",
                    "camera_name": self.camera_name,
                    "camera_channel": annotation.camera_channel,
                    "trajectory_id": annotation.trajectory_identifier or "",
                    "time_residual_ms": (
                        f"{annotation.time_residual_ms:.3f}"
                        if annotation.time_residual_ms is not None else ""
                    ),
                    "source_domain": annotation.source_domain,
                    "sync_revision": annotation.sync_revision,
                    "visible": int(annotation.visible),
                    "note": annotation.note,
                })
