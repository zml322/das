"""DAS 二维滤波对话框：组装参数表单、范围选择器、滤波链视图和后台重放。

原 1765 行 das_filter.py 拆成 7 个文件后，这个对话框只负责组装和协调。
"""

from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

import numpy as np
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.data.data_group import ensure_memory_budget, format_bytes
from core.filter.algorithms import ALGORITHM_LABELS
from core.filter.filter_pipeline import FilterPipeline, FilterStep, clone_steps

from .chain_view import ChainView
from .parameters import ParameterForm, summarize
from .replay import ReplayRunner
from .section import CollapsibleSection
from ..widgets.range_selector import RangeSelector

Range = Tuple[int, int, int, int]


class DASFilterDialog(QDialog):
    """持久化非模态的滤波链编辑器，支持回放、历史和自动重新应用。"""

    previewReady = pyqtSignal(object, str)
    committed = pyqtSignal(object)
    pipelineChanged = pyqtSignal(object)
    settingsChanged = pyqtSignal(object)
    autoReapplyChanged = pyqtSignal(bool)
    pipelineConfirmedByUser = pyqtSignal(object)
    savePipelineRequested = pyqtSignal(str)
    loadPipelineRequested = pyqtSignal(str)
    deletePipelineRequested = pyqtSignal(str)
    backRequested = pyqtSignal()

    def __init__(
        self,
        data: np.ndarray,
        sampling_rate: float,
        visible_range: Range,
        settings: Optional[Dict[str, object]] = None,
        steps: Optional[Iterable[FilterStep]] = None,
        current_data: Optional[np.ndarray] = None,
        segment_ranges: Optional[Sequence[Tuple[int, int]]] = None,
        previous_steps: Optional[Iterable[FilterStep]] = None,
        auto_reapply: bool = True,
        embedded: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.embedded = bool(embedded)
        self.setWindowTitle("DAS 二维滤波工具")
        self.setModal(False)
        if self.embedded:
            self.setWindowFlags(Qt.Widget)
            self.setMinimumSize(0, 0)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            self.setWindowFlag(Qt.Tool, True)
            self.resize(410, 720)
            self.setMinimumSize(380, 560)

        self.raw_data = np.asarray(data, dtype=np.float32).copy()
        if self.raw_data.ndim != 2 or min(self.raw_data.shape) == 0:
            raise ValueError("DAS 数据必须是非空二维数组")
        self.raw_data.setflags(write=False)
        if current_data is None:
            self.working_data = np.asarray(self.raw_data, dtype=np.float32).copy()
        else:
            self.working_data = np.asarray(current_data, dtype=np.float32).copy()
            if self.working_data.shape != self.raw_data.shape:
                raise ValueError("当前滤波数据与原始数据形状不一致")
        self.sampling_rate = float(sampling_rate)
        self.channel_count, self.sample_count = self.working_data.shape
        self.visible_range = self._clamp(visible_range)
        self.segment_ranges = list(segment_ranges or [(0, self.sample_count)])
        self.pipeline = FilterPipeline(steps)
        self.committed_steps = self.pipeline.steps()
        self.previous_steps = clone_steps(previous_steps or [])
        self.auto_reapply = bool(auto_reapply)

        self._pending_steps: List[FilterStep] = []
        self._pending_description = ""
        self._pending_selected_row = -1
        self._pending_commit = False
        self._pending_remember = False
        self._pending_update_draft = True
        self._loading = False

        self._build_ui()
        if settings:
            self.params.restore(settings)
        self._refresh_chain()
        self._update_state()

    def _clamp(self, values: Range) -> Range:
        pin = lambda v, upper: max(1, min(upper, int(v)))  # noqa: E731
        return (
            pin(values[0], self.channel_count),
            pin(values[1], self.channel_count),
            pin(values[2], self.sample_count),
            pin(values[3], self.sample_count),
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        margin = 6 if self.embedded else 8
        root.setContentsMargins(margin, margin, margin, margin)
        root.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content_widget = QWidget()
        content = QVBoxLayout(content_widget)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(8)
        content.setAlignment(Qt.AlignTop)
        scroll.setWidget(content_widget)
        root.addWidget(scroll, 1)

        # 算法
        algo_section = CollapsibleSection("算法", expanded=True)
        algo_layout = QVBoxLayout(algo_section.content)
        algo_layout.setContentsMargins(8, 10, 8, 8)
        algo_layout.setSpacing(4)
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.algorithm_combo.setMinimumContentsLength(12)
        for key, label in ALGORITHM_LABELS:
            self.algorithm_combo.addItem(label, key)
        self.algorithm_combo.currentIndexChanged.connect(self._algorithm_changed)
        algo_layout.addWidget(QLabel("处理方法"))
        algo_layout.addWidget(self.algorithm_combo)
        content.addWidget(algo_section)

        # 范围
        range_section = CollapsibleSection("处理范围（包含起止点）", expanded=True)
        range_layout = QVBoxLayout(range_section.content)
        range_layout.setContentsMargins(8, 10, 8, 8)
        self.processing_mode = QComboBox()
        self.processing_mode.addItem("整体连续（跨文件边界）", "continuous")
        self.processing_mode.addItem("按文件分段", "per_segment")
        self.processing_mode.setEnabled(len(self.segment_ranges) > 1)
        self.processing_mode.setToolTip(
            "确认文件连续时可整体处理；不确定时按文件分段可避免滤波跨越接缝。"
        )
        self.range_selector = RangeSelector(
            self.sampling_rate,
            self.channel_count,
            self.sample_count,
            self.visible_range,
            extra_rows=[("拼接处理", self.processing_mode)],
            parent=range_section.content,
        )
        range_layout.addWidget(self.range_selector)
        content.addWidget(range_section)

        # 参数
        param_section = CollapsibleSection("算法参数", expanded=True)
        param_layout = QVBoxLayout(param_section.content)
        param_layout.setContentsMargins(8, 10, 8, 8)
        self.params = ParameterForm(
            self.sampling_rate, self.channel_count, self.sample_count, param_section.content
        )
        param_layout.addWidget(self.params)
        add_row = QHBoxLayout()
        add_row.addStretch(1)
        self.add_button = QPushButton("加入滤波链")
        self.add_button.setToolTip("把当前算法、参数和范围加入待应用滤波链；不会立即计算或重绘")
        self.add_button.clicked.connect(self._add_step)
        add_row.addWidget(self.add_button)
        param_layout.addLayout(add_row)
        content.addWidget(param_section)

        # 链
        chain_section = CollapsibleSection("滤波链", expanded=True)
        chain_layout = QVBoxLayout(chain_section.content)
        chain_layout.setContentsMargins(8, 10, 8, 8)
        self.chain = ChainView(self.auto_reapply, parent=chain_section.content)
        self.chain.rowChanged.connect(self._row_changed)
        self.chain.stepToggled.connect(self._step_toggled)
        self.chain.updateRequested.connect(self._update_step)
        self.chain.deleteRequested.connect(self._delete_step)
        self.chain.moveRequested.connect(self._move_step)
        self.chain.clearRequested.connect(self._clear_chain)
        self.chain.saveRequested.connect(self.savePipelineRequested)
        self.chain.loadRequested.connect(self.loadPipelineRequested)
        self.chain.deleteSavedRequested.connect(self.deletePipelineRequested)
        self.chain.autoReapplyToggled.connect(self._auto_reapply_toggled)
        chain_layout.addWidget(self.chain)
        content.addWidget(chain_section)

        self.status_label = QLabel(
            "先编辑完整滤波链，再点击\"应用滤波\"一次性计算和绘图。"
        )
        self.status_label.setWordWrap(True)
        self.status_label.setToolTip(self.status_label.text())
        self.status_label.setObjectName("filterStatusLabel")
        root.addWidget(self.status_label)

        action_bar = QWidget()
        action_bar.setObjectName("filterActionBar")
        buttons = QHBoxLayout(action_bar)
        buttons.setContentsMargins(6, 6, 6, 6)
        buttons.setSpacing(6)
        self.apply_button = QPushButton("应用滤波")
        self.apply_button.setObjectName("primaryAction")
        self.apply_button.setToolTip(
            "从不可变原始数据出发，一次性执行所有已启用步骤并刷新主图"
        )
        self.reset_button = QPushButton("恢复原始数据")
        self.reset_button.setToolTip("恢复导入后的原始数据，但保留当前滤波链配置")
        self.apply_button.clicked.connect(self._apply)
        self.reset_button.clicked.connect(self._reset)
        buttons.addWidget(self.apply_button, 1)
        buttons.addWidget(self.reset_button, 1)
        root.addWidget(action_bar)

        self.runner = ReplayRunner(self)
        self.runner.done.connect(self._replay_done)
        self.runner.failed.connect(self._replay_failed)
        self.runner.finished.connect(self._replay_finished)

    # ---- 对外接口（旧 das_filter.py 的 API） ------------------------------
    def is_busy(self) -> bool:
        return self.runner.is_running()

    def set_visible_range(self, values: Range) -> None:
        self.visible_range = self._clamp(values)
        self.range_selector.set_visible_range(self.visible_range)

    def set_data(
        self,
        raw_data: np.ndarray,
        sampling_rate: float,
        visible_range: Range,
        current_data: Optional[np.ndarray] = None,
        steps: Optional[Iterable[FilterStep]] = None,
        segment_ranges: Optional[Sequence[Tuple[int, int]]] = None,
        previous_steps: Optional[Iterable[FilterStep]] = None,
    ) -> None:
        if self.is_busy():
            raise RuntimeError("滤波正在执行，暂时不能切换数据")
        baseline = np.asarray(raw_data, dtype=np.float32).copy()
        if baseline.ndim != 2 or min(baseline.shape) <= 0:
            raise ValueError("DAS 数据必须是非空二维数组")
        current = (
            baseline.copy()
            if current_data is None
            else np.asarray(current_data, dtype=np.float32).copy()
        )
        if current.shape != baseline.shape:
            raise ValueError("当前滤波数据与原始数据形状不一致")
        baseline.setflags(write=False)
        self.raw_data = baseline
        self.working_data = current
        self.sampling_rate = float(sampling_rate)
        self.channel_count, self.sample_count = baseline.shape
        self.visible_range = self._clamp(visible_range)
        self.segment_ranges = list(segment_ranges or [(0, self.sample_count)])
        self.pipeline = FilterPipeline(steps)
        self.committed_steps = self.pipeline.steps()
        self.previous_steps = clone_steps(previous_steps or [])

        self.range_selector.set_limits(
            self.sampling_rate, self.channel_count, self.sample_count, self.visible_range
        )
        self.params.set_limits(self.sampling_rate, self.channel_count, self.sample_count)
        self.processing_mode.setEnabled(len(self.segment_ranges) > 1)
        if len(self.segment_ranges) <= 1:
            index = self.processing_mode.findData("continuous")
            if index >= 0:
                self.processing_mode.setCurrentIndex(index)
        self._refresh_chain()
        msg = (
            f"已切换到新数据组：{self.channel_count} 通道，{self.sample_count} 采样点；"
            + (
                f"当前显示已应用的 {len(self.committed_steps)} 步滤波结果。"
                if self.committed_steps
                else "当前显示原始数据。"
            )
        )
        self._update_state(msg)

    def filter_settings(self) -> Dict[str, object]:
        return {
            "algorithm": self.algorithm_combo.currentData(),
            "processing_mode": self.processing_mode.currentData(),
            **self.params.settings(),
        }

    def pipeline_steps(self) -> List[FilterStep]:
        return self.pipeline.steps()

    def set_draft_pipeline(
        self,
        steps: Iterable[FilterStep],
        description: str = "已载入滤波方案",
        *,
        new_identifiers: bool = True,
    ) -> bool:
        if self.is_busy():
            return False
        candidate = clone_steps(steps, new_identifiers=new_identifiers)
        self.pipeline = FilterPipeline(candidate)
        self._refresh_chain(len(candidate) - 1)
        self.settingsChanged.emit(self.filter_settings())
        self._update_state(
            f"{description}；主图保持不变，点击\"应用滤波\"后一次性计算。"
        )
        return True

    def set_saved_pipelines(self, entries) -> None:
        self.chain.set_saved(entries)

    def setAutoReapply(self, enabled: bool) -> None:
        self.auto_reapply = bool(enabled)
        self.chain.auto_reapply_checkbox.blockSignals(True)
        self.chain.auto_reapply_checkbox.setChecked(self.auto_reapply)
        self.chain.auto_reapply_checkbox.blockSignals(False)

    def replayExternalPipeline(
        self, steps: Iterable[FilterStep], description: str, commit_after: bool = False
    ) -> bool:
        if self.is_busy():
            return False
        candidate = clone_steps(steps, new_identifiers=True)
        if not candidate:
            return False
        self._start_replay(
            candidate, description, len(candidate) - 1, commit_after=commit_after, update_draft=True
        )
        return True

    def restore_original(self) -> None:
        self._reset()

    # ---- 内部逻辑 -------------------------------------------------------
    def _algorithm_changed(self) -> None:
        self.params.set_algorithm(self.algorithm_combo.currentData())

    def _add_step(self) -> None:
        if self.is_busy():
            return
        channel_from, channel_to, sample_from, sample_to = self.range_selector.selected_range()
        if channel_from > channel_to or sample_from > sample_to:
            QMessageBox.warning(self, "范围无效", "请确认通道和采样点的起止范围。")
            return
        algorithm = self.algorithm_combo.currentData()
        step = FilterStep(
            algorithm=algorithm,
            parameters=self.params.values(algorithm),
            selection=(channel_from, channel_to, sample_from, sample_to),
            label=self.algorithm_combo.currentText(),
            enabled=True,
            processing_mode=self.processing_mode.currentData(),
            identifier=uuid4().hex,
        )
        steps = self.pipeline.steps()
        steps.append(step)
        self._replace_steps(
            steps, len(steps) - 1, f"已将\"{step.label}\"加入滤波链；尚未计算或重绘。"
        )

    def _row_changed(self, row: int) -> None:
        self.chain.set_controls(self.is_busy(), len(self.pipeline), False)
        if self._loading or not (0 <= row < len(self.pipeline)):
            return
        step = self.pipeline.steps()[row]
        self._loading = True
        try:
            index = self.algorithm_combo.findData(step.algorithm)
            if index >= 0:
                self.algorithm_combo.setCurrentIndex(index)
            mode_index = self.processing_mode.findData(step.processing_mode)
            if mode_index >= 0:
                self.processing_mode.setCurrentIndex(mode_index)
            self.range_selector.set_selection(step.selection)
            self.params.load(step.parameters)
        finally:
            self._loading = False

    def _step_toggled(self, row: int, enabled: bool) -> None:
        if self.is_busy() or not (0 <= row < len(self.pipeline)):
            return
        steps = self.pipeline.steps()
        if steps[row].enabled == enabled:
            return
        steps[row].enabled = enabled
        self.pipeline = FilterPipeline(steps)
        self.chain.set_controls(self.is_busy(), len(self.pipeline), False)
        self._update_state(
            f"已{'启用' if enabled else '禁用'}第 {row + 1} 个滤波步骤；"
            "主图保持不变，等待一次性应用。"
        )

    def _update_step(self) -> None:
        row = self.chain.current_row()
        if not (0 <= row < len(self.pipeline)) or self.is_busy():
            return
        steps = self.pipeline.steps()
        current = steps[row]
        algorithm = self.algorithm_combo.currentData()
        steps[row] = FilterStep(
            algorithm=algorithm,
            parameters=self.params.values(algorithm),
            selection=self.range_selector.selected_range(),
            label=self.algorithm_combo.currentText(),
            enabled=current.enabled,
            processing_mode=self.processing_mode.currentData(),
            identifier=current.identifier,
        )
        self._replace_steps(steps, row, f"已更新第 {row + 1} 个滤波步骤；尚未计算或重绘。")

    def _delete_step(self) -> None:
        row = self.chain.current_row()
        if not (0 <= row < len(self.pipeline)) or self.is_busy():
            return
        steps = self.pipeline.steps()
        removed = steps.pop(row)
        self._replace_steps(
            steps, min(row, len(steps) - 1), f"已从待应用链删除\"{removed.label}\"；主图保持不变。"
        )

    def _move_step(self, offset: int) -> None:
        row = self.chain.current_row()
        destination = row + int(offset)
        if (
            self.is_busy()
            or not (0 <= row < len(self.pipeline))
            or not (0 <= destination < len(self.pipeline))
        ):
            return
        steps = self.pipeline.steps()
        step = steps.pop(row)
        steps.insert(destination, step)
        self._replace_steps(steps, destination, "已调整滤波步骤顺序；主图保持不变，等待一次性应用。")

    def _clear_chain(self) -> None:
        if self.is_busy() or len(self.pipeline) == 0:
            return
        self._replace_steps([], -1, "已清空待应用滤波链；主图未改变，如需恢复请点击\"恢复原始数据\"。")

    def _replace_steps(self, steps: Iterable[FilterStep], selected_row: int, message: str) -> None:
        self.pipeline = FilterPipeline(steps)
        self._refresh_chain(selected_row)
        self.settingsChanged.emit(self.filter_settings())
        self._update_state(message)

    def _refresh_chain(self, selected_row: int = -1) -> None:
        steps = self.pipeline.steps()
        rows = [
            (self._step_text(i, step), self._step_tooltip(i, step), step.enabled)
            for i, step in enumerate(steps)
        ]
        active = self.chain.show_steps(rows, selected_row)
        if active >= 0:
            self._row_changed(active)
        self.chain.set_controls(self.is_busy(), len(steps), False)
        self._update_state()

    def _step_text(self, index: int, step: FilterStep) -> str:
        channel_from, channel_to, sample_from, sample_to = step.selection
        mode = "整体连续" if step.processing_mode == "continuous" else "按文件分段"
        return (
            f"{index + 1}. {step.label}｜{summarize(step.algorithm, step.parameters)}\n"
            f"通道 {channel_from}-{channel_to}｜采样 {sample_from}-{sample_to}｜{mode}"
        )

    def _step_tooltip(self, index: int, step: FilterStep) -> str:
        return (
            f"{self._step_text(index, step)}\n"
            f"参数：{step.parameters!r}\n步骤 ID：{step.identifier}"
        )

    def _update_state(self, message: Optional[str] = None) -> None:
        steps = self.pipeline.steps()
        dirty = not self._steps_match(steps, self.committed_steps)
        busy = self.is_busy()
        enabled_count = sum(step.enabled for step in steps)

        if busy:
            state, text = "busy", "正在处理"
        elif dirty:
            state, text = "pending", f"{len(steps)} 步 · 待应用"
        elif self.committed_steps:
            state, text = "applied", f"{len(self.committed_steps)} 步 · 已应用"
        else:
            state, text = "empty", "当前为原始数据"
        self.chain.set_state(state, text)

        self.add_button.setEnabled(not busy)
        self.apply_button.setEnabled(not busy and dirty and enabled_count > 0)
        self.reset_button.setEnabled(not busy and bool(self.committed_steps))
        self.chain.set_controls(busy, len(steps), False)

        if message is not None:
            self._set_status(message)
        elif not busy:
            if dirty:
                self._set_status("滤波链已修改，主图保持不变；点击\"应用滤波\"后一次性计算。")
            elif self.committed_steps:
                self._set_status(f"当前显示已应用结果，共 {len(self.committed_steps)} 个滤波步骤。")
            else:
                self._set_status("当前显示原始数据；请先编辑滤波链，再点击\"应用滤波\"。")

    @staticmethod
    def _steps_match(left: Iterable[FilterStep], right: Iterable[FilterStep]) -> bool:
        return [step.to_dict() for step in left] == [step.to_dict() for step in right]

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def _apply(self) -> None:
        if self.is_busy():
            return
        steps = self.pipeline.steps()
        enabled_count = sum(step.enabled for step in steps)
        if enabled_count == 0:
            self._set_status("当前没有启用的滤波步骤；如需显示原始数据，请点击\"恢复原始数据\"。")
            return
        if not self._steps_match(steps, self.committed_steps):
            self._start_replay(
                steps,
                f"应用当前滤波链（{enabled_count} 个启用步骤）",
                self.chain.current_row(),
                commit_after=True,
                remember_after=True,
                update_draft=False,
            )
        else:
            self._set_status("当前滤波链已经应用，无需重复计算。")

    def _reset(self) -> None:
        if self.is_busy():
            return
        if not self.committed_steps:
            self._set_status("当前已经是原始数据；滤波链配置保持不变。")
            return
        self._start_replay(
            [], "恢复导入原始数据", -1, commit_after=True, remember_after=False, update_draft=False
        )

    def _start_replay(
        self,
        steps: Iterable[FilterStep],
        description: str,
        selected_row: int = -1,
        commit_after: bool = False,
        remember_after: bool = False,
        update_draft: bool = True,
    ) -> None:
        if self.is_busy():
            return
        candidate = clone_steps(steps)
        copies = 14.0 if any(step.enabled and step.algorithm == "fk" for step in candidate) else 6.0
        try:
            required, available = ensure_memory_budget(
                self.channel_count, self.sample_count, copies, "滤波链回放"
            )
        except MemoryError as error:
            QMessageBox.warning(self, "内存不足", str(error))
            return
        self._pending_steps = candidate
        self._pending_description = description
        self._pending_selected_row = selected_row
        self._pending_commit = commit_after
        self._pending_remember = remember_after
        self._pending_update_draft = update_draft
        memory_text = f"预计峰值内存约 {format_bytes(required)}"
        if available is not None:
            memory_text += f"，当前可用约 {format_bytes(available)}"
        self._set_status(f"正在从原始数据一次性执行 {len(candidate)} 个步骤；{memory_text}……")
        self.settingsChanged.emit(self.filter_settings())
        self._update_state()
        self.runner.start(self.raw_data, self.sampling_rate, candidate, self.segment_ranges)

    def _replay_done(self, result) -> None:
        applied = clone_steps(self._pending_steps)
        if self._pending_update_draft:
            self.pipeline = FilterPipeline(applied)
        self.working_data = np.asarray(result, dtype=np.float32).copy()
        if self._pending_update_draft:
            self._refresh_chain(self._pending_selected_row)
        if self._pending_commit:
            self._store_commit(
                applied, remember=self._pending_remember, description=self._pending_description
            )
        else:
            self.previewReady.emit(self.working_data.copy(), self._pending_description)
            self._set_status(f"已生成临时结果：{self._pending_description}。")

    def _replay_failed(self, details: str) -> None:
        self._set_status("处理失败，请检查参数、范围或新数据的兼容性；待应用链仍保留。")
        QMessageBox.critical(self, "滤波失败", details.splitlines()[-1])

    def _replay_finished(self) -> None:
        self._pending_commit = False
        self._pending_remember = False
        self._pending_update_draft = True
        self._update_state()

    def _store_commit(
        self,
        steps: Optional[Iterable[FilterStep]] = None,
        remember: bool = False,
        description: str = "",
    ) -> None:
        self.committed_steps = clone_steps(self.pipeline.steps() if steps is None else steps)
        self.pipelineChanged.emit(self.committed_steps)
        self.committed.emit(self.working_data.copy())
        self.settingsChanged.emit(self.filter_settings())
        if remember and self.committed_steps:
            self.pipelineConfirmedByUser.emit(self.committed_steps)
        if self.committed_steps:
            enabled = sum(step.enabled for step in self.committed_steps)
            message = f"已从原始数据一次性应用 {enabled} 个启用步骤。"
        else:
            message = "已恢复原始数据；当前滤波链配置已保留。"
        if description and self.committed_steps:
            message = f"{message} {description}。"
        self._update_state(message)

    def _auto_reapply_toggled(self, enabled: bool) -> None:
        self.auto_reapply = bool(enabled)
        self.autoReapplyChanged.emit(self.auto_reapply)

    def accept(self) -> None:
        if not self.is_busy():
            self._apply()

    def reject(self) -> None:
        self._close_requested()

    def _close_requested(self) -> None:
        if self.embedded:
            self.backRequested.emit()
        else:
            self.hide()

    def closeEvent(self, event) -> None:
        event.ignore()
        self._close_requested()
