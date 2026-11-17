"""Data time correction and visible-range controls."""

from PyQt5.QtWidgets import QDoubleSpinBox, QFormLayout, QHBoxLayout, QVBoxLayout

from ui.components.window_feature import WindowFeature
from ui.widgets.custom_widgets import (
    Action,
    Dialog,
    Label,
    LineEditWithReg,
    Menu,
    PushButton,
)


class DataControlsController(WindowFeature):
    """Data time correction and visible-range controls."""

    def __init__(self, window):
        super().__init__(window)
        self.channel_number = 1
        self.channel_number_step = 1
        self.time_correction_seconds = self.window.preferences.time_correction_seconds()

    def createMenu(self):
        self.operation_menu = Menu(self.window.workspace.menu_bar, "操作", enabled=False)
        self.set_time_range_action = Action(
            self.operation_menu,
            "查看范围（相对秒）",
            "按相对秒设置数据查看范围",
            self.setTimeRangeDialog,
        )
        self.set_channel_range_action = Action(
            self.operation_menu,
            "查看范围（通道）",
            "按通道设置数据查看范围",
            self.setChannelRangeDialog,
        )
        self.time_correction_action = Action(
            self.operation_menu,
            "时间校正设置",
            "设置并保存设备时间偏差",
            self.showTimeCorrectionDialog,
        )
        self.operation_menu.addSeparator()
        self.change_channel_number_step_action = Action(
            self.operation_menu,
            "设置通道切换步长",
            "设置切换通道时的步长",
            self.changeChannelNumberStep,
        )

    def changeChannelNumber(self):
        """Use the integer supplied by the channel spin box."""
        self.channel_number = self.channel_number_spinbx.value()

    def _syncTimeCorrectionSpinBox(self):
        """Reflect the saved correction in the editable sidebar control."""

        self.time_correction_spin_box.blockSignals(True)
        try:
            self.time_correction_spin_box.setValue(self.time_correction_seconds)
        finally:
            self.time_correction_spin_box.blockSignals(False)

    def applyTimeCorrectionFromSidebar(self):
        """Persist the sidebar value only after its explicit Apply action."""

        self.setTimeCorrectionSeconds(self.time_correction_spin_box.value())

    def setTimeCorrectionSeconds(self, correction_seconds: float):
        """Persist a correction and refresh all corrected-time dependent views."""

        self.time_correction_seconds = float(correction_seconds)
        self.window.annotations.video_annotation_project.das_correction_seconds = self.time_correction_seconds
        self.window.preferences.set_time_correction_seconds(self.time_correction_seconds)
        self.window.data.rebuildDataTimeline()
        self.window.video_files.rebuildVideoSequenceTimeline()
        self.window.data.updateDataGPSTime()
        self.window.overlays.updateStitchedFilesList()
        self.window.sync.updateVideoAnnotationDataContext()
        self.window.annotations.refreshVideoAnnotationTable(
            select_identifier=self.window.annotations.video_annotation_selected_id
        )
        if hasattr(self.window.data, "visible_data"):
            self.window.updateImages()
        else:
            self.window.video_plot.plotVideoComparisonImage()
        self.window.statusBar().showMessage(
            f"时间修正已保存：记录时间 {self.time_correction_seconds:+.3f} s。",
            8000,
        )

    def showTimeCorrectionDialog(self):
        """Edit and persist the correction added to device-recorded end times."""

        dialog = Dialog()
        dialog.setWindowTitle("时间校正设置")
        dialog.setMinimumWidth(520)
        correction = QDoubleSpinBox()
        correction.setRange(-86400.0, 86400.0)
        correction.setDecimals(3)
        correction.setSingleStep(0.1)
        correction.setSuffix(" s")
        correction.setValue(self.time_correction_seconds)
        correction.setToolTip("设备时间落后真实时间时填正数；例如落后 12 秒填写 12")

        formula = Label("计算公式：推算实际时间 = 文件名/文件头记录时间 + 修正秒数")
        formula.setWordWrap(True)
        example = Label("例如手机为 01:00:12、设备为 01:00:00，应填写 +12.000 s。")
        example.setWordWrap(True)
        example.setStyleSheet("color: #555;")
        save_button = PushButton("保存并应用")
        cancel_button = PushButton("取消")

        def save():
            self.setTimeCorrectionSeconds(correction.value())
            dialog.accept()

        save_button.clicked.connect(save)
        cancel_button.clicked.connect(dialog.reject)
        form = QFormLayout()
        form.addRow("设备记录时间修正", correction)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(formula)
        layout.addWidget(example)
        layout.addLayout(buttons)
        dialog.setLayout(layout)
        dialog.exec_()

    def setTimeRangeDialog(self):
        """调用按时间查看数据范围的对话框"""
        dialog = Dialog()
        dialog.setWindowTitle("查看数据（时间）")

        from_label = Label("始")
        self.time_range_from_line_edit = LineEditWithReg(digit=True)
        self.time_range_from_line_edit.setText(
            str((self.window.data.sampling_times_from_num - 1) / self.window.data.sampling_rate)
        )
        to_label = Label("止")
        self.time_range_to_line_edit = LineEditWithReg(digit=True)
        self.time_range_to_line_edit.setText(
            str(self.window.data.sampling_times_to_num / self.window.data.sampling_rate)
        )

        btn = PushButton("确定")
        btn.clicked.connect(self.setTimeRange)
        btn.clicked.connect(self.window.data.updateDataRange)
        btn.clicked.connect(self.window.data.updateDataParams)
        btn.clicked.connect(self.window.data.updateDataGPSTime)
        btn.clicked.connect(self.window.updateImages)
        btn.clicked.connect(dialog.close)

        hbox = QHBoxLayout()
        vbox = QVBoxLayout()
        hbox.addWidget(from_label)
        hbox.addWidget(self.time_range_from_line_edit)
        hbox.addStretch(1)
        hbox.addWidget(to_label)
        hbox.addWidget(self.time_range_to_line_edit)
        vbox.addLayout(hbox)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def setTimeRange(self):
        """根据设置时间截取数据"""
        from_num = int(float(self.time_range_from_line_edit.text()) * self.window.data.sampling_rate)
        to_num = int(float(self.time_range_to_line_edit.text()) * self.window.data.sampling_rate)

        if (
            0 <= from_num < self.window.data.origin_data.shape[1]
            and 1 < to_num <= self.window.data.origin_data.shape[1]
        ):
            if from_num > to_num:
                from_num, to_num = to_num, from_num
        else:
            from_num, to_num = 0, self.window.data.origin_data.shape[1]

        self.window.data.sampling_times_from_num, self.window.data.sampling_times_to_num = from_num + 1, to_num
        self.window.overlays.setEventSampleRange(from_num, to_num)
        self.window.filtering.syncDASFilterVisibleRange()

    def setChannelRangeDialog(self):
        """按通道截取数据的对话框"""
        dialog = Dialog()
        dialog.setWindowTitle("查看数据（通道）")

        from_label = Label("始")
        self.channel_from = LineEditWithReg()
        self.channel_from.setText(str(self.window.data.channel_from_num))
        to_label = Label("止")
        self.channel_to = LineEditWithReg()
        self.channel_to.setText(str(self.window.data.channel_to_num))

        btn = PushButton("确定")
        btn.clicked.connect(self.setChannelRange)
        btn.clicked.connect(self.window.data.updateDataRange)
        btn.clicked.connect(self.window.data.updateDataParams)
        btn.clicked.connect(self.window.updateImages)
        btn.clicked.connect(dialog.close)

        vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        hbox.addWidget(from_label)
        hbox.addWidget(self.channel_from)
        hbox.addStretch(1)
        hbox.addWidget(to_label)
        hbox.addWidget(self.channel_to)

        vbox.addLayout(hbox)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def setChannelRange(self):
        """以通道数截取"""
        from_num, to_num = int(self.channel_from.text()), int(self.channel_to.text())

        if (
            1 <= from_num < self.window.data.origin_data.shape[0]
            and 1 < to_num <= self.window.data.origin_data.shape[0]
        ):
            if from_num > to_num:
                from_num, to_num = to_num, from_num
        elif from_num == 0 and 1 < to_num <= self.window.data.origin_data.shape[0]:
            from_num = 1
        else:
            from_num, to_num = 1, self.window.data.origin_data.shape[0]

        self.window.data.channel_from_num, self.window.data.channel_to_num = from_num, to_num

    def changeChannelNumberStep(self):
        """改变通道号的步长"""
        dialog = Dialog()
        dialog.setFixedWidth(400)
        dialog.setWindowTitle("设置通道切换步长")

        channel_number_step_label = Label("步长")
        self.channel_number_step_line_edit = LineEditWithReg()
        self.channel_number_step_line_edit.setToolTip("切换通道时的步长")
        self.channel_number_step_line_edit.setText(str(self.channel_number_step))

        btn = PushButton("确定")
        btn.clicked.connect(self.updateChannelNumberStep)
        btn.clicked.connect(dialog.close)

        vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        hbox.addWidget(channel_number_step_label)
        hbox.addWidget(self.channel_number_step_line_edit)
        vbox.addLayout(hbox)
        vbox.addSpacing(5)
        vbox.addWidget(btn)

        dialog.setLayout(vbox)
        dialog.exec_()

    def updateChannelNumberStep(self):
        """更新读取通道号的步长"""
        self.channel_number_step = int(self.channel_number_step_line_edit.text())

        self.channel_number_spinbx.setSingleStep(self.channel_number_step)
