"""Two-dimensional DAS filter preview, application and saved pipelines."""

from datetime import datetime

import numpy as np
from PyQt5.QtWidgets import QMessageBox

from core.filter.algorithms import ALGORITHM_LABELS
from core.filter.filter_history import (
    add_recent_history,
    history_entry_steps,
    make_history_entry,
    normalize_history,
    upsert_named_history,
)
from core.filter.filter_pipeline import FilterStep, clone_steps
from ui.components.window_feature import WindowFeature
from ui.filter_panel import DASFilterDialog
from ui.widgets.custom_widgets import Action, Menu
from utils.function import printError


class FilteringController(WindowFeature):
    """Two-dimensional DAS filter preview, application and saved pipelines."""

    def __init__(self, window):
        super().__init__(window)
        self.das_filter_dialog = None
        self._das_filter_settings = None
        self._das_filter_steps = []
        self._last_das_filter_steps = []
        self._last_das_filter_shape = None
        self.auto_reapply_filter_pipeline = self.window.preferences.auto_reapply_filter()
        stored_filter_history = self.window.preferences.filter_pipeline_history()
        self._filter_pipeline_history = normalize_history(stored_filter_history)
        if stored_filter_history != self._filter_pipeline_history:
            self.window.preferences.set_filter_pipeline_history(self._filter_pipeline_history)

    def createMenu(self):
        self.filter_menu = Menu(self.window.workspace.menu_bar, "滤波", enabled=False)
        self.das_filter_action = Action(
            self.filter_menu,
            "DAS二维滤波与去噪",
            "配置并应用二维滤波链",
            self.showDASFilterDialog,
        )
        self.reset_das_filter_action = Action(
            self.filter_menu,
            "恢复原始数据",
            "恢复导入后去趋势的数据",
            self.resetDASFilterData,
            enabled=False,
        )

    @staticmethod
    def _defaultEventFilterPipeline(channel_count: int, sample_count: int):
        """Return the shared full-resolution vehicle-event filter preset."""

        selection = (1, max(1, int(channel_count)), 1, max(1, int(sample_count)))
        return [
            FilterStep(
                "bandpass",
                {
                    "frequency_low": 0.01,
                    "frequency_high": 1.0,
                    "order": 4,
                    "zero_phase": True,
                },
                selection,
                "带通滤波",
            ),
            FilterStep(
                "common_mode",
                {"method": "median"},
                selection,
                "共模噪声去除",
            ),
            FilterStep(
                "mad_normalize",
                {},
                selection,
                "各通道 MAD 归一化",
            ),
        ]

    def showDASFilterDialog(self):
        """Select the persistent two-dimensional filter panel in the left sidebar."""
        if self.window.data.raw_data is None:
            printError("请先导入 DAS 数据")
            return

        visible_range = (
            self.window.data.channel_from_num,
            self.window.data.channel_to_num,
            self.window.data.sampling_times_from_num,
            self.window.data.sampling_times_to_num,
        )
        if self.das_filter_dialog is not None:
            self.das_filter_dialog.set_visible_range(visible_range)
            self.das_filter_dialog.set_saved_pipelines(self._filter_pipeline_history)
            self.window.workspace.sidebar_tabs.setCurrentWidget(self.filter_sidebar_widget)
            return

        dialog = DASFilterDialog(
            self.window.data.raw_data,
            self.window.data.sampling_rate,
            visible_range=visible_range,
            settings=self._das_filter_settings,
            steps=self._das_filter_steps,
            current_data=self.window.data.origin_data,
            segment_ranges=self.window.data.data_group.segment_ranges if self.window.data.data_group else None,
            previous_steps=self._last_das_filter_steps,
            auto_reapply=self.auto_reapply_filter_pipeline,
            embedded=True,
            parent=self.filter_sidebar_widget,
        )
        self.das_filter_dialog = dialog
        self.filter_sidebar_placeholder.hide()
        self.filter_sidebar_layout.addWidget(dialog)
        dialog.previewReady.connect(self.previewDASFilterData)
        dialog.committed.connect(self.commitDASFilterData)
        dialog.pipelineChanged.connect(self.setDASFilterPipeline)
        dialog.settingsChanged.connect(self.setDASFilterSettings)
        dialog.autoReapplyChanged.connect(self.setAutoReapplyFilter)
        dialog.pipelineConfirmedByUser.connect(self.rememberConfirmedFilterPipeline)
        dialog.savePipelineRequested.connect(self.saveCurrentFilterPipeline)
        dialog.loadPipelineRequested.connect(self.loadSavedFilterPipeline)
        dialog.deletePipelineRequested.connect(self.deleteSavedFilterPipeline)
        dialog.backRequested.connect(
            lambda: self.window.workspace.sidebar_tabs.setCurrentWidget(self.window.data.data_sidebar_widget)
        )
        dialog.set_saved_pipelines(self._filter_pipeline_history)
        if not self._das_filter_steps:
            dialog.set_draft_pipeline(
                self._defaultEventFilterPipeline(*self.window.data.raw_data.shape),
                "已载入默认车辆事件增强滤波链",
                new_identifiers=False,
            )
        dialog.show()
        self.window.workspace.sidebar_tabs.setCurrentWidget(self.filter_sidebar_widget)

    def syncDASFilterDialog(self):
        """Retarget an existing tool window after a successful data switch."""

        if self.das_filter_dialog is None or self.window.data.raw_data is None:
            return
        self._das_filter_settings = self.das_filter_dialog.filter_settings()
        visible_range = (
            self.window.data.channel_from_num,
            self.window.data.channel_to_num,
            self.window.data.sampling_times_from_num,
            self.window.data.sampling_times_to_num,
        )
        self.das_filter_dialog.set_data(
            self.window.data.raw_data,
            self.window.data.sampling_rate,
            visible_range,
            current_data=self.window.data.origin_data,
            steps=self._das_filter_steps,
            segment_ranges=self.window.data.data_group.segment_ranges if self.window.data.data_group else None,
            previous_steps=self._last_das_filter_steps,
        )
        self.das_filter_dialog.setAutoReapply(self.auto_reapply_filter_pipeline)
        replay_started = False
        if self.auto_reapply_filter_pipeline and self._last_das_filter_steps and not self._das_filter_steps:
            try:
                steps = self.adaptPreviousFilterSteps()
            except ValueError as error:
                self.das_filter_dialog.status_label.setText(f"未自动应用最近一次成功滤波链：{error}")
                self.window.statusBar().showMessage(f"未自动应用最近一次成功滤波链：{error}", 12000)
            else:
                replay_started = self.das_filter_dialog.replayExternalPipeline(
                    steps,
                    "切换文件后自动应用最近一次成功滤波链",
                    commit_after=True,
                )
                if replay_started:
                    self.window.statusBar().showMessage("正在从新文件原始数据自动应用最近一次成功滤波链……")
        if not replay_started and not self._das_filter_steps:
            self.das_filter_dialog.set_draft_pipeline(
                self._defaultEventFilterPipeline(*self.window.data.raw_data.shape),
                "已载入默认车辆事件增强滤波链",
                new_identifiers=False,
            )

    def setDASFilterPipeline(self, steps):
        self._das_filter_steps = clone_steps(steps)
        if self._das_filter_steps and self.window.data.raw_data is not None:
            self._last_das_filter_steps = clone_steps(self._das_filter_steps)
            self._last_das_filter_shape = tuple(self.window.data.raw_data.shape)
        self.reset_das_filter_action.setEnabled(bool(self._das_filter_steps))

    def setDASFilterSettings(self, settings):
        self._das_filter_settings = dict(settings)

    def setAutoReapplyFilter(self, enabled: bool):
        """Persist the cross-file filter replay preference."""

        self.auto_reapply_filter_pipeline = bool(enabled)
        self.window.preferences.set_auto_reapply_filter(self.auto_reapply_filter_pipeline)
        if self.das_filter_dialog is not None:
            self.das_filter_dialog.setAutoReapply(self.auto_reapply_filter_pipeline)

    def _persistFilterPipelineHistory(self):
        self._filter_pipeline_history = normalize_history(self._filter_pipeline_history)
        self.window.preferences.set_filter_pipeline_history(self._filter_pipeline_history)
        if self.das_filter_dialog is not None:
            self.das_filter_dialog.set_saved_pipelines(self._filter_pipeline_history)

    def saveCurrentFilterPipeline(self, name: str):
        """Save the visible working chain as a named cross-restart scheme."""

        if self.das_filter_dialog is None or self.window.data.raw_data is None:
            return
        steps = self.das_filter_dialog.pipeline_steps()
        try:
            entry = make_history_entry(
                name,
                "named",
                steps,
                self.window.data.raw_data.shape,
                self.window.data.sampling_rate,
            )
            self._filter_pipeline_history = upsert_named_history(
                self._filter_pipeline_history,
                entry,
            )
        except ValueError as error:
            QMessageBox.warning(self.window, "无法保存滤波方案", str(error))
            return
        self._persistFilterPipelineHistory()
        self.window.statusBar().showMessage(f"已保存滤波方案“{name}”，下次启动仍可载入。", 8000)

    def rememberConfirmedFilterPipeline(self, steps):
        """Store a deduplicated recent entry only after explicit user confirmation."""

        if self.window.data.raw_data is None or not steps:
            return
        name = datetime.now().strftime("最近使用 %m-%d %H:%M:%S")
        try:
            entry = make_history_entry(
                name,
                "recent",
                steps,
                self.window.data.raw_data.shape,
                self.window.data.sampling_rate,
            )
            self._filter_pipeline_history = add_recent_history(
                self._filter_pipeline_history,
                entry,
            )
        except ValueError as error:
            self.window.statusBar().showMessage(f"滤波链历史未保存：{error}", 8000)
            return
        self._persistFilterPipelineHistory()

    def deleteSavedFilterPipeline(self, identifier: str):
        previous_count = len(self._filter_pipeline_history)
        self._filter_pipeline_history = [
            entry for entry in self._filter_pipeline_history if str(entry.get("identifier")) != str(identifier)
        ]
        if len(self._filter_pipeline_history) == previous_count:
            return
        self._persistFilterPipelineHistory()
        self.window.statusBar().showMessage("已删除保存的滤波方案。", 5000)

    def _historyEntry(self, identifier: str):
        return next(
            (entry for entry in self._filter_pipeline_history if str(entry.get("identifier")) == str(identifier)),
            None,
        )

    def loadSavedFilterPipeline(self, identifier: str):
        """Validate and load a saved chain into the editor without processing data."""

        if self.window.data.raw_data is None or self.das_filter_dialog is None:
            return
        entry = self._historyEntry(identifier)
        if entry is None:
            QMessageBox.warning(self.window, "无法载入滤波方案", "找不到所选滤波方案。")
            return
        try:
            steps = history_entry_steps(entry)
            adapted = self.adaptFilterStepsToCurrentData(
                steps,
                entry.get("source_shape"),
            )
            self.validateFilterStepsForCurrentData(adapted)
        except (TypeError, ValueError) as error:
            QMessageBox.warning(self.window, "滤波方案与当前数据不兼容", str(error))
            return
        if self.das_filter_dialog.set_draft_pipeline(
            adapted,
            f"已载入保存方案“{entry.get('name', '')}”",
        ):
            self.window.statusBar().showMessage(
                f"已载入滤波方案“{entry.get('name', '')}”；主图未改变，点击“应用滤波”后统一计算。",
                8000,
            )

    def adaptFilterStepsToCurrentData(self, steps, source_shape):
        """Adapt only source-wide bounds; keep custom ranges strict."""

        if self.window.data.raw_data is None:
            raise ValueError("当前没有可处理的新数据")
        new_channels, new_samples = map(int, self.window.data.raw_data.shape)
        try:
            old_channels, old_samples = map(int, source_shape)
        except (TypeError, ValueError):
            raise ValueError("保存的滤波方案缺少有效的源数据尺寸")
        if min(old_channels, old_samples) <= 0:
            raise ValueError("保存的滤波方案源数据尺寸无效")
        adapted = []
        for step in steps:
            channel_from, channel_to, sample_from, sample_to = step.selection
            if channel_from == 1 and channel_to == old_channels:
                channel_to = new_channels
            elif channel_to > new_channels:
                raise ValueError(
                    f"步骤“{step.label}”的通道范围 {channel_from}-{channel_to} 超出当前数据 1-{new_channels}"
                )
            if sample_from == 1 and sample_to == old_samples:
                sample_to = new_samples
            elif sample_to > new_samples:
                raise ValueError(f"步骤“{step.label}”的采样范围 {sample_from}-{sample_to} 超出当前数据 1-{new_samples}")
            adapted.append(
                FilterStep(
                    algorithm=step.algorithm,
                    parameters=step.parameters,
                    selection=(channel_from, channel_to, sample_from, sample_to),
                    label=step.label,
                    enabled=step.enabled,
                    processing_mode=step.processing_mode,
                )
            )
        return adapted

    def validateFilterStepsForCurrentData(self, steps):
        """Reject incompatible saved frequencies before starting a worker."""

        nyquist = self.window.data.sampling_rate / 2.0
        supported_algorithms = {algorithm for algorithm, _label in ALGORITHM_LABELS}
        for step in steps:
            if step.algorithm not in supported_algorithms:
                raise ValueError(f"步骤“{step.label}”使用了未知滤波算法：{step.algorithm}")
            parameters = step.parameters
            if step.algorithm in {"bandpass", "bandstop"}:
                low = float(parameters.get("frequency_low", 0.0))
                high = float(parameters.get("frequency_high", 0.0))
                if not 0 < low < high < nyquist:
                    raise ValueError(
                        f"步骤“{step.label}”的频率 {low:g}-{high:g} Hz 不适用于当前采样率 {self.window.data.sampling_rate:g} Hz"
                    )
            elif step.algorithm in {"lowpass", "highpass"}:
                frequency = float(parameters.get("frequency", 0.0))
                if not 0 < frequency < nyquist:
                    raise ValueError(
                        f"步骤“{step.label}”的截止频率 {frequency:g} Hz 不适用于当前采样率 {self.window.data.sampling_rate:g} Hz"
                    )
            elif step.algorithm == "fk":
                high = float(parameters.get("fk_frequency_high", 0.0))
                spacing = float(parameters.get("channel_spacing", 0.0))
                if high and not 0 < high < nyquist:
                    raise ValueError(
                        f"步骤“{step.label}”的 F-K 频率上限 {high:g} Hz 不适用于当前采样率 {self.window.data.sampling_rate:g} Hz"
                    )
                if spacing <= 0:
                    raise ValueError(f"步骤“{step.label}”的相邻通道距离 dx 必须大于 0")

    def adaptPreviousFilterSteps(self):
        """Retarget full-data steps and strictly validate custom ranges for new data."""

        if not self._last_das_filter_steps:
            return []
        if self._last_das_filter_shape is None:
            source_shape = self.window.data.raw_data.shape if self.window.data.raw_data is not None else (0, 0)
        else:
            source_shape = self._last_das_filter_shape
        return self.adaptFilterStepsToCurrentData(
            self._last_das_filter_steps,
            source_shape,
        )

    def syncDASFilterVisibleRange(self):
        if self.das_filter_dialog is None or self.das_filter_dialog.is_busy():
            return
        self.das_filter_dialog.set_visible_range(
            (
                self.window.data.channel_from_num,
                self.window.data.channel_to_num,
                self.window.data.sampling_times_from_num,
                self.window.data.sampling_times_to_num,
            )
        )

    def previewDASFilterData(self, data: np.ndarray, description: str = ""):
        """Refresh all plots with a dialog preview without changing the baseline."""
        self.window.vehicles._hide_vehicle_trajectories = True
        self.window.data.origin_data = np.asarray(data, dtype=np.float32).copy()
        self.window.data.updateDataRange()
        self.window.updateImages()
        if description:
            self.window.statusBar().showMessage(f"预览：{description}", 8000)

    def commitDASFilterData(self, data: np.ndarray):
        """Commit the dialog result as the current working data."""
        self.window.vehicles.clearVehicleTrajectories(update=False)
        self.window.data.origin_data = np.asarray(data, dtype=np.float32).copy()
        self.window.data.updateDataRange()
        self.window.updateImages()
        self.reset_das_filter_action.setEnabled(bool(self._das_filter_steps))
        self.window.statusBar().showMessage("二维滤波结果已应用；可从“滤波”菜单恢复原始数据。", 8000)

    def resetDASFilterData(self):
        """Restore the detrended data loaded from disk."""
        if self.window.data.raw_data is None:
            return
        if self.das_filter_dialog is not None and self.das_filter_dialog.is_busy():
            printError("滤波链正在计算，请等待完成后再恢复原始数据")
            return
        if self.das_filter_dialog is not None:
            self.das_filter_dialog.restore_original()
            return
        self.window.vehicles.clearVehicleTrajectories(update=False)
        self._das_filter_steps = []
        self.window.data.origin_data = np.asarray(self.window.data.raw_data, dtype=np.float32).copy()
        self.window.data.updateDataRange()
        self.window.updateImages()
        self.reset_das_filter_action.setEnabled(False)
        self.window.statusBar().showMessage("已恢复导入后的原始数据（包含现有去趋势步骤）。", 8000)
