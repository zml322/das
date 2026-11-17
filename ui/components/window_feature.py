"""QObject ownership shared by the independently composed window features."""

from typing import TYPE_CHECKING

from PyQt5.QtCore import QObject

if TYPE_CHECKING:
    from ui.main_window import MainWindow


class WindowFeature(QObject):
    """Keep feature state local and use explicit sibling-controller references."""

    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window = window
