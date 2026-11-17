"""
应用入口
"""
import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from main_window import MainWindow
import config


def main():
    """主函数"""
    # 设置高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName(config.APP_AUTHOR)

    # 创建主窗口
    window = MainWindow()
    window.show()

    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    print(f"启动 {config.APP_NAME} v{config.APP_VERSION}")
    print(f"开发模式: {config.DEV_MODE}")
    print(f"Qt graphics backend: {os.environ.get('QSG_RHI_BACKEND', 'default')}")
    print(f"Chromium flags: {os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS', '(default)')}")

    if config.DEV_MODE:
        print("\n请确保前端开发服务器正在运行:")
        print("  cd frontend")
        print("  npm run dev")
        print()

    main()
