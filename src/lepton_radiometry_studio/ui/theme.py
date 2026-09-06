from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


THEMES = ("dark", "light", "system")
THEME_LABELS: Dict[str, str] = {
    "dark": "Dark",
    "light": "Light",
    "system": "System",
}

_SYSTEM_PALETTE: Optional[QPalette] = None
_SYSTEM_STYLE_NAME: Optional[str] = None


def load_theme() -> str:
    """Return the saved appearance, defaulting consistently to dark."""
    value = str(QSettings().value("appearance/theme", "dark")).lower()
    return value if value in THEMES else "dark"


def save_theme(theme: str) -> None:
    if theme not in THEMES:
        raise ValueError(f"Unknown theme: {theme}")
    QSettings().setValue("appearance/theme", theme)


def apply_theme(application: QApplication, theme: str) -> None:
    """Apply one of the app themes without changing the user's OS theme."""
    global _SYSTEM_PALETTE, _SYSTEM_STYLE_NAME

    if theme not in THEMES:
        theme = "dark"
    if _SYSTEM_PALETTE is None:
        _SYSTEM_PALETTE = QPalette(application.palette())
        _SYSTEM_STYLE_NAME = application.style().objectName()

    if theme == "system":
        if _SYSTEM_STYLE_NAME:
            application.setStyle(_SYSTEM_STYLE_NAME)
        if _SYSTEM_PALETTE is not None:
            application.setPalette(_SYSTEM_PALETTE)
        application.setStyleSheet("")
        return

    application.setStyle("Fusion")
    application.setPalette(_palette(theme))
    application.setStyleSheet(_stylesheet(theme))


def _palette(theme: str) -> QPalette:
    palette = QPalette()
    colors = (
        {
            "window": "#15181d",
            "window_text": "#f2f4f7",
            "base": "#101318",
            "alternate": "#1c2129",
            "button": "#252b34",
            "button_text": "#f2f4f7",
            "text": "#f2f4f7",
            "tooltip_base": "#f2f4f7",
            "tooltip_text": "#111419",
            "highlight": "#2f80ed",
            "highlighted_text": "#ffffff",
            "placeholder": "#8d97a5",
            "link": "#69b7ff",
            "disabled": "#747d8a",
        }
        if theme == "dark"
        else {
            "window": "#f4f6f8",
            "window_text": "#18202a",
            "base": "#ffffff",
            "alternate": "#edf1f5",
            "button": "#ffffff",
            "button_text": "#18202a",
            "text": "#18202a",
            "tooltip_base": "#18202a",
            "tooltip_text": "#ffffff",
            "highlight": "#1769c2",
            "highlighted_text": "#ffffff",
            "placeholder": "#687383",
            "link": "#1769c2",
            "disabled": "#8a939e",
        }
    )
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["window_text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["base"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["alternate"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["button"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["button_text"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["tooltip_base"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["tooltip_text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["highlight"]))
    palette.setColor(
        QPalette.ColorRole.HighlightedText, QColor(colors["highlighted_text"])
    )
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["placeholder"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(colors["link"]))
    group = QPalette.ColorGroup.Disabled
    palette.setColor(group, QPalette.ColorRole.Text, QColor(colors["disabled"]))
    palette.setColor(group, QPalette.ColorRole.ButtonText, QColor(colors["disabled"]))
    palette.setColor(group, QPalette.ColorRole.WindowText, QColor(colors["disabled"]))
    return palette


def _stylesheet(theme: str) -> str:
    if theme == "dark":
        border = "#39414d"
        control = "#222832"
        control_hover = "#2d3541"
        control_pressed = "#181d24"
        accent = "#4796ff"
        header = "#262d37"
        muted = "#a8b1be"
    else:
        border = "#c7ced7"
        control = "#ffffff"
        control_hover = "#edf4fc"
        control_pressed = "#dce9f7"
        accent = "#1769c2"
        header = "#e7ecf2"
        muted = "#596575"

    return f"""
        QMainWindow {{ background-color: palette(window); }}
        QGroupBox {{
            border: 1px solid {border};
            border-radius: 7px;
            margin-top: 9px;
            padding-top: 7px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            font-weight: 600;
            padding: 0 5px;
        }}
        QLabel#sectionHeading {{ font-weight: 600; }}
        QPushButton, QComboBox, QDoubleSpinBox {{
            background-color: {control};
            border: 1px solid {border};
            border-radius: 5px;
            padding: 5px 8px;
            min-height: 18px;
        }}
        QPushButton:hover, QComboBox:hover, QDoubleSpinBox:hover {{
            background-color: {control_hover};
            border-color: {accent};
        }}
        QPushButton:pressed {{ background-color: {control_pressed}; }}
        QPushButton:disabled, QComboBox:disabled, QDoubleSpinBox:disabled {{
            color: {muted};
        }}
        QToolButton {{
            background-color: {header};
            border: 1px solid {border};
            border-radius: 3px;
            color: palette(button-text);
            font-size: 9px;
            font-weight: 700;
            min-width: 22px;
            min-height: 14px;
            padding: 0;
        }}
        QToolButton:hover {{
            background-color: {accent};
        }}
        QToolButton:disabled {{ color: {muted}; }}
        QTableWidget {{
            border: 1px solid {border};
            border-radius: 5px;
            gridline-color: {border};
            alternate-background-color: palette(alternate-base);
        }}
        QHeaderView::section {{
            background-color: {header};
            border: 0;
            border-right: 1px solid {border};
            border-bottom: 1px solid {border};
            font-weight: 600;
            padding: 5px 7px;
        }}
        QMenuBar {{ background-color: palette(window); }}
        QMenuBar::item:selected, QMenu::item:selected {{
            background-color: {accent};
            color: white;
        }}
        QMenu {{ border: 1px solid {border}; }}
        QStatusBar {{ color: {muted}; }}
        QScrollArea {{ border: 0; }}
    """
