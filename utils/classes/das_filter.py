"""Two-dimensional DAS filtering controls and processing helpers.

The viewer stores DAS arrays as ``(channels, samples)``.  This module keeps
the processing independent from the file readers and applies a selected
operation only to the requested channel/sample rectangle.
"""

from __future__ import annotations

import traceback
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

import numpy as np
from scipy.ndimage import median_filter as scipy_median_filter
from scipy.signal import iirfilter, sosfilt, zpk2sos

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .data_group import ensure_memory_budget, format_bytes
from .filter_pipeline import (
    FilterPipeline,
    FilterStep,
    clone_steps,
    replay_filter_pipeline,
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


class _PipelineWorker(QThread):
    resultReady = pyqtSignal(object)
    errorRaised = pyqtSignal(str)

    def __init__(
        self,
        raw_data,
        sampling_rate,
        steps: Iterable[FilterStep],
        segment_ranges: Sequence[Tuple[int, int]],
        parent=None,
    ):
        super().__init__(parent)
        self._raw_data = np.asarray(raw_data, dtype=np.float32).copy()
        self._sampling_rate = float(sampling_rate)
        self._steps = clone_steps(steps)
        self._segment_ranges = list(segment_ranges)

    def run(self) -> None:
        try:
            result = replay_filter_pipeline(
                self._raw_data,
                self._sampling_rate,
                self._steps,
                apply_das_filter,
                self._segment_ranges,
            )
        except Exception:
            self.errorRaised.emit(traceback.format_exc())
        else:
            self.resultReady.emit(result)


class DASFilterDialog(QDialog):
    """Persistent non-modal editor for an ordered, replayable filter chain."""

    previewReady = pyqtSignal(object, str)
    committed = pyqtSignal(object)
    pipelineChanged = pyqtSignal(object)
    settingsChanged = pyqtSignal(object)
    autoReapplyChanged = pyqtSignal(bool)

    def __init__(
        self,
        data: np.ndarray,
        sampling_rate: float,
        visible_range: Optional[Tuple[int, int, int, int]] = None,
        settings: Optional[Dict[str, object]] = None,
        steps: Optional[Iterable[FilterStep]] = None,
        current_data: Optional[np.ndarray] = None,
        segment_ranges: Optional[Sequence[Tuple[int, int]]] = None,
        previous_steps: Optional[Iterable[FilterStep]] = None,
        auto_reapply: bool = True,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("DAS 二维滤波工具")
        self.setModal(False)
        self.setWindowFlag(Qt.Tool, True)
        self.resize(760, 780)
        self.setMinimumSize(680, 680)

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
        self.visible_range = self._normalize_range(
            visible_range or (1, self.channel_count, 1, self.sample_count)
        )
        self.segment_ranges = list(segment_ranges or [(0, self.sample_count)])
        self.pipeline = FilterPipeline(steps)
        self.committed_steps = self.pipeline.steps()
        self.previous_steps = clone_steps(previous_steps or [])
        self.auto_reapply = bool(auto_reapply)
        self._worker: Optional[_PipelineWorker] = None
        self._pending_steps: List[FilterStep] = []
        self._pending_description = ""
        self._pending_selected_row = -1
        self._pending_commit = False
        self._syncing_range = False
        self._refreshing_history = False
        self._loading_step = False
        self._build_ui()
        self._restore_filter_settings(settings)
        self._refresh_history()

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

        self.processing_mode_combo = QComboBox()
        self.processing_mode_combo.addItem("整体连续处理（跨文件边界）", "continuous")
        self.processing_mode_combo.addItem("按文件分段处理", "per_segment")
        self.processing_mode_combo.setEnabled(len(self.segment_ranges) > 1)
        self.processing_mode_combo.setToolTip(
            "确认文件连续时可整体处理；不确定时按文件分段可避免滤波跨越接缝。"
        )
        range_form.addRow("拼接处理", self.processing_mode_combo)

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

        history_group = QGroupBox("已应用滤波链（勾选表示启用）")
        history_layout = QVBoxLayout(history_group)
        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(150)
        self.history_list.setAlternatingRowColors(True)
        self.history_list.itemChanged.connect(self._history_item_changed)
        self.history_list.currentRowChanged.connect(self._load_selected_step)
        history_layout.addWidget(self.history_list)

        history_button_row = QHBoxLayout()
        self.update_step_button = QPushButton("更新选中")
        self.delete_step_button = QPushButton("删除")
        self.move_up_button = QPushButton("上移")
        self.move_down_button = QPushButton("下移")
        self.clear_steps_button = QPushButton("清空")
        self.reuse_steps_button = QPushButton("应用上一组滤波链")
        self.update_step_button.clicked.connect(self._update_selected_step)
        self.delete_step_button.clicked.connect(self._delete_selected_step)
        self.move_up_button.clicked.connect(lambda: self._move_selected_step(-1))
        self.move_down_button.clicked.connect(lambda: self._move_selected_step(1))
        self.clear_steps_button.clicked.connect(self._clear_pipeline)
        self.reuse_steps_button.clicked.connect(self._reuse_previous_pipeline)
        for button in (
            self.update_step_button,
            self.delete_step_button,
            self.move_up_button,
            self.move_down_button,
            self.clear_steps_button,
            self.reuse_steps_button,
        ):
            history_button_row.addWidget(button)
        history_layout.addLayout(history_button_row)
        self.auto_reapply_checkbox = QCheckBox("切换文件后自动应用当前滤波链")
        self.auto_reapply_checkbox.setChecked(self.auto_reapply)
        self.auto_reapply_checkbox.setToolTip(
            "自动从新文件的导入基线重新回放相同步骤；不兼容时保持原始数据并提示"
        )
        self.auto_reapply_checkbox.toggled.connect(self._auto_reapply_toggled)
        history_layout.addWidget(self.auto_reapply_checkbox)
        root.addWidget(history_group, 1)

        self.status_label = QLabel("设置参数后点击“添加并预览”，滤波链会从导入基线重新计算。")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        close_hint = QLabel("关闭工具窗会保留当前预览；“撤销未确认”恢复到最近一次确认的滤波链。")
        close_hint.setWordWrap(True)
        close_hint.setStyleSheet("color: #555;")
        root.addWidget(close_hint)

        button_row = QHBoxLayout()
        self.apply_button = QPushButton("添加并预览")
        self.reset_button = QPushButton("恢复导入原始数据")
        self.accept_button = QPushButton("确认当前结果")
        self.cancel_button = QPushButton("撤销未确认")
        self.close_button = QPushButton("关闭")
        self.accept_button.setToolTip("把当前滤波链设为新的确认点")
        self.cancel_button.setToolTip("恢复到最近一次点击“确认当前结果”时的滤波链")
        self.apply_button.clicked.connect(self._start_filter)
        self.reset_button.clicked.connect(self._reset)
        self.accept_button.clicked.connect(self._commit_current)
        self.cancel_button.clicked.connect(self._revert_uncommitted)
        self.close_button.clicked.connect(self.hide)
        for button in (
            self.apply_button,
            self.reset_button,
            self.accept_button,
            self.cancel_button,
            self.close_button,
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
            "processing_mode": self.processing_mode_combo.currentData(),
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
        processing_mode_index = self.processing_mode_combo.findData(
            settings.get("processing_mode")
        )
        if processing_mode_index >= 0:
            self.processing_mode_combo.setCurrentIndex(processing_mode_index)

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

    def pipeline_steps(self) -> List[FilterStep]:
        return self.pipeline.steps()

    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def set_visible_range(self, values: Tuple[int, int, int, int]) -> None:
        self.visible_range = self._normalize_range(values)
        if self.scope_combo.currentData() == "visible":
            self._update_range_controls()

    def set_data(
        self,
        raw_data: np.ndarray,
        sampling_rate: float,
        visible_range: Tuple[int, int, int, int],
        current_data: Optional[np.ndarray] = None,
        steps: Optional[Iterable[FilterStep]] = None,
        segment_ranges: Optional[Sequence[Tuple[int, int]]] = None,
        previous_steps: Optional[Iterable[FilterStep]] = None,
    ) -> None:
        """Attach the persistent tool window to a newly loaded data group."""

        if self.is_busy():
            raise RuntimeError("滤波正在执行，暂时不能切换数据")
        baseline = np.asarray(raw_data, dtype=np.float32).copy()
        if baseline.ndim != 2 or min(baseline.shape) <= 0:
            raise ValueError("DAS 数据必须是非空二维数组")
        current = baseline.copy() if current_data is None else np.asarray(current_data, dtype=np.float32).copy()
        if current.shape != baseline.shape:
            raise ValueError("当前滤波数据与原始数据形状不一致")

        baseline.setflags(write=False)
        self.raw_data = baseline
        self.working_data = current
        self.sampling_rate = float(sampling_rate)
        self.channel_count, self.sample_count = baseline.shape
        self.visible_range = self._normalize_range(visible_range)
        self.segment_ranges = list(segment_ranges or [(0, self.sample_count)])
        self.pipeline = FilterPipeline(steps)
        self.committed_steps = self.pipeline.steps()
        self.previous_steps = clone_steps(previous_steps or [])

        for box in (self.channel_from, self.channel_to):
            box.setRange(1, self.channel_count)
        for box in (self.sample_from, self.sample_to):
            box.setRange(1, self.sample_count)
        duration = self.sample_count / self.sampling_rate
        for box in (self.time_from, self.time_to):
            box.setRange(0.0, duration)
        self.channel_window.setMaximum(max(1, self.channel_count))
        self.sample_window.setMaximum(max(1, self.sample_count))
        nyquist_limit = max(0.002, self.sampling_rate / 2.0 * 0.999)
        for box in (self.frequency_low, self.frequency_high, self.frequency):
            box.setMaximum(nyquist_limit)
        for box in (self.fk_frequency_low, self.fk_frequency_high):
            box.setMaximum(max(0.001, nyquist_limit))

        self.scope_combo.setCurrentIndex(max(0, self.scope_combo.findData("visible")))
        self.processing_mode_combo.setEnabled(len(self.segment_ranges) > 1)
        if len(self.segment_ranges) <= 1:
            self.processing_mode_combo.setCurrentIndex(
                max(0, self.processing_mode_combo.findData("continuous"))
            )
        self._update_range_controls()
        self._refresh_history()
        self.status_label.setText(
            f"已切换到新数据组：{self.channel_count} 通道，{self.sample_count} 采样点；"
            "参数预设已保留，当前滤波链已清空。"
        )

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _make_step(self, identifier: Optional[str] = None, enabled: bool = True) -> FilterStep:
        return FilterStep(
            algorithm=str(self.algorithm_combo.currentData()),
            parameters=self._parameters(),
            selection=self._selected_range(),
            label=self.algorithm_combo.currentText(),
            enabled=enabled,
            processing_mode=str(self.processing_mode_combo.currentData()),
            identifier=identifier or uuid4().hex,
        )

    @staticmethod
    def _parameter_summary(step: FilterStep) -> str:
        p = step.parameters
        if step.algorithm in {"bandpass", "bandstop"}:
            phase = "零相位" if p.get("zero_phase") else "单向"
            return f"{p['frequency_low']:g}-{p['frequency_high']:g} Hz，{p['order']} 阶，{phase}"
        if step.algorithm in {"lowpass", "highpass"}:
            phase = "零相位" if p.get("zero_phase") else "单向"
            return f"{p['frequency']:g} Hz，{p['order']} 阶，{phase}"
        if step.algorithm == "spike":
            return f"窗口 {p['channel_window']}×{p['sample_window']}，阈值 {p['threshold']:g}"
        if step.algorithm == "common_mode":
            return "中位数" if p.get("method") == "median" else "均值"
        if step.algorithm == "fk":
            return (
                f"dx={p['channel_spacing']:g} m，频率 {p['fk_frequency_low']:g}-"
                f"{p['fk_frequency_high']:g} Hz，速度 {p['fk_velocity_low']:g}-"
                f"{p['fk_velocity_high']:g} m/s"
            )
        if step.algorithm == "mad_normalize":
            return "每通道独立 MAD"
        return str(p)

    def _step_text(self, index: int, step: FilterStep) -> str:
        channel_from, channel_to, sample_from, sample_to = step.selection
        mode = "整体连续" if step.processing_mode == "continuous" else "按文件分段"
        return (
            f"{index + 1}. {step.label}｜{self._parameter_summary(step)}｜"
            f"通道 {channel_from}-{channel_to}｜采样 {sample_from}-{sample_to}｜{mode}"
        )

    def _refresh_history(self, selected_row: int = -1) -> None:
        self._refreshing_history = True
        active_row = -1
        try:
            self.history_list.clear()
            steps = self.pipeline.steps()
            for index, step in enumerate(steps):
                item = QListWidgetItem(self._step_text(index, step))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                item.setCheckState(Qt.Checked if step.enabled else Qt.Unchecked)
                item.setToolTip(f"参数：{step.parameters!r}\n步骤 ID：{step.identifier}")
                self.history_list.addItem(item)
            if steps:
                active_row = selected_row if 0 <= selected_row < len(steps) else 0
                self.history_list.setCurrentRow(active_row)
        finally:
            self._refreshing_history = False
        self._update_history_buttons()
        if active_row >= 0:
            self._load_selected_step(active_row)

    def _update_history_buttons(self) -> None:
        row = self.history_list.currentRow()
        count = len(self.pipeline)
        selected = 0 <= row < count
        self.update_step_button.setEnabled(selected and not self.is_busy())
        self.delete_step_button.setEnabled(selected and not self.is_busy())
        self.move_up_button.setEnabled(selected and row > 0 and not self.is_busy())
        self.move_down_button.setEnabled(selected and row < count - 1 and not self.is_busy())
        self.clear_steps_button.setEnabled(count > 0 and not self.is_busy())
        self.reuse_steps_button.setEnabled(bool(self.previous_steps) and not self.is_busy())

    def _load_selected_step(self, row: int) -> None:
        self._update_history_buttons()
        if self._refreshing_history or self._loading_step or not (0 <= row < len(self.pipeline)):
            return
        step = self.pipeline.steps()[row]
        self._loading_step = True
        try:
            self._set_combo_data(self.algorithm_combo, step.algorithm)
            self._set_combo_data(self.processing_mode_combo, step.processing_mode)
            self._set_combo_data(self.scope_combo, "custom")
            channel_from, channel_to, sample_from, sample_to = step.selection
            self.channel_from.setValue(channel_from)
            self.channel_to.setValue(channel_to)
            self.sample_from.setValue(sample_from)
            self.sample_to.setValue(sample_to)
            p = step.parameters
            mappings = (
                (self.frequency_low, "frequency_low"),
                (self.frequency_high, "frequency_high"),
                (self.frequency, "frequency"),
                (self.order, "order"),
                (self.channel_window, "channel_window"),
                (self.sample_window, "sample_window"),
                (self.threshold, "threshold"),
                (self.channel_spacing, "channel_spacing"),
                (self.fk_frequency_low, "fk_frequency_low"),
                (self.fk_frequency_high, "fk_frequency_high"),
                (self.fk_velocity_low, "fk_velocity_low"),
                (self.fk_velocity_high, "fk_velocity_high"),
            )
            for widget, key in mappings:
                if key in p:
                    widget.setValue(p[key])
            if "zero_phase" in p:
                self.zero_phase.setChecked(bool(p["zero_phase"]))
            if "method" in p:
                self._set_combo_data(self.common_method, p["method"])
            if "fk_mode" in p:
                self._set_combo_data(self.fk_mode, p["fk_mode"])
            if "fk_direction" in p:
                self._set_combo_data(self.fk_direction, p["fk_direction"])
        finally:
            self._loading_step = False

    def _history_item_changed(self, item: QListWidgetItem) -> None:
        if self._refreshing_history or self.is_busy():
            return
        row = self.history_list.row(item)
        if not (0 <= row < len(self.pipeline)):
            return
        steps = self.pipeline.steps()
        enabled = item.checkState() == Qt.Checked
        if steps[row].enabled == enabled:
            return
        steps[row].enabled = enabled
        state = "启用" if enabled else "禁用"
        self._start_replay(steps, f"{state}第 {row + 1} 个滤波步骤", row)

    def _start_filter(self) -> None:
        if self.is_busy():
            return
        channel_from, channel_to, sample_from, sample_to = self._selected_range()
        if channel_from > channel_to or sample_from > sample_to:
            QMessageBox.warning(self, "范围无效", "请确认通道和采样点的起止范围。")
            return
        step = self._make_step()
        steps = self.pipeline.steps()
        steps.append(step)
        self._start_replay(
            steps,
            f"添加 {step.label}：通道 {channel_from}-{channel_to}，采样点 {sample_from}-{sample_to}",
            len(steps) - 1,
        )

    def _update_selected_step(self) -> None:
        row = self.history_list.currentRow()
        if not (0 <= row < len(self.pipeline)) or self.is_busy():
            return
        steps = self.pipeline.steps()
        current = steps[row]
        steps[row] = self._make_step(current.identifier, current.enabled)
        self._start_replay(steps, f"更新第 {row + 1} 个滤波步骤", row)

    def _delete_selected_step(self) -> None:
        row = self.history_list.currentRow()
        if not (0 <= row < len(self.pipeline)) or self.is_busy():
            return
        steps = self.pipeline.steps()
        removed = steps.pop(row)
        self._start_replay(steps, f"删除 {removed.label}", min(row, len(steps) - 1))

    def _move_selected_step(self, offset: int) -> None:
        row = self.history_list.currentRow()
        destination = row + int(offset)
        if self.is_busy() or not (0 <= row < len(self.pipeline)) or not (0 <= destination < len(self.pipeline)):
            return
        steps = self.pipeline.steps()
        step = steps.pop(row)
        steps.insert(destination, step)
        self._start_replay(steps, f"调整第 {row + 1} 个滤波步骤的顺序", destination)

    def _clear_pipeline(self) -> None:
        if self.is_busy() or len(self.pipeline) == 0:
            return
        self._start_replay([], "清空滤波链并恢复导入原始数据", -1)

    def _reuse_previous_pipeline(self) -> None:
        if self.is_busy():
            return
        if not self.previous_steps:
            QMessageBox.information(self, "没有历史滤波链", "上一组数据没有可复用的滤波步骤。")
            return
        self.replayExternalPipeline(
            self.previous_steps,
            "应用上一组数据的滤波链",
            commit_after=False,
        )

    def replayExternalPipeline(
        self,
        steps: Iterable[FilterStep],
        description: str,
        commit_after: bool = False,
    ) -> bool:
        """Replay a caller-supplied compatible chain on the current immutable baseline."""

        if self.is_busy():
            return False
        candidate = clone_steps(steps, new_identifiers=True)
        if not candidate:
            return False
        self._start_replay(candidate, description, len(candidate) - 1, commit_after=commit_after)
        return True

    def _auto_reapply_toggled(self, enabled: bool) -> None:
        self.auto_reapply = bool(enabled)
        self.autoReapplyChanged.emit(self.auto_reapply)

    def setAutoReapply(self, enabled: bool) -> None:
        self.auto_reapply = bool(enabled)
        self.auto_reapply_checkbox.blockSignals(True)
        self.auto_reapply_checkbox.setChecked(self.auto_reapply)
        self.auto_reapply_checkbox.blockSignals(False)

    def _start_replay(
        self,
        steps: Iterable[FilterStep],
        description: str,
        selected_row: int = -1,
        commit_after: bool = False,
    ) -> None:
        if self.is_busy():
            return
        candidate = clone_steps(steps)
        copies = 14.0 if any(step.enabled and step.algorithm == "fk" for step in candidate) else 6.0
        try:
            required, available = ensure_memory_budget(
                self.channel_count,
                self.sample_count,
                copies,
                "滤波链回放",
            )
        except MemoryError as error:
            QMessageBox.warning(self, "内存不足", str(error))
            return

        self._pending_steps = candidate
        self._pending_description = description
        self._pending_selected_row = selected_row
        self._pending_commit = commit_after
        self._set_busy(True)
        self._worker = _PipelineWorker(
            self.raw_data,
            self.sampling_rate,
            candidate,
            self.segment_ranges,
            parent=self,
        )
        self._worker.resultReady.connect(self._replay_finished)
        self._worker.errorRaised.connect(self._filter_failed)
        self._worker.finished.connect(self._worker_finished)
        memory_text = f"预计峰值内存约 {format_bytes(required)}"
        if available is not None:
            memory_text += f"，当前可用约 {format_bytes(available)}"
        self.status_label.setText(f"正在从原始基线回放 {len(candidate)} 个步骤；{memory_text}……")
        self.settingsChanged.emit(self.filter_settings())
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self.apply_button.setEnabled(not busy)
        self.reset_button.setEnabled(not busy)
        self.accept_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)
        self.history_list.setEnabled(not busy)
        if busy:
            for button in (
                self.update_step_button,
                self.delete_step_button,
                self.move_up_button,
                self.move_down_button,
                self.clear_steps_button,
                self.reuse_steps_button,
            ):
                button.setEnabled(False)
        else:
            self._update_history_buttons()

    def _replay_finished(self, result) -> None:
        self.pipeline = FilterPipeline(self._pending_steps)
        self.working_data = np.asarray(result, dtype=np.float32).copy()
        self._refresh_history(self._pending_selected_row)
        self.pipelineChanged.emit(self.pipeline.steps())
        self.previewReady.emit(self.working_data.copy(), self._pending_description)
        if self._pending_commit:
            self._store_commit()
        else:
            self.status_label.setText(
                f"已从原始基线回放 {len(self.pipeline)} 个步骤：{self._pending_description}。"
            )

    def _filter_failed(self, details: str) -> None:
        self.status_label.setText("处理失败，请检查参数、范围或新数据的兼容性。")
        QMessageBox.critical(self, "滤波失败", details.splitlines()[-1])

    def _worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._pending_commit = False
        self._set_busy(False)

    def _reset(self) -> None:
        if self.is_busy():
            return
        self._start_replay([], "恢复导入原始数据", -1)

    def _store_commit(self) -> None:
        self.committed_steps = self.pipeline.steps()
        self.committed.emit(self.working_data.copy())
        self.settingsChanged.emit(self.filter_settings())
        self.status_label.setText(f"已确认当前结果，共 {len(self.committed_steps)} 个滤波步骤。")

    def _commit_current(self) -> None:
        if not self.is_busy():
            self._store_commit()

    def _revert_uncommitted(self) -> None:
        if self.is_busy():
            return
        self._start_replay(
            self.committed_steps,
            "撤销未确认修改，恢复最近确认的滤波链",
            len(self.committed_steps) - 1,
        )

    def accept(self) -> None:
        if self.is_busy():
            return
        self._store_commit()
        self.hide()

    def reject(self) -> None:
        self.hide()

    def closeEvent(self, event) -> None:
        """Hide the persistent tool and keep the current preview and history."""

        event.ignore()
        self.hide()
