"""Two-dimensional DAS filtering controls and processing helpers.

The viewer stores DAS arrays as ``(channels, samples)``.  This module keeps
the processing independent from the file readers and applies a selected
operation only to the requested channel/sample rectangle.
"""

from __future__ import annotations

import traceback
from typing import Dict, Optional, Tuple

import numpy as np
from scipy.ndimage import median_filter as scipy_median_filter
from scipy.signal import iirfilter, sosfilt, zpk2sos

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


ALGORITHM_LABELS = (
    ("bandpass", "带通滤波"),
    ("lowpass", "低通滤波"),
    ("highpass", "高通滤波"),
    ("bandstop", "带阻滤波 / 工频抑制"),
    ("fk", "F-K 扇形滤波"),
    ("spike", "尖峰噪声去除"),
    ("common_mode", "共模噪声去除"),
    ("mad_normalize", "各通道 MAD 归一化"),
)


try:
    # DASPy's public basic filter functions use the same channel-by-sample
    # convention as this viewer.
    from daspy.basic_tools.filter import (  # type: ignore
        bandpass as _daspy_bandpass,
        bandstop as _daspy_bandstop,
        highpass as _daspy_highpass,
        lowpass as _daspy_lowpass,
    )

    HAS_DASPY_BASIC = True
except Exception:  # pragma: no cover - only used without DASPy installed
    _daspy_bandpass = _daspy_bandstop = _daspy_highpass = _daspy_lowpass = None
    HAS_DASPY_BASIC = False


def _fallback_iir(
    data: np.ndarray,
    sampling_rate: float,
    btype: str,
    frequencies,
    order: int,
    zero_phase: bool,
) -> np.ndarray:
    """Small SciPy fallback matching DASPy's SOS filtering convention."""

    nyquist = sampling_rate / 2.0
    wn = np.asarray(frequencies, dtype=float) / nyquist
    if np.any(wn <= 0) or np.any(wn >= 1):
        raise ValueError("滤波频率必须位于 0 和 Nyquist 频率之间")
    z, p, k = iirfilter(order, wn, btype=btype, ftype="butter", output="zpk")
    sos = zpk2sos(z, p, k)
    filtered = sosfilt(sos, data, axis=-1)
    if zero_phase:
        filtered = sosfilt(sos, filtered[..., ::-1], axis=-1)[..., ::-1]
    return filtered


def _validate_frequency_range(
    sampling_rate: float, low: float, high: Optional[float] = None
) -> None:
    nyquist = float(sampling_rate) / 2.0
    if low <= 0 or low >= nyquist:
        raise ValueError(f"频率必须大于 0 且小于 Nyquist 频率 {nyquist:g} Hz")
    if high is not None and (high <= low or high >= nyquist):
        raise ValueError(
            f"高频必须大于低频且小于 Nyquist 频率 {nyquist:g} Hz"
        )


def _fallback_spike_removal(
    data: np.ndarray, channel_window: int, sample_window: int, threshold: float
) -> np.ndarray:
    """Robust local fallback for DASPy's median-based spike removal."""

    absolute = np.abs(data)
    medians = scipy_median_filter(
        absolute, size=(channel_window, 1), mode="nearest"
    )
    medians = scipy_median_filter(
        medians, size=(1, sample_window), mode="nearest"
    )
    bad = (medians > 0) & (
        absolute / np.maximum(medians, np.finfo(float).eps) > threshold
    )
    if not np.any(bad):
        return data.copy()

    result = data.copy()
    # Interpolate along the channel axis, preserving the time samples.
    for sample in np.flatnonzero(np.any(bad, axis=0)):
        good = ~bad[:, sample]
        if np.count_nonzero(good) == 0:
            continue
        result[~good, sample] = np.interp(
            np.flatnonzero(~good),
            np.flatnonzero(good),
            data[good, sample],
        )
    return result


def _fallback_common_mode(data: np.ndarray, method: str) -> np.ndarray:
    common = np.median(data, axis=0) if method == "median" else np.mean(data, axis=0)
    denominator = float(np.sum(common**2))
    if denominator <= np.finfo(float).eps:
        return data.copy()
    projection = np.sum(data * common[np.newaxis, :], axis=1) / denominator
    return data - projection[:, np.newaxis] * common[np.newaxis, :]


def _mad_normalize_per_channel(data: np.ndarray) -> np.ndarray:
    """Return robust z-scores using each channel's selected samples only."""

    if not np.all(np.isfinite(data)):
        raise ValueError("MAD 归一化输入不能包含 NaN 或无穷值")

    # Use float64 intermediates so the median and scale estimate remain stable
    # even though the viewer stores its data as float32.
    values = np.asarray(data, dtype=np.float64)
    medians = np.median(values, axis=1, keepdims=True)
    mad = np.median(np.abs(values - medians), axis=1, keepdims=True)
    robust_scale = 1.4826 * mad

    # A channel with no variation has no defined scale.  Its centred signal is
    # zero, so represent it as zeros instead of producing NaN or infinity.
    normalized = np.zeros_like(values)
    amplitudes = np.max(np.abs(values), axis=1, keepdims=True)
    tolerance = np.finfo(np.float64).eps * np.maximum(
        amplitudes, np.finfo(np.float64).tiny
    )
    np.divide(values - medians, robust_scale, out=normalized, where=mad > tolerance)
    return normalized.astype(np.float32)


def apply_das_filter(
    data: np.ndarray,
    sampling_rate: float,
    algorithm: str,
    parameters: Dict[str, object],
) -> np.ndarray:
    """Apply one DASPy-compatible operation to a 2-D array."""

    array = np.asarray(data, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError("DAS 数据必须是二维数组（通道 × 采样点）")
    if array.shape[0] == 0 or array.shape[1] == 0:
        raise ValueError("选择的滤波范围为空")

    if algorithm in {"bandpass", "bandstop"}:
        low = float(parameters["frequency_low"])
        high = float(parameters["frequency_high"])
        _validate_frequency_range(sampling_rate, low, high)
        order = int(parameters["order"])
        zero_phase = bool(parameters["zero_phase"])
        function = _daspy_bandpass if algorithm == "bandpass" else _daspy_bandstop
        if HAS_DASPY_BASIC:
            result = function(
                array,
                fs=float(sampling_rate),
                freqmin=low,
                freqmax=high,
                corners=order,
                zerophase=zero_phase,
            )
        else:
            result = _fallback_iir(
                array, sampling_rate, algorithm, (low, high), order, zero_phase
            )
    elif algorithm in {"lowpass", "highpass"}:
        frequency = float(parameters["frequency"])
        _validate_frequency_range(sampling_rate, frequency)
        order = int(parameters["order"])
        zero_phase = bool(parameters["zero_phase"])
        function = _daspy_lowpass if algorithm == "lowpass" else _daspy_highpass
        if HAS_DASPY_BASIC:
            result = function(
                array,
                fs=float(sampling_rate),
                freq=frequency,
                corners=order,
                zerophase=zero_phase,
            )
        else:
            result = _fallback_iir(
                array, sampling_rate, algorithm, frequency, order, zero_phase
            )
    elif algorithm == "fk":
        channel_spacing = float(parameters["channel_spacing"])
        if channel_spacing <= 0:
            raise ValueError("F-K 滤波需要大于 0 的相邻通道距离 dx（米）")

        mode = str(parameters["fk_mode"])
        if mode not in {"retain", "remove"}:
            raise ValueError("F-K 模式只能是保留扇形或去除扇形")
        direction = str(parameters["fk_direction"])
        direction_flags = {
            "both": 0,
            # DASPy's flag excludes the specified sign from the fan mask.
            # Invert it here so the UI labels retain their physical meaning.
            "positive": -1,
            "negative": 1,
        }
        if direction not in direction_flags:
            raise ValueError("F-K 传播方向无效")

        def optional_limit(name: str) -> Optional[float]:
            value = float(parameters[name])
            return value if value > 0 else None

        fmin = optional_limit("fk_frequency_low")
        fmax = optional_limit("fk_frequency_high")
        vmin = optional_limit("fk_velocity_low")
        vmax = optional_limit("fk_velocity_high")
        nyquist = float(sampling_rate) / 2.0
        if fmin is not None and fmin >= nyquist:
            raise ValueError("F-K 频率下限必须小于 Nyquist 频率")
        if fmax is not None and fmax >= nyquist:
            raise ValueError("F-K 频率上限必须小于 Nyquist 频率")
        if fmin is not None and fmax is not None and fmin >= fmax:
            raise ValueError("F-K 频率下限必须小于频率上限")
        if vmin is not None and vmax is not None and vmin >= vmax:
            raise ValueError("F-K 表观速度下限必须小于速度上限")
        if (
            fmin is None
            and fmax is None
            and vmin is None
            and vmax is None
            and direction == "both"
        ):
            raise ValueError("请至少设置一个 F-K 频率/速度限制或传播方向")

        try:
            from daspy.advanced_tools import fk_filter  # type: ignore
        except Exception as error:
            raise RuntimeError("F-K 滤波需要可用的 DASPy advanced_tools") from error
        result = fk_filter(
            array,
            dx=channel_spacing,
            fs=float(sampling_rate),
            taper=(0.02, 0.05),
            pad="default",
            mode=mode,
            fmin=fmin,
            fmax=fmax,
            vmin=vmin,
            vmax=vmax,
            edge=0.1,
            flag=direction_flags[direction],
        )
    elif algorithm == "spike":
        channel_window = max(1, int(parameters["channel_window"]))
        sample_window = max(1, int(parameters["sample_window"]))
        threshold = float(parameters["threshold"])
        try:
            from daspy.advanced_tools.denoising import spike_removal  # type: ignore
        except Exception:
            result = _fallback_spike_removal(
                array, channel_window, sample_window, threshold
            )
        else:
            try:
                result = spike_removal(
                    array,
                    nch=channel_window,
                    nsp=sample_window,
                    thresh=threshold,
                )
            except ValueError as error:
                # DASPy deliberately raises when every channel in a sample is
                # marked as an outlier.  Fall back to the guarded local
                # implementation so one bad window does not abort the dialog.
                if "all channels are outliers" not in str(error):
                    raise
                result = _fallback_spike_removal(
                    array, channel_window, sample_window, threshold
                )
    elif algorithm == "common_mode":
        method = str(parameters["method"])
        if method not in {"median", "mean"}:
            raise ValueError("共模噪声方法只能是 median 或 mean")
        try:
            from daspy.advanced_tools.denoising import (  # type: ignore
                common_mode_noise_removal,
            )
        except Exception:
            result = _fallback_common_mode(array, method)
        else:
            result = common_mode_noise_removal(array, method=method)
    elif algorithm == "mad_normalize":
        result = _mad_normalize_per_channel(array)
    else:
        raise ValueError(f"不支持的滤波算法: {algorithm}")

    result = np.asarray(result, dtype=np.float32)
    if result.shape != array.shape:
        raise ValueError("滤波器改变了数据形状，已拒绝应用结果")
    if not np.all(np.isfinite(result)):
        raise ValueError("滤波结果包含 NaN 或无穷值")
    return result


class _FilterWorker(QThread):
    resultReady = pyqtSignal(object)
    errorRaised = pyqtSignal(str)

    def __init__(self, data, sampling_rate, algorithm, parameters, parent=None):
        super().__init__(parent)
        self._data = np.asarray(data, dtype=np.float32).copy()
        self._sampling_rate = float(sampling_rate)
        self._algorithm = algorithm
        self._parameters = dict(parameters)

    def run(self) -> None:
        try:
            result = apply_das_filter(
                self._data,
                self._sampling_rate,
                self._algorithm,
                self._parameters,
            )
        except Exception:
            self.errorRaised.emit(traceback.format_exc())
        else:
            self.resultReady.emit(result)


class DASFilterDialog(QDialog):
    """Modal editor for applying filters to a selected DAS rectangle."""

    previewReady = pyqtSignal(object, str)
    committed = pyqtSignal(object)

    def __init__(
        self,
        data: np.ndarray,
        sampling_rate: float,
        visible_range: Optional[Tuple[int, int, int, int]] = None,
        settings: Optional[Dict[str, object]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("DAS 二维滤波与去噪")
        self.setModal(True)
        self.resize(620, 620)

        self.original_data = np.asarray(data, dtype=np.float32).copy()
        if self.original_data.ndim != 2 or min(self.original_data.shape) == 0:
            raise ValueError("DAS 数据必须是非空二维数组")
        self.working_data = self.original_data.copy()
        self.sampling_rate = float(sampling_rate)
        self.channel_count, self.sample_count = self.working_data.shape
        self.visible_range = self._normalize_range(
            visible_range or (1, self.channel_count, 1, self.sample_count)
        )
        self._worker: Optional[_FilterWorker] = None
        self._pending_slice = None
        self._pending_description = ""
        self._operation_count = 0
        self._syncing_range = False
        self._build_ui()
        self._restore_filter_settings(settings)

    def _normalize_range(self, values: Tuple[int, int, int, int]):
        channel_from, channel_to, sample_from, sample_to = map(int, values)
        return (
            max(1, min(self.channel_count, channel_from)),
            max(1, min(self.channel_count, channel_to)),
            max(1, min(self.sample_count, sample_from)),
            max(1, min(self.sample_count, sample_to)),
        )

    @staticmethod
    def _make_spinbox(minimum, maximum, value):
        box = QSpinBox()
        box.setRange(int(minimum), int(maximum))
        box.setValue(int(value))
        box.setKeyboardTracking(False)
        return box

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        algorithm_group = QGroupBox("算法")
        algorithm_form = QFormLayout(algorithm_group)
        self.algorithm_combo = QComboBox()
        for key, label in ALGORITHM_LABELS:
            self.algorithm_combo.addItem(label, key)
        self.algorithm_combo.currentIndexChanged.connect(self._update_parameter_visibility)
        algorithm_form.addRow("处理方法", self.algorithm_combo)
        backend = "DASPy" if HAS_DASPY_BASIC else "SciPy 兼容实现"
        backend_label = QLabel(f"基础滤波后端：{backend}")
        backend_label.setStyleSheet("color: #555;")
        algorithm_form.addRow("", backend_label)
        root.addWidget(algorithm_group)

        range_group = QGroupBox("处理范围（包含起止点）")
        range_form = QFormLayout(range_group)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("当前查看范围", "visible")
        self.scope_combo.addItem("自定义范围", "custom")
        self.scope_combo.currentIndexChanged.connect(self._update_range_controls)
        range_form.addRow("作用范围", self.scope_combo)

        channel_row = QHBoxLayout()
        self.channel_from = self._make_spinbox(1, self.channel_count, self.visible_range[0])
        self.channel_to = self._make_spinbox(1, self.channel_count, self.visible_range[1])
        channel_row.addWidget(QLabel("通道"))
        channel_row.addWidget(self.channel_from)
        channel_row.addWidget(QLabel("至"))
        channel_row.addWidget(self.channel_to)
        channel_row.addStretch(1)
        range_form.addRow("通道范围", channel_row)

        sample_row = QHBoxLayout()
        self.sample_from = self._make_spinbox(1, self.sample_count, self.visible_range[2])
        self.sample_to = self._make_spinbox(1, self.sample_count, self.visible_range[3])
        sample_row.addWidget(QLabel("采样点"))
        sample_row.addWidget(self.sample_from)
        sample_row.addWidget(QLabel("至"))
        sample_row.addWidget(self.sample_to)
        sample_row.addStretch(1)
        range_form.addRow("采样点范围", sample_row)

        time_row = QHBoxLayout()
        duration = self.sample_count / self.sampling_rate
        self.time_from = QDoubleSpinBox()
        self.time_to = QDoubleSpinBox()
        for box in (self.time_from, self.time_to):
            box.setRange(0.0, duration)
            box.setDecimals(6)
            box.setSingleStep(0.01)
        time_row.addWidget(QLabel("时间 (s)"))
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

        parameter_group = QGroupBox("算法参数")
        parameter_form = QFormLayout(parameter_group)

        self.frequency_low = QDoubleSpinBox()
        self.frequency_high = QDoubleSpinBox()
        nyquist = max(0.01, self.sampling_rate / 2.0)
        for box in (self.frequency_low, self.frequency_high):
            box.setRange(0.001, max(0.002, nyquist * 0.999))
            box.setDecimals(3)
            box.setSingleStep(1.0)
        self.frequency_low.setValue(min(5.0, nyquist * 0.1))
        self.frequency_high.setValue(min(120.0, nyquist * 0.8))
        parameter_form.addRow("低频 (Hz)", self.frequency_low)
        parameter_form.addRow("高频 (Hz)", self.frequency_high)

        self.frequency = QDoubleSpinBox()
        self.frequency.setRange(0.001, max(0.002, nyquist * 0.999))
        self.frequency.setDecimals(3)
        self.frequency.setSingleStep(1.0)
        self.frequency.setValue(min(120.0, nyquist * 0.8))
        parameter_form.addRow("截止频率 (Hz)", self.frequency)

        self.order = self._make_spinbox(1, 12, 4)
        parameter_form.addRow("滤波阶数", self.order)
        self.zero_phase = QCheckBox("启用零相位（前后向滤波）")
        self.zero_phase.setChecked(True)
        parameter_form.addRow("相位", self.zero_phase)

        self.channel_window = self._make_spinbox(
            1, max(1, self.channel_count), min(50, self.channel_count)
        )
        self.sample_window = self._make_spinbox(
            1, max(1, self.sample_count), min(5, self.sample_count)
        )
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(1.0, 1000.0)
        self.threshold.setValue(10.0)
        self.threshold.setDecimals(2)
        parameter_form.addRow("尖峰通道窗口", self.channel_window)
        parameter_form.addRow("尖峰采样窗口", self.sample_window)
        parameter_form.addRow("尖峰阈值倍数", self.threshold)

        self.common_method = QComboBox()
        self.common_method.addItem("中位数", "median")
        self.common_method.addItem("均值", "mean")
        parameter_form.addRow("共模估计", self.common_method)

        self.channel_spacing = QDoubleSpinBox()
        self.channel_spacing.setRange(0.001, 100000.0)
        self.channel_spacing.setDecimals(3)
        self.channel_spacing.setSingleStep(0.1)
        self.channel_spacing.setValue(1.0)
        self.channel_spacing.setSuffix(" m")
        parameter_form.addRow("相邻通道距离 dx", self.channel_spacing)

        self.fk_mode = QComboBox()
        self.fk_mode.addItem("保留扇形内信号", "retain")
        self.fk_mode.addItem("去除扇形内信号", "remove")
        parameter_form.addRow("F-K 操作", self.fk_mode)

        self.fk_direction = QComboBox()
        self.fk_direction.addItem("双向", "both")
        self.fk_direction.addItem("仅保留正表观速度", "positive")
        self.fk_direction.addItem("仅保留负表观速度", "negative")
        parameter_form.addRow("传播方向", self.fk_direction)

        self.fk_frequency_low = QDoubleSpinBox()
        self.fk_frequency_high = QDoubleSpinBox()
        for box in (self.fk_frequency_low, self.fk_frequency_high):
            box.setRange(0.0, max(0.001, nyquist * 0.999))
            box.setDecimals(3)
            box.setSingleStep(1.0)
            box.setSuffix(" Hz")
        parameter_form.addRow("F-K 频率下限", self.fk_frequency_low)
        parameter_form.addRow("F-K 频率上限", self.fk_frequency_high)

        self.fk_velocity_low = QDoubleSpinBox()
        self.fk_velocity_high = QDoubleSpinBox()
        for box in (self.fk_velocity_low, self.fk_velocity_high):
            box.setRange(0.0, 1000000.0)
            box.setDecimals(1)
            box.setSingleStep(10.0)
            box.setSuffix(" m/s")
        parameter_form.addRow("表观速度下限", self.fk_velocity_low)
        parameter_form.addRow("表观速度上限", self.fk_velocity_high)

        self.fk_hint = QLabel(
            "F-K：频率和速度填 0 表示不限制；至少设置一个限制或方向。"
            "dx 必须是实际相邻通道距离，不是 gauge length。"
        )
        self.fk_hint.setWordWrap(True)
        self.fk_hint.setStyleSheet("color: #555;")
        parameter_form.addRow("", self.fk_hint)
        root.addWidget(parameter_group)

        self.status_label = QLabel("修改参数后点击“应用并预览”；可连续应用多个步骤。")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        close_hint = QLabel(
            "提示：成功预览后，点“确定并关闭”或右上角 × 都会保留结果；"
            "“取消并还原”会撤销本次会话中的全部滤波。"
        )
        close_hint.setWordWrap(True)
        close_hint.setStyleSheet("color: #555;")
        root.addWidget(close_hint)

        button_row = QHBoxLayout()
        self.apply_button = QPushButton("应用并预览")
        self.reset_button = QPushButton("恢复本次会话")
        self.accept_button = QPushButton("确定并关闭")
        self.cancel_button = QPushButton("取消")
        self.accept_button.setToolTip("保留当前预览结果并关闭窗口")
        self.cancel_button.setText("取消并还原")
        self.cancel_button.setToolTip("撤销本次会话中的全部滤波，并恢复到打开窗口前的数据")
        self.apply_button.clicked.connect(self._start_filter)
        self.reset_button.clicked.connect(self._reset)
        self.accept_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        for button in (
            self.apply_button,
            self.reset_button,
            self.accept_button,
            self.cancel_button,
        ):
            button_row.addWidget(button)
        root.addLayout(button_row)

        self._update_parameter_visibility()
        self._update_range_controls()
        self._update_range_info()

    def filter_settings(self) -> Dict[str, object]:
        """Return the algorithm settings to reuse while the same file is open."""
        return {
            "algorithm": self.algorithm_combo.currentData(),
            "frequency_low": self.frequency_low.value(),
            "frequency_high": self.frequency_high.value(),
            "frequency": self.frequency.value(),
            "order": self.order.value(),
            "zero_phase": self.zero_phase.isChecked(),
            "channel_window": self.channel_window.value(),
            "sample_window": self.sample_window.value(),
            "threshold": self.threshold.value(),
            "common_method": self.common_method.currentData(),
            "channel_spacing": self.channel_spacing.value(),
            "fk_mode": self.fk_mode.currentData(),
            "fk_direction": self.fk_direction.currentData(),
            "fk_frequency_low": self.fk_frequency_low.value(),
            "fk_frequency_high": self.fk_frequency_high.value(),
            "fk_velocity_low": self.fk_velocity_low.value(),
            "fk_velocity_high": self.fk_velocity_high.value(),
        }

    def _restore_filter_settings(self, settings: Optional[Dict[str, object]]) -> None:
        """Restore valid settings saved by the main window for this file."""
        if not settings:
            return

        algorithm_index = self.algorithm_combo.findData(settings.get("algorithm"))
        if algorithm_index >= 0:
            self.algorithm_combo.setCurrentIndex(algorithm_index)
        common_method_index = self.common_method.findData(
            settings.get("common_method")
        )
        if common_method_index >= 0:
            self.common_method.setCurrentIndex(common_method_index)
        fk_mode_index = self.fk_mode.findData(settings.get("fk_mode"))
        if fk_mode_index >= 0:
            self.fk_mode.setCurrentIndex(fk_mode_index)
        fk_direction_index = self.fk_direction.findData(settings.get("fk_direction"))
        if fk_direction_index >= 0:
            self.fk_direction.setCurrentIndex(fk_direction_index)

        def restore_value(widget, name: str, converter) -> None:
            if name not in settings:
                return
            try:
                widget.setValue(converter(settings[name]))
            except (TypeError, ValueError):
                return

        restore_value(self.frequency_low, "frequency_low", float)
        restore_value(self.frequency_high, "frequency_high", float)
        restore_value(self.frequency, "frequency", float)
        restore_value(self.order, "order", int)
        restore_value(self.channel_window, "channel_window", int)
        restore_value(self.sample_window, "sample_window", int)
        restore_value(self.threshold, "threshold", float)
        restore_value(self.channel_spacing, "channel_spacing", float)
        restore_value(self.fk_frequency_low, "fk_frequency_low", float)
        restore_value(self.fk_frequency_high, "fk_frequency_high", float)
        restore_value(self.fk_velocity_low, "fk_velocity_low", float)
        restore_value(self.fk_velocity_high, "fk_velocity_high", float)
        if isinstance(settings.get("zero_phase"), bool):
            self.zero_phase.setChecked(settings["zero_phase"])

        self._update_parameter_visibility()

    def _update_parameter_visibility(self) -> None:
        algorithm = self.algorithm_combo.currentData()
        frequency_pair = algorithm in {"bandpass", "bandstop"}
        one_frequency = algorithm in {"lowpass", "highpass"}
        form = self.frequency_low.parentWidget().layout()
        self._set_form_row_visible(form, 0, frequency_pair)
        self._set_form_row_visible(form, 1, frequency_pair)
        self._set_form_row_visible(form, 2, one_frequency)
        order_visible = frequency_pair or one_frequency
        self._set_form_row_visible(form, 3, order_visible)
        self._set_form_row_visible(form, 4, order_visible)
        spike_visible = algorithm == "spike"
        for row in (5, 6, 7):
            self._set_form_row_visible(form, row, spike_visible)
        self._set_form_row_visible(form, 8, algorithm == "common_mode")
        fk_visible = algorithm == "fk"
        for row in range(9, 17):
            self._set_form_row_visible(form, row, fk_visible)

    @staticmethod
    def _set_form_row_visible(layout, row: int, visible: bool) -> None:
        for role in (QFormLayout.LabelRole, QFormLayout.FieldRole):
            item = layout.itemAt(row, role)
            if item and item.widget():
                item.widget().setVisible(visible)

    def _update_range_controls(self) -> None:
        enabled = self.scope_combo.currentData() == "custom"
        for box in (
            self.channel_from,
            self.channel_to,
            self.sample_from,
            self.sample_to,
            self.time_from,
            self.time_to,
        ):
            box.setEnabled(enabled)
        if not enabled:
            self.channel_from.setValue(self.visible_range[0])
            self.channel_to.setValue(self.visible_range[1])
            self.sample_from.setValue(self.visible_range[2])
            self.sample_to.setValue(self.visible_range[3])
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
        end = self.time_to.value()
        if end < start:
            end = start
            self._syncing_range = True
            try:
                self.time_to.setValue(end)
            finally:
                self._syncing_range = False
        sample_from = max(1, min(self.sample_count, int(round(start * self.sampling_rate)) + 1))
        sample_to = max(1, min(self.sample_count, int(round(end * self.sampling_rate))))
        if sample_to < sample_from:
            sample_to = sample_from
        self._syncing_range = True
        try:
            self.sample_from.setValue(sample_from)
            self.sample_to.setValue(sample_to)
        finally:
            self._syncing_range = False
        self._update_range_info()

    def _update_range_info(self) -> None:
        channel_from, channel_to, sample_from, sample_to = self._selected_range()
        if channel_from > channel_to or sample_from > sample_to:
            self.range_info.setText("范围无效：起点必须不大于终点。")
            return
        duration = (sample_to - sample_from + 1) / self.sampling_rate
        self.range_info.setText(
            f"将处理 {channel_to - channel_from + 1} 个通道、"
            f"{sample_to - sample_from + 1} 个采样点，约 {duration:g} 秒 "
            f"（采样率 {self.sampling_rate:g} Hz）。"
        )

    def _selected_range(self) -> Tuple[int, int, int, int]:
        if self.scope_combo.currentData() == "visible":
            return self.visible_range
        return (
            self.channel_from.value(),
            self.channel_to.value(),
            self.sample_from.value(),
            self.sample_to.value(),
        )

    def _parameters(self) -> Dict[str, object]:
        algorithm = self.algorithm_combo.currentData()
        if algorithm in {"bandpass", "bandstop"}:
            return {
                "frequency_low": self.frequency_low.value(),
                "frequency_high": self.frequency_high.value(),
                "order": self.order.value(),
                "zero_phase": self.zero_phase.isChecked(),
            }
        if algorithm in {"lowpass", "highpass"}:
            return {
                "frequency": self.frequency.value(),
                "order": self.order.value(),
                "zero_phase": self.zero_phase.isChecked(),
            }
        if algorithm == "spike":
            return {
                "channel_window": self.channel_window.value(),
                "sample_window": self.sample_window.value(),
                "threshold": self.threshold.value(),
            }
        if algorithm == "fk":
            return {
                "channel_spacing": self.channel_spacing.value(),
                "fk_mode": self.fk_mode.currentData(),
                "fk_direction": self.fk_direction.currentData(),
                "fk_frequency_low": self.fk_frequency_low.value(),
                "fk_frequency_high": self.fk_frequency_high.value(),
                "fk_velocity_low": self.fk_velocity_low.value(),
                "fk_velocity_high": self.fk_velocity_high.value(),
            }
        if algorithm == "mad_normalize":
            return {}
        return {"method": self.common_method.currentData()}

    def _start_filter(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        channel_from, channel_to, sample_from, sample_to = self._selected_range()
        if channel_from > channel_to or sample_from > sample_to:
            QMessageBox.warning(self, "范围无效", "请确认通道和采样点的起止范围。")
            return
        algorithm = self.algorithm_combo.currentData()
        parameters = self._parameters()
        data_slice = self.working_data[
            channel_from - 1 : channel_to,
            sample_from - 1 : sample_to,
        ]
        label = self.algorithm_combo.currentText()
        self._pending_slice = (channel_from, channel_to, sample_from, sample_to)
        self._pending_description = (
            f"{label}：通道 {channel_from}-{channel_to}，采样点 {sample_from}-{sample_to}"
        )
        self._set_busy(True)
        self._worker = _FilterWorker(
            data_slice,
            self.sampling_rate,
            algorithm,
            parameters,
            parent=self,
        )
        self._worker.resultReady.connect(self._filter_finished)
        self._worker.errorRaised.connect(self._filter_failed)
        self._worker.finished.connect(lambda: self._set_busy(False))
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self.apply_button.setEnabled(not busy)
        self.reset_button.setEnabled(not busy)
        self.accept_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)
        if busy:
            self.status_label.setText("正在处理所选范围，请稍候……")

    def _filter_finished(self, result) -> None:
        channel_from, channel_to, sample_from, sample_to = self._pending_slice
        self.working_data[
            channel_from - 1 : channel_to,
            sample_from - 1 : sample_to,
        ] = result
        self._operation_count += 1
        self.status_label.setText(
            f"已完成第 {self._operation_count} 个步骤：{self._pending_description}。"
        )
        self.previewReady.emit(self.working_data.copy(), self._pending_description)

    def _filter_failed(self, details: str) -> None:
        self.status_label.setText("处理失败，请检查参数或缩小范围。")
        QMessageBox.critical(self, "滤波失败", details.splitlines()[-1])

    def _reset(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.working_data = self.original_data.copy()
        self._operation_count = 0
        self.status_label.setText("已恢复本次对话框打开时的数据。")
        self.previewReady.emit(self.working_data.copy(), "恢复原始预览")

    def accept(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.committed.emit(self.working_data.copy())
        super().accept()

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        super().reject()

    def closeEvent(self, event) -> None:
        """Keep a completed preview when the title-bar close button is used.

        The explicit Cancel button (and Escape) still call ``reject()`` and
        therefore let the main window restore the data from before this dialog
        was opened.  Closing with the title-bar button is treated like Accept
        only after at least one filter operation completed successfully.
        """
        if self._worker is not None and self._worker.isRunning():
            event.ignore()
            return

        if self._operation_count > 0:
            self.accept()
            event.accept()
            return

        super().closeEvent(event)
