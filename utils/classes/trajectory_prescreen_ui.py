"""Non-modal candidate review; the worker never reads or writes Qt widgets."""

import copy
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from PyQt5.QtCore import QObject, QTimer, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHeaderView, QLabel, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .flow_layout import FlowLayout
from .trajectory_prescreen import DEFAULT_PARAMETERS, PrescreenCancelled, analyze_prescreen
from .data_timeline import format_wall_time


class ReviewDialog(QDialog):
    def __init__(self, controller):
        super().__init__(controller.window)
        self.controller = controller
        self.setWindowTitle('轨迹初筛与校对')
        self.setWindowModality(Qt.NonModal)
        self.resize(650, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        self.scope = QLabel('检测当前 DAS 视图；候选确认后才保存到工程')
        self.scope.setWordWrap(True)
        layout.addWidget(self.scope)
        settings = QGroupBox('初筛参数')
        form = QFormLayout(settings)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.sensitivity = QComboBox()
        for text, value in (('保守 · 减少误检', 2.0), ('均衡', 1.5), ('敏感 · 减少漏检', 1.0)):
            self.sensitivity.addItem(text, value)
        self.sensitivity.setCurrentIndex(1)
        self.minimum = QSpinBox()
        self.minimum.setRange(4, 2000)
        self.minimum.setValue(12)
        self.minimum.setSuffix(' 个有效通道')
        self.gaps = QSpinBox()
        self.gaps.setRange(0, 12)
        self.gaps.setValue(5)
        self.gaps.setSuffix(' 个连续通道')
        form.addRow('灵敏度', self.sensitivity)
        form.addRow('最短轨迹', self.minimum)
        form.addRow('允许断点', self.gaps)
        advanced_toggle = QPushButton('高级参数 ▸')
        advanced_toggle.setCheckable(True)
        self.advanced = QWidget()
        advanced_form = QFormLayout(self.advanced)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        self.low = self._number(0.001, 1000, 0.01, ' Hz', 3)
        self.high = self._number(0.01, 1000, 1.0, ' Hz', 2)
        self.speed_low = self._number(0.1, 1000, 7.2, ' km/h', 1)
        self.speed_high = self._number(0.2, 1000, 216, ' km/h', 1)
        self.tolerance = self._number(0.05, 3, 0.6, ' s', 2)
        self.direction = QComboBox()
        for text, value in (('双向', 'auto'), ('向通道增大', 'increasing'), ('向通道减小', 'decreasing')):
            self.direction.addItem(text, value)
        for title, field in (('滤波低频', self.low), ('滤波高频', self.high),
                             ('投影速度下限', self.speed_low), ('投影速度上限', self.speed_high),
                             ('连接时间容差', self.tolerance), ('搜索方向', self.direction)):
            advanced_form.addRow(title, field)
        self.advanced_scroll = QScrollArea()
        self.advanced_scroll.setWidgetResizable(True)
        self.advanced_scroll.setFrameShape(QScrollArea.NoFrame)
        self.advanced_scroll.setMaximumHeight(140)
        self.advanced_scroll.setWidget(self.advanced)
        self.advanced_scroll.hide()
        advanced_toggle.toggled.connect(self.advanced_scroll.setVisible)
        advanced_toggle.toggled.connect(lambda checked: advanced_toggle.setText('高级参数 ▾' if checked else '高级参数 ▸'))
        form.addRow(advanced_toggle)
        form.addRow(self.advanced_scroll)
        layout.addWidget(settings)
        actions = FlowLayout()
        self.start = QPushButton('初筛当前视图')
        self.cancel = QPushButton('取消检测')
        self.cancel.setEnabled(False)
        self.start.clicked.connect(controller.start)
        self.cancel.clicked.connect(controller.cancel)
        actions.addWidget(self.start)
        actions.addWidget(self.cancel)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addLayout(actions)
        layout.addWidget(self.progress)
        self.status = QLabel('选择范围后初筛；车辆、车道、方向使用主界面当前选项')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['确认', '候选', '通道范围', '连续性', '节点', '提示'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selected)
        self.table.itemChanged.connect(lambda item: self.update_actions())
        self.table.itemDoubleClicked.connect(lambda item: controller.edit(self.selected_id()))
        layout.addWidget(self.table, 1)
        review = FlowLayout()
        self.review_buttons = []
        for label, callback in (
            ('编辑选中', lambda: controller.edit(self.selected_id())),
            ('确认选中', lambda: controller.accept([self.selected_id()])),
            ('确认勾选', lambda: controller.accept(self.checked_ids())),
            ('删除选中', lambda: controller.remove(self.selected_id())),
            ('删除勾选', lambda: controller.remove_many(self.checked_ids())),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            review.addWidget(button)
            self.review_buttons.append(button)
        layout.addLayout(review)
        hint = QLabel('虚线为未确认候选；双击编辑节点，Enter 提交修正。勾选后可批量确认。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.update_actions()

    @staticmethod
    def _number(minimum, maximum, value, suffix, decimals):
        field = QDoubleSpinBox()
        field.setRange(minimum, maximum)
        field.setDecimals(decimals)
        field.setValue(value)
        field.setSuffix(suffix)
        field.setKeyboardTracking(False)
        return field

    def parameters(self):
        return {**DEFAULT_PARAMETERS,
                'peak_prominence': self.sensitivity.currentData(),
                'minimum_track_channels': self.minimum.value(),
                'maximum_missed_channels': self.gaps.value(),
                'frequency_low': self.low.value(), 'frequency_high': self.high.value(),
                'minimum_speed': self.speed_low.value() / 3.6,
                'maximum_speed': self.speed_high.value() / 3.6,
                'tracking_tolerance': self.tolerance.value(),
                'direction': self.direction.currentData(),
                'channel_spacing': self.controller.window.video_trajectory_dx_spin_box.value()}

    def selected_id(self):
        row = self.table.currentRow()
        return self.table.item(row, 1).data(Qt.UserRole) if row >= 0 else None

    def checked_ids(self):
        return [self.table.item(row, 1).data(Qt.UserRole) for row in range(self.table.rowCount())
                if self.table.item(row, 0).checkState() == Qt.Checked]

    def _selected(self):
        self.controller.select(self.selected_id())
        self.update_actions()

    def update_actions(self):
        if not hasattr(self, 'review_buttons'):
            return
        selected = self.selected_id() in self.controller.candidates
        checked = bool(self.checked_ids())
        for index, button in enumerate(self.review_buttons):
            button.setEnabled(checked if index in (2, 4) else selected)

    def closeEvent(self, event):
        self.controller.cancel()
        super().closeEvent(event)


class TrajectoryPrescreenController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.candidates = {}
        self.selected_id = None
        self.context = None
        self.future = None
        self.executor = None
        self.cancel_event = Event()
        self.generation = 0
        self.progress_state = (0, '')
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        window.destroyed.connect(lambda: self.shutdown())

    def show(self):
        if self.dialog is None:
            self.dialog = ReviewDialog(self)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def current_context(self):
        group, timeline = self.window._videoDataContext()
        return group, timeline, self.window.video_annotation_project

    def context_matches(self, context):
        return context is not None and all(a is b for a, b in zip(context, self.current_context()))

    def invalidate(self):
        self.generation += 1
        self.cancel()
        self.candidates.clear()
        self.selected_id = None
        self.context = None
        self.refresh()

    def cancel(self):
        if self.future is not None:
            self.cancel_event.set()

    def shutdown(self):
        self.cancel_event.set()
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)

    def start(self):
        if self.future is not None:
            return
        if self.dialog is None:
            self.show()
        w = self.window
        group, timeline = w._videoDataContext()
        if group is None or w._annotationTimeline() is None:
            self.dialog.status.setText('请先导入与标注工程匹配的 DAS 数据')
            return
        x_range, y_range = w.video_das_plot_widget.getViewBox().viewRange()
        import math
        first = max(0, int(math.floor(x_range[0] * timeline.sampling_rate)))
        last = min(group.total_samples, int(math.ceil(x_range[1] * timeline.sampling_rate)))
        origin = getattr(w, '_video_plot_channel_from', 1)
        ch_first = max(1, int(math.floor(y_range[0])) + origin)
        ch_last = min(group.channel_count, int(math.ceil(y_range[1])) + origin - 1)
        parameters = self.dialog.parameters()
        w._pauseForAnnotationDrawing()
        w.annotation_canvas.cancel()
        # Freeze the requested region for review instead of following playback.
        w.video_follow_checkbox.setChecked(False)
        self.invalidate()
        self.context = self.current_context()
        generation = self.generation
        self.cancel_event = Event()
        self.progress_state = (0, '准备读取 DAS 数据')
        self.started_at = time.perf_counter()
        self.dialog.scope.setText(
            f'{format_wall_time(timeline.absolute_time_for_sample(first))}–'
            f'{format_wall_time(timeline.absolute_time_for_sample(last))}；通道 {ch_first}–{ch_last}')
        self.dialog.start.setEnabled(False)
        self.dialog.cancel.setEnabled(True)
        self.dialog.progress.setValue(0)
        self.dialog.status.setText('正在初筛；可取消。播放跟随已关闭，便于校对。')
        raw_data = None if w.video_sequence_data_group is not None else getattr(w, 'raw_data', None)
        if raw_data is None and w.video_sequence_data_group is None:
            raw_data = getattr(w, 'origin_data', None)
        if self.executor is None:
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='das-prescreen')
        context = self.context
        self.future = self.executor.submit(
            analyze_prescreen, copy.deepcopy(group), raw_data, first, last, ch_first, ch_last,
            parameters, self.cancel_event, lambda percent, message: setattr(self, 'progress_state', (percent, message)))
        self.future.prescreen_context = context
        self.future.prescreen_generation = generation
        self.future.prescreen_dx = parameters['channel_spacing']
        w.plotVideoComparisonImage(preserve_view=True)
        self.timer.start()

    def poll(self):
        future = self.future
        if future is None:
            self.timer.stop()
            return
        percent, message = self.progress_state
        self.dialog.progress.setValue(percent)
        if not future.done():
            if not self.cancel_event.is_set():
                self.dialog.status.setText(message)
            return
        self.future = None
        self.timer.stop()
        self.dialog.start.setEnabled(True)
        self.dialog.cancel.setEnabled(False)
        stale = future.prescreen_generation != self.generation or not self.context_matches(future.prescreen_context)
        try:
            result = future.result()
            if stale or self.cancel_event.is_set():
                raise PrescreenCancelled()
            self.context = future.prescreen_context
            self.detected_dx = future.prescreen_dx
            self.candidates = {proposal.identifier: proposal for proposal in result.proposals}
            self.dialog.progress.setValue(100)
            self.dialog.status.setText(
                f'初筛完成：{len(result.proposals)} 条候选，用时 {time.perf_counter() - self.started_at:.1f} 秒。'
                + '；'.join(result.notes))
            self.refresh()
            self.window.plotVideoComparisonImage(preserve_view=True)
        except PrescreenCancelled:
            self.dialog.status.setText('检测已取消或来源已变化，未加入候选')
        except Exception as error:
            self.dialog.status.setText(f'初筛失败：{error}')

    def refresh(self):
        if self.dialog is None:
            return
        checked = set(self.dialog.checked_ids())
        table = self.dialog.table
        table.blockSignals(True)
        table.setRowCount(len(self.candidates))
        for row, proposal in enumerate(self.candidates.values()):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Checked if proposal.identifier in checked else Qt.Unchecked)
            table.setItem(row, 0, check)
            channels = [p[1] for p in proposal.vertices]
            values = [f'C{proposal.identifier}', f'{min(channels):g}–{max(channels):g}',
                      f'{proposal.continuity:.0%}', str(len(proposal.vertices)),
                      '已修正' if proposal.edited else ('分支接近，请检查' if proposal.ambiguous else '待校对')]
            for column, value in enumerate(values, 1):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, proposal.identifier)
                table.setItem(row, column, item)
            if proposal.identifier == self.selected_id:
                table.selectRow(row)
        table.blockSignals(False)
        self.dialog.update_actions()

    def select(self, identifier):
        self.selected_id = identifier if identifier in self.candidates else None
        self.window.plotVideoComparisonImage(preserve_view=True)

    def edit(self, identifier):
        if identifier not in self.candidates or not self.context_matches(self.context):
            return
        self.selected_id = identifier
        self.window._pauseForAnnotationDrawing()
        self.window.plotVideoComparisonImage(preserve_view=True)
        self.window.annotation_canvas.start_edit(-identifier)
        self.window.activateWindow()

    def update_geometry(self, identifier, points):
        proposal = self.candidates.get(identifier)
        if proposal is None or not self.context_matches(self.context):
            return
        proposal.vertices = self.window._geometryVerticesFromPlot(points)
        proposal.edited = True
        self.refresh()
        self.window.plotVideoComparisonImage(preserve_view=True)

    def remove(self, identifier):
        self.remove_many([identifier])

    def remove_many(self, identifiers):
        canvas = self.window.annotation_canvas
        if canvas._edit_id is not None and -canvas._edit_id in identifiers:
            canvas.cancel()
        for identifier in identifiers:
            self.candidates.pop(identifier, None)
        if self.selected_id not in self.candidates:
            self.selected_id = None
        self.refresh()
        self.window.plotVideoComparisonImage(preserve_view=True)

    def accept(self, identifiers):
        if not self.context_matches(self.context) or self.window._annotationTimeline() is None:
            if self.dialog is not None:
                self.dialog.status.setText('DAS 来源已变化，请重新初筛')
            return
        canvas = self.window.annotation_canvas
        if canvas._edit_id is not None:
            canvas.commit_edit()
            if canvas._edit_id is not None:
                return
        proposals = [self.candidates[i] for i in dict.fromkeys(identifiers) if i in self.candidates]
        if not proposals:
            return
        w = self.window
        w._pushAnnotationUndo()
        last_id = None
        for proposal in proposals:
            annotation = w.video_annotation_project.add_geometry_annotation(
                w._annotationTimeline(), 'lin', copy.deepcopy(proposal.vertices),
                w.annotation_kind_combo.currentText(), w.annotation_outcome_combo.currentText(),
                w.annotation_note_edit.text(), self.detected_dx)
            w._setAnnotationVehicleLabels(annotation)
            last_id = annotation.identifier
            del self.candidates[proposal.identifier]
        self.selected_id = None
        w.video_annotation_selected_id = last_id
        w._markVideoAnnotationDirty()
        w.refreshVideoAnnotationTable(last_id)
        self.refresh()
        w.plotVideoComparisonImage(preserve_view=True)
        if self.dialog is not None:
            self.dialog.status.setText(f'已确认 {len(proposals)} 条轨迹；可撤销，保存工程后持久保留')

    def render(self):
        w = self.window
        if not self.context_matches(self.context) or not w.video_annotations_visible_checkbox.isChecked():
            return
        timeline = w._annotationTimeline()
        if timeline is None:
            return
        origin = getattr(w, '_video_plot_channel_from', 1)
        for proposal in self.candidates.values():
            points = [[p[0] / timeline.sampling_rate, p[1] - origin + 0.5] for p in proposal.vertices]
            w.annotation_canvas.render_shape(
                -proposal.identifier, 'lin', points, f'C{proposal.identifier}',
                proposal.identifier == self.selected_id,
                f'未确认候选 C{proposal.identifier}；连续性 {proposal.continuity:.0%}\n'
                '右键编辑或删除；在初筛窗口确认后保存到工程', candidate=True)
