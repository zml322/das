"""Annotation projects, geometry editing, labels and undo history."""

import copy
import os.path

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QMenu,
    QMessageBox,
    QTableWidgetItem,
)

from core.data.data_timeline import format_wall_time
from core.video.annotation import (
    VEHICLE_TYPES,
    AnnotationProject,
    VideoAnnotation,
    format_video_position,
    trajectory_candidates,
    trajectory_crossing_time,
)
from ui.components.window_feature import WindowFeature
from ui.widgets.custom_widgets import ComboBox, LineEdit
from utils.function import printError


class VideoAnnotationsController(WindowFeature):
    """Annotation projects, geometry editing, labels and undo history."""

    def __init__(self, window):
        super().__init__(window)
        self.video_annotation_project = AnnotationProject()
        self.video_annotation_selected_id = None
        self.video_annotation_interval_start_ms = None
        self.video_annotation_dirty = False
        self._video_annotation_items = []
        self.annotation_canvas = None
        self._annotation_undo_stack = []
        self._annotation_redo_stack = []
        self._video_trajectory_candidates = {}

    def newVideoAnnotationProject(self):
        if self.video_annotation_dirty and self.video_annotation_project.annotations:
            reply = QMessageBox.question(
                self.window,
                "新建标注工程",
                "当前标注尚未保存，仍要新建并清空本次会话标签吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._clearAnnotationHistory()
        old_project = self.video_annotation_project
        self.video_annotation_project = AnnotationProject(
            video_path=old_project.video_path,
            camera_name=old_project.camera_name,
            camera_channel=old_project.camera_channel,
            camera_visible=old_project.camera_visible,
            sync=copy.deepcopy(old_project.sync),
            calibration_anchors=copy.deepcopy(old_project.calibration_anchors),
            direction_labels=list(old_project.direction_labels),
            das_correction_seconds=self.window.controls.time_correction_seconds,
        )
        self.video_annotation_selected_id = None
        self.video_annotation_interval_start_ms = None
        self.video_annotation_dirty = False
        self.window.sync._video_sync_undo_stack.clear()
        self.window.sync._finishVideoSyncPick()
        self._video_trajectory_candidates = {}
        self.window.sync.updateVideoAnnotationDataContext()
        self.window.sync._syncVideoProjectWidgets()
        self.refreshVideoAnnotationTable()
        self.window.video_plot.plotVideoComparisonImage(preserve_view=True)

    def openVideoAnnotationProject(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            "打开标注工程",
            "",
            "DAS 视频标注工程 (*.dasannotations.json *.json);;所有文件 (*.*)",
        )
        if not path:
            return
        try:
            project = AnnotationProject.load(path)
        except ValueError as error:
            QMessageBox.warning(self.window, "打开标注工程失败", str(error))
            return
        self.video_annotation_project = project
        self._clearAnnotationHistory()
        if project.das_correction_seconds is not None:
            self.window.controls.setTimeCorrectionSeconds(project.das_correction_seconds)
        self.video_annotation_dirty = False
        self.video_annotation_selected_id = None
        self.video_annotation_interval_start_ms = None
        self.window.sync._video_sync_undo_stack.clear()
        self.window.sync._finishVideoSyncPick()
        _data_group, active_timeline = self.window.sync._videoDataContext()
        matches = self.window.sync.updateVideoAnnotationDataContext() if active_timeline is not None else False
        self.window.sync._syncVideoProjectWidgets()
        self.refreshVideoAnnotationTable()
        if project.video_path:
            self.window.playback.loadVideoComparisonFile(project.video_path, update_project=False)
        else:
            self.window.video_plot.plotVideoComparisonImage()
        if not matches and project.annotations:
            QMessageBox.warning(
                self.window,
                "DAS 数据不匹配",
                "该标注工程绑定的 DAS 文件、采样率或采样数与当前导入数据不一致；"
                "为避免错位，标签暂不显示，也不能新增标注。",
            )

    def saveVideoAnnotationProject(self):
        self.video_annotation_project.das_correction_seconds = self.window.controls.time_correction_seconds
        path = self.video_annotation_project.project_path
        if not path:
            default_name = "video_annotations.dasannotations.json"
            if self.video_annotation_project.video_path:
                stem = os.path.splitext(os.path.basename(self.video_annotation_project.video_path))[0]
                default_name = f"{stem}.dasannotations.json"
            path, _ = QFileDialog.getSaveFileName(
                self.window,
                "保存标注工程",
                default_name,
                "DAS 视频标注工程 (*.dasannotations.json);;JSON 文件 (*.json)",
            )
        if not path:
            return
        try:
            self.video_annotation_project.save(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.window, "保存标注工程失败", str(error))
            return
        self.video_annotation_dirty = False
        self.window.sync._updateVideoProjectLabel()
        self.window.statusBar().showMessage(f"标注工程已保存：{path}", 6000)

    def exportVideoAnnotationsCsv(self):
        if not self.video_annotation_project.annotations:
            printError("当前没有可导出的标注")
            return
        path, _ = QFileDialog.getSaveFileName(
            self.window,
            "导出标注 CSV",
            "video_annotations.csv",
            "CSV 文件 (*.csv)",
        )
        if not path:
            return
        try:
            self.video_annotation_project.export_csv(path, self.window.sync._annotationTimeline())
        except OSError as error:
            QMessageBox.warning(self.window, "导出 CSV 失败", str(error))
            return
        self.window.statusBar().showMessage(
            f"已导出 {len(self.video_annotation_project.annotations)} 条标注：{path}",
            6000,
        )

    def refreshVideoAnnotationTable(self, select_identifier=None):
        timeline = self.window.sync._annotationTimeline()
        selected = self.video_annotation_selected_id if select_identifier is None else select_identifier
        # 断开信号连接以避免触发 itemChanged
        self.annotation_table.itemChanged.disconnect(self._videoAnnotationTableItemChanged)
        self.annotation_table.blockSignals(True)
        try:
            annotations = self.video_annotation_project.annotations
            self.annotation_table.setRowCount(len(annotations))
            target_row = -1
            for row, annotation in enumerate(annotations):
                visible = QTableWidgetItem()
                visible.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                visible.setCheckState(Qt.Checked if annotation.visible else Qt.Unchecked)
                visible.setData(Qt.UserRole, annotation.identifier)
                self.annotation_table.setItem(row, 0, visible)
                identifier = QTableWidgetItem(str(annotation.identifier))
                identifier.setData(Qt.UserRole, annotation.identifier)
                self.annotation_table.setItem(row, 1, identifier)
                self.annotation_table.setItem(
                    row,
                    2,
                    QTableWidgetItem(f"{annotation.shape_label} · {annotation.kind}"),
                )
                video_position = self._annotationVideoPosition(annotation, timeline)
                camera_time = (
                    self.video_annotation_project.sync.wall_time_for_video_position(video_position)
                    if video_position is not None
                    else None
                )
                camera_text = format_wall_time(camera_time) if camera_time is not None else "—"
                if annotation.source_domain == "video" and annotation.is_interval:
                    camera_end = self.video_annotation_project.sync.wall_time_for_video_position(
                        annotation.end_video_ms
                    )
                    if camera_end is not None:
                        camera_text += f" – {format_wall_time(camera_end)}"
                self.annotation_table.setItem(row, 3, QTableWidgetItem(camera_text))
                das_text = ""
                if timeline is not None:
                    das_text = format_wall_time(timeline.absolute_time_for_sample(annotation.start_sample))
                self.annotation_table.setItem(row, 4, QTableWidgetItem(das_text))
                trajectory_text = ""
                if annotation.trajectory_identifier is not None:
                    trajectory_text = f"#{annotation.trajectory_identifier}"
                    if annotation.time_residual_ms is not None:
                        trajectory_text += f"  {annotation.time_residual_ms:+.0f} ms"
                measurement = annotation.track_measurement(timeline.sampling_rate) if timeline is not None else None
                if measurement is not None:
                    speed, r2 = measurement
                    direction = "↑" if speed >= 0 else "↓"
                    trajectory_text = f"{direction} {abs(speed):.1f} km/h · R² {r2:.2f}"
                self.annotation_table.setItem(row, 5, QTableWidgetItem(trajectory_text))
                conclusion = QTableWidgetItem(annotation.outcome)
                conclusion.setToolTip(annotation.note or "无备注")
                self.annotation_table.setItem(row, 6, conclusion)
                channel_text = str(annotation.camera_channel)
                if annotation.vertices:
                    channel_text = (
                        f"{min(p[1] for p in annotation.vertices):.1f}–{max(p[1] for p in annotation.vertices):.1f}"
                    )
                self.annotation_table.setItem(row, 7, QTableWidgetItem(channel_text))
                self.annotation_table.setItem(row, 8, QTableWidgetItem(annotation.vehicle_type or "未设置"))
                self.annotation_table.setItem(
                    row,
                    9,
                    QTableWidgetItem(str(annotation.lane) if annotation.lane is not None else "未设置"),
                )
                self.annotation_table.setItem(row, 10, QTableWidgetItem(annotation.travel_direction or "未设置"))
                if annotation.identifier == selected:
                    target_row = row
            if target_row >= 0:
                self.annotation_table.selectRow(target_row)
        finally:
            self.annotation_table.blockSignals(False)
            # 重新连接信号
            self.annotation_table.itemChanged.connect(self._videoAnnotationTableItemChanged)
        self.window.sync._updateVideoControlEnabledState()

    def _videoAnnotationTableItemChanged(self, item):
        if item.column() != 0:
            return
        identifier_item = self.annotation_table.item(item.row(), 1)
        if identifier_item is None:
            return
        annotation = self.video_annotation_project.annotation_by_identifier(identifier_item.data(Qt.UserRole))
        if annotation is None:
            return
        self._pushAnnotationUndo()
        annotation.visible = item.checkState() == Qt.Checked
        self.window.sync._markVideoAnnotationDirty()
        self.window.video_plot.plotVideoComparisonImage(preserve_view=True)

    def _videoAnnotationTableSelectionChanged(self):
        rows = self.annotation_table.selectionModel().selectedRows()
        if not rows:
            self.video_annotation_selected_id = None
            self.window.sync._updateVideoControlEnabledState()
            return
        identifier_item = self.annotation_table.item(rows[0].row(), 1)
        if identifier_item is None:
            return
        identifier = identifier_item.data(Qt.UserRole)
        annotation = self.video_annotation_project.annotation_by_identifier(identifier)
        if annotation is None:
            return
        self.video_annotation_selected_id = annotation.identifier
        self.annotation_kind_combo.setCurrentText(annotation.kind)
        self.annotation_outcome_combo.setCurrentText(annotation.outcome)
        self.annotation_note_edit.setText(annotation.note)
        self._reflectAnnotationVehicleLabels(annotation)
        self._refreshAnnotationTrajectoryChoices(annotation)
        timeline = self.window.sync._annotationTimeline()
        position = self._annotationVideoPosition(annotation, timeline)
        if annotation.source_domain == "das":
            self._pauseForAnnotationDrawing()
            if position is not None:
                if self.window.playback.backend == "ffmpeg":
                    self.window.playback._seekFfmpegVideo(position, play_continuously=False)
                elif self.window.playback.qt_player is not None:
                    self.window.playback.qt_player.setPosition(position)
                self.window.sync._updateVideoTimeLabel(position)
            self.window.video_plot.plotVideoComparisonImage(preserve_view=True)
            self._centerOnDasAnnotation(annotation)
            self.window.sync._updateVideoControlEnabledState()
            return
        if self.window.playback.backend == "ffmpeg":
            self.window.playback._seekFfmpegVideo(annotation.start_video_ms, play_continuously=False)
        elif self.window.playback.qt_player is not None:
            self.window.playback.qt_player.pause()
            self.window.playback.qt_player.setPosition(annotation.start_video_ms)
        else:
            self.window.playback.position_slider.setValue(annotation.start_video_ms)
        self.window.sync._updateVideoPlayhead(annotation.start_video_ms, force=True)
        self.window.video_plot.plotVideoComparisonImage(preserve_view=True)
        self.window.sync._updateVideoControlEnabledState()

    def _refreshAnnotationTrajectoryChoices(self, annotation):
        self.annotation_trajectory_combo.blockSignals(True)
        try:
            self.annotation_trajectory_combo.clear()
            self.annotation_trajectory_combo.addItem("不关联轨迹", None)
            self._video_trajectory_candidates = {}
            timeline = self.window.sync._annotationTimeline()
            if timeline is not None:
                candidates = trajectory_candidates(
                    self.window.video_analysis._activeVideoTrajectories(),
                    self.video_annotation_project.camera_channel,
                    annotation.start_sample / timeline.sampling_rate,
                    self.annotation_trajectory_tolerance_spin_box.value(),
                )
                for candidate in candidates:
                    self._video_trajectory_candidates[candidate.identifier] = candidate
                    self.annotation_trajectory_combo.addItem(
                        f"轨迹 #{candidate.identifier} · {candidate.direction} · "
                        f"可信 {candidate.confidence:.0%} · Δ {candidate.residual_ms:+.1f} ms",
                        candidate.identifier,
                    )
            if annotation.trajectory_identifier is not None:
                index = self.annotation_trajectory_combo.findData(annotation.trajectory_identifier)
                if index < 0:
                    self.annotation_trajectory_combo.addItem(
                        f"轨迹 #{annotation.trajectory_identifier}（已关联，当前不在候选窗）",
                        annotation.trajectory_identifier,
                    )
                    index = self.annotation_trajectory_combo.count() - 1
                self.annotation_trajectory_combo.setCurrentIndex(index)
            else:
                self.annotation_trajectory_combo.setCurrentIndex(0)
        finally:
            self.annotation_trajectory_combo.blockSignals(False)

    def _currentVideoPosition(self):
        if self.window.playback.backend == "ffmpeg":
            return self.window.playback.position_ms
        return (
            self.window.playback.qt_player.position()
            if self.window.playback.qt_player is not None
            else self.window.playback.position_slider.value()
        )

    def _annotationVideoPosition(self, annotation, timeline):
        if self.video_annotation_project.sync.video_start_time is None:
            return None
        if annotation.source_domain == "video":
            return annotation.start_video_ms
        if timeline is None:
            return None
        sync = self.video_annotation_project.sync
        elapsed = (timeline.absolute_time_for_sample(annotation.start_sample) - sync.video_start_time).total_seconds()
        position = int(round((elapsed - sync.manual_offset_seconds) / sync.rate * 1000))
        maximum = self.window.playback.position_slider.maximum()
        return position if 0 <= position <= maximum else None

    def _reflectAnnotationVehicleLabels(self, annotation):
        self.annotation_vehicle_combo.setCurrentIndex(self.annotation_vehicle_combo.findText(annotation.vehicle_type))
        self.annotation_lane_combo.setCurrentIndex(self.annotation_lane_combo.findData(annotation.lane))
        self.annotation_direction_combo.setEditText(annotation.travel_direction)

    def _setAnnotationVehicleLabels(self, annotation, vehicle_type=None, lane=None, direction=None):
        if vehicle_type is None:
            vehicle_type = self.annotation_vehicle_combo.currentText()
            lane = self.annotation_lane_combo.currentData()
            direction = self.annotation_direction_combo.currentText()
        annotation.set_vehicle_labels(vehicle_type, lane, direction or "")
        direction = annotation.travel_direction
        if direction and direction not in self.video_annotation_project.direction_labels:
            self.video_annotation_project.direction_labels.append(direction)
        if direction and self.annotation_direction_combo.findText(direction) < 0:
            self.annotation_direction_combo.addItem(direction)

    @staticmethod
    def _annotationDisplayLabel(annotation):
        parts = [
            f"#{annotation.identifier}",
            annotation.vehicle_type or annotation.kind,
        ]
        if annotation.lane is not None:
            parts.append(f"{annotation.lane}车道")
        if annotation.travel_direction:
            parts.append(annotation.travel_direction)
        return " · ".join(parts)

    def _pauseForAnnotationDrawing(self):
        if self.window.playback.backend == "ffmpeg":
            self.window.playback.playing = False
            self.window.playback._stopFfmpegVideoWorker()
            self.window.playback.play_button.setText("播放")
        elif self.window.playback.qt_player is not None:
            self.window.playback.qt_player.pause()

    def _showAnnotationMessage(self, message):
        self.annotation_draw_hint.setText(message)
        self.window.statusBar().showMessage(message, 8000)

    def _setAnnotationDrawingTool(self, kind):
        if self.window.sync._annotationTimeline() is None and kind:
            printError("请先导入与标注工程匹配的 DAS 数据")
            return
        self.window.sync._finishVideoSyncPick()
        self._cancelPendingIntervalAnnotation()
        if kind:
            self.window.video_plot.video_annotations_visible_checkbox.setChecked(True)
        self.annotation_canvas.set_mode(kind)

    def _finishAnnotationShape(self):
        canvas = self.annotation_canvas
        if canvas._edit_id is not None:
            canvas.commit_edit()
        elif canvas._ann_type.value in ("kp", "lin"):
            canvas._finalise_multipoint()
        else:
            self._showAnnotationMessage("框标注需要在图内点击完成：事件框两点，倾斜框三点")

    def _annotationCanvasStateChanged(self, kind):
        for key, button in self.annotation_shape_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == kind)
            button.blockSignals(False)
        for key, button in self.annotation_plot_tool_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == kind)
            button.blockSignals(False)
        if kind:
            self._pauseForAnnotationDrawing()
        else:
            self.annotation_draw_hint.setText("浏览模式：选择标注或右键编辑；B 框 / R 倾斜框 / K 点 / L 轨迹")
        for line in (self.window.video_plot.video_playhead_line, self.window.sync.video_camera_line):
            if line is not None:
                line.setMovable(not bool(kind))
        self.window.sync._updateVideoControlEnabledState()

    def _geometryVerticesFromPlot(self, points):
        timeline = self.window.sync._annotationTimeline()
        if timeline is None:
            raise ValueError("DAS 数据上下文已失效")
        channel_from, channel_to = self.window.sync._videoChannelBounds()
        origin = getattr(self.window.video_plot, "_video_plot_channel_from", channel_from)
        duration = timeline.total_samples / timeline.sampling_rate
        if any(
            not np.isfinite(p).all()
            or p[0] < -1e-6
            or p[0] > duration + 1e-6
            or p[1] < -1e-6
            or p[1] > channel_to - channel_from + 1 + 1e-6
            for p in points
        ):
            raise ValueError("标注超出 DAS 数据范围，请在图内重新绘制")
        return [
            [
                min(
                    timeline.total_samples,
                    max(0, int(round(p[0] * timeline.sampling_rate))),
                ),
                float(np.clip(p[1] + origin - 0.5, channel_from, channel_to)),
            ]
            for p in points
        ]

    def _addDasGeometryAnnotation(self, kind, points):
        try:
            vertices = self._geometryVerticesFromPlot(points)
            self._pushAnnotationUndo()
            annotation = self.video_annotation_project.add_geometry_annotation(
                self.window.sync._annotationTimeline(),
                kind,
                vertices,
                self.annotation_kind_combo.currentText(),
                self.annotation_outcome_combo.currentText(),
                self.annotation_note_edit.text(),
                self.window.video_analysis.video_trajectory_dx_spin_box.value(),
            )
            self._setAnnotationVehicleLabels(annotation)
        except (ValueError, TypeError) as error:
            printError(str(error))
            return
        self.video_annotation_selected_id = annotation.identifier
        self.window.sync._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable(annotation.identifier)
        self.window.video_plot.plotVideoComparisonImage(preserve_view=True)
        self._showAnnotationMessage(f"已保存 {annotation.shape_label} #{annotation.identifier}；右键可编辑属性或形状")

    def _updateDasGeometryAnnotation(self, identifier, kind, points):
        if identifier < 0:
            self.window.video_ui.trajectory_prescreen.update_geometry(-identifier, points)
            return
        annotation = self.video_annotation_project.annotation_by_identifier(identifier)
        if annotation is None:
            return
        try:
            vertices = self._geometryVerticesFromPlot(points)
            self._pushAnnotationUndo()
            annotation.set_geometry(kind, vertices)
        except (ValueError, TypeError) as error:
            printError(str(error))
            return
        self.window.sync._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable(identifier)
        self.window.video_plot.plotVideoComparisonImage(preserve_view=True)
        self._showAnnotationMessage(f"标注 #{identifier} 的形状已更新")

    def _selectAnnotationFromPlot(self, identifier):
        if identifier < 0:
            self.window.video_ui.trajectory_prescreen.show()
            self.window.video_ui.trajectory_prescreen.select(-identifier)
            self.window.video_ui.trajectory_prescreen.refresh()
            return
        for row in range(self.annotation_table.rowCount()):
            if self.annotation_table.item(row, 1).data(Qt.UserRole) == identifier:
                self.annotation_table.selectRow(row)
                self.annotation_table.scrollToItem(self.annotation_table.item(row, 1))
                break

    def _centerOnDasAnnotation(self, annotation):
        timeline = self.window.sync._annotationTimeline()
        if timeline is None:
            return
        vb = self.window.video_plot.video_das_plot_widget.getViewBox()
        xmin, xmax = vb.viewRange()[0]
        start = annotation.start_sample / timeline.sampling_rate
        end = (annotation.end_sample or annotation.start_sample) / timeline.sampling_rate
        if start < xmin or end > xmax:
            width = max(xmax - xmin, (end - start) * 1.2, 1 / timeline.sampling_rate)
            left = max(0, (start + end - width) / 2)
            vb.setXRange(left, left + width, padding=0)
        if self.window.video_files.video_sequence_data_group is not None:
            key = self.window.video_analysis._videoTrajectoryKeyForPosition(
                self._annotationVideoPosition(annotation, timeline) or 0
            )
            # Fetch the selected DAS sample directly even when it is outside the video.
            if key is not None:
                count = key[1] - key[0]
                left = max(
                    0,
                    min(
                        annotation.start_sample - count // 4,
                        timeline.total_samples - count,
                    ),
                )
                self.window.video_analysis._queueVideoTrajectoryWindow((left, left + count, key[2], key[3]), priority=0)
                self.window.video_analysis._startNextVideoTrajectoryWork()

    def _editAnnotationProperties(self, identifier):
        if identifier < 0:
            self.window.video_ui.trajectory_prescreen.accept([-identifier])
            return
        annotation = self.video_annotation_project.annotation_by_identifier(identifier)
        if annotation is None:
            return
        self._pauseForAnnotationDrawing()
        dialog = QDialog(self.window)
        dialog.setWindowTitle(f"编辑标注 #{identifier} · {annotation.shape_label}")
        form = QFormLayout(dialog)
        vehicle = ComboBox()
        vehicle.addItems(list(VEHICLE_TYPES))
        vehicle.setCurrentIndex(vehicle.findText(annotation.vehicle_type))
        lane = ComboBox()
        for number in range(1, 6):
            lane.addItem(str(number), number)
        lane.setCurrentIndex(lane.findData(annotation.lane))
        direction = ComboBox()
        direction.setEditable(True)
        direction.addItems(self.video_annotation_project.direction_labels)
        direction.setEditText(annotation.travel_direction)
        direction.lineEdit().setPlaceholderText("输入自定义方向")
        kind = ComboBox()
        kind.setEditable(True)
        kind.addItems([self.annotation_kind_combo.itemText(i) for i in range(self.annotation_kind_combo.count())])
        kind.setCurrentText(annotation.kind)
        outcome = ComboBox()
        outcome.addItems(
            [self.annotation_outcome_combo.itemText(i) for i in range(self.annotation_outcome_combo.count())]
        )
        outcome.setCurrentText(annotation.outcome)
        note = LineEdit()
        note.setText(annotation.note)
        form.addRow("车辆", vehicle)
        form.addRow("车道", lane)
        form.addRow("行驶方向", direction)
        form.addRow("事件类型", kind)
        form.addRow("结论", outcome)
        form.addRow("备注", note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec_() != QDialog.Accepted:
            return
        self._pushAnnotationUndo()
        annotation.kind = kind.currentText().strip() or annotation.kind
        annotation.outcome = outcome.currentText()
        annotation.note = note.text().strip()
        self._setAnnotationVehicleLabels(
            annotation,
            vehicle.currentText(),
            lane.currentData(),
            direction.currentText(),
        )
        self.video_annotation_selected_id = identifier
        self.annotation_kind_combo.setCurrentText(annotation.kind)
        self.annotation_outcome_combo.setCurrentText(annotation.outcome)
        self.annotation_note_edit.setText(annotation.note)
        self._reflectAnnotationVehicleLabels(annotation)
        self.window.sync._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable(identifier)
        self.window.video_plot.plotVideoComparisonImage(preserve_view=True)

    def _deleteAnnotationFromPlot(self, identifier):
        if identifier < 0:
            self.window.video_ui.trajectory_prescreen.remove(-identifier)
            return
        self.video_annotation_selected_id = identifier
        self.deleteSelectedVideoAnnotation()

    def _annotationTableContextMenu(self, position):
        row = self.annotation_table.rowAt(position.y())
        if row < 0:
            return
        identifier = self.annotation_table.item(row, 1).data(Qt.UserRole)
        self.annotation_table.selectRow(row)
        annotation = self.video_annotation_project.annotation_by_identifier(identifier)
        menu = QMenu(self.annotation_table)
        edit = menu.addAction("编辑属性")
        shape = menu.addAction("编辑形状")
        shape.setEnabled(bool(annotation and annotation.geometry_type))
        delete = menu.addAction("删除标注")
        action = menu.exec_(self.annotation_table.viewport().mapToGlobal(position))
        if action == edit:
            self._editAnnotationProperties(identifier)
        elif action == shape:
            self.annotation_canvas.start_edit(identifier)
        elif action == delete:
            self._deleteAnnotationFromPlot(identifier)

    def _clearAnnotationHistory(self):
        if hasattr(self.window.video_ui, "trajectory_prescreen"):
            self.window.video_ui.trajectory_prescreen.invalidate()
        if self.annotation_canvas is not None:
            self.annotation_canvas.cancel()
        self._annotation_undo_stack.clear()
        self._annotation_redo_stack.clear()

    def _pushAnnotationUndo(self):
        snapshot = [copy.deepcopy(item.to_dict()) for item in self.video_annotation_project.annotations]
        self._annotation_undo_stack.append(snapshot)
        del self._annotation_undo_stack[:-30]
        self._annotation_redo_stack.clear()

    def _restoreAnnotationSnapshot(self, snapshot):
        self.annotation_canvas.cancel()
        self.video_annotation_project.annotations = [VideoAnnotation.from_dict(item) for item in snapshot]
        timeline = self.window.sync._annotationTimeline()
        if timeline is not None:
            self.video_annotation_project.reproject_video_annotations(timeline)
        self.video_annotation_selected_id = None
        self.window.sync._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable()
        self.window.video_plot.plotVideoComparisonImage(preserve_view=True)

    def redoVideoAnnotation(self):
        if not self._annotation_redo_stack:
            return
        self._annotation_undo_stack.append(
            [copy.deepcopy(a.to_dict()) for a in self.video_annotation_project.annotations]
        )
        self._restoreAnnotationSnapshot(self._annotation_redo_stack.pop())

    def _addVideoAnnotation(self, start_ms: int, end_ms=None):
        timeline = self.window.sync._annotationTimeline()
        if timeline is None:
            printError("请先导入与标注工程匹配的 DAS 数据")
            return None
        try:
            self._pushAnnotationUndo()
            annotation = self.video_annotation_project.add_video_annotation(
                timeline,
                self.annotation_kind_combo.currentText(),
                self.annotation_outcome_combo.currentText(),
                start_ms,
                self.video_annotation_project.camera_channel,
                end_video_ms=end_ms,
                note=self.annotation_note_edit.text(),
            )
            self._setAnnotationVehicleLabels(annotation)
        except ValueError as error:
            printError(str(error))
            return None
        self.video_annotation_selected_id = annotation.identifier
        self.window.sync._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable(select_identifier=annotation.identifier)
        self._refreshAnnotationTrajectoryChoices(annotation)
        self.window.video_plot.plotVideoComparisonImage(preserve_view=True)
        self.window.statusBar().showMessage(
            f"已添加标注 #{annotation.identifier}：{annotation.kind}。可在左侧关联候选轨迹。",
            6000,
        )
        return annotation

    def _cancelPendingIntervalAnnotation(self):
        """清除正在进行的区间标注状态（上下文变化或用户取消时调用）"""
        if self.annotation_canvas is not None:
            self.annotation_canvas.cancel()
        if self.video_annotation_interval_start_ms is not None:
            self.video_annotation_interval_start_ms = None
            if hasattr(self, "annotation_interval_label"):
                self.annotation_interval_label.setText("未开始区间标注")
            if hasattr(self, "annotation_interval_finish_button"):
                self.window.sync._updateVideoControlEnabledState()

    def addVideoPointAnnotation(self):
        self.annotation_canvas.cancel()
        self._addVideoAnnotation(self._currentVideoPosition())

    def beginVideoIntervalAnnotation(self):
        self.annotation_canvas.cancel()
        if self.window.sync._annotationTimeline() is None:
            printError("请先完成视频与 DAS 的对时")
            return
        self.video_annotation_interval_start_ms = self._currentVideoPosition()
        self.annotation_interval_label.setText(
            f"区间起点：{format_video_position(self.video_annotation_interval_start_ms)}"
        )
        self.window.sync._updateVideoControlEnabledState()

    def finishVideoIntervalAnnotation(self):
        if self.video_annotation_interval_start_ms is None:
            return
        # 验证上下文仍然有效
        if self.window.sync._annotationTimeline() is None:
            printError("DAS 数据上下文已失效，区间标注已取消")
            self._cancelPendingIntervalAnnotation()
            return
        start = self.video_annotation_interval_start_ms
        end = self._currentVideoPosition()
        annotation = self._addVideoAnnotation(start, end)
        if annotation is not None:
            self.video_annotation_interval_start_ms = None
            self.annotation_interval_label.setText("未开始区间标注")
            self.window.sync._updateVideoControlEnabledState()

    def updateSelectedVideoAnnotation(self):
        annotation = self.video_annotation_project.annotation_by_identifier(self.video_annotation_selected_id)
        if annotation is None:
            printError("请先在标注列表中选择一条记录")
            return
        self._pushAnnotationUndo()
        annotation.kind = self.annotation_kind_combo.currentText().strip() or annotation.kind
        annotation.outcome = self.annotation_outcome_combo.currentText().strip() or annotation.outcome
        annotation.note = self.annotation_note_edit.text().strip()
        self._setAnnotationVehicleLabels(annotation)
        selected_trajectory = self.annotation_trajectory_combo.currentData()
        try:
            selected_trajectory = int(selected_trajectory) if selected_trajectory is not None else None
        except (TypeError, ValueError):
            selected_trajectory = None
        annotation.trajectory_identifier = selected_trajectory
        annotation.time_residual_ms = None
        if selected_trajectory is not None:
            trajectory = next(
                (
                    item
                    for item in self.window.video_analysis._activeVideoTrajectories()
                    if item.identifier == selected_trajectory
                ),
                None,
            )
            crossing = (
                trajectory_crossing_time(trajectory, self.video_annotation_project.camera_channel)
                if trajectory
                else None
            )
            if crossing is not None:
                timeline = self.window.sync._annotationTimeline()
                sampling_rate = timeline.sampling_rate if timeline is not None else self.window.data.sampling_rate
                annotation.time_residual_ms = (crossing - annotation.start_sample / sampling_rate) * 1000.0
        self.window.sync._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable(select_identifier=annotation.identifier)
        self.window.video_plot.plotVideoComparisonImage(preserve_view=True)

    def deleteSelectedVideoAnnotation(self):
        if self.video_annotation_selected_id is None:
            return
        self.annotation_canvas.cancel()
        self._pushAnnotationUndo()
        removed = self.video_annotation_project.delete_annotation(self.video_annotation_selected_id)
        if removed is None:
            return
        self.video_annotation_selected_id = None
        self.window.sync._markVideoAnnotationDirty()
        self.refreshVideoAnnotationTable()
        self.window.video_plot.plotVideoComparisonImage(preserve_view=True)
        self.window.statusBar().showMessage(f"已删除标注 #{removed.identifier}。", 5000)

    def undoLastVideoAnnotation(self):
        if not self._annotation_undo_stack:
            return
        self._annotation_redo_stack.append(
            [copy.deepcopy(a.to_dict()) for a in self.video_annotation_project.annotations]
        )
        self._restoreAnnotationSnapshot(self._annotation_undo_stack.pop())
        self.window.statusBar().showMessage("已撤销上一次标注修改。", 5000)

    def _drawVideoAnnotations(self):
        if not self.window.video_plot.video_annotations_visible_checkbox.isChecked():
            return
        timeline = self.window.sync._annotationTimeline()
        if timeline is None:
            return
        sampling_rate = float(timeline.sampling_rate)
        duration = timeline.total_samples / sampling_rate
        channel_from, channel_to = self.window.sync._videoChannelBounds()
        palette = {
            "确认匹配": ("#13734a", (230, 247, 239, 76), "t"),
            "DAS未检测到": ("#b42318", (254, 243, 242, 76), "x"),
            "疑似误检": ("#b42318", (254, 243, 242, 76), "x"),
            "拒绝": ("#b42318", (254, 243, 242, 76), "x"),
            "不确定": ("#9a5b00", (255, 243, 214, 76), "o"),
        }
        for index, annotation in enumerate(self.video_annotation_project.annotations):
            if not annotation.visible:
                continue
            if annotation.geometry_type:
                plot_origin = getattr(self.window.video_plot, "_video_plot_channel_from", channel_from)
                points = [[p[0] / sampling_rate, p[1] - plot_origin + 0.5] for p in annotation.vertices]
                measurement = annotation.track_measurement(sampling_rate)
                speed_label = f" · {abs(measurement[0]):.1f} km/h" if measurement else ""
                self.annotation_canvas.render_shape(
                    annotation.identifier,
                    annotation.geometry_type,
                    points,
                    f"{self._annotationDisplayLabel(annotation)}{speed_label}",
                    annotation.identifier == self.video_annotation_selected_id,
                    f"{annotation.shape_label} #{annotation.identifier}：{annotation.kind}\n"
                    f"{annotation.outcome}\n{annotation.note}\n右键可编辑属性、形状或删除",
                )
                continue
            color, brush_color, symbol = palette.get(
                annotation.outcome,
                ("#2563eb", (234, 241, 255, 72), "o"),
            )
            start_seconds = annotation.start_sample / sampling_rate
            selected = annotation.identifier == self.video_annotation_selected_id
            width = 4 if selected else 2
            label_text = self._annotationDisplayLabel(annotation)
            if annotation.is_interval:
                end_seconds = annotation.end_sample / sampling_rate
                region = pg.LinearRegionItem(
                    values=(start_seconds, end_seconds),
                    orientation=pg.LinearRegionItem.Vertical,
                    movable=False,
                    brush=pg.mkBrush(*brush_color),
                    hoverBrush=pg.mkBrush(*brush_color),
                    bounds=(0.0, duration),
                )
                region.setZValue(34)
                for line in region.lines:
                    line.setPen(pg.mkPen(color, width=width))
                pg.InfLineLabel(
                    region.lines[0],
                    text=label_text,
                    position=0.12 + (index % 5) * 0.13,
                    color=color,
                    fill=pg.mkBrush(255, 255, 255, 215),
                    movable=False,
                )
                self.window.video_plot.video_das_plot_widget.addItem(region)
                self._video_annotation_items.append(region)
            else:
                line = pg.InfiniteLine(
                    pos=start_seconds,
                    angle=90,
                    movable=False,
                    pen=pg.mkPen(color, width=width),
                    hoverPen=pg.mkPen(color, width=width + 1),
                )
                line.setZValue(34)
                line.setToolTip(
                    f"标注 #{annotation.identifier}：{annotation.kind}；"
                    f"{format_video_position(annotation.start_video_ms)}"
                )
                pg.InfLineLabel(
                    line,
                    text=label_text,
                    position=0.12 + (index % 5) * 0.13,
                    color=color,
                    fill=pg.mkBrush(255, 255, 255, 215),
                    movable=False,
                )
                self.window.video_plot.video_das_plot_widget.addItem(line)
                self._video_annotation_items.append(line)
            if channel_from <= annotation.camera_channel <= channel_to:
                plot_origin = getattr(self.window.video_plot, "_video_plot_channel_from", channel_from)
                marker = pg.ScatterPlotItem(
                    [start_seconds],
                    [annotation.camera_channel - plot_origin + 0.5],
                    size=11 if selected else 9,
                    pen=pg.mkPen("#ffffff", width=1),
                    brush=pg.mkBrush(color),
                    symbol=symbol,
                )
                marker.setZValue(36)
                self.window.video_plot.video_das_plot_widget.addItem(marker)
                self._video_annotation_items.append(marker)
            if self.annotation_canvas is not None:
                yrange = self.window.video_plot.video_das_plot_widget.getViewBox().viewRange()[1]
                if annotation.is_interval:
                    points = [
                        [start_seconds, yrange[0]],
                        [annotation.end_sample / sampling_rate, yrange[0]],
                        [annotation.end_sample / sampling_rate, yrange[1]],
                        [start_seconds, yrange[1]],
                    ]
                    kind = "interval"
                else:
                    points = [[start_seconds, yrange[0]], [start_seconds, yrange[1]]]
                    kind = "point"
                self.annotation_canvas._ann_geoms[annotation.identifier] = (
                    kind,
                    points,
                )
