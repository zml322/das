"""Video/DAS context, camera channel and clock calibration."""

from datetime import datetime, timedelta

import numpy as np
from PyQt5.QtCore import QDateTime, Qt

from core.data.data_timeline import format_wall_time
from core.video.annotation import format_video_position, parse_video_start_time
from ui.components.window_feature import WindowFeature
from utils.function import printError


class VideoSyncController(WindowFeature):
    """Video/DAS context, camera channel and clock calibration."""

    def __init__(self, window):
        super().__init__(window)
        self.video_annotation_context_matches = True
        self._last_video_playhead_update_ms = -1000
        self.video_camera_line = None
        self.video_sync_calibration_anchors = []
        self._video_sync_undo_stack = []
        self._video_sync_pick_mode = None
        self._video_playhead_dragging = False

    def _videoDataContext(self):
        """Return the long-recording context when one is active for video work."""

        if (
            self.window.video_files.video_sequence_data_group is not None
            and self.window.video_files.video_sequence_timeline is not None
        ):
            return self.window.video_files.video_sequence_data_group, self.window.video_files.video_sequence_timeline
        if self.window.video_files.video_das_match_required:
            return None, None
        return self.window.data.data_group, self.window.data.data_timeline

    def _clearVideoSequenceContext(self):
        """Return video comparison to the normal, full-resolution data context."""

        if self.window.video_analysis.video_filter_dialog is not None:
            self.window.video_analysis.video_filter_dialog.close()
            self.window.video_analysis.video_filter_dialog.deleteLater()
            self.window.video_analysis.video_filter_dialog = None
        self.window.video_files.video_sequence_data_group = None
        self.window.video_files.video_sequence_timeline = None
        self.window.video_files.video_sequence_source_paths = []
        self.window.video_files.video_sequence_time_headers = []
        self.window.video_files.video_sequence_selected_segment_index = None
        self.window.video_files.video_das_match_required = bool(
            self.window.annotations.video_annotation_project.video_path
        )
        self.window.video_analysis.video_trajectory_windows.clear()
        self.window.video_analysis.video_trajectory_pending.clear()
        self.window.video_analysis.video_trajectory_current_window = None
        # 清除正在进行的区间标注状态
        self.window.annotations._cancelPendingIntervalAnnotation()
        if hasattr(self.window.video_files, "video_sequence_status_label"):
            self.window.video_files.video_sequence_status_label.setText("匹配 DAS：未加载")
            self.window.video_files.video_sequence_status_label.setToolTip("")

    def _videoChannelBounds(self):
        group, _timeline = self._videoDataContext()
        if group is not None:
            return 1, int(group.channel_count)
        return 1, 1

    def _annotationTimeline(self):
        _group, timeline = self._videoDataContext()
        if timeline is None or not self.video_annotation_context_matches:
            return None
        return timeline

    def updateVideoAnnotationDataContext(self):
        """Bind an annotation project only to its matching imported DAS source."""

        if hasattr(self.window.video_ui, "trajectory_prescreen"):
            self.window.video_ui.trajectory_prescreen.invalidate()
        data_group, timeline = self._videoDataContext()
        if self.window.annotations.annotation_canvas is not None:
            self.window.annotations.annotation_canvas.cancel()
        if data_group is None or timeline is None:
            self.video_annotation_context_matches = False
            # 上下文无效时清除正在进行的区间标注
            self.window.annotations._cancelPendingIntervalAnnotation()
            self._updateVideoControlEnabledState()
            return False
        matches = self.window.annotations.video_annotation_project.set_das_context(data_group, timeline)
        self.video_annotation_context_matches = bool(matches)
        if matches:
            self.window.annotations.video_annotation_project.das_correction_seconds = (
                self.window.controls.time_correction_seconds
            )
            self.window.annotations.video_annotation_project.reproject_video_annotations(timeline)
        else:
            # 上下文不匹配时清除正在进行的区间标注
            self.window.annotations._cancelPendingIntervalAnnotation()
        self._updateVideoControlEnabledState()
        return matches

    def _updateVideoControlEnabledState(self):
        """Keep media controls usable while withholding data-dependent marking."""

        has_video = bool(self.window.annotations.video_annotation_project.video_path)
        has_timeline = self._annotationTimeline() is not None
        has_sync = has_video and self.window.annotations.video_annotation_project.sync.video_start_time is not None
        can_mark = has_timeline and has_sync
        self.window.video_files.video_das_load_button.setEnabled(has_sync)
        for widget in (
            self.video_camera_channel_spin_box,
            self.video_camera_channel_apply_button,
            self.window.video_analysis.video_trajectory_dx_spin_box,
            self.video_camera_visible_checkbox,
            self.window.video_plot.video_annotations_visible_checkbox,
            self.window.video_plot.video_follow_checkbox,
            self.window.video_analysis.video_filter_button,
            self.window.video_plot.video_reset_view_button,
            self.window.video_ui.video_prescreen_button,
        ):
            widget.setEnabled(has_timeline)
        for widget in (
            self.window.annotations.annotation_point_button,
            self.window.annotations.annotation_interval_start_button,
            self.window.annotations.annotation_update_button,
            self.video_sync_single_button,
            self.video_sync_anchor_button,
        ):
            widget.setEnabled(can_mark)
        self.video_start_time_edit.setEnabled(has_video)
        self.video_sync_apply_button.setEnabled(has_video)
        self.window.annotations.annotation_interval_finish_button.setEnabled(
            can_mark and self.window.annotations.video_annotation_interval_start_ms is not None
        )
        self.window.annotations.annotation_export_button.setEnabled(
            bool(self.window.annotations.video_annotation_project.annotations)
        )
        self.window.annotations.annotation_save_button.setEnabled(True)
        self.window.annotations.annotation_delete_button.setEnabled(
            self.window.annotations.video_annotation_selected_id is not None
        )
        self.window.annotations.annotation_undo_button.setEnabled(bool(self.window.annotations._annotation_undo_stack))
        self.window.annotations.annotation_redo_button.setEnabled(bool(self.window.annotations._annotation_redo_stack))
        for button in list(self.window.annotations.annotation_shape_buttons.values()) + list(
            self.window.annotations.annotation_plot_tool_buttons.values()
        ):
            button.setEnabled(has_timeline)
        self.window.annotations.annotation_update_button.setEnabled(
            has_timeline and self.window.annotations.video_annotation_selected_id is not None
        )
        canvas = self.window.annotations.annotation_canvas
        self.window.annotations.annotation_shape_save_button.setEnabled(
            canvas is not None and canvas._edit_id is not None
        )
        self.window.annotations.annotation_shape_cancel_button.setEnabled(canvas is not None and canvas.busy)
        self.window.annotations.annotation_plot_finish_button.setEnabled(canvas is not None and canvas.busy)
        self.window.annotations.annotation_plot_cancel_button.setEnabled(canvas is not None and canvas.busy)
        if not has_timeline:
            self.video_sync_summary_label.setText("对时：请先导入与视频对应的 DAS 数据")
        elif not self.video_annotation_context_matches:
            self.video_sync_summary_label.setText("对时：当前标注工程不属于这组 DAS 文件，已停止显示标签")
        elif not has_video:
            self.video_sync_summary_label.setText("对时：请选择摄像头视频")
        elif not has_sync:
            self.video_sync_summary_label.setText("对时：请设置视频开始时间")

    def _markVideoAnnotationDirty(self):
        self.window.annotations.video_annotation_dirty = True
        self._updateVideoProjectLabel()

    def _updateVideoProjectLabel(self):
        project_path = self.window.annotations.video_annotation_project.project_path
        if project_path:
            state = "有未保存修改" if self.window.annotations.video_annotation_dirty else "已保存"
            self.window.annotations.annotation_project_label.setText(f"{state}：{project_path}")
            self.window.annotations.annotation_project_label.setToolTip(project_path)
        else:
            self.window.annotations.annotation_project_label.setText("未保存：标签仅在本次会话保留")
            self.window.annotations.annotation_project_label.setToolTip("请使用“保存”创建独立标注工程文件")

    def _syncVideoProjectWidgets(self):
        """Reflect model state in controls without accidentally applying edits."""

        project = self.window.annotations.video_annotation_project
        direction_text = self.window.annotations.annotation_direction_combo.currentText()
        self.window.annotations.annotation_direction_combo.clear()
        self.window.annotations.annotation_direction_combo.addItems(project.direction_labels)
        self.window.annotations.annotation_direction_combo.setEditText(direction_text)
        self.video_camera_channel_spin_box.blockSignals(True)
        self.video_camera_visible_checkbox.blockSignals(True)
        self.video_start_time_edit.blockSignals(True)
        self.video_sync_offset_spin_box.blockSignals(True)
        self.video_sync_rate_spin_box.blockSignals(True)
        try:
            self.video_camera_channel_spin_box.setValue(max(1, project.camera_channel))
            self.video_camera_visible_checkbox.setChecked(project.camera_visible)
            if project.sync.video_start_time is not None:
                self.video_start_time_edit.setDateTime(QDateTime(project.sync.video_start_time))
            self.video_sync_offset_spin_box.setValue(project.sync.manual_offset_seconds)
            self.video_sync_rate_spin_box.setValue(project.sync.rate)
        finally:
            self.video_camera_channel_spin_box.blockSignals(False)
            self.video_camera_visible_checkbox.blockSignals(False)
            self.video_start_time_edit.blockSignals(False)
            self.video_sync_offset_spin_box.blockSignals(False)
            self.video_sync_rate_spin_box.blockSignals(False)
        self._updateVideoTimeLabel(
            self.window.annotations._currentVideoPosition(), self.window.playback.position_slider.maximum()
        )
        self._updateVideoProjectLabel()
        self._updateVideoControlEnabledState()
        self._updateVideoSyncState()

    def _videoFrameTime(self, position_ms: int):
        """Return the camera-clock time for one playback position."""

        start_time = self.window.annotations.video_annotation_project.sync.video_start_time
        if start_time is None:
            return None
        return start_time + timedelta(seconds=max(0, int(position_ms)) / 1000.0)

    def _updateVideoTimeLabel(self, position_ms: int, duration_ms: int = None):
        """Show camera wall time prominently while retaining playback progress."""

        position_ms = max(0, int(position_ms))
        if duration_ms is None:
            duration_ms = self.window.playback.position_slider.maximum()
        duration_ms = max(0, int(duration_ms))
        progress = f"{format_video_position(position_ms)} / {format_video_position(duration_ms)}"
        frame_time = self._videoFrameTime(position_ms)
        if frame_time is None:
            self.window.playback.time_label.setText(progress)
            self.window.playback.time_label.setToolTip("请先设置视频开始时间")
            return
        wall_time = format_wall_time(frame_time)
        self.window.playback.time_label.setText(f"摄像头 {wall_time}\n进度 {progress}")
        self.window.playback.time_label.setToolTip(
            f"当前视频帧的摄像头时间：{wall_time}\n视频开始时间："
            f"{format_wall_time(self.window.annotations.video_annotation_project.sync.video_start_time)}"
        )

    def _videoPositionChanged(self, position: int):
        if not self.window.playback.slider_dragging:
            self.window.playback.position_slider.setValue(max(0, int(position)))
        self._updateVideoTimeLabel(position, self.window.playback.position_slider.maximum())
        self._updateVideoPlayhead(position)

    def _updateVideoPlayhead(self, position_ms: int, force: bool = False):
        """Move the synchronized cursor only; never redraw the data image per frame."""

        if not force and abs(int(position_ms) - self._last_video_playhead_update_ms) < 50:
            return
        self._last_video_playhead_update_ms = int(position_ms)
        timeline = self._annotationTimeline()
        if timeline is None:
            self.window.video_plot.video_current_das_label.setText("DAS：等待数据")
            return
        sample = self.window.annotations.video_annotation_project.sync.sample_for_video_position(position_ms, timeline)
        if sample is None:
            self.window.video_plot.video_current_das_label.setText("DAS：未设置视频开始时间")
            return
        sampling_rate = float(timeline.sampling_rate)
        seconds = sample / sampling_rate
        wall_time = timeline.absolute_time_for_sample(sample)
        self.window.video_plot.video_current_das_label.setText(f"DAS {format_wall_time(wall_time)}  |  样点 {sample}")
        if self.window.video_plot.video_playhead_line is not None:
            if not self._video_playhead_dragging:
                self.window.video_plot.video_playhead_line.setPos(seconds)
                self._setVideoPlayheadTooltip(self.window.video_plot.video_playhead_line, sample, wall_time)
        if (
            self.window.video_plot.video_follow_checkbox.isChecked()
            and self.window.video_plot.video_das_plot_widget is not None
            and not (
                self.window.annotations.annotation_canvas is not None and self.window.annotations.annotation_canvas.busy
            )
        ):
            view_box = self.window.video_plot.video_das_plot_widget.getViewBox()
            maximum = timeline.total_samples / sampling_rate
            width = min(self.window.video_analysis._videoVisibleWindowSeconds(), maximum)
            width = max(width, 1 / sampling_rate)
            # Keep the playhead at one quarter of the window.  Updating this
            # range on every clock tick produces a continuous stitched scroll
            # instead of the former edge-triggered jumps.
            target_left = min(
                max(seconds - width * 0.25, 0.0),
                max(0.0, maximum - width),
            )
            target_right = min(maximum, target_left + width)
            view_box.setXRange(target_left, target_right, padding=0)
        self.window.video_analysis._requestVideoTrajectoryForPosition(position_ms)

    def _videoPlayheadTarget(self, line):
        """Return the DAS sample and wall time represented by a cursor line."""

        timeline = self._annotationTimeline()
        if timeline is None:
            return None
        seconds = min(
            max(float(line.value()), 0.0),
            timeline.total_samples / float(timeline.sampling_rate),
        )
        sample = min(
            max(int(round(seconds * float(timeline.sampling_rate))), 0),
            timeline.total_samples,
        )
        return sample, timeline.absolute_time_for_sample(sample)

    @staticmethod
    def _setVideoPlayheadTooltip(line, sample: int, wall_time: datetime):
        line.setToolTip(
            f"DAS 时间：{format_wall_time(wall_time)}\n样点：{sample}\n拖动紫色虚线并松开，可校正当前视频帧"
        )

    def _videoPlayheadDragged(self, line):
        """Pause playback and preview the DAS time underneath the dragged cursor."""

        if not self._video_playhead_dragging:
            self._video_playhead_dragging = True
            if self.window.playback.backend == "ffmpeg":
                self.window.playback.playing = False
                self.window.playback._stopFfmpegVideoWorker()
                self.window.playback.play_button.setText("播放")
            elif self.window.playback.qt_player is not None:
                self.window.playback.qt_player.pause()
        target = self._videoPlayheadTarget(line)
        if target is None:
            return
        sample, wall_time = target
        self._setVideoPlayheadTooltip(line, sample, wall_time)
        self.window.video_plot.video_current_das_label.setText(f"DAS {format_wall_time(wall_time)}  |  样点 {sample}")
        camera_time = self._videoFrameTime(self.window.annotations._currentVideoPosition())
        if camera_time is not None:
            delta = (camera_time - wall_time).total_seconds()
            self.video_sync_summary_label.setText(
                f"拖动对时：摄像头 {format_wall_time(camera_time)}；"
                f"所选 DAS {format_wall_time(wall_time)}；松开后修正 DAS "
                f"{delta:+.3f} s。"
            )

    def _videoPlayheadMoveFinished(self, line):
        """Commit one drag as a single-start-time video/DAS calibration."""

        if not self._video_playhead_dragging:
            return
        self._video_playhead_dragging = False
        target = self._videoPlayheadTarget(line)
        if target is None:
            return
        sample, _wall_time = target
        self._alignCurrentVideoToDasSample(sample)

    def _beginVideoSyncPick(self, mode: str):
        """Pause playback and let the next DAS click establish correspondence."""

        button = self.video_sync_single_button if mode == "single" else self.video_sync_anchor_button
        if not button.isChecked():
            self._finishVideoSyncPick()
            self.video_sync_summary_label.setText("已取消人工对时取点。")
            return
        if self._annotationTimeline() is None:
            self._finishVideoSyncPick()
            printError("请先自动匹配视频对应的 DAS 数据")
            return
        if self.window.annotations.video_annotation_project.sync.video_start_time is None:
            self._finishVideoSyncPick()
            printError("请先设置视频开始时间")
            return
        if self.window.playback.backend == "ffmpeg":
            self.window.playback.playing = False
            self.window.playback._stopFfmpegVideoWorker()
            self.window.playback.play_button.setText("播放")
        elif self.window.playback.qt_player is not None:
            self.window.playback.qt_player.pause()
        self._video_sync_pick_mode = mode
        other = self.video_sync_anchor_button if mode == "single" else self.video_sync_single_button
        other.blockSignals(True)
        other.setChecked(False)
        other.blockSignals(False)
        action = "单点校正" if mode == "single" else "校准点"
        self.video_sync_summary_label.setText(
            f"{action}取点中：请在右侧 DAS 图点击与当前视频帧相同的事件时刻；再次点击按钮可取消。"
        )

    def _finishVideoSyncPick(self):
        self._video_sync_pick_mode = None
        for button in (
            self.video_sync_single_button,
            self.video_sync_anchor_button,
        ):
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)

    def _videoSyncSnapshot(self):
        sync = self.window.annotations.video_annotation_project.sync
        return {
            "video_start_time": sync.video_start_time,
            "manual_offset_seconds": float(sync.manual_offset_seconds),
            "rate": float(sync.rate),
            "anchors": [dict(item) for item in self.window.annotations.video_annotation_project.calibration_anchors],
        }

    def _pushVideoSyncUndo(self):
        snapshot = self._videoSyncSnapshot()
        if not self._video_sync_undo_stack or self._video_sync_undo_stack[-1] != snapshot:
            self._video_sync_undo_stack.append(snapshot)
            self._video_sync_undo_stack = self._video_sync_undo_stack[-20:]

    def _restoreVideoSyncSnapshot(self, snapshot, message: str):
        sync = self.window.annotations.video_annotation_project.sync
        sync.update(
            snapshot.get("video_start_time"),
            snapshot.get("manual_offset_seconds", 0.0),
            snapshot.get("rate", 1.0),
        )
        self.window.annotations.video_annotation_project.calibration_anchors = [
            dict(item) for item in snapshot.get("anchors", [])
        ]
        self.video_sync_calibration_anchors = list(self.window.annotations.video_annotation_project.calibration_anchors)
        timeline = self._annotationTimeline()
        moved = (
            self.window.annotations.video_annotation_project.reproject_video_annotations(timeline) if timeline else 0
        )
        self._markVideoAnnotationDirty()
        self._syncVideoProjectWidgets()
        self.window.annotations.refreshVideoAnnotationTable(
            select_identifier=self.window.annotations.video_annotation_selected_id
        )
        self.window.video_plot.plotVideoComparisonImage()
        self._updateVideoPlayhead(self.window.annotations._currentVideoPosition(), force=True)
        self.video_sync_summary_label.setText(f"{message}；重新定位 {moved} 条标注。")

    def undoVideoSyncCalibration(self):
        if not self._video_sync_undo_stack:
            return
        self._restoreVideoSyncSnapshot(
            self._video_sync_undo_stack.pop(),
            "已撤销上一次对时修改",
        )

    def resetVideoSyncCalibration(self):
        sync = self.window.annotations.video_annotation_project.sync
        initial_start = parse_video_start_time(self.window.annotations.video_annotation_project.video_path)
        if initial_start is None:
            initial_start = sync.video_start_time
        target = {
            "video_start_time": initial_start,
            "manual_offset_seconds": 0.0,
            "rate": 1.0,
            "anchors": [],
        }
        if self._videoSyncSnapshot() == target:
            return
        self._pushVideoSyncUndo()
        self._restoreVideoSyncSnapshot(target, "已恢复文件名初始对时")

    def _updateVideoSyncState(self):
        if not hasattr(self, "video_sync_state_label"):
            return
        sync = self.window.annotations.video_annotation_project.sync
        if not self.window.annotations.video_annotation_project.video_path:
            text = "等待选择视频"
            active = False
        elif sync.video_start_time is None:
            text = "未设置视频开始时间"
            active = False
        else:
            parsed = parse_video_start_time(self.window.annotations.video_annotation_project.video_path)
            source = "文件名对时" if parsed == sync.video_start_time else "手工开始时间"
            anchor_count = len(self.window.annotations.video_annotation_project.calibration_anchors)
            text = (
                f"{source} · 偏移 {sync.manual_offset_seconds:+.3f} s · 倍率 {sync.rate:.6f} · {anchor_count} 个校准点"
            )
            active = self._annotationTimeline() is not None
        self.video_sync_state_label.setText(text)
        self.video_sync_state_label.setProperty("state", "active" if active else "inactive")
        self.video_sync_state_label.style().unpolish(self.video_sync_state_label)
        self.video_sync_state_label.style().polish(self.video_sync_state_label)
        self.video_sync_undo_button.setEnabled(bool(self._video_sync_undo_stack))
        reset_needed = bool(
            self.window.annotations.video_annotation_project.calibration_anchors
            or not np.isclose(sync.manual_offset_seconds, 0.0)
            or not np.isclose(sync.rate, 1.0)
        )
        self.video_sync_reset_button.setEnabled(
            bool(self.window.annotations.video_annotation_project.video_path) and reset_needed
        )

    def _videoDasClicked(self, event):
        """Seek, or use Ctrl+Shift to anchor the current video frame to DAS."""

        if self.window.annotations.annotation_canvas is not None and self.window.annotations.annotation_canvas.busy:
            return
        if event.button() != Qt.LeftButton:
            return
        if getattr(event, "double", lambda: False)():
            if (
                self.window.annotations.annotation_canvas is not None
                and self.window.annotations.annotation_canvas._hit_test(event.scenePos()) is not None
            ):
                return
            self.window.video_plot.video_focus_button.toggle()
            return
        pick_mode = self._video_sync_pick_mode
        if pick_mode is None and not (event.modifiers() & Qt.ControlModifier):
            return
        timeline = self._annotationTimeline()
        if timeline is None:
            return
        view_box = self.window.video_plot.video_das_plot_widget.getViewBox()
        point = view_box.mapSceneToView(event.scenePos())
        sample = min(
            max(int(round(point.x() * timeline.sampling_rate)), 0),
            timeline.total_samples,
        )
        if pick_mode == "anchor" or event.modifiers() & Qt.ShiftModifier:
            self._recordVideoCalibrationAnchor(sample)
            self._finishVideoSyncPick()
            return
        if pick_mode == "single":
            self._alignCurrentVideoToDasSample(sample)
            self._finishVideoSyncPick()
            return
        position = self.window.annotations.video_annotation_project.sync.video_position_for_sample(sample, timeline)
        if position is None:
            return
        if self.window.playback.backend == "ffmpeg":
            self.window.playback._seekFfmpegVideo(position, play_continuously=False)
        elif self.window.playback.qt_player is not None:
            self.window.playback.qt_player.pause()
            self.window.playback.qt_player.setPosition(position)
        self._updateVideoPlayhead(position, force=True)

    def _alignCurrentVideoToDasSample(self, sample: int):
        """Use the camera clock to correct the DAS wall-clock timeline."""

        timeline = self._annotationTimeline()
        sync = self.window.annotations.video_annotation_project.sync
        if timeline is None or sync.video_start_time is None:
            printError("请先选择视频并设置视频开始时间，再建立手工对时锚点")
            return
        if self.window.playback.backend == "ffmpeg":
            self.window.playback._stopFfmpegVideoWorker()
        elif self.window.playback.qt_player is not None:
            self.window.playback.qt_player.pause()
        position_ms = self.window.annotations._currentVideoPosition()
        camera_time = self._videoFrameTime(position_ms)
        if camera_time is None:
            printError("无法计算当前视频帧的摄像头时间")
            return
        das_time_before = timeline.absolute_time_for_sample(sample)
        correction_delta = (camera_time - das_time_before).total_seconds()
        new_correction = self.window.controls.time_correction_seconds + correction_delta
        annotation_positions = {
            annotation.identifier: (annotation.start_sample, annotation.end_sample)
            for annotation in self.window.annotations.video_annotation_project.annotations
        }
        self.window.annotations.video_annotation_project.calibration_anchors = []
        self.video_sync_calibration_anchors = []
        self.window.controls.setTimeCorrectionSeconds(new_correction)
        moved = sum(
            annotation_positions.get(annotation.identifier) != (annotation.start_sample, annotation.end_sample)
            for annotation in self.window.annotations.video_annotation_project.annotations
        )
        self._markVideoAnnotationDirty()
        self.window.annotations.refreshVideoAnnotationTable(
            select_identifier=self.window.annotations.video_annotation_selected_id
        )
        self._updateVideoPlayhead(position_ms, force=True)
        self.video_sync_summary_label.setText(
            f"摄像头基准对时已应用：当前帧 {format_wall_time(camera_time)}；"
            f"DAS 时间轴修正 {correction_delta:+.3f} s，累计 "
            f"{new_correction:+.3f} s；重新定位 {moved} 条标签。"
        )

    def _recordVideoCalibrationAnchor(self, sample: int):
        """Use two operator-confirmed events to solve offset and clock rate."""
        timeline = self._annotationTimeline()
        sync = self.window.annotations.video_annotation_project.sync
        if timeline is None or sync.video_start_time is None:
            printError("请先选择视频、导入匹配 DAS，再记录校准锚点")
            return
        if self.window.playback.backend == "ffmpeg":
            self.window.playback._stopFfmpegVideoWorker()
        elif self.window.playback.qt_player is not None:
            self.window.playback.qt_player.pause()
        anchor = {
            "video_position_ms": int(self.window.annotations._currentVideoPosition()),
            "das_sample": int(sample),
        }
        anchors = list(self.window.annotations.video_annotation_project.calibration_anchors)
        if anchors and abs(anchor["video_position_ms"] - anchors[-1]["video_position_ms"]) < 100:
            printError("两次校准锚点的视频时刻过近；请使用两次明确且相隔较远的车辆经过事件")
            return
        candidate_anchors = (anchors + [anchor])[-2:]
        if len(candidate_anchors) < 2:
            self._pushVideoSyncUndo()
            self.window.annotations.video_annotation_project.calibration_anchors = candidate_anchors
            self.video_sync_calibration_anchors = list(candidate_anchors)
            self._markVideoAnnotationDirty()
            self._updateVideoSyncState()
            self.video_sync_summary_label.setText(
                "已记录第 1 个校准点。暂停到另一个相隔较远的明确事件，点击“添加校准点”后在 DAS 图选取第 2 点。"
            )
            return
        first, second = candidate_anchors
        video_delta = (second["video_position_ms"] - first["video_position_ms"]) / 1000.0
        das_first = timeline.absolute_time_for_sample(first["das_sample"])
        das_second = timeline.absolute_time_for_sample(second["das_sample"])
        das_delta = (das_second - das_first).total_seconds()
        if video_delta <= 0 or das_delta <= 0:
            printError("校准锚点必须按时间先后记录，且两次事件不能是同一时刻")
            return
        rate = das_delta / video_delta
        if not 0.9 <= rate <= 1.1:
            printError(f"两点推得的时钟倍率 {rate:.6f} 超出安全范围；请核对是否点中了同一车辆事件")
            return
        offset = (das_first - sync.video_start_time).total_seconds() - first["video_position_ms"] / 1000.0 * rate
        self._pushVideoSyncUndo()
        self.window.annotations.video_annotation_project.calibration_anchors = candidate_anchors
        self.video_sync_calibration_anchors = list(candidate_anchors)
        sync.update(sync.video_start_time, offset, rate)
        moved = self.window.annotations.video_annotation_project.reproject_video_annotations(timeline)
        self._markVideoAnnotationDirty()
        self._syncVideoProjectWidgets()
        self.window.annotations.refreshVideoAnnotationTable(
            select_identifier=self.window.annotations.video_annotation_selected_id
        )
        self.window.video_plot.plotVideoComparisonImage()
        self.video_sync_summary_label.setText(
            f"两点校准已应用：偏移 {offset:+.3f} s，时钟倍率 {rate:.8f}；重新定位 {moved} 条标注。"
        )

    def applyVideoCameraChannel(self):
        if self._annotationTimeline() is None:
            return
        channel_from, channel_to = self._videoChannelBounds()
        channel = min(
            max(channel_from, int(self.video_camera_channel_spin_box.value())),
            channel_to,
        )
        self.window.annotations.video_annotation_project.set_camera_channel(channel)
        self._markVideoAnnotationDirty()
        annotation = self.window.annotations.video_annotation_project.annotation_by_identifier(
            self.window.annotations.video_annotation_selected_id
        )
        if annotation is not None:
            self.window.annotations._refreshAnnotationTrajectoryChoices(annotation)
        self.window.video_plot.plotVideoComparisonImage()

    def _videoCameraLineMoved(self, line):
        if self.window.video_plot.video_das_plot_widget is None or self._annotationTimeline() is None:
            return
        local_channel = float(line.value())
        channel_from, channel_to = self._videoChannelBounds()
        plot_origin = getattr(self.window.video_plot, "_video_plot_channel_from", channel_from)
        global_channel = min(
            max(channel_from, int(round(local_channel - 0.5 + plot_origin))),
            channel_to,
        )
        self.window.annotations.video_annotation_project.set_camera_channel(global_channel)
        self.video_camera_channel_spin_box.blockSignals(True)
        try:
            self.video_camera_channel_spin_box.setValue(global_channel)
        finally:
            self.video_camera_channel_spin_box.blockSignals(False)
        self._markVideoAnnotationDirty()
        annotation = self.window.annotations.video_annotation_project.annotation_by_identifier(
            self.window.annotations.video_annotation_selected_id
        )
        if annotation is not None:
            self.window.annotations._refreshAnnotationTrajectoryChoices(annotation)
        self.window.video_plot.plotVideoComparisonImage()

    def setVideoCameraVisible(self, visible: bool):
        self.window.annotations.video_annotation_project.camera_visible = bool(visible)
        self._markVideoAnnotationDirty()
        self.window.video_plot.plotVideoComparisonImage()

    def setVideoAnnotationsVisible(self, _visible: bool):
        self.window.video_plot.plotVideoComparisonImage()

    def applyVideoSync(self):
        """Apply the only editable sync value: video start time."""

        if not self.window.annotations.video_annotation_project.video_path:
            printError("请先选择摄像头视频")
            return
        start_time = self.video_start_time_edit.dateTime().toPyDateTime()
        previous = self._videoSyncSnapshot()
        anchors_changed = bool(self.window.annotations.video_annotation_project.calibration_anchors)
        try:
            changed = self.window.annotations.video_annotation_project.sync.update(
                start_time,
                0.0,
                1.0,
            )
        except ValueError as error:
            printError(str(error))
            return
        if changed or anchors_changed:
            self._video_sync_undo_stack.append(previous)
            self._video_sync_undo_stack = self._video_sync_undo_stack[-20:]
        self.window.annotations.video_annotation_project.calibration_anchors = []
        self.video_sync_calibration_anchors = []
        timeline = self._annotationTimeline()
        moved = (
            self.window.annotations.video_annotation_project.reproject_video_annotations(timeline) if timeline else 0
        )
        if changed or anchors_changed or moved:
            self._markVideoAnnotationDirty()
        self._syncVideoProjectWidgets()
        self.window.annotations.refreshVideoAnnotationTable(
            select_identifier=self.window.annotations.video_annotation_selected_id
        )
        self.window.video_plot.plotVideoComparisonImage()
        self._updateVideoPlayhead(
            self.window.annotations._currentVideoPosition(),
            force=True,
        )
        self.video_sync_summary_label.setText(
            f"视频开始时间已应用：{format_wall_time(start_time)}；重新定位 {moved} 条视频标注。"
        )
