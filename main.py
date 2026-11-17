import os
import sys

os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication
from utils.function import resourcePath
from ui.main_window import MainWindow
from utils.theme import apply_application_theme
from utils.version import __version__

"Windows 打包：python build_windows.py；macOS 打包：python build_macos.py"

if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    apply_application_theme(app)
    app.setApplicationName('DASViewer')
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(resourcePath('image/img.png')))
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
