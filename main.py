"""
2024-2-19
ver2.0.3

1.修改了表格区域查看文件的功能
"""
import os
import sys

os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from utils.mainwindow import MainWindow

"pyinstaller -F -w -i image/favicon.ico main.py"

if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
