"""Video display filtering and background windowed vehicle analysis."""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox

from core.filter.algorithms import ALGORITHM_LABELS
from ui.filter_panel import DASFilterDialog
from core.filter.filter_history import (
    add_recent_history,
    history_entry_steps,
    make_history_entry,
    upsert_named_history,
)
from core.filter.filter_pipeline import clone_steps
from core.video.trajectory import (
    VideoTrajectoryWindow,
    analyze_group_window,
    read_group_window,
    required_window_seconds,
)
from ui.components.window_feature import WindowFeature
from ui.tabs.video_constants import (
    VIDEO_DISPLAY_WINDOW_SECONDS,
    VIDEO_FILTER_PREVIEW_MAX_VALUES,
    VIDEO_TRAJECTORY_PREFETCH_SECONDS,
    VIDEO_TRAJECTORY_REQUESTED_WINDOW_SECONDS,
)
from utils.function import printError


class VideoAnalysisController(WindowFeature):
    """Video display filtering and background windowed vehicle analysis."""

    def __init__(self, window):
        super().__init__(window)
        self.video_filter_dialog = None
        self._video_filter_settings = None
        self._video_filter_steps = []
        self._video_filter_customized = False
        self.video_trajectory_parameters = None
        self.video_trajectory_window_seconds = None
        self.video_trajectory_windows = {}
        self.video_trajectory_pending = []
        self.video_trajectory_future: Future | None = None
        self.video_trajectory_current_window = None
        self.video_trajectory_generation = 0
        self.video_trajectory_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="das-video-trajectory")
        self.video_trajectory_poll_timer = QTimer(self)
        self.video_trajectory_poll_timer.setInterval(100)
        self.video_trajectory_poll_timer.timeout.connect(self._pollVideoTrajectoryWork)

    def shutdown(self):
        """Release the window-analysis timer and pending executor tasks."""
        self.video_trajectory_poll_timer.stop()
        self.video_trajectory_executor.shutdown(wait=False, cancel_futures=True)

    def _ensureDefaultVideoFilterPipeline(self, channel_count: int, sample_count: int):
        if self._video_filter_customized:
            return
        self._video_filter_steps = self.window.filtering._defaultEventFilterPipeline(channel_count, sample_count)
        self._updateVideoFilterSummary()

    def _videoTrajectoryParameters(self):
        """Return window display settings and optional trajectory geometry."""
        dx = float(self.video_trajectory_dx_spin_box.value())
        parameters = dict(self.window.vehicles._vehicle_tracking_settings or {})
        data_group, _timeline = self.window.sync._videoDataContext()
        data_channel_count = int(data_group.channel_count) if data_group is not None else 0
        detect_trajectories = dx > 0 and data_channel_count >= 8
        display_steps = [
            {
                "algorithm": step.algorithm,
                "parameters": dict(step.parameters),
                "selection": tuple(step.selection),
                "processing_mode": step.processing_mode,
                "label": step.label,
                "enabled": bool(step.enabled),
            }
            for step in self._video_filter_steps
        ]
        display_choice = self.video_display_mode_combo.currentData()
        display_mode = "raw" if display_choice == "raw" else "current"
        parameters.update(
            {
                "channel_spacing": dx if dx > 0 else 4.0,
                "frequency_low": parameters.get("frequency_low", 0.01),
                "frequency_high": parameters.get("frequency_high", 1.0),
                "seed_width": parameters.get("seed_width", 8),
                "peak_prominence": parameters.get("peak_prominence", 1.5),
                "minimum_separation": parameters.get("minimum_separation", 0.8),
                "prominence_window": parameters.get("prominence_window", 12.0),
                "minimum_speed": parameters.get("minimum_speed", 2.0),
                "maximum_speed": parameters.get("maximum_speed", 60.0),
                "tracking_tolerance": parameters.get("tracking_tolerance", 0.15),
                "minimum_coverage": parameters.get("minimum_coverage", 0.55),
                "maximum_missed_channels": parameters.get("maximum_missed_channels", 3),
                "direction": parameters.get("direction", "auto"),
                "polarity": parameters.get("polarity", "auto"),
                "common_mode_method": "median",
                "display_mode": display_mode,
                "display_filter_steps": display_steps,
                "detect_trajectories": detect_trajectories,
            }
        )
        return parameters

    def _videoFilterSummary(self) -> str:
        if self.video_display_mode_combo.currentData() == "raw":
            return "原始去趋势"
        if not self._video_filter_customized:
            return "车辆事件增强"
        enabled = [step for step in self._video_filter_steps if step.enabled]
        if not enabled:
            return "原始去趋势"
        return f"{len(enabled)} 步滤波"

    def _updateVideoFilterSummary(self):
        summary = self._videoFilterSummary()
        labels = [step.label for step in self._video_filter_steps if step.enabled]
        self.video_filter_summary_label.setText(summary)
        if not self._video_filter_customized:
            detail = "带通 0.01–1 Hz → 中位数共模抑制 → MAD 归一化；仅影响显示与轨迹分析"
        else:
            detail = " → ".join(labels) if labels else "当前窗口显示原始去趋势数据"
        self.video_filter_summary_label.setToolTip(detail)

    def _videoVisibleWindowSeconds(self) -> float:
        return float(self.video_window_combo.currentData())

    def _videoDisplayModeChanged(self, _index: int):
        self._updateVideoFilterSummary()
        self._configureVideoTrajectoryAnalysis()

    def _videoVisibleWindowChanged(self, _index: int):
        self.window.sync._updateVideoPlayhead(self.window.annotations._currentVideoPosition(), force=True)

    def _videoDisplayWindowSeconds(self) -> float:
        """Give low-frequency display filters enough signal for two periods."""

        if self.video_display_mode_combo.currentData() == "raw":
            return max(VIDEO_DISPLAY_WINDOW_SECONDS, self._videoVisibleWindowSeconds())
        lows = []
        for step in self._video_filter_steps:
            if not step.enabled:
                continue
            value = step.parameters.get("frequency_low")
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(value) and value > 0:
                lows.append(value)
        return max(
            VIDEO_DISPLAY_WINDOW_SECONDS,
            2.0 / min(lows) if lows else VIDEO_DISPLAY_WINDOW_SECONDS,
        )

    def setVideoFilterPipeline(self, steps):
        """Commit the dedicated, read-only video display filter chain."""

        self._video_filter_steps = clone_steps(steps)
        self._video_filter_customized = True
        self._updateVideoFilterSummary()
        self._configureVideoTrajectoryAnalysis()

    def setVideoFilterSettings(self, settings):
        self._video_filter_settings = dict(settings)

    def showVideoFilterDialog(self):
        """Reuse the 2-D filter editor for the rolling video/DAS display."""

        data_group, timeline = self.window.sync._videoDataContext()
        if data_group is None or timeline is None or self.window.video_files.video_sequence_data_group is None:
            printError("请先选择视频并匹配对应的 DAS 文件")
            return
        current_sample = self.window.annotations.video_annotation_project.sync.sample_for_video_position(
            self.window.annotations._currentVideoPosition(), timeline
        )
        current_sample = 0 if current_sample is None else int(current_sample)
        rate = float(data_group.sampling_rate)
        channel_count = int(data_group.channel_count)
        preview_seconds = min(
            30.0,
            max(5.0, VIDEO_FILTER_PREVIEW_MAX_VALUES / max(1.0, channel_count * rate)),
        )
        preview_count = min(
            data_group.total_samples,
            max(32, int(round(preview_seconds * rate))),
        )
        preview_start = min(
            max(0, current_sample - preview_count // 2),
            max(0, data_group.total_samples - preview_count),
        )
        preview_end = preview_start + preview_count
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.window.statusBar().showMessage("正在读取当前视频位置附近的二维滤波预览…")
        QApplication.processEvents()
        try:
            preview = read_group_window(data_group, preview_start, preview_end, 1, channel_count)
        except Exception as error:
            printError(f"无法读取二维滤波预览：{error}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        preview_steps = clone_steps(self._video_filter_steps)
        for step in preview_steps:
            channel_from, channel_to, _sample_from, _sample_to = step.selection
            step.selection = (
                max(1, min(channel_count, channel_from)),
                max(1, min(channel_count, channel_to)),
                1,
                preview.shape[1],
            )
        visible_range = (1, channel_count, 1, preview.shape[1])
        try:
            if self.video_filter_dialog is None:
                dialog = DASFilterDialog(
                    preview,
                    rate,
                    visible_range,
                    settings=self._video_filter_settings,
                    steps=preview_steps,
                    current_data=preview,
                    segment_ranges=[(0, preview.shape[1])],
                    previous_steps=preview_steps,
                    auto_reapply=False,
                    parent=self.window,
                )
                dialog.setWindowTitle("视频对照 · 二维显示滤波")
                dialog.pipelineChanged.connect(self.setVideoFilterPipeline)
                dialog.settingsChanged.connect(self.setVideoFilterSettings)
                dialog.pipelineConfirmedByUser.connect(self.rememberConfirmedVideoFilterPipeline)
                dialog.savePipelineRequested.connect(self.saveCurrentVideoFilterPipeline)
                dialog.loadPipelineRequested.connect(self.loadSavedVideoFilterPipeline)
                dialog.deletePipelineRequested.connect(self.window.filtering.deleteSavedFilterPipeline)
                dialog.destroyed.connect(lambda: setattr(self, "video_filter_dialog", None))
                dialog.auto_reapply_checkbox.hide()
                dialog.set_saved_pipelines(self.window.filtering._filter_pipeline_history)
                self.video_filter_dialog = dialog
            else:
                self.video_filter_dialog.set_data(
                    preview,
                    rate,
                    visible_range,
                    current_data=preview,
                    steps=preview_steps,
                    segment_ranges=[(0, preview.shape[1])],
                    previous_steps=preview_steps,
                )
            self.video_filter_dialog.status_label.setText(
                "这里编辑的步骤会按顺序应用到每个播放窗口；时间范围自动扩展为整个窗口。"
            )
            self.video_filter_dialog.show()
            self.video_filter_dialog.raise_()
            self.video_filter_dialog.activateWindow()
        except (RuntimeError, ValueError) as error:
            printError(f"无法打开视频二维滤波：{error}")

    def saveCurrentVideoFilterPipeline(self, name: str):
        dialog = self.video_filter_dialog
        if dialog is None:
            return
        try:
            entry = make_history_entry(
                name,
                "named",
                dialog.pipeline_steps(),
                dialog.raw_data.shape,
                dialog.sampling_rate,
            )
            self.window.filtering._filter_pipeline_history = upsert_named_history(
                self.window.filtering._filter_pipeline_history, entry
            )
        except ValueError as error:
            QMessageBox.warning(self.window, "无法保存滤波方案", str(error))
            return
        self.window.filtering._persistFilterPipelineHistory()
        self.window.statusBar().showMessage(f"已保存视频显示滤波方案“{name}”。", 6000)

    def rememberConfirmedVideoFilterPipeline(self, steps):
        dialog = self.video_filter_dialog
        if dialog is None or not steps:
            return
        name = datetime.now().strftime("最近使用 %m-%d %H:%M:%S")
        try:
            entry = make_history_entry(
                name,
                "recent",
                steps,
                dialog.raw_data.shape,
                dialog.sampling_rate,
            )
            self.window.filtering._filter_pipeline_history = add_recent_history(
                self.window.filtering._filter_pipeline_history, entry
            )
        except ValueError as error:
            self.window.statusBar().showMessage(f"视频滤波链历史未保存：{error}", 8000)
            return
        self.window.filtering._persistFilterPipelineHistory()

    def loadSavedVideoFilterPipeline(self, identifier: str):
        dialog = self.video_filter_dialog
        entry = self.window.filtering._historyEntry(identifier)
        if dialog is None or entry is None:
            return
        try:
            steps = history_entry_steps(entry)
            old_channels, _old_samples = map(int, entry.get("source_shape"))
            new_channels, new_samples = map(int, dialog.raw_data.shape)
            adapted = []
            for step in steps:
                channel_from, channel_to, _sample_from, _sample_to = step.selection
                if channel_from == 1 and channel_to == old_channels:
                    channel_to = new_channels
                if channel_from < 1 or channel_to > new_channels:
                    raise ValueError(
                        f"步骤“{step.label}”的通道范围 {channel_from}-{channel_to} 超出当前视频 DAS 的 1-{new_channels}"
                    )
                clone = step.clone(new_identifier=True)
                clone.selection = (channel_from, channel_to, 1, new_samples)
                adapted.append(clone)
        except (TypeError, ValueError) as error:
            QMessageBox.warning(self.window, "滤波方案与视频 DAS 不兼容", str(error))
            return
        dialog.set_draft_pipeline(
            adapted,
            f"已载入保存方案“{entry.get('name', '')}”",
            new_identifiers=False,
        )

    def _configureVideoTrajectoryAnalysis(self):
        """Validate calibration and reset only derived local-window cache."""
        self.video_trajectory_parameters = self._videoTrajectoryParameters()
        self.video_trajectory_windows.clear()
        self.video_trajectory_pending.clear()
        self.video_trajectory_current_window = None
        self.video_trajectory_generation += 1
        parameters = self.video_trajectory_parameters
        detection_enabled = bool(parameters.get("detect_trajectories"))
        try:
            display_window = self._videoDisplayWindowSeconds()
            if detection_enabled:
                self.video_trajectory_window_seconds = max(
                    display_window,
                    required_window_seconds(parameters, VIDEO_TRAJECTORY_REQUESTED_WINDOW_SECONDS),
                )
            else:
                self.video_trajectory_window_seconds = display_window
        except ValueError as error:
            self.video_trajectory_window_seconds = None
            self.video_trajectory_status_label.setText(f"轨迹：参数无效：{error}")
            return
        filter_note = self._videoFilterSummary()
        if detection_enabled:
            tracking_note = "轨迹检测已启用"
        else:
            tracking_note = "填写 dx 且 DAS 至少包含 8 个通道后启用轨迹检测"
        self.video_trajectory_status_label.setText(
            f"显示：{filter_note}；{tracking_note}；连续滚动窗口 "
            f"{self._videoVisibleWindowSeconds():.0f} s，后台提前预读。"
        )
        self.window.video_plot.plotVideoComparisonImage()
        self._requestVideoTrajectoryForPosition(self.window.annotations._currentVideoPosition())

    def _videoTrajectoryKeyForPosition(self, position_ms):
        data_group, timeline = self.window.sync._videoDataContext()
        parameters = self.video_trajectory_parameters
        if (
            data_group is None
            or timeline is None
            or parameters is None
            or self.video_trajectory_window_seconds is None
            or self.window.video_files.video_sequence_data_group is None
        ):
            return None
        camera_start = 1
        camera_end = int(data_group.channel_count)
        sample = self.window.annotations.video_annotation_project.sync.sample_for_video_position(position_ms, timeline)
        if sample is None:
            return None
        sample = min(max(0, int(sample)), max(0, data_group.total_samples - 1))
        count = min(
            data_group.total_samples,
            max(
                32,
                int(round(self.video_trajectory_window_seconds * data_group.sampling_rate)),
            ),
        )
        stride = max(1, count // 2)
        start = (sample // stride) * stride
        start = min(max(0, start), max(0, data_group.total_samples - count))
        return start, start + count, camera_start, camera_end

    def _requestVideoTrajectoryForPosition(self, position_ms):
        """Queue the visible analysis window followed by one look-ahead window."""
        key = self._videoTrajectoryKeyForPosition(position_ms)
        if key is None:
            return
        self._queueVideoTrajectoryWindow(key, priority=0)
        _group, timeline = self.window.sync._videoDataContext()
        look_ahead = max(
            VIDEO_TRAJECTORY_PREFETCH_SECONDS,
            self._videoVisibleWindowSeconds() * 0.5,
        )
        next_position = int(position_ms + look_ahead * 1000)
        if timeline is not None:
            self._queueVideoTrajectoryWindow(self._videoTrajectoryKeyForPosition(next_position), priority=1)
        self._startNextVideoTrajectoryWork()

    def _queueVideoTrajectoryWindow(self, key, priority):
        if key is None or key in self.video_trajectory_windows:
            return
        if (
            self.video_trajectory_future is not None
            and getattr(self.video_trajectory_future, "_das_video_key", None) == key
        ):
            return
        if any(item[1] == key for item in self.video_trajectory_pending):
            return
        self.video_trajectory_pending.append((int(priority), key))
        self.video_trajectory_pending.sort(key=lambda item: item[0])
        del self.video_trajectory_pending[4:]

    def _startNextVideoTrajectoryWork(self):
        if self.video_trajectory_future is not None or not self.video_trajectory_pending:
            return
        data_group, _timeline = self.window.sync._videoDataContext()
        if data_group is None or self.video_trajectory_parameters is None:
            self.video_trajectory_pending.clear()
            return
        _priority, key = self.video_trajectory_pending.pop(0)
        start, end, channel_start, channel_end = key
        worker_parameters = dict(self.video_trajectory_parameters)
        worker_parameters["window_channel_from"] = channel_start
        future = self.video_trajectory_executor.submit(
            analyze_group_window,
            data_group,
            start,
            end,
            channel_start,
            channel_end,
            worker_parameters,
        )
        future._das_video_key = key
        future._das_video_generation = self.video_trajectory_generation
        self.video_trajectory_future = future
        mode_text = self._videoFilterSummary()
        self.video_trajectory_status_label.setText(
            f"显示：正在后台预读“{mode_text}”窗口 "
            f"{start / data_group.sampling_rate:.1f}–{end / data_group.sampling_rate:.1f} s；"
            "播放与滚动不会等待到窗口末端再加载。"
        )
        self.video_trajectory_poll_timer.start()

    def _pollVideoTrajectoryWork(self):
        future = self.video_trajectory_future
        if future is None or not future.done():
            return
        self.video_trajectory_future = None
        key = future._das_video_key
        if getattr(future, "_das_video_generation", -1) != self.video_trajectory_generation:
            self._startNextVideoTrajectoryWork()
            return
        try:
            window: VideoTrajectoryWindow = future.result()
            for index, trajectory in enumerate(window.trajectories, start=1):
                # Window-local picker IDs must not collide after annotations are saved.
                trajectory.identifier = int(window.start_sample + index)
            self.video_trajectory_windows[key] = window
            while len(self.video_trajectory_windows) > 3:
                self.video_trajectory_windows.pop(next(iter(self.video_trajectory_windows)))
            self.video_trajectory_current_window = window
            mode_text = self._videoFilterSummary()
            detection_enabled = bool(self.video_trajectory_parameters.get("detect_trajectories"))
            candidate_text = f"{len(window.trajectories)} 条候选" if detection_enabled else "轨迹检测未启用"
            self.video_trajectory_status_label.setText(
                f"显示：{mode_text}窗口 "
                f"{window.start_sample / self.window.video_files.video_sequence_data_group.sampling_rate:.1f}–"
                f"{window.end_sample / self.window.video_files.video_sequence_data_group.sampling_rate:.1f} s；"
                f"{candidate_text}。"
            )
            self.window.video_plot.plotVideoComparisonImage()
            if self.window.annotations.video_annotation_selected_id is not None:
                annotation = self.window.annotations.video_annotation_project.annotation_by_identifier(
                    self.window.annotations.video_annotation_selected_id
                )
                if annotation is not None:
                    self.window.annotations._refreshAnnotationTrajectoryChoices(annotation)
        except Exception as error:
            self.video_trajectory_status_label.setText(f"轨迹：窗口处理失败：{error}；未将其视为无车。")
        self._startNextVideoTrajectoryWork()
        if self.video_trajectory_future is None:
            self.video_trajectory_poll_timer.stop()

    def _activeVideoTrajectories(self):
        if self.video_trajectory_current_window is not None:
            return list(self.video_trajectory_current_window.trajectories)
        return list(self.window.vehicles.vehicle_trajectories)

    def _drawVideoWindowTrajectories(self, plot_widget, window):
        colors = ("#e6194B", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4")
        for index, trajectory in enumerate(window.trajectories):
            channels = np.asarray(trajectory.channels)
            times = np.asarray(trajectory.times)
            visible = (channels >= window.channel_from) & (channels <= window.channel_to)
            if np.count_nonzero(visible) < 2:
                continue
            color = colors[index % len(colors)]
            plot_widget.plot(
                times[visible],
                channels[visible] - window.channel_from + 0.5,
                pen=pg.mkPen(color=color, width=2),
                connect="finite",
            )
