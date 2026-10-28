"""Colour palettes and the application stylesheet."""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

PALETTES: dict[str, dict[str, str]] = {
    "Dark": dict(window="#1f2023", base="#26272b", alt="#2d2e33", text="#d8d9dc", muted="#8d8f96",
                 border="#3a3b41", accent="#4f7cac", accent_text="#ffffff", danger="#c0605a",
                 warn="#b48a3c", low="#6b6d74"),
    "Graphite": dict(window="#2b2b2b", base="#323232", alt="#3a3a3a", text="#dcdcdc", muted="#9a9a9a",
                     border="#454545", accent="#6a8f6a", accent_text="#ffffff", danger="#c26a5f",
                     warn="#b8914a", low="#777777"),
    "Light": dict(window="#f1f1f2", base="#ffffff", alt="#f7f7f8", text="#222326", muted="#6c6e75",
                  border="#cfd0d4", accent="#3b6ea5", accent_text="#ffffff", danger="#b3433c",
                  warn="#946f1f", low="#9a9ca3"),
}


def apply_theme(app: QApplication, name: str) -> dict[str, str]:
    c = PALETTES.get(name, PALETTES["Dark"])
    app.setStyle("Fusion")
    font = QFont(app.font())
    font.setPointSize(9)
    app.setFont(font)
    app.setStyleSheet(f"""
    QWidget {{ background: {c['window']}; color: {c['text']}; }}
    QLabel {{ background: transparent; }}
    QLabel#muted {{ color: {c['muted']}; }}
    QLabel#statValue {{ font-size: 15pt; }}
    QFrame#tile {{ background: {c['base']}; border: 1px solid {c['border']}; border-radius: 3px; }}
    QFrame#tile QLabel {{ background: transparent; }}
    QLineEdit, QPlainTextEdit, QComboBox, QDateEdit, QKeySequenceEdit {{
        background: {c['base']}; border: 1px solid {c['border']}; padding: 3px 5px;
        selection-background-color: {c['accent']}; selection-color: {c['accent_text']}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDateEdit:focus {{ border-color: {c['accent']}; }}
    QComboBox QAbstractItemView {{ background: {c['base']}; selection-background-color: {c['accent']};
        selection-color: {c['accent_text']}; border: 1px solid {c['border']}; }}
    QListWidget, QTableWidget {{ background: {c['base']}; border: 1px solid {c['border']};
        alternate-background-color: {c['alt']}; gridline-color: {c['border']}; outline: 0; }}
    QListWidget#sidebar {{ border: none; border-right: 1px solid {c['border']}; }}
    QListWidget#sidebar::item {{ padding: 4px 8px; }}
    QListWidget#sidebar::item:selected, QTableWidget::item:selected {{
        background: {c['accent']}; color: {c['accent_text']}; }}
    QHeaderView::section {{ background: {c['alt']}; color: {c['muted']}; border: none;
        border-right: 1px solid {c['border']}; border-bottom: 1px solid {c['border']}; padding: 4px 6px; }}
    QPushButton {{ background: {c['alt']}; border: 1px solid {c['border']}; padding: 4px 12px; }}
    QPushButton:hover {{ border-color: {c['muted']}; }}
    QPushButton:default {{ background: {c['accent']}; color: {c['accent_text']}; border-color: {c['accent']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QCheckBox {{ background: transparent; spacing: 6px; }}
    QCheckBox::indicator {{ width: 13px; height: 13px; background: {c['base']}; border: 1px solid {c['muted']}; }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
    QTableWidget::indicator {{ width: 13px; height: 13px; background: {c['window']}; border: 1px solid {c['muted']}; }}
    QTableWidget::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
    QMenuBar {{ background: {c['window']}; }}
    QMenuBar::item:selected, QMenu::item:selected {{ background: {c['accent']}; color: {c['accent_text']}; }}
    QMenu {{ background: {c['base']}; border: 1px solid {c['border']}; }}
    QMenu::item {{ padding: 4px 22px 4px 18px; }}
    QMenu::item:disabled {{ color: {c['muted']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 3px 0; }}
    QStatusBar {{ border-top: 1px solid {c['border']}; }}
    QProgressBar {{ background: {c['base']}; border: 1px solid {c['border']}; text-align: center; height: 14px; }}
    QProgressBar::chunk {{ background: {c['accent']}; }}
    QScrollBar:vertical {{ width: 10px; background: transparent; }}
    QScrollBar:horizontal {{ height: 10px; background: transparent; }}
    QScrollBar::handle {{ background: {c['border']}; min-height: 24px; min-width: 24px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QSplitter::handle {{ background: {c['border']}; }}
    QToolTip {{ background: {c['base']}; color: {c['text']}; border: 1px solid {c['border']}; }}
    """)
    return c
