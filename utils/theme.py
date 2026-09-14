"""Shared typography and compact desktop styling for DASViewer."""

from __future__ import annotations

from html import escape

from PyQt5.QtGui import QFont, QFontDatabase, QGuiApplication


# Use the Windows Chinese UI face when available.  The fallbacks keep source
# runs usable on systems which do not ship Microsoft's fonts.
UI_FONT_CANDIDATES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Segoe UI",
    "Noto Sans CJK SC",
    "Sans Serif",
)

UI_POINT_SIZE = 10
SMALL_POINT_SIZE = 9
PLOT_TITLE_POINT_SIZE = 12
PLOT_LABEL_POINT_SIZE = 10
PLOT_TICK_POINT_SIZE = 9


def ui_font_family() -> str:
    """Return the first preferred UI font installed on this machine."""

    if QGuiApplication.instance() is None:
        # Font discovery requires a GUI application.  Returning the preferred
        # family keeps non-GUI imports and batch processing safe; Qt will apply
        # its normal fallback when a widget is later created.
        return UI_FONT_CANDIDATES[0]

    installed = {family.casefold(): family for family in QFontDatabase().families()}
    for candidate in UI_FONT_CANDIDATES:
        if candidate.casefold() in installed:
            return installed[candidate.casefold()]
    return "Sans Serif"


def ui_font(point_size: int = UI_POINT_SIZE) -> QFont:
    """Build a DPI-aware application font at the requested semantic size."""

    font = QFont(ui_font_family(), point_size)
    font.setStyleStrategy(QFont.PreferAntialias)
    return font


def plot_font(point_size: int = PLOT_TICK_POINT_SIZE) -> QFont:
    """Return the same family used by the Qt interface for plot text."""

    return ui_font(point_size)


def plot_html(text: str, point_size: int) -> str:
    """Return escaped rich text for pyqtgraph titles and axis labels."""

    family = escape(ui_font_family(), quote=True)
    return (
        f'<span style="font-family: &quot;{family}&quot;; '
        f'font-size: {point_size}pt;">{escape(text)}</span>'
    )


def apply_application_theme(application) -> None:
    """Apply one compact, DPI-aware typography system to every Qt window."""

    family = ui_font_family().replace('"', '\\"')
    application.setFont(ui_font())
    application.setStyleSheet(
        f'''
        QMainWindow, QDialog {{
            font-family: "{family}";
            font-size: {UI_POINT_SIZE}pt;
        }}
        QMenuBar {{
            padding: 2px 4px;
        }}
        QMenuBar::item {{
            padding: 5px 8px;
        }}
        QMenu {{
            padding: 4px;
        }}
        QMenu::item {{
            padding: 5px 24px 5px 20px;
        }}
        QStatusBar {{
            font-size: {SMALL_POINT_SIZE}pt;
            padding: 2px 6px;
        }}
        QTabBar::tab {{
            min-height: 22px;
            padding: 5px 11px;
        }}
        QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QLineEdit {{
            min-height: 24px;
            padding: 2px 5px;
        }}
        QToolButton {{
            min-width: 24px;
            min-height: 24px;
            padding: 2px;
        }}
        QGroupBox {{
            font-weight: 600;
            margin-top: 10px;
            padding-top: 8px;
        }}
        QLabel#sectionTitle {{
            font-weight: 600;
        }}
        '''
    )
