"""Colour palettes and the application stylesheet."""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

PALETTES: dict[str, dict[str, str]] = {
    "Dark": dict(window="#17181b", sidebar="#1c1d21", panel="#1e1f24", base="#232429", alt="#2a2b31",
                 hover="#30323a", text="#e4e5e8", muted="#8b8e97", border="#2f3138", accent="#5b8def",
                 accent_text="#ffffff", danger="#e0675f", warn="#d9a441", low="#6f7480"),
    "Graphite": dict(window="#232323", sidebar="#282828", panel="#2a2a2a", base="#303030", alt="#383838",
                     hover="#424242", text="#e6e6e6", muted="#9a9a9a", border="#3d3d3d", accent="#5fa586",
                     accent_text="#ffffff", danger="#e0705f", warn="#d9a441", low="#7a7a7a"),
    "Light": dict(window="#f5f6f8", sidebar="#eceef2", panel="#eceef2", base="#ffffff", alt="#ffffff",
                  hover="#e4e7ec", text="#1d2026", muted="#6b7280", border="#d9dce2", accent="#3b73e0",
                  accent_text="#ffffff", danger="#cc4b43", warn="#b07d12", low="#9aa0ab"),
}


def apply_theme(app: QApplication, name: str) -> dict[str, str]:
    c = PALETTES.get(name, PALETTES["Dark"])
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)
    app.setStyleSheet(f"""
    QWidget {{ background: {c['window']}; color: {c['text']}; }}
    QLabel {{ background: transparent; }}
    QLabel#muted {{ color: {c['muted']}; }}
    QLabel#section {{ color: {c['muted']}; font-size: 8pt; font-weight: 600; padding: 2px 0; }}
    QLabel#statValue {{ font-size: 18pt; font-weight: 600; }}
    QFrame#tile {{ background: {c['base']}; border: 1px solid {c['border']}; border-radius: 8px; }}
    QFrame#tile QLabel {{ background: transparent; }}
    QWidget#sidebarBox {{ background: {c['sidebar']}; }}
    QWidget#toolbar, QWidget#filterBar {{ background: {c['window']}; }}
    QWidget#columnPanel {{ background: {c['panel']}; border-radius: 8px; }}
    QWidget#columnPanel QLabel {{ background: transparent; }}
    QLineEdit, QPlainTextEdit, QComboBox, QDateEdit, QKeySequenceEdit {{
        background: {c['base']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 8px;
        selection-background-color: {c['accent']}; selection-color: {c['accent_text']}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDateEdit:focus {{ border-color: {c['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{ background: {c['base']}; selection-background-color: {c['accent']};
        selection-color: {c['accent_text']}; border: 1px solid {c['border']}; outline: 0; }}
    QListWidget, QTableWidget {{ background: {c['base']}; border: 1px solid {c['border']}; border-radius: 8px;
        alternate-background-color: {c['alt']}; gridline-color: {c['border']}; outline: 0; }}
    QListWidget#column {{ background: transparent; border: none; }}
    QListWidget#sidebar {{ background: {c['sidebar']}; border: none; border-radius: 0; padding: 4px; }}
    QListWidget#sidebar::item {{ padding: 6px 10px; border-radius: 6px; margin: 1px 0; }}
    QListWidget#sidebar::item:hover {{ background: {c['hover']}; }}
    QListWidget#sidebar::item:selected {{ background: {c['accent']}; color: {c['accent_text']}; }}
    QTableWidget::item {{ padding: 4px 6px; }}
    QTableWidget::item:selected {{ background: {c['accent']}; color: {c['accent_text']}; }}
    QHeaderView::section {{ background: {c['base']}; color: {c['muted']}; border: none;
        border-bottom: 1px solid {c['border']}; padding: 6px 8px; font-weight: 600; }}
    QPushButton {{ background: {c['alt']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 14px; }}
    QPushButton:hover {{ background: {c['hover']}; }}
    QPushButton:default, QPushButton#primary {{ background: {c['accent']}; color: {c['accent_text']};
        border-color: {c['accent']}; font-weight: 600; }}
    QPushButton#primary:hover {{ background: {c['accent']}; border-color: {c['text']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton#seg {{ background: transparent; border: none; border-radius: 6px; padding: 5px 14px;
        color: {c['muted']}; }}
    QPushButton#seg:hover {{ background: {c['hover']}; color: {c['text']}; }}
    QPushButton#seg:checked {{ background: {c['alt']}; color: {c['text']}; font-weight: 600; }}
    QCheckBox {{ background: transparent; spacing: 6px; }}
    QCheckBox::indicator {{ width: 14px; height: 14px; background: {c['base']}; border: 1px solid {c['muted']};
        border-radius: 4px; }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
    QTableWidget::indicator {{ width: 14px; height: 14px; background: {c['window']}; border: 1px solid {c['muted']};
        border-radius: 4px; }}
    QTableWidget::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
    QMenuBar {{ background: {c['window']}; }}
    QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; }}
    QMenuBar::item:selected, QMenu::item:selected {{ background: {c['accent']}; color: {c['accent_text']}; }}
    QMenu {{ background: {c['base']}; border: 1px solid {c['border']}; padding: 4px; }}
    QMenu::item {{ padding: 5px 24px 5px 18px; border-radius: 4px; }}
    QMenu::item:disabled {{ color: {c['muted']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 0; }}
    QStatusBar {{ background: {c['window']}; color: {c['muted']}; }}
    QProgressBar {{ background: {c['alt']}; border: none; border-radius: 5px; text-align: center; height: 16px; }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 5px; }}
    QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
    QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 2px; }}
    QScrollBar::handle {{ background: {c['border']}; min-height: 24px; min-width: 24px; border-radius: 4px; }}
    QScrollBar::handle:hover {{ background: {c['muted']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QSplitter::handle {{ background: {c['window']}; width: 1px; }}
    QToolTip {{ background: {c['base']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px; }}
    """)
    return c
