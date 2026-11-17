"""DAS images and single-channel plots."""

import numpy as np
import pyqtgraph as pg
from matplotlib import pyplot as plt
from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QColor
from scipy.integrate import cumulative_trapezoid

from core.analysis.binary_image import BinaryImageHandler
from ui.components.window_feature import WindowFeature
from ui.widgets.custom_widgets import Action, Menu, MyPlotWidget
from utils.function import printError, toAmplitude, xAxis
from utils.theme import ui_font_family

IMAGE_LEVEL_SAMPLE_LIMIT = 2_000_000


class DataPlotsController(WindowFeature):
    """DAS images and single-channel plots."""

    def __init__(self, window):
        super().__init__(window)
        self.image_colormap = "灰度"
        self.image_level_min = None
        self.image_level_max = None
        self.gray_scale_color_bar = None
        self.diverging_colormaps = {"RdBu", "seismic", "coolwarm"}
        self.binary_image = None

    def createMenu(self):
        self.plot_menu = Menu(self.window.workspace.menu_bar, "绘图", enabled=False)
        self.plot_binary_image_action = Action(self.plot_menu, "二值图", "绘制二值图", self.ployBinaryImage)
        self.plot_heatmap_action = Action(self.plot_menu, "热力图", "绘制热力图", self.plotHeatMapImage)
        self.plot_multichannel_image_action = Action(
            self.plot_menu, "多通道云图", "绘制多通道云图", self.window.waves.showMultiWavesTab
        )
        self.plot_strain_image_action = Action(self.plot_menu, "应变图", "绘制应变图", self.plotStrain)

    def configurePlotDefaults(self):
        plt.rcParams["font.sans-serif"] = [
            ui_font_family(),
            "Microsoft YaHei",
            "DejaVu Sans",
        ]
        plt.rcParams["axes.unicode_minus"] = False
        plt.rcParams["axes.labelsize"] = 10
        plt.rcParams["axes.titlesize"] = 12
        plt.rcParams["xtick.labelsize"] = 9
        plt.rcParams["ytick.labelsize"] = 9
        pg.setConfigOptions(leftButtonPan=True)
        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")

    def plotGrayScaleImage(self):
        """绘制灰度图"""
        self.window.vehicles.speed_ruler_roi = None
        self.plot_gray_scale_widget.clear()
        self.plot_gray_scale_widget.setTimeOrigin(
            self.window.data.data_timeline.start_time if self.window.data.data_timeline is not None else None
        )
        title = "灰度图" if self.image_colormap == "灰度" else f"彩色图 - {self.image_colormap}"
        # The active workspace tab already identifies this view.  Leaving the
        # canvas title empty prevents the same label appearing three times and
        # returns useful vertical space to the data image.
        self.plot_gray_scale_widget.setTitle("")
        self.window.workspace.tab_widget.setTabText(0, title)

        item = pg.ImageItem()
        self.addDataImageItem(
            self.plot_gray_scale_widget,
            item,
            self.window.data.visible_data,
            use_image_controls=True,
            show_color_bar=True,
        )
        self.window.overlays.drawFileBoundaries(self.plot_gray_scale_widget, 0, self.window.data.current_channels)
        self.window.vehicles.drawVehicleTrajectories()
        self.window.overlays.drawEventRange(self.plot_gray_scale_widget)
        self.window.vehicles.drawSpeedRuler()

    def addDataImageItem(
        self,
        plot_widget: MyPlotWidget,
        item: pg.ImageItem,
        data: np.array,
        use_image_controls: bool = False,
        show_color_bar: bool = False,
    ) -> None:
        """
        按当前数据的实际时间长度和通道数绘制二维图，避免自动坐标轴范围过大。
        """
        start_time = (self.window.data.sampling_times_from_num - 1) / self.window.data.sampling_rate
        duration = self.window.data.current_sampling_times / self.window.data.sampling_rate
        channel_count = self.window.data.current_channels

        levels = self.imageLevels(data) if use_image_controls else None
        color_map = self.imageColorMap() if use_image_controls else None

        item.setImage(data.T, autoLevels=levels is None)
        if levels is not None:
            item.setLevels(levels)
        if color_map is not None:
            item.setColorMap(color_map)
        item.setRect(QRectF(start_time, 0, duration, channel_count))
        plot_widget.addItem(item)
        self.updateGrayScaleColorBar(plot_widget, item, color_map, levels, show_color_bar)

        view_box = plot_widget.getViewBox()
        view_box.setLimits(xMin=start_time, xMax=start_time + duration, yMin=0, yMax=channel_count)
        view_box.setRange(
            xRange=(start_time, start_time + duration),
            yRange=(0, channel_count),
            padding=0,
        )

    def updateImageColorParams(self, *args):
        self.image_colormap = self.image_colormap_combx.currentText()
        try:
            self.image_level_min = self.parseOptionalFloat(self.image_level_min_line_edit.text())
            self.image_level_max = self.parseOptionalFloat(self.image_level_max_line_edit.text())
            if (self.image_level_min is None) != (self.image_level_max is None):
                raise ValueError("最小值和最大值需要同时填写，或都留空自动计算")
            if self.image_level_min is not None and self.image_level_max is not None:
                if self.image_level_min >= self.image_level_max:
                    raise ValueError("最小值必须小于最大值")
        except ValueError as err:
            printError(err)
            return

        if hasattr(self.window.data, "visible_data"):
            self.plotGrayScaleImage()

    def autoImageLevels(self):
        self.image_level_min_line_edit.clear()
        self.image_level_max_line_edit.clear()
        self.image_level_min = None
        self.image_level_max = None
        if hasattr(self.window.data, "visible_data"):
            self.plotGrayScaleImage()

    @staticmethod
    def parseOptionalFloat(text: str):
        text = text.strip()
        return None if text == "" else float(text)

    def imageLevels(self, data: np.array):
        flat_data = np.asarray(data).reshape(-1)
        if flat_data.size > IMAGE_LEVEL_SAMPLE_LIMIT:
            stride = int(np.ceil(flat_data.size / IMAGE_LEVEL_SAMPLE_LIMIT))
            flat_data = flat_data[::stride]
        finite_data = flat_data[np.isfinite(flat_data)]
        if finite_data.size == 0:
            return None

        if self.image_level_min is not None and self.image_level_max is not None:
            max_abs = float(np.max(np.abs(finite_data)))
            if max_abs == 0:
                max_abs = 1.0
            return [
                max_abs * self.image_level_min / 100,
                max_abs * self.image_level_max / 100,
            ]

        if self.image_colormap in self.diverging_colormaps:
            limit = float(np.percentile(np.abs(finite_data), 90))
            vmin, vmax = -limit, limit
        else:
            vmin, vmax = np.percentile(finite_data, [2, 98])
            vmin, vmax = float(vmin), float(vmax)

        if vmin == vmax:
            vmin, vmax = vmin - 1, vmax + 1
        return [vmin, vmax]

    def imageColorMap(self):
        if self.image_colormap == "灰度":
            return None

        try:
            return pg.colormap.get(self.image_colormap)
        except Exception:
            values = np.linspace(0.0, 1.0, 256)
            colors = (plt.get_cmap(self.image_colormap)(values) * 255).astype(np.ubyte)
            return pg.ColorMap(values, colors)

    def updateGrayScaleColorBar(
        self,
        plot_widget: MyPlotWidget,
        item: pg.ImageItem,
        color_map,
        levels,
        show_color_bar: bool,
    ) -> None:
        if not show_color_bar:
            return

        if color_map is None:
            if self.gray_scale_color_bar is not None:
                self.gray_scale_color_bar.setVisible(False)
            return

        if self.gray_scale_color_bar is None:
            self.gray_scale_color_bar = pg.ColorBarItem(
                values=levels,
                width=18,
                colorMap=color_map,
                label="幅值",
                interactive=True,
            )
            self.gray_scale_color_bar.setImageItem(item, insert_in=plot_widget.getPlotItem())
        else:
            self.gray_scale_color_bar.setVisible(True)
            self.gray_scale_color_bar.setColorMap(color_map)
            if levels is not None:
                self.gray_scale_color_bar.setLevels(levels)
            self.gray_scale_color_bar.setImageItem(item)

    def plotSingleChannelTime(self):
        """绘制单通道时域图"""
        self.plot_single_channel_time_widget.plot_item.clear()
        self.plot_single_channel_time_widget.setTimeOrigin(
            self.window.data.data_timeline.start_time if self.window.data.data_timeline is not None else None
        )

        x = xAxis(
            self.window.data.current_sampling_times,
            self.window.data.sampling_times_from_num,
            self.window.data.sampling_times_to_num,
            self.window.data.sampling_rate,
        )
        data = self.window.data.visible_data[self.window.controls.channel_number - 1]
        self.plot_single_channel_time_widget.draw(x, data, pen=QColor("blue"))
        self.window.overlays.drawEventRange(self.plot_single_channel_time_widget)

    def plotAmplitudeFrequency(self):
        """绘制幅值图"""
        self.plot_amplitude_frequency_widget.plot_item.clear()

        data = self.window.data.visible_data[self.window.controls.channel_number - 1]
        data = toAmplitude(data)

        x = xAxis(self.window.data.current_sampling_times, sampling_rate=self.window.data.sampling_rate, freq=True)
        self.plot_amplitude_frequency_widget.draw(x, data, pen=QColor("blue"))

    def plotHeatMapImage(self):
        """绘制伪颜色图"""
        plot_widget = MyPlotWidget("热力图", "推算时间", "通道", check_mouse=False, time_axis=True)
        plot_widget.setTimeOrigin(
            self.window.data.data_timeline.start_time if self.window.data.data_timeline is not None else None
        )
        self.window.workspace.tab_widget.addTab(plot_widget, "热力图")

        item = pg.ImageItem()
        item.setColorMap("viridis")
        self.addDataImageItem(plot_widget, item, self.window.data.visible_data)
        self.window.overlays.drawFileBoundaries(plot_widget, 0, self.window.data.current_channels)
        self.window.overlays.drawEventRange(plot_widget)

    def ployBinaryImage(self):
        """二值图设置组件"""
        if not self.binary_image:
            self.binary_image = BinaryImageHandler()
        data = self.binary_image.run(self.window.data.visible_data)

        if data is not None:
            plot_widget = MyPlotWidget("二值图", "推算时间", "通道", check_mouse=False, time_axis=True)
            plot_widget.setTimeOrigin(
                self.window.data.data_timeline.start_time if self.window.data.data_timeline is not None else None
            )
            self.window.workspace.tab_widget.addTab(plot_widget, f"二值图 - 阈值={self.binary_image.threshold}")

            item = pg.ImageItem()
            self.addDataImageItem(plot_widget, item, data)
            self.window.overlays.drawFileBoundaries(plot_widget, 0, self.window.data.current_channels)
            self.window.overlays.drawEventRange(plot_widget)

    def plotStrain(self):
        """将相位差转为应变率再积分"""
        data = self.window.data.visible_data[self.window.controls.channel_number - 1]
        x = xAxis(
            self.window.data.current_sampling_times,
            self.window.data.sampling_times_from_num,
            self.window.data.sampling_times_to_num,
            self.window.data.sampling_rate,
        )
        data = cumulative_trapezoid(data, x, initial=0) * 1e6
        plot_widget = MyPlotWidget("应变图", "推算时间", "应变（με）", grid=True, time_axis=True)
        plot_widget.setTimeOrigin(
            self.window.data.data_timeline.start_time if self.window.data.data_timeline is not None else None
        )
        plot_widget.draw(x, data, pen=QColor("blue"))
        self.window.overlays.drawEventRange(plot_widget)
        self.window.workspace.tab_widget.addTab(plot_widget, f"应变图 - 通道号={self.window.controls.channel_number}")
