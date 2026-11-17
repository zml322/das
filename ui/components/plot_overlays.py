"""Source-file segments and synchronized event-range overlays."""

import os.path
import re

import pyqtgraph as pg
from PyQt5.QtCore import QDateTime, QRectF, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QPen
from PyQt5.QtWidgets import QListWidgetItem

from core.data.data_timeline import format_wall_time
from ui.components.file_segment_bar import FileSegmentBarItem
from ui.components.window_feature import WindowFeature


class PlotOverlaysController(WindowFeature):
    """Source-file segments and synchronized event-range overlays."""

    def __init__(self, window):
        super().__init__(window)
        self.selected_file_segment_index = None
        self._refreshing_stitched_files = False
        self._file_segment_plot_widgets = []
        self._event_range_plot_widgets = []
        self._syncing_event_range = False

    def resetRange(self):
        self.event_range_start_sample = 0
        self.event_range_end_sample = self.window.data.sampling_times

    def drawFileBoundaries(self, plot_widget, y_min: float, y_max: float):
        """Draw one clickable source strip per file plus dashed seam lines."""

        if self.window.data.data_group is None or len(self.window.data.data_group.segments) <= 1:
            plot_widget._file_segment_visuals = []
            return
        visible_start = (self.window.data.sampling_times_from_num - 1) / self.window.data.sampling_rate
        visible_end = self.window.data.sampling_times_to_num / self.window.data.sampling_rate
        strip_height = max((float(y_max) - float(y_min)) * 0.075, 0.1)
        strip_y = float(y_max) - strip_height
        visuals = []

        for index, segment in enumerate(self.window.data.data_group.segments):
            segment_start = segment.start_sample / self.window.data.sampling_rate
            segment_end = segment.end_sample / self.window.data.sampling_rate
            if segment_end <= visible_start or segment_start >= visible_end:
                continue

            detail = self.fileSegmentDetails(index)
            bar = FileSegmentBarItem(
                QRectF(segment_start, strip_y, segment_end - segment_start, strip_height),
                index,
                self.selectFileSegment,
            )
            bar.setToolTip(detail)
            plot_widget.addItem(bar)

            label = pg.TextItem(str(index + 1), color="#5b21b6", anchor=(0.5, 0.5))
            label.setZValue(21)
            label.setAcceptedMouseButtons(Qt.NoButton)
            label.setPos((segment_start + segment_end) / 2, strip_y + strip_height / 2)
            label.setToolTip(detail)
            plot_widget.addItem(label)
            visuals.append(
                {
                    "index": index,
                    "start": segment_start,
                    "end": segment_end,
                    "label_y": strip_y + strip_height / 2,
                    "bar": bar,
                    "label": label,
                }
            )

            if index > 0 and visible_start < segment_start < visible_end:
                previous = self.window.data.data_group.segments[index - 1]
                line = pg.InfiniteLine(
                    pos=segment_start,
                    angle=90,
                    movable=False,
                    pen=pg.mkPen("#7b2cbf", width=1.5, style=Qt.DashLine),
                )
                line.setZValue(19)
                line.setToolTip(f"文件接缝：{previous.name} → {segment.name}\n全局采样点：{segment.start_sample + 1}")
                plot_widget.addItem(line)

        plot_widget._file_segment_visuals = visuals
        self._registerFileSegmentPlot(plot_widget)
        self.updateFileSegmentLabels(plot_widget)
        self._refreshFileSegmentHighlights()
        QTimer.singleShot(0, lambda widget=plot_widget: self.updateFileSegmentLabels(widget))

    @staticmethod
    def _formatRelativeSeconds(value: float) -> str:
        return f"{float(value):.6f}".rstrip("0").rstrip(".") or "0"

    @staticmethod
    def _fileNameClock(name: str):
        """Extract HH:MM:SS from the common DAS datetime filename pattern."""

        match = re.search(
            r"(?:19|20)\d{2}[-_]\d{1,2}[-_]\d{1,2}[-_]"
            r"(\d{1,2})[-_](\d{1,2})[-_](\d{1,2})(?:[-_.]|$)",
            os.path.basename(str(name)),
        )
        if match is None:
            return None
        return ":".join(f"{int(part):02d}" for part in match.groups())

    def fileSegmentLabel(self, index: int, pixel_width: float) -> str:
        """Return a collision-resistant label for a source strip."""

        if self.window.data.data_group is None or not (0 <= index < len(self.window.data.data_group.segments)):
            return ""
        sequence = str(index + 1)
        if pixel_width < 58:
            return sequence
        segment = self.window.data.data_group.segments[index]
        clock = self._fileNameClock(segment.name)
        if clock:
            return f"{sequence}  {clock}"
        if pixel_width >= 180:
            maximum = max(8, int(pixel_width // 8) - len(sequence) - 2)
            name = segment.name
            if len(name) > maximum:
                name = f"{name[: maximum - 1]}…"
            return f"{sequence}  {name}"
        return sequence

    def fileSegmentDetails(self, index: int) -> str:
        """Build the path, sample range and corrected time details."""

        if self.window.data.data_group is None or not (0 <= index < len(self.window.data.data_group.segments)):
            return ""
        segment = self.window.data.data_group.segments[index]
        sampling_rate = float(self.window.data.data_group.sampling_rate)
        start_time = segment.start_sample / sampling_rate
        end_time = segment.end_sample / sampling_rate
        duration = segment.sample_count / sampling_rate
        lines = [
            f"第 {index + 1}/{len(self.window.data.data_group.segments)} 段\n"
            f"文件：{segment.name}\n"
            f"完整路径：{segment.path}\n"
            f"全局采样范围：{segment.start_sample + 1} - {segment.end_sample} "
            f"（{segment.sample_count} 点）\n"
            f"起止相对时间：{self._formatRelativeSeconds(start_time)} - "
            f"{self._formatRelativeSeconds(end_time)} s\n"
            f"时长：{self._formatRelativeSeconds(duration)} s"
        ]
        if self.window.data.data_timeline is not None and index < len(self.window.data.data_timeline.segments):
            timeline_segment = self.window.data.data_timeline.segments[index]
            source_name = "文件名" if timeline_segment.timestamp_source == "filename" else "文件头"
            lines.append(
                f"\n记录结束时间（{source_name}）：{format_wall_time(timeline_segment.recorded_end)}"
                f"\n修正后记录结束：{format_wall_time(timeline_segment.corrected_recorded_end)}"
                f"\n连续推算范围：{format_wall_time(timeline_segment.inferred_start)} - "
                f"{format_wall_time(timeline_segment.inferred_end)}"
            )
            if index > 0:
                lines.append(f"\n记录与连续推算偏差：{timeline_segment.end_time_difference_seconds:+.3f} s")
        return "".join(lines)

    def updateStitchedFilesList(self):
        """Refresh the left-side source list in exact stitching order."""

        self._refreshing_stitched_files = True
        try:
            self.window.data.stitched_files_list.clear()
            segments = self.window.data.data_group.segments if self.window.data.data_group is not None else []
            self.window.data.stitched_files_group.setTitle(f"当前拼接文件（{len(segments)}）")
            digits = max(2, len(str(len(segments))))
            for index, segment in enumerate(segments):
                warning = False
                if (
                    self.window.data.data_timeline is not None
                    and index < len(self.window.data.data_timeline.segments)
                    and index > 0
                ):
                    difference = self.window.data.data_timeline.segments[index].end_time_difference_seconds
                    warning = abs(difference) > self.window.data.data_timeline.continuity_tolerance_seconds
                prefix = "⚠ " if warning else ""
                item = QListWidgetItem(f"{prefix}{index + 1:0{digits}d}  {segment.name}")
                item.setData(Qt.UserRole, index)
                item.setToolTip(self.fileSegmentDetails(index))
                self.window.data.stitched_files_list.addItem(item)
            if self.selected_file_segment_index is not None and self.selected_file_segment_index < len(segments):
                self.window.data.stitched_files_list.setCurrentRow(self.selected_file_segment_index)
            else:
                self.window.data.stitched_files_list.setCurrentRow(-1)
        finally:
            self._refreshing_stitched_files = False

    def _stitchedFileRowChanged(self, index: int):
        if not self._refreshing_stitched_files and index >= 0:
            self.selectFileSegment(index)

    def selectFileSegment(self, index: int):
        """Synchronize segment selection between the source list and all plots."""

        if self.window.data.data_group is None or not (0 <= int(index) < len(self.window.data.data_group.segments)):
            return
        self.selected_file_segment_index = int(index)
        if hasattr(
            self.window.data, "stitched_files_list"
        ) and self.window.data.stitched_files_list.currentRow() != int(index):
            self._refreshing_stitched_files = True
            try:
                self.window.data.stitched_files_list.setCurrentRow(int(index))
            finally:
                self._refreshing_stitched_files = False
        self._refreshFileSegmentHighlights()
        self.window.statusBar().showMessage(self.fileSegmentDetails(int(index)).replace("\n", "  |  "))

    def _registerFileSegmentPlot(self, plot_widget):
        if plot_widget not in self._file_segment_plot_widgets:
            self._file_segment_plot_widgets.append(plot_widget)
        if getattr(plot_widget, "_file_segment_range_tracking", False):
            return
        plot_widget._file_segment_range_tracking = True
        plot_widget.getViewBox().sigXRangeChanged.connect(
            lambda *_args, widget=plot_widget: self.updateFileSegmentLabels(widget)
        )

    def updateFileSegmentLabels(self, plot_widget):
        """Reposition and shorten strip labels after zooming or resizing."""

        visuals = getattr(plot_widget, "_file_segment_visuals", [])
        if not visuals:
            return
        try:
            view_box = plot_widget.getViewBox()
            view_start, view_end = view_box.viewRange()[0]
            view_width = max(float(view_end) - float(view_start), 1e-12)
            pixel_scale = max(float(view_box.width()), 1.0) / view_width
            for visual in visuals:
                clipped_start = max(float(visual["start"]), float(view_start))
                clipped_end = min(float(visual["end"]), float(view_end))
                is_visible = clipped_end > clipped_start
                visual["label"].setVisible(is_visible)
                if not is_visible:
                    continue
                pixel_width = (clipped_end - clipped_start) * pixel_scale
                visual["label"].setText(self.fileSegmentLabel(visual["index"], pixel_width))
                visual["label"].setPos(
                    (clipped_start + clipped_end) / 2,
                    visual["label_y"],
                )
        except RuntimeError:
            return

    def _refreshFileSegmentHighlights(self):
        selected = self.selected_file_segment_index
        live_widgets = []
        for plot_widget in self._file_segment_plot_widgets:
            try:
                visuals = getattr(plot_widget, "_file_segment_visuals", [])
                for visual in visuals:
                    is_selected = visual["index"] == selected
                    color = QColor(245, 158, 11, 112) if is_selected else QColor(124, 58, 237, 60)
                    outline = QColor("#d97706") if is_selected else QColor(124, 58, 237, 120)
                    pen = QPen(outline, 1.5 if is_selected else 0.8)
                    pen.setCosmetic(True)
                    visual["bar"].setBrush(QBrush(color))
                    visual["bar"].setPen(pen)
                    visual["label"].setColor("#92400e" if is_selected else "#5b21b6")
                live_widgets.append(plot_widget)
            except RuntimeError:
                continue
        self._file_segment_plot_widgets = live_widgets

    def setEventRangeControlsEnabled(self, enabled: bool):
        for widget in (
            self.event_range_from_edit,
            self.event_range_to_edit,
            self.event_range_set_button,
            self.event_range_view_button,
            self.event_range_reset_button,
            self.event_markers_visible_checkbox,
        ):
            widget.setEnabled(bool(enabled))

    def updateEventRangeEditors(self):
        """Synchronize corrected wall times into the event-range controls."""

        if self.window.data.data_timeline is None or not hasattr(self, "event_range_start_sample"):
            self.setEventRangeControlsEnabled(False)
            return
        self.setEventRangeControlsEnabled(True)
        minimum = QDateTime(self.window.data.data_timeline.start_time)
        maximum = QDateTime(self.window.data.data_timeline.end_time)
        self._syncing_event_range = True
        try:
            for editor in (self.event_range_from_edit, self.event_range_to_edit):
                editor.setDateTimeRange(minimum, maximum)
            self.event_range_from_edit.setDateTime(
                QDateTime(self.window.data.data_timeline.absolute_time_for_sample(self.event_range_start_sample))
            )
            self.event_range_to_edit.setDateTime(
                QDateTime(self.window.data.data_timeline.absolute_time_for_sample(self.event_range_end_sample))
            )
        finally:
            self._syncing_event_range = False

    def setEventRangeFromInputs(self):
        """Move the event markers from corrected absolute-time inputs."""

        if self.window.data.data_timeline is None:
            return
        start = self.window.data.data_timeline.sample_boundary_for_time(
            self.event_range_from_edit.dateTime().toPyDateTime()
        )
        end = self.window.data.data_timeline.sample_boundary_for_time(
            self.event_range_to_edit.dateTime().toPyDateTime()
        )
        self.setEventSampleRange(start, end, show_status=True)

    def setEventSampleRange(self, start: int, end: int, show_status: bool = False):
        """Set a clamped non-empty event interval in zero-based sample boundaries."""

        if not hasattr(self.window.data, "sampling_times") or self.window.data.sampling_times <= 0:
            return
        start = min(max(int(start), 0), self.window.data.sampling_times)
        end = min(max(int(end), 0), self.window.data.sampling_times)
        if start > end:
            start, end = end, start
        if start == end:
            if end < self.window.data.sampling_times:
                end += 1
            else:
                start = max(0, start - 1)
        self.event_range_start_sample = start
        self.event_range_end_sample = end
        self.updateEventRangeEditors()
        self._syncEventRangePlots()
        if show_status and self.window.data.data_timeline is not None:
            start_text = format_wall_time(self.window.data.data_timeline.absolute_time_for_sample(start))
            end_text = format_wall_time(self.window.data.data_timeline.absolute_time_for_sample(end))
            self.window.statusBar().showMessage(
                f"事件范围：{start_text} - {end_text}  |  "
                f"采样边界：{start} - {end}  |  时长 {(end - start) / self.window.data.sampling_rate:.3f} s",
                8000,
            )

    def _eventRangeMoved(self, region):
        if self._syncing_event_range:
            return
        start_seconds, end_seconds = sorted(map(float, region.getRegion()))
        self.setEventSampleRange(
            round(start_seconds * self.window.data.sampling_rate),
            round(end_seconds * self.window.data.sampling_rate),
            show_status=True,
        )

    def _eventLineText(self, sample_boundary: int, prefix: str) -> str:
        if self.window.data.data_timeline is None:
            return prefix
        value = self.window.data.data_timeline.absolute_time_for_sample(sample_boundary)
        return f"{prefix} {value.strftime('%H:%M:%S.%f')[:-3]}"

    def setEventMarkersVisible(self, visible: bool):
        """Show or hide only the event overlay, without changing the data view."""

        self.show_event_markers = bool(visible)
        live_widgets = []
        for plot_widget in list(self._event_range_plot_widgets):
            try:
                visual = getattr(plot_widget, "_event_range_visual", None)
                if visual is not None:
                    plot_widget.removeItem(visual["region"])
                plot_widget._event_range_visual = None
                if (
                    self.show_event_markers
                    and self.window.data.data_timeline is not None
                    and hasattr(self, "event_range_start_sample")
                ):
                    self.drawEventRange(plot_widget)
                live_widgets.append(plot_widget)
            except RuntimeError:
                continue
        self._event_range_plot_widgets = live_widgets

    def drawEventRange(self, plot_widget):
        """Draw two synchronized draggable time markers without obscuring the data."""

        if (
            not getattr(self, "show_event_markers", True)
            or self.window.data.data_timeline is None
            or not hasattr(self, "event_range_start_sample")
        ):
            plot_widget._event_range_visual = None
            return
        start_seconds = self.event_range_start_sample / self.window.data.sampling_rate
        end_seconds = self.event_range_end_sample / self.window.data.sampling_rate
        region = pg.LinearRegionItem(
            values=(start_seconds, end_seconds),
            orientation=pg.LinearRegionItem.Vertical,
            brush=pg.mkBrush(0, 0, 0, 0),
            hoverBrush=pg.mkBrush(0, 0, 0, 0),
            movable=True,
            bounds=(0.0, self.window.data.sampling_times / self.window.data.sampling_rate),
            swapMode="sort",
        )
        # File strips occupy layers 19-21.  Keep event markers and their
        # labels higher so the end marker remains readable at the top edge.
        region.setZValue(30)
        start_pen = pg.mkPen("#16a34a", width=3)
        end_pen = pg.mkPen("#dc2626", width=3)
        region.lines[0].setPen(start_pen)
        region.lines[0].setHoverPen(pg.mkPen("#4ade80", width=5))
        region.lines[1].setPen(end_pen)
        region.lines[1].setHoverPen(pg.mkPen("#fb7185", width=5))
        start_label = pg.InfLineLabel(
            region.lines[0],
            text=self._eventLineText(self.event_range_start_sample, "开始"),
            position=0.86,
            color="#166534",
            fill=pg.mkBrush(255, 255, 255, 205),
            movable=True,
        )
        end_label = pg.InfLineLabel(
            region.lines[1],
            text=self._eventLineText(self.event_range_end_sample, "结束"),
            position=0.72,
            color="#991b1b",
            fill=pg.mkBrush(255, 255, 255, 205),
            movable=True,
        )
        start_label.setZValue(1)
        end_label.setZValue(1)
        region.sigRegionChangeFinished.connect(lambda item=region: self._eventRangeMoved(item))
        plot_widget.addItem(region)
        plot_widget._event_range_visual = {
            "region": region,
            "start_label": start_label,
            "end_label": end_label,
        }
        if plot_widget not in self._event_range_plot_widgets:
            self._event_range_plot_widgets.append(plot_widget)

    def _syncEventRangePlots(self):
        if not hasattr(self, "event_range_start_sample"):
            return
        start_seconds = self.event_range_start_sample / self.window.data.sampling_rate
        end_seconds = self.event_range_end_sample / self.window.data.sampling_rate
        self._syncing_event_range = True
        live_widgets = []
        try:
            for plot_widget in self._event_range_plot_widgets:
                try:
                    visual = getattr(plot_widget, "_event_range_visual", None)
                    if visual is not None:
                        visual["region"].setRegion((start_seconds, end_seconds))
                        visual["start_label"].setText(self._eventLineText(self.event_range_start_sample, "开始"))
                        visual["end_label"].setText(self._eventLineText(self.event_range_end_sample, "结束"))
                    live_widgets.append(plot_widget)
                except RuntimeError:
                    continue
        finally:
            self._syncing_event_range = False
        self._event_range_plot_widgets = live_widgets

    def viewEventRange(self):
        """Apply the marker range as the current non-destructive data view."""

        self.setEventRangeFromInputs()
        self.window.data.sampling_times_from_num = self.event_range_start_sample + 1
        self.window.data.sampling_times_to_num = self.event_range_end_sample
        self.window.data.updateDataRange()
        self.window.data.updateDataParams()
        self.window.data.updateDataGPSTime()
        self.window.updateImages()
        self.window.filtering.syncDASFilterVisibleRange()

    def restoreFullEventRange(self):
        if not hasattr(self.window.data, "sampling_times"):
            return
        self.setEventSampleRange(0, self.window.data.sampling_times)
        self.window.data.sampling_times_from_num = 1
        self.window.data.sampling_times_to_num = self.window.data.sampling_times
        self.window.data.updateDataRange()
        self.window.data.updateDataParams()
        self.window.data.updateDataGPSTime()
        self.window.updateImages()
        self.window.filtering.syncDASFilterVisibleRange()
