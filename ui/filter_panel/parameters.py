"""滤波参数表单：一张字段表 + 一套通用逻辑。

想加/改一个参数，只需要改下面的 FIELDS；创建控件、按算法显隐、读取、
恢复、载入步骤全部由 ParameterForm 统一处理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Callable, Dict, Optional

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

BAND = {"bandpass", "bandstop"}
CUTOFF = {"lowpass", "highpass"}


@dataclass(frozen=True)
class Field:
    key: str                          # 写进滤波步骤 parameters 的键
    label: str
    kind: str                         # double | int | check | combo
    algorithms: frozenset
    range: Optional[Callable] = None  # ctx -> (最小, 最大)；ctx 含 nyquist/channels/samples
    default: object = 0               # 值，或 ctx -> 值
    decimals: int = 3
    step: float = 1.0
    suffix: str = ""
    items: tuple = ()                 # combo：((文字, 数据), ...)
    text: str = ""                    # check：复选框旁的文字
    tooltip: str = ""
    setting_key: str = ""             # 保存到"当前设置"时的键，默认同 key


def _field(key, label, kind, algorithms, **options) -> Field:
    return Field(key, label, kind, frozenset(algorithms), **options)


def _frequency_range(ctx):
    return 0.001, max(0.002, ctx.nyquist * 0.999)


def _fk_frequency_range(ctx):
    return 0.0, max(0.001, ctx.nyquist * 0.999)


FIELDS = (
    # 带通 / 带阻 / 低通 / 高通
    _field("frequency_low", "低频 (Hz)", "double", BAND,
           range=_frequency_range, default=lambda c: min(5.0, c.nyquist * 0.1)),
    _field("frequency_high", "高频 (Hz)", "double", BAND,
           range=_frequency_range, default=lambda c: min(120.0, c.nyquist * 0.8)),
    _field("frequency", "截止频率 (Hz)", "double", CUTOFF,
           range=_frequency_range, default=lambda c: min(120.0, c.nyquist * 0.8)),
    _field("order", "滤波阶数", "int", BAND | CUTOFF, range=lambda c: (1, 12), default=4),
    _field("zero_phase", "相位", "check", BAND | CUTOFF, default=True,
           text="零相位（前后向）", tooltip="启用前后向滤波以获得零相位响应"),
    # 尖峰噪声
    _field("channel_window", "尖峰通道窗口", "int", {"spike"},
           range=lambda c: (1, max(1, c.channels)), default=lambda c: min(50, c.channels)),
    _field("sample_window", "尖峰采样窗口", "int", {"spike"},
           range=lambda c: (1, max(1, c.samples)), default=lambda c: min(5, c.samples)),
    _field("threshold", "尖峰阈值倍数", "double", {"spike"},
           range=lambda c: (1.0, 1000.0), default=10.0, decimals=2),
    # 共模噪声
    _field("method", "共模估计", "combo", {"common_mode"}, setting_key="common_method",
           items=(("中位数", "median"), ("均值", "mean"))),
    # F-K 扇形
    _field("channel_spacing", "相邻通道距离 dx", "double", {"fk"},
           range=lambda c: (0.001, 100000.0), default=4.0, step=0.1, suffix=" m"),
    _field("fk_mode", "F-K 操作", "combo", {"fk"},
           items=(("保留扇形内信号", "retain"), ("去除扇形内信号", "remove"))),
    _field("fk_direction", "传播方向", "combo", {"fk"},
           items=(("双向", "both"), ("仅保留正表观速度", "positive"), ("仅保留负表观速度", "negative"))),
    _field("fk_frequency_low", "F-K 频率下限", "double", {"fk"},
           range=_fk_frequency_range, suffix=" Hz"),
    _field("fk_frequency_high", "F-K 频率上限", "double", {"fk"},
           range=_fk_frequency_range, suffix=" Hz"),
    _field("fk_velocity_low", "表观速度下限", "double", {"fk"},
           range=lambda c: (0.0, 1_000_000.0), decimals=1, step=10.0, suffix=" m/s"),
    _field("fk_velocity_high", "表观速度上限", "double", {"fk"},
           range=lambda c: (0.0, 1_000_000.0), decimals=1, step=10.0, suffix=" m/s"),
)

FK_HINT = (
    "F-K：频率和速度填 0 表示不限制；至少设置一个限制或方向。"
    "dx 必须是实际相邻通道距离，不是 gauge length。"
)


def _context(sampling_rate, channel_count, sample_count):
    return SimpleNamespace(
        nyquist=max(0.01, float(sampling_rate) / 2.0),
        channels=int(channel_count),
        samples=int(sample_count),
    )


class ParameterForm(QWidget):
    def __init__(self, sampling_rate: float, channel_count: int, sample_count: int, parent=None):
        super().__init__(parent)
        self._layout = QFormLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(6)
        self._layout.setVerticalSpacing(2)
        self.widgets: Dict[str, QWidget] = {}
        self._hint = QLabel(FK_HINT)
        self._hint.setWordWrap(True)
        self._hint.setObjectName("secondaryLabel")

        ctx = _context(sampling_rate, channel_count, sample_count)
        for spec in FIELDS:
            widget = self._make_widget(spec, ctx)
            self.widgets[spec.key] = widget
            if spec.kind == "check":
                self._layout.addRow(spec.label, widget)
            else:
                self._layout.addRow(spec.label, widget)
        # F-K 的说明放在 dx…速度之后，这里单独加一行并跟随 fk 显隐
        self._layout.addRow("", self._hint)
        self.set_algorithm("bandpass")

    # ---- 创建 -----------------------------------------------------------
    @staticmethod
    def _make_widget(spec: Field, ctx) -> QWidget:
        default = spec.default(ctx) if callable(spec.default) else spec.default
        if spec.kind == "combo":
            box = QComboBox()
            for text, data in spec.items:
                box.addItem(text, data)
            return box
        if spec.kind == "check":
            box = QCheckBox(spec.text)
            box.setChecked(bool(default))
            box.setToolTip(spec.tooltip)
            return box
        box = QSpinBox() if spec.kind == "int" else QDoubleSpinBox()
        box.setKeyboardTracking(False)
        box.setMaximumWidth(150)
        if spec.kind == "double":
            box.setDecimals(spec.decimals)
            box.setSingleStep(spec.step)
            box.setSuffix(spec.suffix)
        box.setRange(*spec.range(ctx))
        box.setValue(int(default) if spec.kind == "int" else float(default))
        return box

    # ---- 对外接口 -------------------------------------------------------
    def set_limits(self, sampling_rate, channel_count, sample_count) -> None:
        """换了数据：只更新各控件的取值范围，保留已填的值。"""
        ctx = _context(sampling_rate, channel_count, sample_count)
        for spec in FIELDS:
            if spec.kind in ("int", "double"):
                self.widgets[spec.key].setRange(*spec.range(ctx))

    def set_algorithm(self, algorithm: str) -> None:
        """只显示当前算法用得到的行。"""
        for spec in FIELDS:
            self._show_row(self.widgets[spec.key], algorithm in spec.algorithms)
        self._show_row(self._hint, algorithm == "fk")

    def values(self, algorithm: str) -> Dict[str, object]:
        """当前算法的参数（写入滤波步骤）。"""
        return {
            spec.key: self._read(spec)
            for spec in FIELDS
            if algorithm in spec.algorithms
        }

    def settings(self) -> Dict[str, object]:
        """所有字段的当前值（用于切换文件后复用）。"""
        return {spec.setting_key or spec.key: self._read(spec) for spec in FIELDS}

    def restore(self, settings: Dict[str, object]) -> None:
        for spec in FIELDS:
            name = spec.setting_key or spec.key
            if name in settings:
                self._write(spec, settings[name])

    def load(self, parameters: Dict[str, object]) -> None:
        """把某个滤波步骤的参数载回编辑器。"""
        for spec in FIELDS:
            if spec.key in parameters:
                self._write(spec, parameters[spec.key])

    # ---- 内部 -----------------------------------------------------------
    def _show_row(self, widget: QWidget, visible: bool) -> None:
        label = self._layout.labelForField(widget)
        if label is not None:
            label.setVisible(visible)
        widget.setVisible(visible)

    def _read(self, spec: Field):
        widget = self.widgets[spec.key]
        if spec.kind == "combo":
            return widget.currentData()
        if spec.kind == "check":
            return widget.isChecked()
        return widget.value()

    def _write(self, spec: Field, value) -> None:
        widget = self.widgets[spec.key]
        try:
            if spec.kind == "combo":
                index = widget.findData(value)
                if index >= 0:
                    widget.setCurrentIndex(index)
            elif spec.kind == "check":
                widget.setChecked(bool(value))
            else:
                widget.setValue(int(value) if spec.kind == "int" else float(value))
        except (TypeError, ValueError):
            pass  # 旧设置里的坏值直接忽略


def summarize(algorithm: str, p: Dict[str, object]) -> str:
    """滤波链列表里每一步的一行参数摘要。"""
    phase = "零相位" if p.get("zero_phase") else "单向"
    if algorithm in BAND:
        return f"{p['frequency_low']:g}-{p['frequency_high']:g} Hz，{p['order']} 阶，{phase}"
    if algorithm in CUTOFF:
        return f"{p['frequency']:g} Hz，{p['order']} 阶，{phase}"
    if algorithm == "spike":
        return f"窗口 {p['channel_window']}×{p['sample_window']}，阈值 {p['threshold']:g}"
    if algorithm == "common_mode":
        return "中位数" if p.get("method") == "median" else "均值"
    if algorithm == "fk":
        return (
            f"dx={p['channel_spacing']:g} m，频率 {p['fk_frequency_low']:g}-"
            f"{p['fk_frequency_high']:g} Hz，速度 {p['fk_velocity_low']:g}-"
            f"{p['fk_velocity_high']:g} m/s"
        )
    if algorithm == "mad_normalize":
        return "每通道独立 MAD"
    return str(p)
