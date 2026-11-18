"""BIN file selection, loading and data-view refresh."""

import os.path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QTableWidgetItem,
    QVBoxLayout,
    qApp,
)

from core.data.bin_loader import load_bin_group
from core.data.data_group import natural_sort_key
from core.data.data_timeline import DataTimeline, format_wall_time
from core.filter.filter_pipeline import clone_steps
from ui.components.window_feature import WindowFeature
from ui.widgets.custom_widgets import Action, Dialog, Menu, TextEdit
from utils.function import DAS_FILE_FILTER, DAS_FILE_SUFFIXES, printError


class DataFilesController(WindowFeature):
    """BIN file selection, loading and data-view refresh."""

    def __init__(self, window):
        super().__init__(window)
        self.acquisition_params = {}
        self.raw_data = None
        self.data_group = None
        self.data_timeline = None
        self._source_time_headers = []
        self.file_path = ""

    def createMenu(self):
        self.file_menu = Menu(self.window.workspace.menu_bar, "文件")
        self.import_action = Action(
            self.file_menu,
            "导入",
            "导入 BIN 数据文件",
            self.importData,
            shortcut="Ctrl+I",
        )
        self.show_aquisition_params_action = Action(
            self.file_menu, "采集参数", "显示数据采集参数", self.showAcquisitionParams
        )
        self.file_menu.addSeparator()
        self.quit_action = Action(self.file_menu, "退出", "退出软件", qApp.quit, shortcut="Ctrl+Q")

    def resetRange(self):
        self.channel_from_num = 1
        self.channel_to_num = self.channels_num
        self.sampling_times_from_num = 1
        self.sampling_times_to_num = self.sampling_times

    def changeFilePath(self):
        """更改显示的文件路径"""
        file_path = QFileDialog.getExistingDirectory(self.window, "设置文件路径", "")  # 起始路径
        if file_path:
            self.file_path = file_path
            self.updateFile()

    def selectDataFromTable(self):
        """确认后按文件表顺序一次性读取、拼接并更新所选文件。"""
        rows = self.selectedFileRows()
        if not rows:
            printError("请先在文件表中选择要加载和拼接的文件")
            return

        self.loadDataFiles([self.files_table_widget.item(row, 0).text() for row in rows])

    def loadDataFiles(self, file_names):
        """Share the loading lifecycle between the file picker and directory table."""
        if self.window.filtering.das_filter_dialog is not None and self.window.filtering.das_filter_dialog.is_busy():
            printError("滤波链正在计算，请等待完成后再切换文件")
            return
        self.file_names = file_names
        self.load_selected_files_button.setEnabled(False)
        self.load_selected_files_button.setText("正在加载…")
        self.window.statusBar().showMessage(f"正在读取并拼接 {len(self.file_names)} 个文件…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            self.readData()
            self.window.initLocalParams()
            self.window.updateAll()
            self.window.filtering.syncDASFilterDialog()
            self.window.statusBar().showMessage(
                f"已加载并拼接 {len(self.data_group.segments)} 个文件。",
                8000,
            )
        except Exception as err:
            printError(err)
            self.window.statusBar().showMessage(f"文件加载失败：{err}", 10000)
        finally:
            QApplication.restoreOverrideCursor()
            self.load_selected_files_button.setText("确定加载并拼接")
            self.updatePendingFileSelection()

    def selectedFileRows(self):
        """Return selected directory-table rows in the visible file order."""

        return sorted(index.row() for index in self.files_table_widget.selectionModel().selectedRows(0))

    def selectedFilePaths(self):
        """Return normalized absolute paths for the pending table selection."""

        paths = []
        for row in self.selectedFileRows():
            item = self.files_table_widget.item(row, 0)
            if item is not None:
                paths.append(os.path.normcase(os.path.realpath(os.path.join(self.file_path, item.text()))))
        return paths

    def updatePendingFileSelection(self):
        """Update only the pending-selection summary; never read data or redraw plots."""

        rows = self.selectedFileRows()
        if not rows:
            self.pending_file_selection_label.setText("待拼接：请选择文件")
            self.load_selected_files_button.setEnabled(False)
            self.load_selected_files_button.setText("确定加载并拼接")
            return

        items = [self.files_table_widget.item(row, 0) for row in rows]
        names = [item.text() for item in items if item is not None]
        loaded_paths = (
            []
            if self.data_group is None
            else [os.path.normcase(os.path.realpath(segment.path)) for segment in self.data_group.segments]
        )
        matches_loaded = bool(names) and self.selectedFilePaths() == loaded_paths
        if matches_loaded:
            self.pending_file_selection_label.setText(f"当前已加载：{len(names)} 个文件")
        elif len(names) == 1:
            self.pending_file_selection_label.setText(f"待加载：{names[0]}")
        else:
            self.pending_file_selection_label.setText(f"待拼接：{len(names)} 个文件（{names[0]} → {names[-1]}）")
        self.load_selected_files_button.setText("确定加载并拼接")
        self.load_selected_files_button.setEnabled(not matches_loaded)

    def updateWidgetsState(self):
        """更新菜单可操作性状态"""
        self.window.controls.operation_menu.setEnabled(True)
        self.window.plots.plot_menu.setEnabled(True)
        self.window.filtering.filter_menu.setEnabled(True)
        self.window.vehicles.analysis_menu.setEnabled(True)
        self.window.filtering.das_filter_action.setEnabled(True)
        self.window.filtering.reset_das_filter_action.setEnabled(bool(self.window.filtering._das_filter_steps))
        self.window.vehicles.updateSpeedRulerButtons()

    def updateFile(self):
        """更新文件列表显示"""
        self.file_path_line_edit.setText(self.file_path)
        self.file_path_line_edit.setToolTip(os.path.abspath(self.file_path))
        files = sorted(
            (f for f in os.listdir(self.file_path) if f.lower().endswith(DAS_FILE_SUFFIXES)),
            key=natural_sort_key,
        )
        signals_were_blocked = self.files_table_widget.blockSignals(True)
        try:
            self.files_table_widget.setRowCount(len(files))  # 有多少个文件就显示多少行
            for i, file_name in enumerate(files):
                table_widget_item = QTableWidgetItem(file_name)
                table_widget_item.setToolTip(os.path.abspath(os.path.join(self.file_path, file_name)))
                self.files_table_widget.setItem(i, 0, table_widget_item)
            self.highlightLoadedFiles()
        finally:
            self.files_table_widget.blockSignals(signals_were_blocked)
        self.updatePendingFileSelection()

    def highlightLoadedFiles(self):
        """Highlight every directory-table row represented by the loaded data group."""

        self.files_table_widget.clearSelection()
        if self.data_group is None:
            return
        loaded_paths = {os.path.normcase(os.path.realpath(segment.path)) for segment in self.data_group.segments}
        first_item = None
        for row in range(self.files_table_widget.rowCount()):
            item = self.files_table_widget.item(row, 0)
            if item is None:
                continue
            item_path = os.path.normcase(os.path.realpath(os.path.join(self.file_path, item.text())))
            if item_path in loaded_paths:
                item.setSelected(True)
                if first_item is None:
                    first_item = item
        if first_item is not None:
            self.files_table_widget.scrollToItem(first_item, QAbstractItemView.PositionAtCenter)

    def updateDataRange(self):
        """更新数据显示范围"""
        self.visible_data = self.origin_data[
            self.channel_from_num - 1 : self.channel_to_num,
            self.sampling_times_from_num - 1 : self.sampling_times_to_num,
        ]

    def updateDataParams(self):
        """更新数据相关参数"""
        self.current_channels = self.channel_to_num - self.channel_from_num + 1
        self.current_sampling_times = self.sampling_times_to_num - self.sampling_times_from_num + 1

        self.window.controls.channel_number_spinbx.setRange(1, self.current_channels)
        self.window.controls.channel_number_spinbx.setValue(self.window.controls.channel_number)
        self.sampling_rate_line_edit.setText(f"{self.sampling_rate:g}")
        self.current_sampling_times_line_edit.setText(str(self.current_sampling_times))
        self.current_channels_line_edit.setText(str(self.current_channels))

    def updateDataGPSTime(self):
        """Update corrected inferred times for the current visible sample range."""

        self.window.controls._syncTimeCorrectionSpinBox()
        if self.data_timeline is None:
            self.gps_from_line_edit.clear()
            self.gps_to_line_edit.clear()
            self.window.overlays.setEventRangeControlsEnabled(False)
            return
        start_sample = 0
        end_sample = self.data_timeline.total_samples
        if hasattr(self, "sampling_times_from_num") and hasattr(self, "sampling_times_to_num"):
            start_sample = self.sampling_times_from_num - 1
            end_sample = self.sampling_times_to_num
        visible_start = self.data_timeline.absolute_time_for_sample(start_sample)
        visible_end = self.data_timeline.absolute_time_for_sample(end_sample)
        self.gps_from_line_edit.setText(format_wall_time(visible_start))
        self.gps_to_line_edit.setText(format_wall_time(visible_end))
        self.window.plots.plot_gray_scale_widget.setTimeOrigin(self.data_timeline.start_time)
        self.window.plots.plot_single_channel_time_widget.setTimeOrigin(self.data_timeline.start_time)
        self.window.waves.multi_waves_time_axis.setOrigin(self.data_timeline.start_time)
        self.window.overlays.updateEventRangeEditors()
        if self.data_timeline.discontinuities:
            self.window.statusBar().showMessage(
                f"时间连续性提示：{len(self.data_timeline.discontinuities)} 个文件的记录结束时间"
                f"与连续推算偏差超过 {self.data_timeline.continuity_tolerance_seconds:g} s；"
                f"拼接数据仍按采样率连续显示。",
                12000,
            )

    def rebuildDataTimeline(self):
        """Recalculate the continuous wall-clock mapping after loading or correction changes."""

        if self.data_group is None or not self._source_time_headers:
            self.data_timeline = None
            return
        self.data_timeline = DataTimeline.from_data_group(
            self.data_group,
            self._source_time_headers,
            correction_seconds=self.window.controls.time_correction_seconds,
        )
        self.acquisition_params["时间口径"] = "文件名/文件头为采集结束时间；按采样率连续推算"
        self.acquisition_params["设备时间修正"] = f"记录时间 {self.window.controls.time_correction_seconds:+.3f} s"
        self.acquisition_params["推算实际时间"] = (
            f"{format_wall_time(self.data_timeline.start_time)} 至 {format_wall_time(self.data_timeline.end_time)}"
        )
        self.acquisition_params["时间连续性警告"] = str(len(self.data_timeline.discontinuities))

    def importData(self):
        """导入（多个）数据文件后更新参数和绘图等"""
        if self.window.filtering.das_filter_dialog is not None and self.window.filtering.das_filter_dialog.is_busy():
            printError("滤波链正在计算，请等待完成后再导入文件")
            return
        file_names = QFileDialog.getOpenFileNames(self.window, "导入", "", DAS_FILE_FILTER)[0]  # 打开多个数据文件
        if file_names:
            self.file_path = os.path.dirname(file_names[0])
            self.loadDataFiles(file_names)

    def readData(self):
        """Load a BIN group and reset data-dependent analysis state."""
        previous_shape = self.raw_data.shape if self.raw_data is not None else None
        paths = [self.dataFilePath(name) for name in self.file_names]
        loaded = load_bin_group(paths, correction_seconds=self.window.controls.time_correction_seconds)
        self.file_names = [segment.path for segment in loaded.group.segments]
        self.data_group = loaded.group
        self.data_timeline = loaded.timeline
        self.acquisition_params = loaded.acquisition_params
        self._source_time_headers = loaded.time_headers
        self.window.overlays.selected_file_segment_index = None
        self.raw_data = loaded.data
        self.raw_data.setflags(write=False)
        self.origin_data = self.raw_data.copy()
        self.visible_data = self.origin_data
        if self.window.filtering._das_filter_steps:
            self.window.filtering._last_das_filter_steps = clone_steps(self.window.filtering._das_filter_steps)
            self.window.filtering._last_das_filter_shape = previous_shape
        self.window.filtering._das_filter_steps = []
        self.window.vehicles._vehicle_tracking_settings = None
        self.window.vehicles.vehicle_trajectories = []
        self.window.vehicles._hide_vehicle_trajectories = False
        self.window.vehicles.speed_ruler_points = None
        self.sampling_rate = loaded.group.sampling_rate
        self.channels_num = loaded.group.channel_count
        self.sampling_times = loaded.group.total_samples
        self.window.overlays.updateStitchedFilesList()

    def dataFilePath(self, file_name):
        """
        获取数据文件绝对路径。
        """
        file_name = str(file_name)
        return file_name if os.path.isabs(file_name) else os.path.join(self.file_path, file_name)

    @staticmethod
    def dataFileSuffix(file_name):
        """
        获取数据文件后缀。
        """
        return os.path.splitext(str(file_name))[1].lower()

    def showAcquisitionParams(self):
        """打印采集参数"""
        dialog = Dialog()
        dialog.setWindowTitle("采集参数")
        dialog.resize(450, 650)
        text_edit = TextEdit()
        for k, v in self.acquisition_params.items():
            text_edit.append(f"{k}: {v}")

        vbox = QVBoxLayout()
        vbox.addWidget(text_edit)

        dialog.setLayout(vbox)
        dialog.exec_()
