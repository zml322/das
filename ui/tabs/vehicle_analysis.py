"""Vehicle trajectory picking and manual speed measurement."""

import numpy as np
import pyqtgraph as pg

from core.tracking.speed_ruler import (
    SpeedRulerROI,
    calculate_projected_speed,
    format_speed_measurement,
)
from ui.components.window_feature import WindowFeature
from ui.dialogs.vehicle_tracking_dialog import VehicleTrackingDialog
from ui.widgets.custom_widgets import Action, Menu
from utils.function import printError


class VehicleAnalysisController(WindowFeature):
    """Vehicle trajectory picking and manual speed measurement."""

    def __init__(self, window):
        super().__init__(window)
        self._vehicle_tracking_settings = None
        self.vehicle_trajectories = []
        self._hide_vehicle_trajectories = False
        self.speed_ruler_channel_spacing = 4.0
        self.speed_ruler_active = False
        self.speed_ruler_points = None
        self.speed_ruler_roi = None

    def createMenu(self):
        self.analysis_menu = Menu(self.window.workspace.menu_bar, "分析", enabled=False)
        self.vehicle_tracking_action = Action(
            self.analysis_menu,
            "车辆轨迹拾取",
            "提取车辆时空轨迹",
            self.showVehicleTrackingDialog,
        )
        self.speed_ruler_action = Action(
            self.analysis_menu,
            "车辆速度标尺",
            "添加可拖动的车辆投影速度测量线",
            self.addOrResetSpeedRuler,
        )

    def drawVehicleTrajectories(self, plot_widget=None, full_range: bool = False):
        """Draw stored vehicle paths in an image plot's local coordinates."""
        if self._hide_vehicle_trajectories or not self.vehicle_trajectories:
            return
        if not hasattr(self.window.data, "sampling_times_from_num") or not hasattr(
            self.window.data, "channel_from_num"
        ):
            return
        plot_widget = plot_widget or self.window.plots.plot_gray_scale_widget

        if full_range:
            start_time = 0.0
            end_time = self.window.data.sampling_times / self.window.data.sampling_rate
            channel_from = 1
            channel_to = self.window.data.channels_num
        else:
            start_time = (self.window.data.sampling_times_from_num - 1) / self.window.data.sampling_rate
            end_time = self.window.data.sampling_times_to_num / self.window.data.sampling_rate
            channel_from = self.window.data.channel_from_num
            channel_to = self.window.data.channel_to_num
        colors = (
            "#e6194B",
            "#3cb44b",
            "#4363d8",
            "#f58231",
            "#911eb4",
            "#42d4f4",
            "#f032e6",
            "#bfef45",
        )

        for trajectory in self.vehicle_trajectories:
            if not getattr(trajectory, "visible", True):
                continue
            channels = np.asarray(trajectory.channels)
            times = np.asarray(trajectory.times)
            visible = (
                (channels >= channel_from) & (channels <= channel_to) & (times >= start_time) & (times <= end_time)
            )
            if np.count_nonzero(visible) < 2:
                continue
            color = colors[(int(trajectory.identifier) - 1) % len(colors)]
            local_channels = channels[visible] - channel_from + 0.5
            plot_widget.plot(
                times[visible],
                local_channels,
                pen=pg.mkPen(color=color, width=2),
                connect="finite",
            )
            label = pg.TextItem(str(trajectory.identifier), color=color, anchor=(0, 1))
            label.setPos(float(times[visible][0]), float(local_channels[0]))
            plot_widget.addItem(label)

    def defaultSpeedRulerPoints(self):
        """Return a visible diagonal in full-data time/global-channel coordinates."""

        start_time = (self.window.data.sampling_times_from_num - 1) / self.window.data.sampling_rate
        end_time = self.window.data.sampling_times_to_num / self.window.data.sampling_rate
        time_span = max(end_time - start_time, 1 / self.window.data.sampling_rate)
        channel_span = max(float(self.window.data.channel_to_num - self.window.data.channel_from_num), 0.0)
        elapsed = time_span * 0.5
        channel_delta = min(
            channel_span * 0.5,
            20.0 * elapsed / self.speed_ruler_channel_spacing,
        )
        if 0 < channel_delta < 20.0 * elapsed / self.speed_ruler_channel_spacing:
            elapsed = channel_delta * self.speed_ruler_channel_spacing / 20.0
        return (
            (
                start_time + time_span * 0.25,
                self.window.data.channel_from_num + channel_span * 0.25,
            ),
            (
                start_time + time_span * 0.25 + elapsed,
                self.window.data.channel_from_num + channel_span * 0.25 + channel_delta,
            ),
        )

    def addOrResetSpeedRuler(self):
        """Add one speed ruler, or reset the existing ruler into the current view."""

        if not hasattr(self.window.data, "visible_data") or self.window.data.visible_data.size == 0:
            printError("请先导入 DAS 数据")
            return
        self.speed_ruler_active = True
        self.speed_ruler_points = self.defaultSpeedRulerPoints()
        self._removeSpeedRulerGraphics()
        self.drawSpeedRuler()
        self.window.workspace.tab_widget.setCurrentWidget(self.window.plots.gray_scale_container)
        self.updateSpeedRulerButtons()

    def _setSpeedRulerStatus(self, text: str, detail: str, state: str) -> None:
        """Keep the toolbar status compact while retaining the full measurement."""

        self.speed_ruler_status_label.setText(text)
        self.speed_ruler_status_label.setToolTip(detail)
        self.speed_ruler_status_label.setProperty("state", state)
        self.speed_ruler_status_label.style().unpolish(self.speed_ruler_status_label)
        self.speed_ruler_status_label.style().polish(self.speed_ruler_status_label)

    def removeSpeedRuler(self):
        """Remove only the manual overlay; never modify DAS or trajectory data."""

        self.speed_ruler_active = False
        self.speed_ruler_points = None
        self._removeSpeedRulerGraphics()
        self._setSpeedRulerStatus("未添加", "速度标尺未添加", "inactive")
        self.updateSpeedRulerButtons()

    def _removeSpeedRulerGraphics(self):
        ruler = self.speed_ruler_roi
        self.speed_ruler_roi = None
        if ruler is None:
            return
        try:
            self.window.plots.plot_gray_scale_widget.removeItem(ruler)
        except RuntimeError:
            pass

    def drawSpeedRuler(self):
        """Recreate the ruler after plot refresh using stored full-data coordinates."""

        if (
            not self.speed_ruler_active
            or not hasattr(self.window.data, "visible_data")
            or self.window.data.visible_data.size == 0
        ):
            return
        if self.speed_ruler_points is None:
            self.speed_ruler_points = self.defaultSpeedRulerPoints()
        local_points = [
            (time_value, channel - self.window.data.channel_from_num + 0.5)
            for time_value, channel in self.speed_ruler_points
        ]
        ruler = SpeedRulerROI(local_points, self.speed_ruler_channel_spacing)
        self.speed_ruler_roi = ruler
        ruler.sigRegionChanged.connect(self.speedRulerMoved)
        self.window.plots.plot_gray_scale_widget.addItem(ruler)
        self.speedRulerMoved(ruler)
        self.updateSpeedRulerButtons()

    def speedRulerMoved(self, ruler):
        """Persist ruler endpoints and update speed text during dragging/rotation."""

        if ruler is not self.speed_ruler_roi:
            return
        parent_points = ruler.parentPoints()
        self.speed_ruler_points = tuple(
            (time_value, local_channel + self.window.data.channel_from_num - 0.5)
            for time_value, local_channel in parent_points
        )
        measurement = calculate_projected_speed(
            self.speed_ruler_points[0],
            self.speed_ruler_points[1],
            self.speed_ruler_channel_spacing,
        )
        detail = format_speed_measurement(measurement)
        if measurement.valid:
            text = f"{measurement.speed_mps:.2f} m/s · {measurement.direction_text}"
            state = "active"
        else:
            text = "无法测量"
            state = "inactive"
        self._setSpeedRulerStatus(text, detail, state)

    def updateSpeedRulerChannelSpacing(self, value: float):
        """Recalculate the active ruler when the real adjacent-channel spacing changes."""

        self.speed_ruler_channel_spacing = float(value)
        if self.speed_ruler_roi is not None:
            self.speed_ruler_roi.setChannelSpacing(self.speed_ruler_channel_spacing)
            self.speedRulerMoved(self.speed_ruler_roi)

    def updateSpeedRulerButtons(self):
        has_data = hasattr(self.window.data, "visible_data") and self.window.data.visible_data.size > 0
        self.speed_ruler_reset_button.setEnabled(has_data)
        self.speed_ruler_reset_button.setText("重置速度标尺" if self.speed_ruler_active else "添加速度标尺")
        self.speed_ruler_remove_button.setEnabled(self.speed_ruler_active)

    def showVehicleTrackingDialog(self):
        """Open the non-destructive vehicle trajectory picker."""
        if self.window.data.raw_data is None:
            printError("请先导入 DAS 数据")
            return
        visible_range = (
            self.window.data.channel_from_num,
            self.window.data.channel_to_num,
            self.window.data.sampling_times_from_num,
            self.window.data.sampling_times_to_num,
        )
        dialog = VehicleTrackingDialog(
            self.window.data.raw_data,
            self.window.data.sampling_rate,
            visible_range=visible_range,
            settings=self._vehicle_tracking_settings,
            trajectories=self.vehicle_trajectories,
            parent=self.window,
        )
        self.vehicle_tracking_dialog = dialog
        dialog.trajectoriesChanged.connect(self.setVehicleTrajectories)
        dialog.exec_()
        self._vehicle_tracking_settings = dialog.settings()
        self.vehicle_tracking_dialog = None

    def setVehicleTrajectories(self, trajectories):
        """Persist analysis-only trajectories and refresh their image overlay."""
        self.vehicle_trajectories = list(trajectories)
        self._hide_vehicle_trajectories = False
        self.window.updateImages()
        count = len(self.vehicle_trajectories)
        self.window.statusBar().showMessage(
            f"车辆轨迹拾取结果已更新：{count} 条。结果仅叠加显示，不会修改数据。",
            6000,
        )

    def clearVehicleTrajectories(self, update: bool = True):
        """Discard paths whose source data have been replaced."""
        self.vehicle_trajectories = []
        self._hide_vehicle_trajectories = False
        if update and self.window.data.raw_data is not None:
            self.window.updateImages()
