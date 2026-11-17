"""滤波链区域：已保存方案、当前链列表和编辑按钮。

只负责显示和发信号；链本身的数据由对话框持有。
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ChainView(QWidget):
    rowChanged = pyqtSignal(int)
    stepToggled = pyqtSignal(int, bool)
    updateRequested = pyqtSignal()
    deleteRequested = pyqtSignal()
    moveRequested = pyqtSignal(int)
    clearRequested = pyqtSignal()
    saveRequested = pyqtSignal(str)
    loadRequested = pyqtSignal(str)
    deleteSavedRequested = pyqtSignal(str)
    autoReapplyToggled = pyqtSignal(bool)

    def __init__(self, auto_reapply: bool, parent=None):
        super().__init__(parent)
        self._refreshing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 已保存方案
        saved_row = QHBoxLayout()
        saved_row.setSpacing(4)
        saved_row.addWidget(QLabel("滤波方案"))
        self.saved_combo = QComboBox()
        self.saved_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.saved_combo.setMinimumContentsLength(10)
        self.saved_combo.setPlaceholderText("暂无已保存方案")
        self.saved_combo.setToolTip("命名方案和最近确认的滤波链会在下次启动时保留")
        self.saved_combo.currentIndexChanged.connect(
            lambda _i: self.set_controls(*self._last_controls)
        )
        saved_row.addWidget(self.saved_combo, 1)
        layout.addLayout(saved_row)

        self.load_button = QPushButton("载入方案")
        self.save_button = QPushButton("保存方案")
        self.delete_saved_button = QPushButton("删除方案")
        self.load_button.clicked.connect(self._load_clicked)
        self.save_button.clicked.connect(self._save_clicked)
        self.delete_saved_button.clicked.connect(self._delete_saved_clicked)
        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        for button in (self.load_button, self.save_button, self.delete_saved_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        # 当前链
        header = QHBoxLayout()
        header.addWidget(QLabel("当前链（勾选表示启用）"))
        header.addStretch(1)
        self.state_label = QLabel()
        self.state_label.setObjectName("pipelineStateLabel")
        header.addWidget(self.state_label)
        layout.addLayout(header)

        self.list = QListWidget()
        self.list.setMinimumHeight(132)
        self.list.setMaximumHeight(190)
        self.list.setAlternatingRowColors(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setWordWrap(True)
        self.list.setSpacing(2)
        self.list.setTextElideMode(Qt.ElideNone)
        self.list.itemChanged.connect(self._item_changed)
        self.list.currentRowChanged.connect(self._row_changed)
        layout.addWidget(self.list)

        # 编辑按钮
        trash = getattr(QStyle, "SP_TrashIcon", QStyle.SP_DialogCancelButton)
        specs = (
            (QStyle.SP_DialogApplyButton, "替换选中步骤", self.updateRequested.emit),
            (trash, "删除选中步骤", self.deleteRequested.emit),
            (QStyle.SP_ArrowUp, "上移选中步骤", lambda: self.moveRequested.emit(-1)),
            (QStyle.SP_ArrowDown, "下移选中步骤", lambda: self.moveRequested.emit(1)),
        )
        self.update_button, self.delete_button, self.up_button, self.down_button = (
            self._tool_button(*spec) for spec in specs
        )
        self.clear_button = QPushButton("清空链")
        self.clear_button.setToolTip("仅清空待应用滤波链；不会立即改变主图")
        self.clear_button.clicked.connect(self.clearRequested)
        tools = QHBoxLayout()
        tools.setSpacing(4)
        for button in (self.update_button, self.delete_button, self.up_button, self.down_button):
            tools.addWidget(button)
        tools.addStretch(1)
        tools.addWidget(self.clear_button)
        layout.addLayout(tools)

        self.auto_reapply_checkbox = QCheckBox("切换文件后自动应用最近一次成功应用的滤波链")
        self.auto_reapply_checkbox.setChecked(auto_reapply)
        self.auto_reapply_checkbox.setToolTip(
            "自动从新文件的导入基线重新回放相同步骤；不兼容时保持原始数据并提示"
        )
        self.auto_reapply_checkbox.toggled.connect(self.autoReapplyToggled)
        layout.addWidget(self.auto_reapply_checkbox)

        self._last_controls = (False, 0, False)
        self.set_controls(False, 0, False)

    def _tool_button(self, icon, text, action) -> QToolButton:
        button = QToolButton()
        button.setIcon(self.style().standardIcon(icon))
        button.setAccessibleName(text)
        button.setToolTip(text)
        button.setObjectName("pipelineToolButton")
        button.setAutoRaise(False)
        button.clicked.connect(lambda _checked=False: action())
        return button

    def current_row(self) -> int:
        return self.list.currentRow()

    def show_steps(self, rows, selected_row: int = -1) -> int:
        """rows: [(文字, 悬停提示, 是否启用)]。返回选中的行（无则 -1）。"""
        self._refreshing = True
        try:
            self.list.clear()
            for text, tooltip, enabled in rows:
                item = QListWidgetItem(text)
                item.setFlags(
                    item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled
                )
                item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
                item.setToolTip(tooltip)
                self.list.addItem(item)
            row = -1
            if rows:
                row = selected_row if 0 <= selected_row < len(rows) else 0
                self.list.setCurrentRow(row)
        finally:
            self._refreshing = False
        return row

    def set_state(self, state: str, text: str) -> None:
        self.state_label.setText(text)
        self.state_label.setProperty("state", state)
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)

    def set_controls(self, busy: bool, count: int, _unused: bool = False) -> None:
        """按 busy/count/row 刷新按钮可用状态。"""
        self._last_controls = (busy, count, _unused)
        row = self.list.currentRow()
        selected = 0 <= row < count and not busy
        self.list.setEnabled(not busy)
        self.saved_combo.setEnabled(not busy)
        self.update_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)
        self.up_button.setEnabled(selected and row > 0)
        self.down_button.setEnabled(selected and row < count - 1)
        self.clear_button.setEnabled(count > 0 and not busy)
        has_saved = bool(self.saved_combo.currentData())
        self.load_button.setEnabled(has_saved and not busy)
        self.delete_saved_button.setEnabled(has_saved and not busy)
        self.save_button.setEnabled(count > 0 and not busy)

    def set_saved(self, entries) -> None:
        """刷新已保存方案下拉框，不改动当前链。"""
        current = self.saved_combo.currentData()
        self.saved_combo.blockSignals(True)
        self.saved_combo.clear()
        named = [entry for entry in entries if entry.get("kind") == "named"]
        recent = [entry for entry in entries if entry.get("kind") == "recent"]
        for entry in named:
            self.saved_combo.addItem(
                f"方案｜{entry.get('name', '')}", entry.get("identifier")
            )
        if named and recent:
            self.saved_combo.insertSeparator(self.saved_combo.count())
        for entry in recent:
            saved_at = str(entry.get("saved_at", "")).replace("T", " ")
            shown = saved_at[5:16] if len(saved_at) >= 16 else saved_at
            self.saved_combo.addItem(
                f"最近｜{shown}｜{len(entry.get('steps', []))} 步",
                entry.get("identifier"),
            )
        if current:
            index = self.saved_combo.findData(current)
            if index >= 0:
                self.saved_combo.setCurrentIndex(index)
        self.saved_combo.blockSignals(False)
        self.set_controls(*self._last_controls)

    def _row_changed(self, row: int) -> None:
        if not self._refreshing:
            self.rowChanged.emit(row)

    def _item_changed(self, item: QListWidgetItem) -> None:
        if not self._refreshing:
            self.stepToggled.emit(self.list.row(item), item.checkState() == Qt.Checked)

    def _save_clicked(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "保存滤波方案", "方案名称", text="我的滤波方案"
        )
        if accepted and name.strip():
            self.saveRequested.emit(name.strip())

    def _load_clicked(self) -> None:
        identifier = self.saved_combo.currentData()
        if identifier:
            self.loadRequested.emit(str(identifier))

    def _delete_saved_clicked(self) -> None:
        identifier = self.saved_combo.currentData()
        if not identifier:
            return
        reply = QMessageBox.question(
            self,
            "删除滤波方案",
            f"确定删除\"{self.saved_combo.currentText()}\"吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.deleteSavedRequested.emit(str(identifier))
