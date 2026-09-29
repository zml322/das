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
        QWidget {{
            color: #172033;
        }}
        QMainWindow, QDialog {{
            font-family: "{family}";
            font-size: {UI_POINT_SIZE}pt;
            background-color: #f3f6fa;
        }}
        QLabel, QCheckBox, QRadioButton {{
            color: #172033;
            background-color: transparent;
        }}
        QMenuBar {{
            padding: 4px 8px;
            spacing: 2px;
            color: #344054;
            background-color: #f7f9fc;
            border-bottom: 1px solid #d8dee8;
        }}
        QMenuBar::item {{
            padding: 6px 10px;
            border-radius: 6px;
            background: transparent;
        }}
        QMenuBar::item:selected, QMenuBar::item:pressed {{
            color: #1d4ed8;
            background-color: #eaf1ff;
        }}
        QMenu {{
            padding: 5px;
            color: #344054;
            background-color: #ffffff;
            border: 1px solid #d8dee8;
        }}
        QMenu::item {{
            padding: 6px 26px 6px 20px;
            border-radius: 5px;
        }}
        QMenu::item:selected {{
            color: #1d4ed8;
            background-color: #eaf1ff;
        }}
        QStatusBar {{
            font-size: {SMALL_POINT_SIZE}pt;
            padding: 2px 6px;
            color: #475467;
            background-color: #f7f9fc;
            border-top: 1px solid #d8dee8;
        }}
        QTabWidget::pane {{
            background-color: #ffffff;
            border: 1px solid #d8dee8;
            border-radius: 7px;
            top: -1px;
        }}
        QTabBar::tab {{
            min-height: 24px;
            padding: 7px 14px;
            color: #667085;
            background: transparent;
            border: none;
            border-bottom: 3px solid transparent;
        }}
        QTabBar::tab:hover {{
            color: #1d4ed8;
            background-color: #f4f7fb;
        }}
        QTabBar::tab:selected {{
            color: #172033;
            background-color: #ffffff;
            border-bottom: 3px solid #2563eb;
        }}
        QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QLineEdit {{
            min-height: 24px;
            padding: 3px 7px;
            color: #172033;
            background-color: #ffffff;
            border: 1px solid #cfd6e2;
            border-radius: 6px;
        }}
        QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
        QDateTimeEdit:hover, QLineEdit:hover {{
            border-color: #8aaaf0;
        }}
        QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QDateTimeEdit:focus, QLineEdit:focus {{
            border: 1px solid #2563eb;
        }}
        QPushButton:hover {{
            color: #1d4ed8;
            border-color: #2563eb;
            background-color: #f7faff;
        }}
        QPushButton:pressed {{
            background-color: #eaf1ff;
        }}
        QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled,
        QDoubleSpinBox:disabled, QDateTimeEdit:disabled, QLineEdit:disabled {{
            color: #98a2b3;
            background-color: #f2f4f7;
            border-color: #e1e5eb;
        }}
        QPushButton#primaryAction {{
            color: #ffffff;
            background-color: #2563eb;
            border-color: #2563eb;
            font-weight: 600;
        }}
        QPushButton#primaryAction:hover {{
            color: #ffffff;
            background-color: #1d4ed8;
            border-color: #1d4ed8;
        }}
        QPushButton#primaryAction:disabled {{
            color: #d0d5dd;
            background-color: #98a2b3;
            border-color: #98a2b3;
        }}
        QToolButton {{
            min-width: 28px;
            min-height: 28px;
            padding: 2px;
            color: #344054;
            background-color: #ffffff;
            border: 1px solid #cfd6e2;
            border-radius: 6px;
        }}
        QToolButton:hover {{
            color: #1d4ed8;
            border-color: #2563eb;
            background-color: #f7faff;
        }}
        QToolButton:disabled {{
            color: #98a2b3;
            background-color: #f2f4f7;
            border-color: #e1e5eb;
        }}
        QGroupBox {{
            font-weight: 600;
            color: #172033;
            background-color: #f8fafc;
            border: 1px solid #d8dee8;
            border-radius: 8px;
            margin-top: 16px;
            padding-top: 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 5px;
            color: #172033;
            background-color: #f8fafc;
        }}
        QListWidget {{
            color: #172033;
            background-color: #ffffff;
            alternate-background-color: #f8fafc;
            border: 1px solid #cfd6e2;
            border-radius: 6px;
            padding: 3px;
        }}
        QListWidget::item {{
            padding: 5px 4px;
            border-radius: 5px;
        }}
        QListWidget::item:selected {{
            color: #172033;
            background-color: #eaf1ff;
        }}
        QLabel#secondaryLabel {{
            color: #667085;
            font-size: {SMALL_POINT_SIZE}pt;
        }}
        QLabel#pipelineStateLabel {{
            padding: 2px 7px;
            color: #667085;
            background-color: #eef1f5;
            border-radius: 8px;
            font-size: {SMALL_POINT_SIZE}pt;
            font-weight: 500;
        }}
        QLabel#pipelineStateLabel[state="pending"] {{
            color: #9a5b00;
            background-color: #fff3d6;
        }}
        QLabel#pipelineStateLabel[state="applied"] {{
            color: #13734a;
            background-color: #e6f7ef;
        }}
        QLabel#pipelineStateLabel[state="busy"] {{
            color: #1d4ed8;
            background-color: #eaf1ff;
        }}
        QLabel#filterStatusLabel {{
            padding: 7px 9px;
            color: #475467;
            background-color: #f7f9fc;
            border: 1px solid #d8dee8;
            border-radius: 6px;
        }}
        QLabel#sectionTitle {{
            font-weight: 600;
        }}
        '''
    )
