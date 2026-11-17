"""供 Vue 标题栏调用的窗口动作，以及无边框窗口的边缘缩放。"""
from PySide6.QtCore import QObject, QEvent, Qt, Slot


class WindowBridge(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window

    @Slot()
    def minimize(self):
        self.window.showMinimized()

    @Slot()
    def toggleMaximize(self):
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()

    @Slot()
    def close(self):
        self.window.close()

    @Slot()
    def startMove(self):
        self.window.windowHandle().startSystemMove()


class ResizeEdges(QObject):
    """Retain native edge resizing after removing the system title bar."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.MouseButtonPress:
            return False
        if event.button() != Qt.MouseButton.LeftButton or self.window.isMaximized():
            return False
        if not hasattr(watched, "window") or watched.window() is not self.window:
            return False
        point = self.window.mapFromGlobal(event.globalPosition().toPoint())
        edges = Qt.Edge(0)
        if point.x() < 5:
            edges |= Qt.Edge.LeftEdge
        elif point.x() > self.window.width() - 5:
            edges |= Qt.Edge.RightEdge
        if point.y() < 5:
            edges |= Qt.Edge.TopEdge
        elif point.y() > self.window.height() - 5:
            edges |= Qt.Edge.BottomEdge
        if edges:
            return self.window.windowHandle().startSystemResize(edges)
        return False
