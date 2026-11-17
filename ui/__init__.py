# -*- coding: utf-8 -*-
"""
用户界面层

- main_window: 控制器组合与窗口生命周期
- tabs: 按功能拆分的Tab页面
- dialogs: 功能对话框
- widgets: 自定义控件
- components: UI组件
"""
__all__ = ['MainWindow']


def __getattr__(name):
    if name == 'MainWindow':
        from .main_window import MainWindow
        return MainWindow
    raise AttributeError(name)
