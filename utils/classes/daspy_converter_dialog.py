"""Dialog for exporting project BIN files to DASPy-readable formats."""

from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QDateTime, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .daspy_conversion import (
    FORMAT_EXTENSIONS,
    OUTPUT_FORMATS,
    BinMetadata,
    convert_bin_to_daspy,
    normalize_output_path,
    read_bin_metadata,
)


class _DASPyConversionWorker(QThread):
    completed = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, source: str, output: str, output_format: str, parameters, parent=None):
        super().__init__(parent)
        self._source = source
        self._output = output
        self._output_format = output_format
        self._parameters = dict(parameters)

    def run(self) -> None:
        try:
            output_path, metadata = convert_bin_to_daspy(
                self._source,
                self._output,
                self._output_format,
                overwrite=True,
                **self._parameters,
            )
        except Exception:
            self.failed.emit(traceback.format_exc())
        else:
            self.completed.emit(str(output_path), metadata)


class DASPyConverterDialog(QDialog):
    """Read one project BIN file and export it through DASPy's writers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BIN 转 DASPy 格式")
        self.setModal(True)
        self.resize(720, 740)
        self._metadata: Optional[BinMetadata] = None
        self._worker: Optional[_DASPyConversionWorker] = None
        self._build_ui()

    @staticmethod
    def _double_spinbox(
        minimum: float,
        maximum: float,
        value: float,
        *,
        decimals: int = 3,
        step: float = 0.1,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setSingleStep(step)
        box.setValue(value)
        box.setSuffix(suffix)
        box.setKeyboardTracking(False)
        return box

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        source_group = QGroupBox("BIN 源文件")
        source_form = QFormLayout(source_group)
        source_row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setReadOnly(True)
        self.source_edit.setPlaceholderText("请选择项目支持的 .bin 文件")
        self.source_edit.setToolTip("源文件只读，不会被转换操作修改")
        self.source_button = QPushButton("选择 BIN…")
        self.source_button.clicked.connect(self._choose_source)
        source_row.addWidget(self.source_edit)
        source_row.addWidget(self.source_button)
        source_form.addRow("源文件", source_row)
        self.source_info = QLabel("选择文件后将读取 20-float BIN 头部。")
        self.source_info.setWordWrap(True)
        source_form.addRow("头部信息", self.source_info)
        root.addWidget(source_group)

        output_group = QGroupBox("DASPy 输出")
        output_form = QFormLayout(output_group)
        self.output_format = QComboBox()
        for name, label, _extension in OUTPUT_FORMATS:
            self.output_format.addItem(label, name)
        self.output_format.currentIndexChanged.connect(self._format_changed)
        output_form.addRow("输出格式", self.output_format)
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("选择输出文件位置")
        self.output_button = QPushButton("选择位置…")
        self.output_button.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_edit)
        output_row.addWidget(self.output_button)
        output_form.addRow("输出文件", output_row)
        self.format_hint = QLabel()
        self.format_hint.setWordWrap(True)
        self.format_hint.setStyleSheet("color: #555;")
        output_form.addRow("格式说明", self.format_hint)
        root.addWidget(output_group)

        metadata_group = QGroupBox("DASPy 元数据（可手动修改）")
        metadata_form = QFormLayout(metadata_group)
        self.channel_spacing = self._double_spinbox(
            0.001, 1_000_000.0, 4.0, decimals=3, step=0.1, suffix=" m"
        )
        self.channel_spacing.setToolTip("真实相邻通道间距 dx；不是 gauge length")
        metadata_form.addRow("相邻通道间距 dx", self.channel_spacing)
        self.sampling_rate = self._double_spinbox(
            0.001, 10_000_000.0, 1000.0, decimals=3, step=1.0, suffix=" Hz"
        )
        self.sampling_rate.setToolTip("默认来自 BIN 头 header[9]；可手动覆盖")
        metadata_form.addRow("采样率 fs", self.sampling_rate)
        self.start_channel = QSpinBox()
        self.start_channel.setRange(0, 1_000_000_000)
        self.start_channel.setKeyboardTracking(False)
        metadata_form.addRow("起始通道号", self.start_channel)
        self.start_distance = self._double_spinbox(
            -1_000_000.0, 1_000_000_000.0, 0.0, decimals=3, step=1.0, suffix=" m"
        )
        metadata_form.addRow("起始距离", self.start_distance)
        self.gauge_length = self._double_spinbox(
            0.0, 1_000_000.0, 0.0, decimals=3, step=0.1, suffix=" m"
        )
        self.gauge_length.setToolTip("填 0 表示不写入 gauge length 元数据")
        metadata_form.addRow("Gauge length（0=未提供）", self.gauge_length)
        self.start_time = QDateTimeEdit()
        self.start_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_time.setCalendarPopup(True)
        self.start_time.setDateTime(QDateTime.currentDateTime())
        metadata_form.addRow("采集起始时间", self.start_time)
        self.data_type = QComboBox()
        self.data_type.setEditable(True)
        self.data_type.addItem("未指定", "")
        for value in (
            "phase shift",
            "phase change rate",
            "strain",
            "strain rate",
            "displacement",
            "velocity",
            "acceleration",
        ):
            self.data_type.addItem(value, value)
        metadata_form.addRow("数据物理量", self.data_type)
        self.scale = self._double_spinbox(
            0.000001, 1_000_000_000.0, 1.0, decimals=6, step=0.1
        )
        metadata_form.addRow("数据比例 scale", self.scale)
        root.addWidget(metadata_group)

        self.status_label = QLabel(
            "推荐导出 PKL，它会保留 DASPy Section 的数据和元数据。"
        )
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.convert_button = QPushButton("转换")
        self.close_button = QPushButton("关闭")
        self.convert_button.clicked.connect(self._start_conversion)
        self.close_button.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(self.convert_button)
        buttons.addWidget(self.close_button)
        root.addLayout(buttons)
        self._format_changed()

    def _current_format(self) -> str:
        return str(self.output_format.currentData())

    def _format_changed(self) -> None:
        output_format = self._current_format()
        hints = {
            "pkl": "推荐：DASPy PKL 会保存数组与 Section 元数据。",
            "h5": "HDF5 使用 DASPy 的默认 OptaSense QuantX 布局。",
            "sgy": "SEG-Y 可导出波形，但该格式本身不保存通道间距 dx。",
        }
        self.format_hint.setText(hints[output_format])
        self._suggest_output_path()

    def _suggest_output_path(self) -> None:
        source_text = self.source_edit.text().strip()
        if not source_text:
            return
        current_output = self.output_edit.text().strip()
        source_path = Path(source_text)
        extension = FORMAT_EXTENSIONS[self._current_format()]
        if not current_output or Path(current_output).parent == source_path.parent:
            self.output_edit.setText(
                str(source_path.with_name(f"{source_path.stem}_daspy").with_suffix(extension))
            )

    def _choose_source(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "选择 BIN 源文件", "", "BIN 数据 (*.bin)"
        )
        if not source:
            return
        try:
            metadata = read_bin_metadata(source)
        except Exception as error:
            QMessageBox.critical(self, "读取 BIN 头失败", str(error))
            return
        self._metadata = metadata
        self.source_edit.setText(str(metadata.source))
        self.source_edit.setToolTip(str(metadata.source))
        self.sampling_rate.setValue(metadata.sampling_rate)
        if metadata.start_time is not None:
            self.start_time.setDateTime(QDateTime(metadata.start_time))
            start_text = metadata.start_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            start_text = "无有效日期，保留手动填写值"
        self.source_info.setText(
            f"{metadata.channel_count} 个通道 × {metadata.sampling_times} 个采样点；"
            f"头部采样率 {metadata.sampling_rate:g} Hz；开始时间：{start_text}。"
        )
        self._suggest_output_path()

    def _choose_output(self) -> None:
        output_format = self._current_format()
        extension = FORMAT_EXTENSIONS[output_format]
        label = self.output_format.currentText()
        output, _ = QFileDialog.getSaveFileName(
            self,
            "选择 DASPy 输出文件",
            self.output_edit.text().strip(),
            f"{label} (*{extension})",
        )
        if output:
            self.output_edit.setText(str(normalize_output_path(output, output_format)))

    def _parameters(self):
        data_type = self.data_type.currentData()
        if data_type is None:
            data_type = self.data_type.currentText()
        gauge_length = self.gauge_length.value()
        return {
            "channel_spacing": self.channel_spacing.value(),
            "sampling_rate": self.sampling_rate.value(),
            "start_channel": self.start_channel.value(),
            "start_distance": self.start_distance.value(),
            "gauge_length": gauge_length if gauge_length > 0 else None,
            "start_time": self.start_time.dateTime().toPyDateTime(),
            "data_type": str(data_type or ""),
            "scale": self.scale.value(),
        }

    def _start_conversion(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        if self._metadata is None:
            QMessageBox.warning(self, "缺少源文件", "请先选择一个有效的 BIN 源文件。")
            return
        output_text = self.output_edit.text().strip()
        if not output_text:
            QMessageBox.warning(self, "缺少输出文件", "请选择 DASPy 输出文件位置。")
            return
        output_path = normalize_output_path(output_text, self._current_format())
        if output_path.exists():
            choice = QMessageBox.question(
                self,
                "覆盖输出文件？",
                f"文件已存在：\n{output_path}\n\n是否覆盖？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if choice != QMessageBox.Yes:
                return
        self.output_edit.setText(str(output_path))
        self._set_busy(True)
        self._worker = _DASPyConversionWorker(
            self.source_edit.text().strip(),
            str(output_path),
            self._current_format(),
            self._parameters(),
            parent=self,
        )
        self._worker.completed.connect(self._conversion_completed)
        self._worker.failed.connect(self._conversion_failed)
        self._worker.finished.connect(lambda: self._set_busy(False))
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self.convert_button.setEnabled(not busy)
        self.close_button.setEnabled(not busy)
        self.source_button.setEnabled(not busy)
        self.output_button.setEnabled(not busy)
        if busy:
            self.status_label.setText("正在读取 BIN 并通过 DASPy 写出文件，请稍候…")

    def _conversion_completed(self, output_path: str, metadata: BinMetadata) -> None:
        self.status_label.setText(
            f"转换完成：{Path(output_path).name}（{metadata.channel_count} 通道 × "
            f"{metadata.sampling_times} 采样点）。"
        )
        QMessageBox.information(
            self,
            "转换完成",
            f"已生成 DASPy 文件：\n{output_path}\n\n源 BIN 未被修改。",
        )

    def _conversion_failed(self, details: str) -> None:
        error = details.splitlines()[-1] if details else "未知错误"
        self.status_label.setText("转换失败；未替换目标文件。")
        QMessageBox.critical(self, "DASPy 转换失败", error)

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        super().reject()
