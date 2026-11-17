"""通道 / 采样点 / 时间范围选择器。

采样点与时间互相联动；"当前查看范围"模式下隐藏手动输入，只显示说明文字。
"""

from __future__ import annotations

from typing import Sequence, Tuple

from PyQt5.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

Range = Tuple[int, int, int, int]  # 通道起止、采样点起止（均从 1 开始，含端点）


def _int_spin(width: int) -> QSpinBox:
    box = QSpinBox()
    box.setKeyboardTracking(False)
    box.setFixedWidth(width)
    return box


def _pair_row(first: QWidget, second: QWidget) -> QWidget:
    """"起 至 止" 一行，包进一个控件里，方便整行显隐。"""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(first)
    layout.addWidget(QLabel("至"))
    layout.addWidget(second)
    layout.addStretch(1)
    return row


class RangeSelector(QWidget):
    def __init__(
        self,
        sampling_rate: float,
        channel_count: int,
        sample_count: int,
        visible_range: Range,
        extra_rows: Sequence[Tuple[str, QWidget]] = (),
        parent=None,
    ):
        """extra_rows 会插在"作用范围"之后，用来放调用方自己的选项。"""
        super().__init__(parent)
        self._syncing = False
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(2)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem("当前查看范围", "visible")
        self.scope_combo.addItem("自定义范围", "custom")
        form.addRow("作用范围", self.scope_combo)
        for label, widget in extra_rows:
            form.addRow(label, widget)

        self.channel_from, self.channel_to = _int_spin(82), _int_spin(82)
        self.sample_from, self.sample_to = _int_spin(90), _int_spin(90)
        self.time_from, self.time_to = QDoubleSpinBox(), QDoubleSpinBox()
        for box in (self.time_from, self.time_to):
            box.setDecimals(6)
            box.setSingleStep(0.01)
            box.setFixedWidth(104)

        # 只在"自定义范围"下显示的三行：(标签, 输入行)
        self._custom_rows = []
        for text, first, second in (
            ("通道范围", self.channel_from, self.channel_to),
            ("采样点范围", self.sample_from, self.sample_to),
            ("时间范围", self.time_from, self.time_to),
        ):
            label, row = QLabel(text), _pair_row(first, second)
            form.addRow(label, row)
            self._custom_rows.append((label, row))
        self._spins = (
            self.channel_from, self.channel_to, self.sample_from,
            self.sample_to, self.time_from, self.time_to,
        )

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setObjectName("secondaryLabel")
        form.addRow("范围说明", self.info_label)

        self.scope_combo.currentIndexChanged.connect(self._scope_changed)
        for box in (self.channel_from, self.channel_to):
            box.valueChanged.connect(self._update_info)
        for box in (self.sample_from, self.sample_to):
            box.valueChanged.connect(self._samples_changed)
        for box in (self.time_from, self.time_to):
            box.valueChanged.connect(self._times_changed)

        self.set_limits(sampling_rate, channel_count, sample_count, visible_range)

    # ---- 对外接口 -------------------------------------------------------
    def selected_range(self) -> Range:
        if self.scope_combo.currentData() == "visible":
            return self.visible_range
        return (
            self.channel_from.value(), self.channel_to.value(),
            self.sample_from.value(), self.sample_to.value(),
        )

    def set_limits(self, sampling_rate, channel_count, sample_count, visible_range) -> None:
        """换了一组数据：重设上限，并回到"当前查看范围"。"""
        self.sampling_rate = float(sampling_rate)
        self.channel_count = int(channel_count)
        self.sample_count = int(sample_count)
        self.visible_range = self._clamp(visible_range)
        for box in (self.channel_from, self.channel_to):
            box.setRange(1, self.channel_count)
        for box in (self.sample_from, self.sample_to):
            box.setRange(1, self.sample_count)
        for box in (self.time_from, self.time_to):
            box.setRange(0.0, self.sample_count / self.sampling_rate)
        self.scope_combo.setCurrentIndex(0)
        self._scope_changed()

    def set_visible_range(self, values: Range) -> None:
        self.visible_range = self._clamp(values)
        if self.scope_combo.currentData() == "visible":
            self._scope_changed()

    def set_selection(self, selection: Range) -> None:
        """把某一步的范围载回编辑器。"""
        same = tuple(selection) == tuple(self.visible_range)
        index = self.scope_combo.findData("visible" if same else "custom")
        self.scope_combo.setCurrentIndex(index)
        channel_from, channel_to, sample_from, sample_to = selection
        self.channel_from.setValue(channel_from)
        self.channel_to.setValue(channel_to)
        self.sample_from.setValue(sample_from)
        self.sample_to.setValue(sample_to)

    # ---- 内部 -----------------------------------------------------------
    def _clamp(self, values) -> Range:
        channel_from, channel_to, sample_from, sample_to = map(int, values)
        pin = lambda value, upper: max(1, min(upper, value))  # noqa: E731
        return (
            pin(channel_from, self.channel_count), pin(channel_to, self.channel_count),
            pin(sample_from, self.sample_count), pin(sample_to, self.sample_count),
        )

    def _scope_changed(self) -> None:
        custom = self.scope_combo.currentData() == "custom"
        for label, row in self._custom_rows:
            label.setVisible(custom)
            row.setVisible(custom)
        for box in self._spins:
            box.setEnabled(custom)
        if not custom:
            channel_from, channel_to, sample_from, sample_to = self.visible_range
            self.channel_from.setValue(channel_from)
            self.channel_to.setValue(channel_to)
            self.sample_from.setValue(sample_from)
            self.sample_to.setValue(sample_to)
            self._sync_times_from_samples()
        self._update_info()

    def _sync_times_from_samples(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.time_from.setValue((self.sample_from.value() - 1) / self.sampling_rate)
            self.time_to.setValue(self.sample_to.value() / self.sampling_rate)
        finally:
            self._syncing = False

    def _samples_changed(self) -> None:
        self._sync_times_from_samples()
        self._update_info()

    def _times_changed(self) -> None:
        if self._syncing or self.scope_combo.currentData() != "custom":
            self._update_info()
            return
        start = self.time_from.value()
        end = max(start, self.time_to.value())
        sample_from = max(1, min(self.sample_count, int(round(start * self.sampling_rate)) + 1))
        sample_to = max(sample_from, min(self.sample_count, int(round(end * self.sampling_rate))))
        self._syncing = True
        try:
            self.time_to.setValue(end)
            self.sample_from.setValue(sample_from)
            self.sample_to.setValue(sample_to)
        finally:
            self._syncing = False
        self._update_info()

    def _update_info(self) -> None:
        channel_from, channel_to, sample_from, sample_to = self.selected_range()
        if channel_from > channel_to or sample_from > sample_to:
            self.info_label.setText("范围无效：起点必须不大于终点。")
            return
        samples = sample_to - sample_from + 1
        self.info_label.setText(
            f"将处理 {channel_to - channel_from + 1} 个通道、{samples} 个采样点，"
            f"约 {samples / self.sampling_rate:g} 秒 （采样率 {self.sampling_rate:g} Hz）。"
        )
