"""可折叠分组：标题按钮 + 内容区。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSizePolicy, QToolButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("filterSection")
        self.header = QToolButton(text=title)
        self.header.setObjectName("sectionToggle")
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setCheckable(True)
        self.header.setAccessibleName(f"{title}分组")
        self.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.content = QWidget()
        self.content.setObjectName("filterSectionBody")
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.content)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self.header.toggled.connect(self.set_expanded)
        self.header.setChecked(bool(expanded))
        self.set_expanded(bool(expanded))

    def set_expanded(self, expanded: bool) -> None:
        self.content.setVisible(bool(expanded))
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.header.setToolTip(f"{'收起' if expanded else '展开'}{self.header.text()}分组")
