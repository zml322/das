# -*- coding: utf-8 -*-
"""
@Time    : 2024/6/12 上午9:28
@Author  : zxy
@File    : widget.py
"""
from datetime import datetime, timedelta
from typing import Callable, Union, Tuple

import numpy as np
import pyqtgraph as pg
from scipy.spatial.distance import euclidean

from PyQt5.QtCore import QRegExp, Qt
from PyQt5.QtGui import QRegExpValidator, QColor
from PyQt5.QtWidgets import QLineEdit, QLabel, QComboBox, QCheckBox, QPushButton, QRadioButton, QSpinBox, QMenu, \
    QAction, QWidget, QTextEdit, QDialog
from .theme import PLOT_LABEL_POINT_SIZE, PLOT_TICK_POINT_SIZE, PLOT_TITLE_POINT_SIZE, plot_font, plot_html


class AbsoluteTimeAxisItem(pg.AxisItem):
    """Format relative-second plot coordinates as corrected local wall time."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._origin = None

    def setOrigin(self, origin: datetime | None) -> None:
        self._origin = origin
        self.update()

    def tickSpacing(self, minVal, maxVal, size):
        """Align relative plot ticks to round wall-clock boundaries."""

        levels = super().tickSpacing(minVal, maxVal, size)
        if self._origin is None:
            return levels
        origin_microseconds = (
            (
                self._origin.toordinal() * 86400
                + self._origin.hour * 3600
                + self._origin.minute * 60
                + self._origin.second
            ) * 1_000_000
            + self._origin.microsecond
        )
        aligned = []
        for spacing, _offset in levels:
            spacing = float(spacing)
            if not np.isfinite(spacing) or spacing <= 0:
                aligned.append((spacing, 0.0))
                continue
            # AxisItem applies this offset in relative seconds.  Shifting by
            # the wall-clock phase makes, for example, 13:44:20 land on a
            # major tick even when the first DAS sample is at xx:xx:00.280.
            spacing_microseconds = max(1, int(round(spacing * 1_000_000)))
            offset = ((-origin_microseconds) % spacing_microseconds) / 1_000_000.0
            aligned.append((spacing, offset))
        return aligned

    def tickStrings(self, values, scale, spacing):
        if self._origin is None:
            return super().tickStrings(values, scale, spacing)
        try:
            span = abs(float(self.range[1]) - float(self.range[0]))
        except (AttributeError, IndexError, TypeError, ValueError):
            span = 0.0
        try:
            range_end = self._origin + timedelta(seconds=max(map(float, self.range)))
            crosses_date = range_end.date() != self._origin.date()
        except (AttributeError, TypeError, ValueError, OverflowError):
            crosses_date = False
        show_date = span >= 12 * 3600 or crosses_date
        show_milliseconds = span < 3600 and abs(float(spacing)) < 1.0
        result = []
        for value in values:
            moment = self._origin + timedelta(seconds=float(value))
            if show_date and show_milliseconds:
                result.append(moment.strftime("%m-%d %H:%M:%S.%f")[:-3])
            elif show_date:
                result.append(moment.strftime("%m-%d %H:%M:%S"))
            elif show_milliseconds:
                result.append(moment.strftime("%H:%M:%S.%f")[:-3])
            else:
                result.append(moment.strftime("%H:%M:%S"))
        return result


class Menu(QMenu):
    def __init__(self,
                 parent: QWidget,
                 title: str,
                 status_tip: str = None,
                 enabled: bool = True):
        super().__init__(parent=parent, title=title)
        self.setStatusTip(status_tip)
        self.setEnabled(enabled)
        parent.addMenu(self)


class Action(QAction):
    def __init__(self,
                 parent: QWidget,
                 text: str,
                 status_tip: str,
                 slot_func: Callable,
                 shortcut: Union[int, str] = 0,
                 enabled: bool = True):
        super().__init__(parent=parent, text=text)
        self.setStatusTip(status_tip)
        self.setShortcut(shortcut)
        self.triggered.connect(slot_func)
        self.setEnabled(enabled)
        parent.addAction(self)


class Dialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)


class Label(QLabel):
    def __init__(self, text: str):
        super().__init__(text)


class PushButton(QPushButton):
    def __init__(self, text: str = None):
        super().__init__(text)


class LineEdit(QLineEdit):
    def __init__(self, focus: bool = True):
        super().__init__()
        if not focus:
            self.setFocusPolicy(Qt.NoFocus)


class LineEditWithReg(LineEdit):
    """只能输入数字"""

    def __init__(self, digit: bool = False, space: bool = False, *args, **kwargs):
        """
        带正则的行输入
        Args:
            digit: 是否可输入小数点
            space: 是否可输入空格
            *args:
            **kwargs:
        """
        super().__init__(*args, **kwargs)
        if digit and space:
            reg = '[0-9. ]+'
        elif digit:
            reg = '[0-9.]+'
        elif space:
            reg = '[0-9 ]+'
        else:
            reg = '[0-9]+'
        self.regex = QRegExp(reg)
        self.validator = QRegExpValidator(self.regex)
        self.setValidator(self.validator)


class TextEdit(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)


class ComboBox(QComboBox):
    def __init__(self):
        super().__init__()


class RadioButton(QRadioButton):
    def __init__(self, text: str):
        super().__init__(text)


class CheckBox(QCheckBox):
    def __init__(self, text: str):
        super().__init__(text)


class SpinBox(QSpinBox):
    def __init__(self):
        super().__init__()


# class FigureCanvas(FigureCanvasQTAgg):
#     """设置matplotlib图可以鼠标拖动和缩放"""
#     def __init__(self, figure):
#         super(FigureCanvas, self).__init__(figure)
#         self.mouseX = 0  # 获取鼠标按下时的坐标X
#         self.mouseY = 0  # 获取鼠标按下时的坐标Y
#         self.buttonPressed = False
#
#         self.figure.canvas.mpl_connect("button_press_event", self.buttonPressEvent)
#         self.figure.canvas.mpl_connect("button_release_event", self.buttonReleaseEvent)
#         self.figure.canvas.mpl_connect("motion_notify_event", self.motionNotifyEvent)
#         self.figure.canvas.mpl_connect('scroll_event', self.scrollEvent)
#
#     def buttonPressEvent(self, event):
#         """鼠标按键按下"""
#
#         if event.inaxes:  # 判断鼠标是否在axes内
#             if event.button == 1:  # 判断按下的是否为鼠标左键1（右键是3）
#                 self.buttonPressed = True
#                 self.mouseX = event.xdata  # 获取鼠标按下时的坐标X
#                 self.mouseY = event.ydata  # 获取鼠标按下时的坐标Y
#
#     def buttonReleaseEvent(self, event):
#         """鼠标按键释放"""
#
#         if self.buttonPressed:
#             self.buttonPressed = False  # 鼠标松开，结束移动
#
#     def motionNotifyEvent(self, event):
#         """鼠标移动"""
#
#         axes = event.inaxes
#         if axes:
#             if self.buttonPressed:  # 按下状态
#                 # 计算新的坐标原点并移动
#                 # 获取当前最新鼠标坐标与按下时坐标的差值
#                 x = event.xdata - self.mouseX
#                 y = event.ydata - self.mouseY
#                 # 获取当前原点和最大点的4个位置
#                 x_min, x_max = axes.get_xlim()
#                 y_min, y_max = axes.get_ylim()
#
#                 x_min = x_min - x
#                 x_max = x_max - x
#                 y_min = y_min - y
#                 y_max = y_max - y
#
#                 axes.set_xlim(x_min, x_max)
#                 axes.set_ylim(y_min, y_max)
#                 self.figure.canvas.draw()  # 绘图动作实时反映在图像上
#
#     def scrollEvent(self, event):
#         """鼠标滚轮事件"""
#
#         axes = event.inaxes
#         x_min, x_max = axes.get_xlim()
#         y_min, y_max = axes.get_ylim()
#         if not hasattr(self, 'xfanwei'):
#             self.x_range = (x_max - x_min) / 10
#             self.y_range = (y_max - y_min) / 10
#         if event.button == 'up':
#             axes.set(xlim=(x_min + self.x_range, x_max - self.x_range))
#             axes.set(ylim=(y_min + self.y_range, y_max - self.y_range))
#         elif event.button == 'down':
#             axes.set(xlim=(x_min - self.x_range, x_max + self.x_range))
#             axes.set(ylim=(y_min - self.y_range, y_max + self.y_range))
#         self.figure.canvas.draw_idle()  # 绘图动作实时反映在图像上


class MyPlotWidget(pg.PlotWidget):
    """带字体、可显示数据"""

    def __init__(self, title: str, xlabel: str, ylabel: str, grid: bool = False, check_mouse: bool = True,
                 time_axis: bool = False):
        self.time_axis = AbsoluteTimeAxisItem(orientation='bottom') if time_axis else None
        plot_item = pg.PlotItem(axisItems={'bottom': self.time_axis}) if self.time_axis is not None else None
        super().__init__(plotItem=plot_item)
        self.check_mouse = check_mouse
        self.setTitle(plot_html(title, PLOT_TITLE_POINT_SIZE))
        self.setLabel('bottom', plot_html(xlabel, PLOT_LABEL_POINT_SIZE))
        self.setLabel('left', plot_html(ylabel, PLOT_LABEL_POINT_SIZE))
        self.getAxis('bottom').setTickFont(plot_font(PLOT_TICK_POINT_SIZE))
        self.getAxis('left').setTickFont(plot_font(PLOT_TICK_POINT_SIZE))
        self.getAxis('left').setWidth(50)
        if check_mouse:
            self.initPlotItem(title, xlabel, ylabel, grid)
        self.sig_mouse_moved_connected = False

    def initPlotItem(self, title: str, xlabel: str, ylabel: str, grid: bool) -> None:
        """初始化一个plotitem"""
        self.plot_item = self.getPlotItem()
        self.plot_item.setTitle(plot_html(title, PLOT_TITLE_POINT_SIZE))
        self.plot_item.setLabel('bottom', plot_html(xlabel, PLOT_LABEL_POINT_SIZE))
        self.plot_item.setLabel('left', plot_html(ylabel, PLOT_LABEL_POINT_SIZE))
        self.plot_item.getAxis('bottom').setTickFont(plot_font(PLOT_TICK_POINT_SIZE))
        self.plot_item.getAxis('left').setTickFont(plot_font(PLOT_TICK_POINT_SIZE))
        self.plot_item.getAxis('left').setWidth(50)
        if grid:
            self.plot_item.showGrid(x=True, y=True, alpha=0.2)

    def setTimeOrigin(self, origin: datetime | None) -> None:
        if self.time_axis is not None:
            self.time_axis.setOrigin(origin)

    def updateAxesRange(self):
        """更新xy轴范围"""
        self.data = np.nan_to_num(np.array(self.plot_data_item.getData()))  # 获取绘图数据，并把其中可能存在的nan值替换为0
        self.xmin, self.xmax = np.min(self.data[0]), np.max(self.data[0])
        self.ymin, self.ymax = np.min(self.data[1]), np.max(self.data[1])
        self.plot_item.setXRange(self.xmin, self.xmax)
        self.plot_item.setYRange(self.ymin, self.ymax)

    def draw(self, *args, **kwargs) -> None:
        """让plotwidget中的plotitem绘图"""
        if self.check_mouse:
            self.plot_data_item = self.plot_item.plot(*args, **kwargs)
            self.updateAxesRange()
            if not self.sig_mouse_moved_connected:
                self.plot_item.scene().sigMouseMoved.connect(self.mouseMoved)  # 绘图之后绑定槽函数，否则会导致scene快速移动
                self.sig_mouse_moved_connected = True
        else:
            self.plot(*args, **kwargs)

    def mouseMoved(self, pos: Tuple) -> None:
        """鼠标移动槽函数"""
        if hasattr(self, 'text_item'):
            self.plot_item.removeItem(self.text_item)
            self.plot_item.removeItem(self.vertical_line)
            self.plot_item.removeItem(self.horizontal_line)
            self.plot_item.removeItem(self.scatter_plot_item)

        # 数据标签
        self.text_item = pg.TextItem(color=QColor('black'), border=pg.mkPen(QColor('black')),
                                     fill=pg.mkBrush(QColor('yellow')))
        self.text_item.setFont(plot_font(PLOT_TICK_POINT_SIZE))
        self.plot_item.addItem(self.text_item)

        # 十字线
        self.vertical_line = pg.InfiniteLine(angle=90, pen=pg.mkPen('black', width=0.5, style=Qt.DashLine),
                                             movable=False)
        self.horizontal_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('black', width=0.5, style=Qt.DashLine),
                                               movable=False)
        self.plot_item.addItem(self.vertical_line, ignoreBounds=True)
        self.plot_item.addItem(self.horizontal_line, ignoreBounds=True)

        # 数据点
        self.scatter_plot_item = pg.ScatterPlotItem()
        self.plot_item.addItem(self.scatter_plot_item)

        # 设置各item位置
        vb = self.plot_item.vb
        if self.plot_item.sceneBoundingRect().contains(pos):
            mouse_point = vb.mapSceneToView(pos)
            x, y = float(mouse_point.x()), float(mouse_point.y())
            if self.xmin <= x <= self.xmax and self.ymin <= y <= self.ymax:
                index = self.searchPointIndex(x, y)
                self.scatter_plot_item.setData(pos=[[self.data[0][index], self.data[1][index]]], size=10,
                                               pen=QColor('red'))
                self.text_item.setText(f'x: {self.data[0][index]}\ny: {self.data[1][index]}')
                self.text_item.setPos(self.data[0][index], self.data[1][index])
                self.vertical_line.setPos(self.data[0][index])
                self.horizontal_line.setPos(self.data[1][index])

    def searchPointIndex(self, xpos: float, ypos: float) -> int:
        """寻找x坐标附近的点，返回该点的索引"""
        return np.argmin([euclidean((xpos, ypos), (x, y)) for x, y in zip(*self.data)])
