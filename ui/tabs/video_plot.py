"""Video comparison DAS rendering, playhead overlays and focus mode."""

import pyqtgraph as pg
from PyQt5.QtCore import QRectF, Qt, QTimer

from ui.components.window_feature import WindowFeature


class VideoPlotController(WindowFeature):
    """Video comparison DAS rendering, playhead overlays and focus mode."""

    def __init__(self, window):
        super().__init__(window)
        self.video_playhead_line = None
        self._video_focus_mode = False

    def resetVideoComparisonView(self):
        """Undo wheel zoom/pan using the current data and video window."""
        group, timeline = self.window.sync._videoDataContext()
        if group is None or timeline is None:
            return
        duration = timeline.total_samples / timeline.sampling_rate
        if self.window.video_files.video_sequence_data_group is None:
            data = getattr(self.window.data, "origin_data", None)
            if data is not None:
                duration = data.shape[1] / timeline.sampling_rate
        left, right = 0.0, duration
        if (
            self.window.annotations.video_annotation_project.video_path
            or self.window.video_files.video_sequence_data_group is not None
        ):
            width = min(duration, self.window.video_analysis._videoVisibleWindowSeconds())
            sample = self.window.annotations.video_annotation_project.sync.sample_for_video_position(
                self.window.annotations._currentVideoPosition(), timeline
            )
            seconds = (sample or 0) / timeline.sampling_rate
            left = min(max(seconds - width * 0.25, 0.0), max(0.0, duration - width))
            right = left + width
        channel_from, channel_to = self.window.sync._videoChannelBounds()
        self.video_das_plot_widget.getViewBox().setRange(
            xRange=(left, right), yRange=(0, channel_to - channel_from + 1), padding=0
        )

    def setVideoFocusMode(self, enabled: bool):
        """Temporarily give the DAS plot all available workspace."""

        enabled = bool(enabled)
        self._video_focus_mode = enabled
        if hasattr(self.window.workspace, "sidebar_tabs"):
            self.window.workspace.sidebar_tabs.setVisible(not enabled)
        if hasattr(self.window.overlays, "event_range_widget"):
            self.window.overlays.event_range_widget.setVisible(
                not enabled
                and self.window.workspace.tab_widget.currentWidget() is not self.window.video_ui.video_compare_container
            )
        if hasattr(self, "video_focus_button"):
            self.video_focus_button.setText("退出专注" if enabled else "专注模式")
        QTimer.singleShot(0, self._refreshPlayhead)

    def _refreshPlayhead(self):
        self.window.sync._updateVideoPlayhead(self.window.annotations._currentVideoPosition(), force=True)

    def plotVideoComparisonImage(self, preserve_view=False):
        """Draw only the processed DAS window around the current video time."""

        if not hasattr(self, "video_das_plot_widget"):
            return
        plot_widget = self.video_das_plot_widget
        canvas = self.window.annotations.annotation_canvas
        previous_range = (
            plot_widget.getViewBox().viewRange() if (preserve_view or (canvas is not None and canvas.busy)) else None
        )
        if canvas is not None:
            canvas.clear_rendered()
        # 暂停绘制，避免 clear() 和重新添加 Item 之间出现空白帧（闪烁）
        updates_disabled = not plot_widget.updatesEnabled()
        plot_widget.setUpdatesEnabled(False)
        plot_widget.clear()
        self.window.annotations._video_annotation_items = []
        self.video_playhead_line = None
        self.window.sync.video_camera_line = None
        data_group, timeline = self.window.sync._videoDataContext()
        sequence_active = self.window.video_files.video_sequence_data_group is not None
        display_data = None if sequence_active else getattr(self.window.data, "origin_data", None)
        plot_widget.setTimeOrigin(timeline.start_time if timeline is not None else None)
        plot_widget.setTitle("")
        if timeline is None or data_group is None or (not sequence_active and display_data is None):
            if canvas is not None:
                canvas.cancel()
                canvas.bounds = None
            self.video_current_das_label.setText("DAS：请先匹配数据")
            self.window.video_files.video_sequence_status_label.setText("匹配 DAS：未加载")
            if not updates_disabled:
                plot_widget.setUpdatesEnabled(True)
            return

        channel_from, channel_to = self.window.sync._videoChannelBounds()
        channel_count = channel_to - channel_from + 1
        if canvas is not None:
            canvas.set_bounds(timeline.total_samples / timeline.sampling_rate, channel_count)
        if not sequence_active:
            count = len(data_group.segments)
            self.window.video_files.video_sequence_status_label.setText(f"DAS：普通加载 {count} 文件")
            self.window.video_files.video_sequence_status_label.setToolTip(
                "当前显示来自数据页完整加载的数据；长录像请使用“匹配 DAS”按窗口读取。"
            )

        self.window.sync.video_camera_channel_spin_box.blockSignals(True)
        try:
            self.window.sync.video_camera_channel_spin_box.setRange(channel_from, channel_to)
            camera_channel = self.window.annotations.video_annotation_project.camera_channel
            self.window.sync.video_camera_channel_spin_box.setValue(min(max(channel_from, camera_channel), channel_to))
        finally:
            self.window.sync.video_camera_channel_spin_box.blockSignals(False)

        item = pg.ImageItem()
        if sequence_active:
            current_sample = self.window.annotations.video_annotation_project.sync.sample_for_video_position(
                self.window.annotations._currentVideoPosition(), timeline
            )
            current_sample = 0 if current_sample is None else int(current_sample)
            current_seconds = current_sample / timeline.sampling_rate
            candidates = [
                window
                for window in self.window.video_analysis.video_trajectory_windows.values()
                if window.start_sample <= current_sample <= window.end_sample
            ]
            active_window = min(
                candidates,
                key=lambda window: abs((window.start_sample + window.end_sample) // 2 - current_sample),
                default=None,
            )
            self.window.video_analysis.video_trajectory_current_window = active_window

            plot_channel_count = channel_count
            self._video_plot_channel_from = channel_from
            duration = timeline.total_samples / timeline.sampling_rate
            visible_width = min(duration, self.window.video_analysis._videoVisibleWindowSeconds())
            visible_width = max(1 / timeline.sampling_rate, visible_width)
            visible_left = min(
                max(current_seconds - visible_width * 0.25, 0.0),
                max(0.0, duration - visible_width),
            )
            view_box = plot_widget.getViewBox()
            view_box.setLimits(
                xMin=0.0,
                xMax=duration,
                yMin=0.0,
                yMax=plot_channel_count,
            )
            view_box.setRange(
                xRange=(visible_left, visible_left + visible_width),
                yRange=(0.0, plot_channel_count),
                padding=0,
            )

            if active_window is not None:
                levels = self.window.plots.imageLevels(active_window.processed_data)
                cached_windows = sorted(
                    self.window.video_analysis.video_trajectory_windows.values(),
                    key=lambda window: window.start_sample,
                )
                centers = [(window.start_sample + window.end_sample) / 2.0 for window in cached_windows]
                for index, cached_window in enumerate(cached_windows):
                    display_start = cached_window.start_sample
                    display_end = cached_window.end_sample
                    if index > 0:
                        display_start = max(
                            display_start,
                            int(round((centers[index - 1] + centers[index]) / 2.0)),
                        )
                    if index + 1 < len(cached_windows):
                        display_end = min(
                            display_end,
                            int(round((centers[index] + centers[index + 1]) / 2.0)),
                        )
                    if display_end <= display_start:
                        continue
                    data_width = cached_window.processed_data.shape[1]
                    sample_scale = data_width / max(1, cached_window.sample_count)
                    data_start = max(
                        0,
                        int(round((display_start - cached_window.start_sample) * sample_scale)),
                    )
                    data_end = min(
                        data_width,
                        int(round((display_end - cached_window.start_sample) * sample_scale)),
                    )
                    if data_end <= data_start:
                        continue
                    cached_item = pg.ImageItem()
                    cached_item.setImage(
                        cached_window.processed_data[:, data_start:data_end].T,
                        autoLevels=levels is None,
                    )
                    if levels is not None:
                        cached_item.setLevels(levels)
                    cached_item.setRect(
                        QRectF(
                            display_start / timeline.sampling_rate,
                            0.0,
                            (display_end - display_start) / timeline.sampling_rate,
                            plot_channel_count,
                        )
                    )
                    plot_widget.addItem(cached_item)
                self.window.video_analysis._drawVideoWindowTrajectories(plot_widget, active_window)
            else:
                waiting = pg.TextItem("正在预读当前 DAS 连续滚动窗口…", color="#667085", anchor=(0.5, 0.5))
                waiting.setPos(visible_left + visible_width / 2.0, plot_channel_count / 2.0)
                plot_widget.addItem(waiting)
        else:
            self._video_plot_channel_from = channel_from
            levels = self.window.plots.imageLevels(display_data)
            item.setImage(display_data.T, autoLevels=levels is None)
            if levels is not None:
                item.setLevels(levels)
            duration = display_data.shape[1] / timeline.sampling_rate
            item.setRect(QRectF(0.0, 0.0, duration, channel_count))
            plot_widget.addItem(item)
            view_box = plot_widget.getViewBox()
            view_box.setLimits(xMin=0.0, xMax=duration, yMin=0.0, yMax=channel_count)
            view_box.setRange(xRange=(0.0, duration), yRange=(0.0, channel_count), padding=0)
            self.window.overlays.drawFileBoundaries(plot_widget, 0, channel_count)
            self.window.vehicles.drawVehicleTrajectories(plot_widget, full_range=True)
            self.window.overlays.drawEventRange(plot_widget)
        if self.window.sync.video_annotation_context_matches:
            self._drawVideoCameraLine()
            self.window.annotations._drawVideoAnnotations()
            self.window.video_ui.trajectory_prescreen.render()
        self._drawVideoPlayhead()
        self.window.sync._updateVideoPlayhead(self.window.annotations._currentVideoPosition(), force=True)
        if previous_range is not None:
            plot_widget.getViewBox().setRange(xRange=previous_range[0], yRange=previous_range[1], padding=0)
        if canvas is not None:
            canvas.restore_overlays()
            if canvas.busy:
                for line in (self.video_playhead_line, self.window.sync.video_camera_line):
                    if line is not None:
                        line.setMovable(False)
        # 恢复绘制，所有 Item 一次性渲染到屏幕，消除重建过程中的白帧
        plot_widget.setUpdatesEnabled(True)

    def _drawVideoCameraLine(self):
        if not self.window.annotations.video_annotation_project.camera_visible:
            return
        channel = self.window.annotations.video_annotation_project.camera_channel
        channel_from, channel_to = self.window.sync._videoChannelBounds()
        if not (channel_from <= channel <= channel_to):
            return
        plot_origin = getattr(self, "_video_plot_channel_from", channel_from)
        local_channel = channel - plot_origin + 0.5
        line = pg.InfiniteLine(
            pos=local_channel,
            angle=0,
            movable=True,
            bounds=(0, channel_to - channel_from + 1),
            pen=pg.mkPen("#2563eb", width=3),
            hoverPen=pg.mkPen("#1d4ed8", width=5),
        )
        line.setZValue(28)
        line.setToolTip("拖动此线可修正摄像头对应的全局 DAS 通道；不会修改 DAS 数据。")
        pg.InfLineLabel(
            line,
            text=(
                f"{self.window.annotations.video_annotation_project.camera_name} · 通道 {self.window.annotations.video_annotation_project.camera_channel}"
            ),
            position=0.97,
            color="#1d4ed8",
            fill=pg.mkBrush(255, 255, 255, 215),
            movable=True,
        )
        line.sigPositionChangeFinished.connect(lambda item=line: self.window.sync._videoCameraLineMoved(item))
        self.video_das_plot_widget.addItem(line)
        self.window.sync.video_camera_line = line
        self.window.annotations._video_annotation_items.append(line)

    def _drawVideoPlayhead(self):
        timeline = self.window.sync._annotationTimeline()
        can_calibrate = bool(
            timeline is not None and self.window.annotations.video_annotation_project.sync.video_start_time is not None
        )
        line = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=can_calibrate,
            pen=pg.mkPen("#7c3aed", width=3, style=Qt.DashLine),
            hoverPen=pg.mkPen("#5b21b6", width=5, style=Qt.DashLine),
        )
        if timeline is not None:
            line.setBounds((0.0, timeline.total_samples / float(timeline.sampling_rate)))
        line.setZValue(40)
        if can_calibrate:
            target = self.window.sync._videoPlayheadTarget(line)
            if target is not None:
                sample, wall_time = target
                self.window.sync._setVideoPlayheadTooltip(line, sample, wall_time)
            line.sigDragged.connect(self.window.sync._videoPlayheadDragged)
            line.sigPositionChangeFinished.connect(self.window.sync._videoPlayheadMoveFinished)
        else:
            line.setToolTip("请先设置视频开始时间，再拖动紫色虚线进行校正")
        self.video_das_plot_widget.addItem(line)
        self.video_playhead_line = line
        self.window.annotations._video_annotation_items.append(line)
