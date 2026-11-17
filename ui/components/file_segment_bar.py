"""Clickable source-file strip used by stitched DAS plots."""

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtWidgets import QGraphicsRectItem


class FileSegmentBarItem(QGraphicsRectItem):
    """Clickable strip identifying one source file in a stitched plot."""

    def __init__(self, rect: QRectF, segment_index: int, on_clicked):
        super().__init__(rect)
        self.segment_index = int(segment_index)
        self._on_clicked = on_clicked
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(20)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_clicked(self.segment_index)
            event.accept()
            return
        super().mousePressEvent(event)
