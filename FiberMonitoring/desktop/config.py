"""
应用配置
"""
import os
from pathlib import Path

# 应用信息
APP_NAME = "光纤全场景三维智能监测平台"
APP_VERSION = "1.0.0"
APP_AUTHOR = "DAS Monitoring Team"

# 路径配置
BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"

# 开发模式：连接 Vite 开发服务器
# 默认由本地 HTTP 服务加载构建产物，不依赖 Vite。
DEV_MODE = os.environ.get("FIBER_DEV", "0") == "1"
DEV_SERVER_URL = "http://localhost:5173"

# 窗口配置
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
WINDOW_MIN_WIDTH = 1280
WINDOW_MIN_HEIGHT = 720

