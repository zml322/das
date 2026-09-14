"""Qt controls for non-destructive vehicle-trajectory picking."""

from __future__ import annotations

import csv
import traceback
from typing import Dict, List, Optional, Tuple

import numpy as np

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .vehicle_tracking import VehicleTrajectory, pick_vehicle_trajectories


class _VehicleTrackingWorker(QThread):
    resultReady = pyqtSignal(object)
    errorRaised = pyqtSignal(str)

    def __init__(
        self,
        data: np.ndarray,
        sampling_rate: float,
        parameters: Dict[str, object],
        channel_start: int,
        time_start: float,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._data = np.asarray(data, dtype=np.float32).copy()
        self._sampling_rate = float(sampling_rate)
        self._parameters = dict(parameters)
        self._channel_start = int(channel_start)
        self._time_start = float(time_start)

    def run(self) -> None:
        try:
            trajectories = pick_vehicle_trajectories(
                self._data,
                self._sampling_rate,
                self._parameters,
                channel_start=self._channel_start,
                time_start=self._time_start,
            )
        except Exception:
            self.errorRaised.emit(traceback.format_exc())
        else:
            self.resultReady.emit(trajectories)


class VehicleTrackingDialog(QDialog):
    """Parameter editor and result manager for vehicle trajectories."""

    trajectoriesChanged = pyqtSignal(object)

    def __init__(
        self,
        data: np.ndarray,
        sampling_rate: float,
        visible_range: Tuple[int, int, int, int],
        settings: Optional[Dict[str, object]] = None,
        trajectories: Optional[List[VehicleTrajectory]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        source = np.asarray(data, dtype=np.float32)
        if source.ndim != 2 or min(source.shape) == 0:
            raise ValueError("车辆轨迹拾取需要非空的二维 DAS 数据")

        self.setWindowTitle("车辆轨迹拾取")
        self.setModal(True)
        self.resize(760, 800)
        self.source_data = source
        self.sampling_rate = float(sampling_rate)
        self.channel_count, self.sample_count = source.shape
        self.visible_range = self._normalize_range(visible_range)
        self.trajectories: List[VehicleTrajectory] = list(trajectories or [])
        self._worker: Optional[_VehicleTrackingWorker] = None
        self._syncing_range = False

        self._build_ui()
        self._restore_settings(settings)
        self._populate_trajectory_table()

    def _normalize_range(self, values: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
        channel_from, channel_to, sample_from, sample_to = map(int, values)
        return (
            max(1, min(self.channel_count, channel_from)),
            max(1, min(self.channel_count, channel_to)),
            max(1, min(self.sample_count, sample_from)),
            max(1, min(self.sample_count, sample_to)),
        )

    @staticmethod
    def _spinbox(minimum: int, maximum: int, value: int) -> QSpinBox:
        box = QSpinBox()
        box.setRange(minimum, maximum)
        box.setValue(value)
        box.setKeyboardTracking(False)
        return box

    @staticmethod
    def _double_spinbox(
        minimum: float,
        maximum: float,
        value: float,
        decimals: int = 3,
        step: float = 0.1,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setValue(value)
        box.setDecimals(decimals)
        box.setSingleStep(step)
        box.setSuffix(suffix)
        box.setKeyboardTracking(False)
        return box

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        range_group = QGroupBox("拾取范围（仅用于分析，不修改数据）")
        range_form = QFormLayout(range_group)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("当前查看范围", "visible")
        self.scope_combo.addItem("自定义范围", "custom")
        self.scope_combo.currentIndexChanged.connect(self._update_scope_controls)
        range_form.addRow("分析范围", self.scope_combo)

        channel_row = QHBoxLayout()
        self.channel_from = self._spinbox(1, self.channel_count, self.visible_range[0])
        self.channel_to = self._spinbox(1, self.channel_count, self.visible_range[1])
        channel_row.addWidget(QLabel("通道"))
        channel_row.addWidget(self.channel_from)
        channel_row.addWidget(QLabel("至"))
        channel_row.addWidget(self.channel_to)
        channel_row.addStretch(1)
        range_form.addRow("通道范围", channel_row)

        sample_row = QHBoxLayout()
        self.sample_from = self._spinbox(1, self.sample_count, self.visible_range[2])
        self.sample_to = self._spinbox(1, self.sample_count, self.visible_range[3])
        sample_row.addWidget(QLabel("采样点"))
        sample_row.addWidget(self.sample_from)
        sample_row.addWidget(QLabel("至"))
        sample_row.addWidget(self.sample_to)
        sample_row.addStretch(1)
        range_form.addRow("采样点范围", sample_row)

        duration = self.sample_count / self.sampling_rate
        time_row = QHBoxLayout()
        self.time_from = self._double_spinbox(0.0, duration, 0.0, decimals=6, step=0.01, suffix=" s")
        self.time_to = self._double_spinbox(0.0, duration, duration, decimals=6, step=0.01, suffix=" s")
        time_row.addWidget(QLabel("时间"))
        time_row.addWidget(self.time_from)
        time_row.addWidget(QLabel("至"))
        time_row.addWidget(self.time_to)
        time_row.addStretch(1)
        range_form.addRow("时间范围", time_row)
        self.range_info = QLabel()
        self.range_info.setWordWrap(True)
        range_form.addRow("范围说明", self.range_info)
        for box in (self.channel_from, self.channel_to):
            box.valueChanged.connect(self._update_range_info)
        self.sample_from.valueChanged.connect(self._samples_changed)
        self.sample_to.valueChanged.connect(self._samples_changed)
        self.time_from.valueChanged.connect(self._times_changed)
        self.time_to.valueChanged.connect(self._times_changed)
        root.addWidget(range_group)

        basic_group = QGroupBox("车辆响应与方向")
        basic_form = QFormLayout(basic_group)
        self.channel_spacing = QLineEdit()
        self.channel_spacing.setValidator(QDoubleValidator(0.000001, 1_000_000.0, 6, self))
        self.channel_spacing.setPlaceholderText("必填，例如 2.0")
        self.channel_spacing.setToolTip("真实相邻通道距离 dx（米），不能填写 gauge length")
        basic_form.addRow("相邻通道距离 dx", self.channel_spacing)

        self.band_preset = QComboBox()
        self.band_preset.addItem("车辆低频：0.01–1 Hz", "paper")
        self.band_preset.addItem("仓库预设：0.08–1 Hz", "repository")
        self.band_preset.addItem("自定义", "custom")
        self.band_preset.currentIndexChanged.connect(self._apply_band_preset)
        basic_form.addRow("频段预设", self.band_preset)
        band_row = QHBoxLayout()
        self.frequency_low = self._double_spinbox(0.001, max(0.002, self.sampling_rate / 2 * 0.999), 0.01, decimals=3, step=0.01, suffix=" Hz")
        self.frequency_high = self._double_spinbox(0.002, max(0.003, self.sampling_rate / 2 * 0.999), min(1.0, self.sampling_rate / 2 * 0.999), decimals=3, step=0.1, suffix=" Hz")
        self.frequency_low.valueChanged.connect(self._mark_band_custom)
        self.frequency_high.valueChanged.connect(self._mark_band_custom)
        band_row.addWidget(self.frequency_low)
        band_row.addWidget(QLabel("至"))
        band_row.addWidget(self.frequency_high)
        band_row.addStretch(1)
        basic_form.addRow("跟踪频带", band_row)

        self.direction_combo = QComboBox()
        self.direction_combo.addItem("自动：两方向均尝试", "auto")
        self.direction_combo.addItem("通道递增方向行驶", "increasing")
        self.direction_combo.addItem("通道递减方向行驶", "decreasing")
        basic_form.addRow("车辆方向", self.direction_combo)
        self.polarity_combo = QComboBox()
        self.polarity_combo.addItem("自动：正负峰均尝试", "auto")
        self.polarity_combo.addItem("正峰", "positive")
        self.polarity_combo.addItem("负峰", "negative")
        basic_form.addRow("车辆峰极性", self.polarity_combo)
        basic_hint = QLabel(
            "轨迹仅叠加显示，运行后不会更改滤波结果。速度是沿光纤投影速度；"
            "dx 必须是相邻通道距离。"
        )
        basic_hint.setStyleSheet("color: #555;")
        basic_hint.setWordWrap(True)
        basic_form.addRow("", basic_hint)
        root.addWidget(basic_group)

        advanced_group = QGroupBox("高级拾取参数")
        advanced_form = QFormLayout(advanced_group)
        self.seed_width = self._spinbox(1, max(1, self.channel_count - 1), min(8, max(1, self.channel_count - 1)))
        advanced_form.addRow("起始检测通道数", self.seed_width)
        self.peak_prominence = self._double_spinbox(0.1, 100.0, 1.5, decimals=2, step=0.1)
        advanced_form.addRow("峰突出度（归一化）", self.peak_prominence)
        self.minimum_separation = self._double_spinbox(0.01, 3600.0, 0.8, decimals=2, step=0.1, suffix=" s")
        advanced_form.addRow("最小车辆间隔", self.minimum_separation)
        self.prominence_window = self._double_spinbox(0.1, 3600.0, 12.0, decimals=1, step=1.0, suffix=" s")
        advanced_form.addRow("峰背景时间窗", self.prominence_window)
        speed_row = QHBoxLayout()
        self.minimum_speed = self._double_spinbox(0.1, 10000.0, 2.0, decimals=1, step=1.0, suffix=" m/s")
        self.maximum_speed = self._double_spinbox(0.2, 10000.0, 60.0, decimals=1, step=1.0, suffix=" m/s")
        speed_row.addWidget(self.minimum_speed)
        speed_row.addWidget(QLabel("至"))
        speed_row.addWidget(self.maximum_speed)
        speed_row.addStretch(1)
        advanced_form.addRow("投影速度范围", speed_row)
        self.tracking_tolerance = self._double_spinbox(0.01, 60.0, 0.15, decimals=3, step=0.01, suffix=" s")
        advanced_form.addRow("卡尔曼跟踪容差", self.tracking_tolerance)
        self.minimum_coverage = self._double_spinbox(0.05, 1.0, 0.55, decimals=2, step=0.05)
        advanced_form.addRow("最小有效覆盖率", self.minimum_coverage)
        self.maximum_missed_channels = self._spinbox(0, 1000, 3)
        advanced_form.addRow("允许连续缺失通道", self.maximum_missed_channels)
        self.target_sampling_rate = self._double_spinbox(2.5, 10000.0, min(50.0, self.sampling_rate), decimals=1, step=5.0, suffix=" Hz")
        advanced_form.addRow("内部目标采样率", self.target_sampling_rate)
        root.addWidget(advanced_group)

        self.status_label = QLabel("设置范围和参数后点击“开始拾取”。")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        result_group = QGroupBox("已拾取轨迹")
        result_layout = QVBoxLayout(result_group)
        self.trajectory_table = QTableWidget(0, 8)
        self.trajectory_table.setHorizontalHeaderLabels(
            ["显示", "编号", "起始时间 (s)", "结束时间 (s)", "通道", "覆盖率", "投影速度 (m/s)", "质量"]
        )
        self.trajectory_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.trajectory_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.trajectory_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.trajectory_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.trajectory_table.horizontalHeader().setStretchLastSection(True)
        self.trajectory_table.itemChanged.connect(self._visibility_changed)
        result_layout.addWidget(self.trajectory_table)
        result_buttons = QHBoxLayout()
        self.delete_button = QPushButton("删除所选轨迹")
        self.clear_button = QPushButton("清空全部轨迹")
        self.export_button = QPushButton("导出 CSV")
        self.delete_button.clicked.connect(self._delete_selected)
        self.clear_button.clicked.connect(self._clear_all)
        self.export_button.clicked.connect(self._export_csv)
        result_buttons.addWidget(self.delete_button)
        result_buttons.addWidget(self.clear_button)
        result_buttons.addWidget(self.export_button)
        result_buttons.addStretch(1)
        result_layout.addLayout(result_buttons)
        root.addWidget(result_group, 1)

        button_row = QHBoxLayout()
        self.run_button = QPushButton("开始拾取")
        self.close_button = QPushButton("关闭")
        self.run_button.clicked.connect(self._start_tracking)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.run_button)
        button_row.addStretch(1)
        button_row.addWidget(self.close_button)
        root.addLayout(button_row)

        self._update_scope_controls()
        self._update_range_info()

    def _selected_range(self) -> Tuple[int, int, int, int]:
        if self.scope_combo.currentData() == "visible":
            return self.visible_range
        return (
            self.channel_from.value(),
            self.channel_to.value(),
            self.sample_from.value(),
            self.sample_to.value(),
        )

    def _update_scope_controls(self) -> None:
        custom = self.scope_combo.currentData() == "custom"
        for box in (self.channel_from, self.channel_to, self.sample_from, self.sample_to, self.time_from, self.time_to):
            box.setEnabled(custom)
        if not custom:
            channel_from, channel_to, sample_from, sample_to = self.visible_range
            self.channel_from.setValue(channel_from)
            self.channel_to.setValue(channel_to)
            self.sample_from.setValue(sample_from)
            self.sample_to.setValue(sample_to)
            self._sync_times_from_samples()
        self._update_range_info()

    def _sync_times_from_samples(self) -> None:
        if self._syncing_range:
            return
        self._syncing_range = True
        try:
            self.time_from.setValue((self.sample_from.value() - 1) / self.sampling_rate)
            self.time_to.setValue(self.sample_to.value() / self.sampling_rate)
        finally:
            self._syncing_range = False

    def _samples_changed(self) -> None:
        self._sync_times_from_samples()
        self._update_range_info()

    def _times_changed(self) -> None:
        if self._syncing_range or self.scope_combo.currentData() != "custom":
            self._update_range_info()
            return
        start = self.time_from.value()
        end = max(start, self.time_to.value())
        self._syncing_range = True
        try:
            self.time_to.setValue(end)
            sample_from = max(1, min(self.sample_count, int(round(start * self.sampling_rate)) + 1))
            sample_to = max(1, min(self.sample_count, int(round(end * self.sampling_rate))))
            self.sample_from.setValue(sample_from)
            self.sample_to.setValue(max(sample_from, sample_to))
        finally:
            self._syncing_range = False
        self._update_range_info()

    def _update_range_info(self) -> None:
        channel_from, channel_to, sample_from, sample_to = self._selected_range()
        if channel_from > channel_to or sample_from > sample_to:
            self.range_info.setText("范围无效：起点不能大于终点。")
            return
        duration = (sample_to - sample_from + 1) / self.sampling_rate
        self.range_info.setText(
            f"将分析 {channel_to - channel_from + 1} 个通道、"
            f"{sample_to - sample_from + 1} 个采样点，约 {duration:g} 秒。"
        )

    def _apply_band_preset(self) -> None:
        preset = self.band_preset.currentData()
        if preset == "paper":
            values = (0.01, 1.0)
        elif preset == "repository":
            values = (0.08, 1.0)
        else:
            return
        self.frequency_low.blockSignals(True)
        self.frequency_high.blockSignals(True)
        try:
            self.frequency_low.setValue(values[0])
            self.frequency_high.setValue(min(values[1], self.frequency_high.maximum()))
        finally:
            self.frequency_low.blockSignals(False)
            self.frequency_high.blockSignals(False)

    def _mark_band_custom(self) -> None:
        if self.band_preset.currentData() != "custom":
            self.band_preset.blockSignals(True)
            try:
                self.band_preset.setCurrentIndex(self.band_preset.findData("custom"))
            finally:
                self.band_preset.blockSignals(False)

    def _parameters(self) -> Dict[str, object]:
        text = self.channel_spacing.text().strip()
        if not text:
            raise ValueError("请填写真实的相邻通道距离 dx（米）")
        try:
            spacing = float(text)
        except ValueError as error:
            raise ValueError("相邻通道距离 dx 无效") from error
        return {
            "channel_spacing": spacing,
            "frequency_low": self.frequency_low.value(),
            "frequency_high": self.frequency_high.value(),
            "target_sampling_rate": self.target_sampling_rate.value(),
            "seed_width": self.seed_width.value(),
            "peak_prominence": self.peak_prominence.value(),
            "minimum_separation": self.minimum_separation.value(),
            "prominence_window": self.prominence_window.value(),
            "minimum_speed": self.minimum_speed.value(),
            "maximum_speed": self.maximum_speed.value(),
            "tracking_tolerance": self.tracking_tolerance.value(),
            "minimum_coverage": self.minimum_coverage.value(),
            "maximum_missed_channels": self.maximum_missed_channels.value(),
            "direction": self.direction_combo.currentData(),
            "polarity": self.polarity_combo.currentData(),
        }

    def settings(self) -> Dict[str, object]:
        """Return settings that are meaningful while this file remains loaded."""

        try:
            settings = self._parameters()
        except ValueError:
            settings = {}
        settings["band_preset"] = self.band_preset.currentData()
        return settings

    def _restore_settings(self, settings: Optional[Dict[str, object]]) -> None:
        if not settings:
            return
        preset_index = self.band_preset.findData(settings.get("band_preset"))
        if preset_index >= 0:
            self.band_preset.blockSignals(True)
            try:
                self.band_preset.setCurrentIndex(preset_index)
            finally:
                self.band_preset.blockSignals(False)
        direction_index = self.direction_combo.findData(settings.get("direction"))
        if direction_index >= 0:
            self.direction_combo.setCurrentIndex(direction_index)
        polarity_index = self.polarity_combo.findData(settings.get("polarity"))
        if polarity_index >= 0:
            self.polarity_combo.setCurrentIndex(polarity_index)
        if settings.get("channel_spacing") is not None:
            self.channel_spacing.setText(str(settings["channel_spacing"]))

        fields = (
            (self.frequency_low, "frequency_low", float),
            (self.frequency_high, "frequency_high", float),
            (self.target_sampling_rate, "target_sampling_rate", float),
            (self.seed_width, "seed_width", int),
            (self.peak_prominence, "peak_prominence", float),
            (self.minimum_separation, "minimum_separation", float),
            (self.prominence_window, "prominence_window", float),
            (self.minimum_speed, "minimum_speed", float),
            (self.maximum_speed, "maximum_speed", float),
            (self.tracking_tolerance, "tracking_tolerance", float),
            (self.minimum_coverage, "minimum_coverage", float),
            (self.maximum_missed_channels, "maximum_missed_channels", int),
        )
        for widget, name, converter in fields:
            if name in settings:
                try:
                    widget.blockSignals(True)
                    try:
                        widget.setValue(converter(settings[name]))
                    finally:
                        widget.blockSignals(False)
                except (TypeError, ValueError):
                    continue

    def _start_tracking(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        channel_from, channel_to, sample_from, sample_to = self._selected_range()
        if channel_from > channel_to or sample_from > sample_to:
            QMessageBox.warning(self, "范围无效", "请确认通道和采样点的起止范围。")
            return
        try:
            parameters = self._parameters()
        except ValueError as error:
            QMessageBox.warning(self, "参数无效", str(error))
            return
        data = self.source_data[channel_from - 1 : channel_to, sample_from - 1 : sample_to]
        self._set_busy(True)
        self.status_label.setText("正在进行低频预处理、峰值检测和卡尔曼轨迹关联，请稍候…")
        self._worker = _VehicleTrackingWorker(
            data,
            self.sampling_rate,
            parameters,
            channel_start=channel_from,
            time_start=(sample_from - 1) / self.sampling_rate,
            parent=self,
        )
        self._worker.resultReady.connect(self._tracking_finished)
        self._worker.errorRaised.connect(self._tracking_failed)
        self._worker.finished.connect(lambda: self._set_busy(False))
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.run_button, self.close_button, self.delete_button, self.clear_button, self.export_button):
            widget.setEnabled(not busy)

    def _tracking_finished(self, trajectories: object) -> None:
        self.trajectories = list(trajectories)
        self._populate_trajectory_table()
        self.trajectoriesChanged.emit(self.trajectories)
        count = len(self.trajectories)
        self.status_label.setText(
            f"拾取完成：找到 {count} 条有效轨迹。"
            "可在下表取消显示或删除误拾取，再关闭窗口。"
        )

    def _tracking_failed(self, details: str) -> None:
        summary = details.splitlines()[-1] if details else "未知错误"
        self.status_label.setText("拾取失败，请检查范围与参数。")
        QMessageBox.critical(self, "车辆轨迹拾取失败", summary)

    def _populate_trajectory_table(self) -> None:
        self.trajectory_table.blockSignals(True)
        try:
            self.trajectory_table.setRowCount(len(self.trajectories))
            for row, trajectory in enumerate(self.trajectories):
                visible = QTableWidgetItem()
                visible.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                visible.setCheckState(Qt.Checked if trajectory.visible else Qt.Unchecked)
                self.trajectory_table.setItem(row, 0, visible)
                values = (
                    str(trajectory.identifier),
                    f"{trajectory.start_time:.3f}",
                    f"{trajectory.end_time:.3f}",
                    f"{trajectory.start_channel} → {trajectory.end_channel}",
                    f"{trajectory.coverage:.0%}",
                    f"{trajectory.projected_speed:.2f}",
                    f"{trajectory.quality:.2f}",
                )
                for column, value in enumerate(values, start=1):
                    self.trajectory_table.setItem(row, column, QTableWidgetItem(value))
        finally:
            self.trajectory_table.blockSignals(False)

    def _visibility_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0 or not (0 <= item.row() < len(self.trajectories)):
            return
        self.trajectories[item.row()].visible = item.checkState() == Qt.Checked
        self.trajectoriesChanged.emit(self.trajectories)

    def _delete_selected(self) -> None:
        rows = sorted({index.row() for index in self.trajectory_table.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            return
        for row in rows:
            del self.trajectories[row]
        for identifier, trajectory in enumerate(self.trajectories, start=1):
            trajectory.identifier = identifier
        self._populate_trajectory_table()
        self.trajectoriesChanged.emit(self.trajectories)
        self.status_label.setText(f"已删除 {len(rows)} 条轨迹。")

    def _clear_all(self) -> None:
        if not self.trajectories:
            return
        self.trajectories = []
        self._populate_trajectory_table()
        self.trajectoriesChanged.emit(self.trajectories)
        self.status_label.setText("已清空全部轨迹。")

    def _export_csv(self) -> None:
        if not self.trajectories:
            QMessageBox.information(self, "没有轨迹", "当前没有可导出的车辆轨迹。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出车辆轨迹", "vehicle_trajectories.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            spacing = float(self.channel_spacing.text())
        except ValueError:
            QMessageBox.warning(self, "参数无效", "导出前请填写真实的相邻通道距离 dx（米）。")
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        "trajectory_id",
                        "visible",
                        "channel",
                        "time_s",
                        "relative_distance_m",
                        "coverage",
                        "projected_speed_mps",
                        "quality",
                    ]
                )
                for trajectory in self.trajectories:
                    distance = (trajectory.channels - trajectory.channels[0]) * spacing
                    for channel, time, offset in zip(trajectory.channels, trajectory.times, distance):
                        writer.writerow(
                            [
                                trajectory.identifier,
                                int(trajectory.visible),
                                int(channel),
                                f"{time:.9f}",
                                f"{offset:.6f}",
                                f"{trajectory.coverage:.6f}",
                                f"{trajectory.projected_speed:.6f}",
                                f"{trajectory.quality:.6f}",
                            ]
                        )
        except OSError as error:
            QMessageBox.critical(self, "导出失败", str(error))
            return
        self.status_label.setText(f"已导出 {len(self.trajectories)} 条轨迹：{path}")

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
