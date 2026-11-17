"""
WebView 窗口组件
"""
import os
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtGui import QColor
from web_channel import attach_window_channel
from frontend_server import FrontendServer
from PySide6.QtWidgets import QApplication
import config


class MonitoringPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        if level != QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
            print(f"[WebView] {message} ({source}:{line})", flush=True)


class MonitoringWebView(QWebEngineView):
    """监测平台 WebView"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_page()

    def setup_page(self):
        """设置页面"""
        page = MonitoringPage(self)
        page.setBackgroundColor(QColor("#020e20"))
        self.setPage(page)
        page.renderProcessTerminated.connect(
            lambda status, code: print(
                f"[WebView] Renderer terminated: {status.name}, exit code {code}",
                flush=True,
            )
        )
        if os.environ.get("FIBER_DIAGNOSTICS") == "1":
            page.loadStarted.connect(lambda: print("[WebView] Page load started", flush=True))
            page.loadFinished.connect(
                lambda ok: print(f"[WebView] Page load finished: {ok}", flush=True)
            )
        self.setStyleSheet("QWebEngineView { background: #020e20; border: 0; }")
        self.window_channel, self.window_bridge = attach_window_channel(page, self.window())

        # 开发模式：连接 Vite 服务器
        if config.DEV_MODE:
            url = QUrl(config.DEV_SERVER_URL)
            print(f"开发模式：连接到 {config.DEV_SERVER_URL}")
        else:
            # 生产模式：加载本地文件
            index_file = config.FRONTEND_DIST_DIR / "index.html"
            if index_file.exists():
                self.frontend_server = FrontendServer(config.FRONTEND_DIST_DIR)
                QApplication.instance().aboutToQuit.connect(self.frontend_server.stop)
                url = QUrl(self.frontend_server.url)
                print(f"生产模式：加载 {index_file}")
            else:
                print(f"错误：找不到前端文件 {index_file}")
                print("请先运行: cd frontend && npm run build")
                url = QUrl("about:blank")

        self.setUrl(url)

