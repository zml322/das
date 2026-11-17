"""二维滤波对话框（重构后的模块化版本）。

向后兼容旧的 `from core.filter.das_filter import DASFilterDialog` 导入。
"""

from .dialog import DASFilterDialog

__all__ = ["DASFilterDialog"]
