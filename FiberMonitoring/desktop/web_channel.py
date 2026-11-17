"""在前端挂载前注入窗口通信桥，避免异步加载竞态。"""
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineScript
from window_bridge import WindowBridge
from PySide6.QtCore import QFile, QIODevice


def attach_window_channel(page, window):
    channel = QWebChannel(page)
    bridge = WindowBridge(window)
    channel.registerObject("nativeWindow", bridge)
    page.setWebChannel(channel)
    script = QWebEngineScript()
    script.setName("desktop-window-controls")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    library = QFile(":/qtwebchannel/qwebchannel.js")
    if not library.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError("Qt WebChannel JavaScript resource is unavailable")
    source = bytes(library.readAll()).decode("utf-8")
    library.close()
    script.setSourceCode(source + """
        new QWebChannel(qt.webChannelTransport, channel => {
            window.desktopWindow = channel.objects.nativeWindow;
            window.dispatchEvent(new Event('desktop-window-ready'));
        });
    """)
    page.scripts().insert(script)
    return channel, bridge
