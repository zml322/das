"""Multi-channel waveform page and range navigation."""

import numpy as np
import pyqtgraph as pg
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QDoubleSpinBox, QHBoxLayout, QVBoxLayout, QWidget

from core.data.data_timeline import format_wall_time
from ui.components.window_feature import WindowFeature
from ui.widgets.custom_widgets import AbsoluteTimeAxisItem, Label, PushButton, SpinBox
from utils.function import printError, xAxis
from utils.theme import (
    PLOT_LABEL_POINT_SIZE,
    PLOT_TICK_POINT_SIZE,
    PLOT_TITLE_POINT_SIZE,
    plot_font,
    plot_html,
)


class MultiWavesController(WindowFeature):
    """Multi-channel waveform page and range navigation."""

    def __init__(self, window):
        super().__init__(window)

    def resetView(self):
        self.multi_waves_reset_pending = True

    def initMultiWavesTab(self):
        """创建固定的多通道云图页；数据变化时只重绘，不重复创建 Tab。"""
        self.multi_waves_view_box = pg.ViewBox(enableMenu=False)
        self.multi_waves_time_axis = AbsoluteTimeAxisItem(orientation="bottom")
        self.plot_multi_waves_widget = pg.PlotWidget(
            viewBox=self.multi_waves_view_box,
            axisItems={"bottom": self.multi_waves_time_axis},
        )
        self.plot_multi_waves_widget.setTitle(plot_html("多通道云图", PLOT_TITLE_POINT_SIZE))
        self.plot_multi_waves_widget.setLabel("bottom", plot_html("推算时间", PLOT_LABEL_POINT_SIZE))
        self.plot_multi_waves_widget.setLabel("left", plot_html("通道", PLOT_LABEL_POINT_SIZE))
        self.plot_multi_waves_widget.getAxis("bottom").setTickFont(plot_font(PLOT_TICK_POINT_SIZE))
        self.plot_multi_waves_widget.getAxis("left").setTickFont(plot_font(PLOT_TICK_POINT_SIZE))
        self.plot_multi_waves_widget.getAxis("left").setWidth(50)
        self.plot_multi_waves_widget.showGrid(x=True, y=True, alpha=0.2)

        self.multi_waves_channel_from_spin_box = SpinBox()
        self.multi_waves_channel_to_spin_box = SpinBox()
        for spin_box in (
            self.multi_waves_channel_from_spin_box,
            self.multi_waves_channel_to_spin_box,
        ):
            spin_box.setFixedWidth(90)
            spin_box.setKeyboardTracking(False)

        self.multi_waves_confirm_button = PushButton("确认")
        self.multi_waves_channel_range_label = Label("")
        self.multi_waves_time_range_label = Label("")
        self.multi_waves_time_from_spin_box = QDoubleSpinBox()
        self.multi_waves_time_to_spin_box = QDoubleSpinBox()
        for spin_box in (
            self.multi_waves_time_from_spin_box,
            self.multi_waves_time_to_spin_box,
        ):
            spin_box.setDecimals(6)
            spin_box.setFixedWidth(110)
            spin_box.setKeyboardTracking(False)
            spin_box.setSuffix(" s")
        self.multi_waves_time_confirm_button = PushButton("确认时间")
        self.multi_waves_left_button = PushButton("←")
        self.multi_waves_right_button = PushButton("→")
        self.multi_waves_up_button = PushButton("↑")
        self.multi_waves_down_button = PushButton("↓")
        for button in (
            self.multi_waves_left_button,
            self.multi_waves_right_button,
            self.multi_waves_up_button,
            self.multi_waves_down_button,
        ):
            button.setFixedWidth(45)
        self.multi_waves_left_button.setToolTip("向前移动时间范围")
        self.multi_waves_right_button.setToolTip("向后移动时间范围")
        self.multi_waves_up_button.setToolTip("向更大通道号移动范围")
        self.multi_waves_down_button.setToolTip("向更小通道号移动范围")

        self.multi_waves_confirm_button.clicked.connect(self.confirmMultiWavesChannelRange)
        self.multi_waves_time_confirm_button.clicked.connect(self.confirmMultiWavesTimeRange)
        self.multi_waves_left_button.clicked.connect(lambda: self.moveMultiWavesTime(-1))
        self.multi_waves_right_button.clicked.connect(lambda: self.moveMultiWavesTime(1))
        self.multi_waves_up_button.clicked.connect(lambda: self.moveMultiWavesChannels(1))
        self.multi_waves_down_button.clicked.connect(lambda: self.moveMultiWavesChannels(-1))

        selection_controls_hbox = QHBoxLayout()
        selection_controls_hbox.setContentsMargins(0, 0, 0, 0)
        selection_controls_hbox.setSpacing(6)
        selection_controls_hbox.addWidget(Label("显示通道"))
        selection_controls_hbox.addWidget(self.multi_waves_channel_from_spin_box)
        selection_controls_hbox.addWidget(Label("至"))
        selection_controls_hbox.addWidget(self.multi_waves_channel_to_spin_box)
        selection_controls_hbox.addWidget(self.multi_waves_confirm_button)
        selection_controls_hbox.addSpacing(12)
        selection_controls_hbox.addWidget(Label("显示时间（相对秒）"))
        selection_controls_hbox.addWidget(self.multi_waves_time_from_spin_box)
        selection_controls_hbox.addWidget(Label("至"))
        selection_controls_hbox.addWidget(self.multi_waves_time_to_spin_box)
        selection_controls_hbox.addWidget(self.multi_waves_time_confirm_button)
        selection_controls_hbox.addStretch(1)

        navigation_controls_hbox = QHBoxLayout()
        navigation_controls_hbox.setContentsMargins(0, 0, 0, 0)
        navigation_controls_hbox.setSpacing(6)
        navigation_controls_hbox.addWidget(Label("浏览"))
        navigation_controls_hbox.addWidget(self.multi_waves_left_button)
        navigation_controls_hbox.addWidget(self.multi_waves_right_button)
        navigation_controls_hbox.addWidget(self.multi_waves_up_button)
        navigation_controls_hbox.addWidget(self.multi_waves_down_button)
        navigation_controls_hbox.addSpacing(12)
        navigation_controls_hbox.addWidget(self.multi_waves_channel_range_label)
        navigation_controls_hbox.addSpacing(12)
        navigation_controls_hbox.addWidget(self.multi_waves_time_range_label)
        navigation_controls_hbox.addStretch(1)

        self.multi_waves_container = QWidget()
        vbox = QVBoxLayout()
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(6)
        vbox.addLayout(selection_controls_hbox)
        vbox.addLayout(navigation_controls_hbox)
        vbox.addWidget(self.plot_multi_waves_widget)
        self.multi_waves_container.setLayout(vbox)
        self.multi_waves_view_box.sigRangeChanged.connect(self.syncMultiWavesTimeRange)
        self.multi_waves_reset_pending = True
        self.multi_waves_colors = [
            "red",
            "lime",
            "deepskyblue",
            "yellow",
            "plum",
            "gold",
            "blue",
            "fuchsia",
            "aqua",
            "orange",
        ]

    def showMultiWavesTab(self):
        """定位到固定云图页；菜单入口不再创建临时 Tab。"""
        self.window.workspace.tab_widget.setCurrentWidget(self.multi_waves_container)
        self.plotMultiWavesImage()

    def plotMultiWavesImage(self):
        """按当前数据刷新固定的多通道云图页。"""
        if not hasattr(self.window.data, "visible_data") or self.window.data.visible_data.size == 0:
            self.plot_multi_waves_widget.clear()
            return

        self.multi_waves_time_axis.setOrigin(
            self.window.data.data_timeline.start_time if self.window.data.data_timeline is not None else None
        )

        self.multi_waves_x = xAxis(
            self.window.data.current_sampling_times,
            self.window.data.sampling_times_from_num,
            self.window.data.sampling_times_to_num,
            self.window.data.sampling_rate,
        )
        self.multi_waves_x_min = float(self.multi_waves_x[0])
        self.multi_waves_x_max = float(self.multi_waves_x[-1])
        if self.multi_waves_x_max <= self.multi_waves_x_min:
            self.multi_waves_x_max = self.multi_waves_x_min + 1 / self.window.data.sampling_rate

        self.multi_waves_channel_min = self.window.data.channel_from_num
        self.multi_waves_channel_max = self.window.data.channel_to_num
        full_time_width = self.multi_waves_x_max - self.multi_waves_x_min
        min_time_window_width = min(1 / self.window.data.sampling_rate, full_time_width)
        default_time_window_width = min(max(full_time_width / 5, min_time_window_width), full_time_width)

        previous_channel_from = self.multi_waves_channel_from_spin_box.value()
        previous_channel_to = self.multi_waves_channel_to_spin_box.value()
        should_reset = (
            self.multi_waves_reset_pending
            or previous_channel_from < self.multi_waves_channel_min
            or previous_channel_to > self.multi_waves_channel_max
            or previous_channel_from > previous_channel_to
        )
        if should_reset:
            channel_from = self.multi_waves_channel_min
            channel_to = min(channel_from + 19, self.multi_waves_channel_max)
            self.multi_waves_time_from = self.multi_waves_x_min
            self.multi_waves_time_window_width = default_time_window_width
        else:
            channel_from = max(self.multi_waves_channel_min, previous_channel_from)
            channel_to = min(self.multi_waves_channel_max, previous_channel_to)
            self.multi_waves_time_window_width = min(
                max(
                    getattr(self, "multi_waves_time_window_width", default_time_window_width),
                    min_time_window_width,
                ),
                full_time_width,
            )
            max_time_from = self.multi_waves_x_max - self.multi_waves_time_window_width
            self.multi_waves_time_from = min(
                max(
                    getattr(self, "multi_waves_time_from", self.multi_waves_x_min),
                    self.multi_waves_x_min,
                ),
                max_time_from,
            )

        self.multi_waves_channel_from_spin_box.blockSignals(True)
        self.multi_waves_channel_to_spin_box.blockSignals(True)
        self.multi_waves_channel_from_spin_box.setRange(self.multi_waves_channel_min, self.multi_waves_channel_max)
        self.multi_waves_channel_to_spin_box.setRange(self.multi_waves_channel_min, self.multi_waves_channel_max)
        self.multi_waves_channel_from_spin_box.setValue(channel_from)
        self.multi_waves_channel_to_spin_box.setValue(channel_to)
        self.multi_waves_channel_from_spin_box.blockSignals(False)
        self.multi_waves_channel_to_spin_box.blockSignals(False)

        time_decimals = min(9, max(3, int(np.ceil(np.log10(max(self.window.data.sampling_rate, 1)))) + 1))
        for spin_box in (
            self.multi_waves_time_from_spin_box,
            self.multi_waves_time_to_spin_box,
        ):
            spin_box.blockSignals(True)
            spin_box.setDecimals(time_decimals)
            spin_box.setRange(self.multi_waves_x_min, self.multi_waves_x_max)
            spin_box.setSingleStep(min_time_window_width)
            spin_box.blockSignals(False)

        self.multi_waves_view_box.setLimits(
            xMin=self.multi_waves_x_min,
            xMax=self.multi_waves_x_max,
            yMin=self.multi_waves_channel_min - 0.5,
            yMax=self.multi_waves_channel_max + 0.5,
            minXRange=min_time_window_width,
            maxXRange=full_time_width,
            minYRange=1,
            maxYRange=self.window.data.current_channels,
        )
        self.multi_waves_reset_pending = False
        self.drawMultiWavesVisibleChannels()

    def drawMultiWavesVisibleChannels(self):
        """重绘当前选定的云图通道，并保持视图范围在新数据边界内。"""
        if not hasattr(self, "multi_waves_x"):
            return
        channel_from = self.multi_waves_channel_from_spin_box.value()
        channel_to = self.multi_waves_channel_to_spin_box.value()
        self.plot_multi_waves_widget.clear()
        for channel_number in range(channel_from, channel_to + 1):
            self.plot_multi_waves_widget.plot(
                self.multi_waves_x,
                self.window.data.visible_data[channel_number - self.multi_waves_channel_min] + channel_number,
                pen=QColor(self.multi_waves_colors[(channel_number - 1) % len(self.multi_waves_colors)]),
            )
        self.window.overlays.drawFileBoundaries(
            self.plot_multi_waves_widget,
            channel_from - 0.5,
            channel_to + 0.5,
        )
        self.window.overlays.drawEventRange(self.plot_multi_waves_widget)
        self.updateMultiWavesViewRange()

    def updateMultiWavesViewRange(self):
        """同步云图的按钮导航状态、标签和 ViewBox 范围。"""
        channel_from = self.multi_waves_channel_from_spin_box.value()
        channel_to = self.multi_waves_channel_to_spin_box.value()
        max_time_from = self.multi_waves_x_max - self.multi_waves_time_window_width
        self.multi_waves_time_from = min(max(self.multi_waves_time_from, self.multi_waves_x_min), max_time_from)
        self.multi_waves_view_box.setRange(
            xRange=(
                self.multi_waves_time_from,
                self.multi_waves_time_from + self.multi_waves_time_window_width,
            ),
            yRange=(channel_from - 0.5, channel_to + 0.5),
            padding=0,
        )
        self.multi_waves_channel_range_label.setText(f"通道：{channel_from} - {channel_to}")
        self.updateMultiWavesTimeDisplay()

    def updateMultiWavesTimeDisplay(self):
        """把当前时间窗口同步到输入框和提示文字。"""
        time_to = self.multi_waves_time_from + self.multi_waves_time_window_width
        self.multi_waves_time_from_spin_box.blockSignals(True)
        self.multi_waves_time_to_spin_box.blockSignals(True)
        self.multi_waves_time_from_spin_box.setValue(self.multi_waves_time_from)
        self.multi_waves_time_to_spin_box.setValue(time_to)
        self.multi_waves_time_from_spin_box.blockSignals(False)
        self.multi_waves_time_to_spin_box.blockSignals(False)
        if self.window.data.data_timeline is not None:
            absolute_from = self.window.data.data_timeline.absolute_time_for_sample(
                self.multi_waves_time_from * self.window.data.sampling_rate
            )
            absolute_to = self.window.data.data_timeline.absolute_time_for_sample(
                time_to * self.window.data.sampling_rate
            )
            self.multi_waves_time_range_label.setText(
                f"推算时间：{format_wall_time(absolute_from)} - {format_wall_time(absolute_to)}"
            )
        else:
            self.multi_waves_time_range_label.setText(f"时间：{self.multi_waves_time_from:.3f} - {time_to:.3f} s")

    def syncMultiWavesTimeRange(self, _view_box, view_range):
        """鼠标平移或缩放后，同步云图的时间窗口状态和输入框。"""
        if not hasattr(self, "multi_waves_x"):
            return
        time_from, time_to = view_range[0]
        if time_to <= time_from:
            return
        self.multi_waves_time_from = max(time_from, self.multi_waves_x_min)
        self.multi_waves_time_window_width = min(time_to - time_from, self.multi_waves_x_max - self.multi_waves_x_min)
        self.updateMultiWavesTimeDisplay()

    def setMultiWavesChannelRange(self, channel_from: int, channel_to: int):
        """限制通道范围、同步输入框并重绘固定云图。"""
        channel_from = min(
            max(channel_from, self.multi_waves_channel_min),
            self.multi_waves_channel_max,
        )
        channel_to = min(max(channel_to, channel_from), self.multi_waves_channel_max)
        self.multi_waves_channel_from_spin_box.blockSignals(True)
        self.multi_waves_channel_to_spin_box.blockSignals(True)
        self.multi_waves_channel_from_spin_box.setValue(channel_from)
        self.multi_waves_channel_to_spin_box.setValue(channel_to)
        self.multi_waves_channel_from_spin_box.blockSignals(False)
        self.multi_waves_channel_to_spin_box.blockSignals(False)
        self.drawMultiWavesVisibleChannels()

    def confirmMultiWavesChannelRange(self):
        """提交完整的多位通道输入，并防止起止通道颠倒。"""
        self.multi_waves_channel_from_spin_box.interpretText()
        self.multi_waves_channel_to_spin_box.interpretText()
        channel_from = self.multi_waves_channel_from_spin_box.value()
        channel_to = self.multi_waves_channel_to_spin_box.value()
        if channel_from > channel_to:
            printError("起始通道不能大于结束通道")
            return
        self.drawMultiWavesVisibleChannels()

    def confirmMultiWavesTimeRange(self):
        """提交输入的时间起止范围，并在该范围内显示云图。"""
        if not hasattr(self, "multi_waves_x"):
            return
        self.multi_waves_time_from_spin_box.interpretText()
        self.multi_waves_time_to_spin_box.interpretText()
        time_from = self.multi_waves_time_from_spin_box.value()
        time_to = self.multi_waves_time_to_spin_box.value()
        minimum_width = min(1 / self.window.data.sampling_rate, self.multi_waves_x_max - self.multi_waves_x_min)
        if time_to - time_from < minimum_width:
            printError("结束时间必须至少比起始时间大一个采样间隔")
            return
        self.multi_waves_time_from = time_from
        self.multi_waves_time_window_width = time_to - time_from
        self.updateMultiWavesViewRange()

    def moveMultiWavesTime(self, direction: int):
        """按当前时间窗口宽度平移固定云图。"""
        if not hasattr(self, "multi_waves_x"):
            return
        step = max(self.multi_waves_time_window_width * 0.8, 1 / self.window.data.sampling_rate)
        self.multi_waves_time_from += direction * step
        self.updateMultiWavesViewRange()

    def moveMultiWavesChannels(self, direction: int):
        """保持当前通道窗口宽度，向上或向下浏览云图。"""
        if not hasattr(self, "multi_waves_x"):
            return
        channel_from = self.multi_waves_channel_from_spin_box.value()
        channel_to = self.multi_waves_channel_to_spin_box.value()
        width = channel_to - channel_from + 1
        step = max(1, width // 2)
        new_channel_from = min(
            max(channel_from + direction * step, self.multi_waves_channel_min),
            self.multi_waves_channel_max - width + 1,
        )
        self.setMultiWavesChannelRange(new_channel_from, new_channel_from + width - 1)
