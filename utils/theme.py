"""Shared typography and compact desktop styling for DASViewer."""

from __future__ import annotations

from html import escape

from PyQt5.QtGui import QFont, QFontDatabase, QGuiApplication


# Use the Windows Chinese UI face when available.  The fallbacks keep source
# runs usable on systems which do not ship Microsoft's fonts.
UI_FONT_CANDIDATES = (
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "Segoe UI",
    "Noto Sans CJK SC",
    "Sans Serif",
)

UI_POINT_SIZE = 10
SMALL_POINT_SIZE = 9
PLOT_TITLE_POINT_SIZE = 12
PLOT_LABEL_POINT_SIZE = 10
PLOT_TICK_POINT_SIZE = 9


# Semantic roles keep the desktop tool visually consistent without tying UI
# behavior to a colour name.  Plot palettes deliberately stay independent: a
# scientific colormap communicates data, while these roles communicate UI.
PALETTE = {
    "surface_base": "#f4f7fb",
    "surface_panel": "#ffffff",
    "surface_subtle": "#f8fafc",
    "surface_selected": "#eaf1ff",
    "surface_pressed": "#dce8ff",
    "text_primary": "#101828",
    "text_secondary": "#475467",
    "text_muted": "#7a8699",
    "border": "#d8dee8",
    "border_strong": "#c4cedd",
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "success_text": "#13734a",
    "success_surface": "#e6f7ef",
    "warning_text": "#9a5b00",
    "warning_surface": "#fff3d6",
    "danger": "#b42318",
    "danger_surface": "#fef3f2",
}


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
    # Full hinting keeps small Chinese UI text crisp on Windows raster displays
    # while antialiasing preserves the smoother strokes on high-DPI screens.
    font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferFullHinting)
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
    """Apply the compact, semantic light theme used by every Qt window."""

    family = ui_font_family().replace('"', '\\"')
    colors = PALETTE
    application.setFont(ui_font())
    application.setStyleSheet(
        f'''
        QWidget {{ color: {colors["text_primary"]}; }}
        QMainWindow, QDialog {{
            font-family: "{family}";
            font-size: {UI_POINT_SIZE}pt;
            background-color: {colors["surface_base"]};
        }}
        QLabel, QCheckBox, QRadioButton {{
            color: {colors["text_primary"]};
            background-color: transparent;
        }}
        QMenuBar {{
            padding: 4px 8px;
            spacing: 2px;
            color: {colors["text_secondary"]};
            background-color: {colors["surface_subtle"]};
            border-bottom: 1px solid {colors["border"]};
        }}
        QMenuBar::item {{ padding: 6px 10px; border-radius: 6px; background: transparent; }}
        QMenuBar::item:selected, QMenuBar::item:pressed {{
            color: {colors["primary_hover"]};
            background-color: {colors["surface_selected"]};
        }}
        QMenu {{
            padding: 5px;
            color: {colors["text_secondary"]};
            background-color: {colors["surface_panel"]};
            border: 1px solid {colors["border"]};
        }}
        QMenu::item {{ padding: 6px 26px 6px 20px; border-radius: 5px; }}
        QMenu::item:selected {{
            color: {colors["primary_hover"]};
            background-color: {colors["surface_selected"]};
        }}
        QStatusBar {{
            font-size: {SMALL_POINT_SIZE}pt;
            padding: 2px 8px;
            color: {colors["text_secondary"]};
            background-color: {colors["surface_subtle"]};
            border-top: 1px solid {colors["border"]};
        }}
        QSplitter::handle {{ background-color: {colors["border"]}; margin: 4px 0; }}
        QSplitter::handle:hover {{ background-color: {colors["primary"]}; }}
        QTabWidget::pane {{
            background-color: {colors["surface_panel"]};
            border: 1px solid {colors["border"]};
            border-radius: 7px;
            top: -1px;
        }}
        QTabBar::tab {{
            min-height: 25px;
            padding: 7px 14px;
            color: {colors["text_secondary"]};
            background: transparent;
            border: none;
            border-bottom: 3px solid transparent;
        }}
        QTabBar::tab:hover {{ color: {colors["primary_hover"]}; background-color: {colors["surface_base"]}; }}
        QTabBar::tab:selected {{
            color: {colors["text_primary"]};
            background-color: {colors["surface_panel"]};
            border-bottom: 3px solid {colors["primary"]};
        }}
        QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QLineEdit {{
            min-height: 25px;
            padding: 3px 8px;
            color: {colors["text_primary"]};
            background-color: {colors["surface_panel"]};
            border: 1px solid {colors["border_strong"]};
            border-radius: 6px;
        }}
        QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
        QDateTimeEdit:hover, QLineEdit:hover {{ border-color: #8aaaf0; }}
        QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QDateTimeEdit:focus, QLineEdit:focus {{ border: 2px solid {colors["primary"]}; padding: 2px 7px; }}
        QLineEdit:read-only {{
            color: {colors["text_primary"]};
            background-color: {colors["surface_subtle"]};
            border-color: {colors["border"]};
        }}
        QPushButton:hover {{
            color: {colors["primary_hover"]};
            border-color: {colors["primary"]};
            background-color: #f7faff;
        }}
        QPushButton:pressed {{ background-color: {colors["surface_pressed"]}; }}
        QPushButton:focus, QToolButton:focus {{ border: 2px solid {colors["primary"]}; }}
        QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled,
        QDoubleSpinBox:disabled, QDateTimeEdit:disabled, QLineEdit:disabled {{
            color: {colors["text_muted"]};
            background-color: #f2f4f7;
            border-color: #e1e5eb;
        }}
        QPushButton#primaryAction {{
            color: #ffffff;
            background-color: {colors["primary"]};
            border-color: {colors["primary"]};
            font-weight: 600;
        }}
        QPushButton#primaryAction:hover {{
            color: #ffffff;
            background-color: {colors["primary_hover"]};
            border-color: {colors["primary_hover"]};
        }}
        QPushButton#primaryAction:disabled {{
            color: #d0d5dd;
            background-color: {colors["text_muted"]};
            border-color: {colors["text_muted"]};
        }}
        QPushButton#dangerAction {{
            color: {colors["danger"]};
            background-color: {colors["danger_surface"]};
            border-color: #fecdca;
        }}
        QToolButton {{
            min-width: 28px;
            min-height: 28px;
            padding: 2px;
            color: {colors["text_secondary"]};
            background-color: {colors["surface_panel"]};
            border: 1px solid {colors["border_strong"]};
            border-radius: 6px;
        }}
        QToolButton:hover {{
            color: {colors["primary_hover"]};
            border-color: {colors["primary"]};
            background-color: #f7faff;
        }}
        QToolButton:disabled {{
            color: {colors["text_muted"]};
            background-color: #f2f4f7;
            border-color: #e1e5eb;
        }}
        QToolButton#sectionToggle {{
            min-width: 0;
            min-height: 30px;
            padding: 3px 8px;
            color: {colors["text_primary"]};
            background-color: {colors["surface_subtle"]};
            border: 1px solid {colors["border"]};
            border-radius: 7px;
            font-weight: 600;
            text-align: left;
        }}
        QToolButton#sectionToggle:checked {{
            border-bottom-left-radius: 0;
            border-bottom-right-radius: 0;
        }}
        QToolButton#sectionToggle:hover {{ background-color: {colors["surface_selected"]}; }}
        QToolButton#sectionToggle:focus {{ border: 2px solid {colors["primary"]}; }}
        QWidget#filterSectionBody {{
            background-color: {colors["surface_panel"]};
            border: 1px solid {colors["border"]};
            border-top: none;
            border-bottom-left-radius: 7px;
            border-bottom-right-radius: 7px;
        }}
        QWidget#videoSurface, QLabel#videoUnavailable {{
            color: #e5e7eb;
            background-color: #111827;
            border: 1px solid #344054;
            border-radius: 7px;
        }}
        QGroupBox {{
            font-weight: 600;
            color: {colors["text_primary"]};
            background-color: {colors["surface_subtle"]};
            border: 1px solid {colors["border"]};
            border-radius: 8px;
            margin-top: 16px;
            padding-top: 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 5px;
            color: {colors["text_primary"]};
            background-color: {colors["surface_subtle"]};
        }}
        QTableWidget, QListWidget {{
            color: {colors["text_primary"]};
            background-color: {colors["surface_panel"]};
            alternate-background-color: {colors["surface_subtle"]};
            border: 1px solid {colors["border_strong"]};
            border-radius: 6px;
            padding: 3px;
        }}
        QHeaderView::section {{
            padding: 5px 6px;
            color: {colors["text_primary"]};
            background-color: #eaf1fa;
            border: none;
            border-bottom: 1px solid {colors["border"]};
            font-weight: 600;
        }}
        QListWidget::item {{ padding: 5px 4px; border-radius: 5px; }}
        QListWidget::item:selected, QTableWidget::item:selected {{
            color: {colors["text_primary"]};
            background-color: {colors["surface_selected"]};
        }}
        QLabel#secondaryLabel {{ color: {colors["text_secondary"]}; font-size: {SMALL_POINT_SIZE}pt; }}
        QLabel#pipelineStateLabel, QLabel#statusBadge {{
            padding: 3px 8px;
            color: {colors["text_secondary"]};
            background-color: #eef1f5;
            border: 1px solid {colors["border"]};
            border-radius: 9px;
            font-size: {SMALL_POINT_SIZE}pt;
            font-weight: 500;
        }}
        QLabel#pipelineStateLabel[state="pending"] {{
            color: {colors["warning_text"]}; background-color: {colors["warning_surface"]}; border-color: #fedf89;
        }}
        QLabel#pipelineStateLabel[state="applied"], QLabel#statusBadge[state="active"] {{
            color: {colors["success_text"]}; background-color: {colors["success_surface"]}; border-color: #abefc6;
        }}
        QLabel#pipelineStateLabel[state="busy"] {{
            color: {colors["primary_hover"]}; background-color: {colors["surface_selected"]}; border-color: #b2ccff;
        }}
        QLabel#filterStatusLabel {{
            padding: 7px 9px;
            color: {colors["text_secondary"]};
            background-color: {colors["surface_subtle"]};
            border: 1px solid {colors["border"]};
            border-radius: 6px;
        }}
        QWidget#plotToolbar, QWidget#eventRangeBar, QWidget#filterActionBar {{
            background-color: {colors["surface_subtle"]};
            border: 1px solid {colors["border"]};
            border-radius: 7px;
        }}
        QLabel#sectionTitle {{ color: {colors["text_primary"]}; font-weight: 600; }}
        '''
    )
