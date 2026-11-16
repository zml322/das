"""Interactive projected-speed ruler for DAS channel-by-time plots."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence, Tuple

import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QPainterPath


PointTuple = Tuple[float, float]


@dataclass(frozen=True)
class SpeedMeasurement:
    """Projected speed derived from two time/channel points."""

    start_time: float
    end_time: float
    start_channel: float
    end_channel: float
    elapsed_seconds: float
    channel_delta: float
    distance_m: float
    speed_mps: float
    speed_kmh: float
    valid: bool

    @property
    def direction_text(self) -> str:
        if self.channel_delta > 1e-9:
            return "通道递增"
        if self.channel_delta < -1e-9:
            return "通道递减"
        return "无通道变化"


def calculate_projected_speed(
    first: Sequence[float],
    second: Sequence[float],
    channel_spacing: float,
) -> SpeedMeasurement:
    """Calculate along-fibre projected speed from plot coordinates.

    Each point is ``(seconds from imported-data start, global channel number)``.
    The endpoints are ordered by time before direction is determined, so swapping
    handles does not reverse the reported vehicle direction.
    """

    spacing = float(channel_spacing)
    if not isfinite(spacing) or spacing <= 0:
        raise ValueError("相邻通道距离 dx 必须为大于 0 的有限数")
    first_time, first_channel = map(float, first)
    second_time, second_channel = map(float, second)
    if not all(isfinite(value) for value in (first_time, first_channel, second_time, second_channel)):
        raise ValueError("速度标尺端点必须是有限坐标")
    if second_time < first_time:
        first_time, second_time = second_time, first_time
        first_channel, second_channel = second_channel, first_channel

    elapsed = second_time - first_time
    channel_delta = second_channel - first_channel
    distance = abs(channel_delta) * spacing
    valid = elapsed > 1e-9
    speed_mps = distance / elapsed if valid else float("inf")
    return SpeedMeasurement(
        start_time=first_time,
        end_time=second_time,
        start_channel=first_channel,
        end_channel=second_channel,
        elapsed_seconds=elapsed,
        channel_delta=channel_delta,
        distance_m=distance,
        speed_mps=speed_mps,
        speed_kmh=speed_mps * 3.6,
        valid=valid,
    )


def format_speed_measurement(measurement: SpeedMeasurement) -> str:
    """Return detailed text for the controls and ruler tooltip."""

    if not measurement.valid:
        return "投影速度：无法计算\n两个端点的时间差过小"
    return (
        f"投影速度：{measurement.speed_mps:.2f} m/s | "
        f"{measurement.speed_kmh:.2f} km/h\n"
        f"{measurement.direction_text} | Δt {measurement.elapsed_seconds:.3f} s | "
        f"Δ通道 {abs(measurement.channel_delta):.2f}"
    )


class SpeedRulerROI(pg.LineSegmentROI):
    """Two-handle line that updates its projected-speed label continuously."""

    def __init__(self, positions, channel_spacing: float = 4.0):
        self._channel_spacing = float(channel_spacing)
        self.halo_pen = pg.mkPen("#111827", width=9)
        self.halo_hover_pen = pg.mkPen("#111827", width=11)
        self.halo_pen.setCapStyle(Qt.RoundCap)
        self.halo_hover_pen.setCapStyle(Qt.RoundCap)
        line_pen = pg.mkPen("#ffea00", width=5)
        hover_pen = pg.mkPen("#ffffff", width=6)
        line_pen.setCapStyle(Qt.RoundCap)
        hover_pen.setCapStyle(Qt.RoundCap)
        super().__init__(
            positions=positions,
            pen=line_pen,
            hoverPen=hover_pen,
            handlePen=pg.mkPen("#ffea00", width=4),
            handleHoverPen=pg.mkPen("#ffffff", width=5),
            movable=True,
            removable=False,
        )
        for handle in self.getHandles():
            handle.radius = 8
            handle.buildPath()
            handle._shape = None
            handle.update()
        self.setZValue(40)
        self.label_item = pg.TextItem(
            color="#111827",
            anchor=(0.5, 1.15),
            border=pg.mkPen("#111827", width=2),
            fill=pg.mkBrush(255, 248, 168, 240),
        )
        self.label_item.setAcceptedMouseButtons(Qt.NoButton)
        self.label_item.setZValue(1)
        self.label_item.setParentItem(self)
        self.sigRegionChanged.connect(self._refresh_label)
        self._refresh_label()

    def paint(self, painter, *_args) -> None:
        """Draw a dark halo below the bright line for any image colour map."""

        painter.setRenderHint(QPainter.Antialiasing, self._antialias)
        first, second = self.listPoints()
        painter.setPen(self.halo_hover_pen if self.mouseHovering else self.halo_pen)
        painter.drawLine(first, second)
        painter.setPen(self.currentPen)
        painter.drawLine(first, second)

    def shape(self):
        """Keep the thick ruler easy to grab and fully inside its paint bounds."""

        path = QPainterPath()
        first, second = self.listPoints()
        delta = second - first
        if delta.length() == 0:
            return path
        perpendicular = self.pixelVectors(delta)[1]
        if perpendicular is None:
            return path
        perpendicular *= 7
        path.moveTo(first + perpendicular)
        path.lineTo(second + perpendicular)
        path.lineTo(second - perpendicular)
        path.lineTo(first - perpendicular)
        path.closeSubpath()
        return path

    @property
    def channel_spacing(self) -> float:
        return self._channel_spacing

    def setChannelSpacing(self, value: float) -> None:
        value = float(value)
        if not isfinite(value) or value <= 0:
            raise ValueError("相邻通道距离 dx 必须大于 0")
        self._channel_spacing = value
        self._refresh_label()

    def localPoints(self) -> Tuple[PointTuple, PointTuple]:
        points = self.listPoints()
        return tuple((float(point.x()), float(point.y())) for point in points)

    def parentPoints(self) -> Tuple[PointTuple, PointTuple]:
        points = [self.mapToParent(point) for point in self.listPoints()]
        return tuple((float(point.x()), float(point.y())) for point in points)

    def measurement(self) -> SpeedMeasurement:
        first, second = self.localPoints()
        return calculate_projected_speed(first, second, self._channel_spacing)

    def labelText(self) -> str:
        measurement = self.measurement()
        if not measurement.valid:
            return "时间差过小"
        return f"{measurement.speed_mps:.2f} m/s\n{measurement.speed_kmh:.2f} km/h"

    def _refresh_label(self, *_args) -> None:
        first, second = self.listPoints()
        midpoint = (first + second) * 0.5
        self.label_item.setPos(midpoint)
        text = self.labelText()
        self.label_item.setText(text)
        self.setToolTip(format_speed_measurement(self.measurement()).replace("\n", " | "))
