"""桌面外壳：窗口生命周期与快捷键；可见标题栏由 Vue 提供。"""
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QKeySequence, QShortcut
from webview import MonitoringWebView
from window_bridge import ResizeEdges
import config


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("QMainWindow { background: #020e20; }")
        self.setMinimumSize(QSize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT))
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(config.WINDOW_WIDTH, screen.width()),
                    min(config.WINDOW_HEIGHT, screen.height()))
        self.web_view = MonitoringWebView(self)
        self.setCentralWidget(self.web_view)
        self.resize_edges = ResizeEdges(self)
        QApplication.instance().installEventFilter(self.resize_edges)
        self.bind_shortcuts()

    def bind_shortcuts(self):
        for key, callback in (("F5", self.refresh_page),
                              ("F11", self.toggle_fullscreen),
                              ("Ctrl+Q", self.close),
                              ("Alt+Left", self.web_view.back),
                              ("Alt+Right", self.web_view.forward)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)

    def refresh_page(self):
        self.web_view.reload()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def closeEvent(self, event):
        reply = QMessageBox.question(self, "确认退出", "确定要退出监测平台吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            QApplication.instance().removeEventFilter(self.resize_edges)
            event.accept()
        else:
            event.ignore()
