"""Modal dialogs. They only collect input; callers validate and save."""
from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QKeySequenceEdit, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..models import PRIORITIES, STATUS_LABELS, STATUSES, Project, Task
from ..settings import DEFAULT_SHORTCUTS
from .theme import PALETTES

ACTION_LABELS = {
    "new_task": "New task", "new_project": "New project", "edit_task": "Edit task",
    "delete_task": "Delete task", "search": "Focus search", "refresh": "Refresh",
    "view_board": "Board view", "view_list": "List view", "view_dashboard": "Dashboard view",
    "import": "Import", "export": "Export", "backup": "Back up database",
    "restore": "Restore database", "preferences": "Preferences",
}


def _buttons(dialog: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class ProjectDialog(QDialog):
    def __init__(self, parent: QWidget, project: Project | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit project" if project else "New project")
        self.setMinimumWidth(360)
        self.name = QLineEdit(project.name if project else "")
        self.description = QPlainTextEdit(project.description if project else "")
        self.description.setFixedHeight(70)
        form = QFormLayout(self)
        form.addRow("Name", self.name)
        form.addRow("Description", self.description)
        form.addRow(_buttons(self))

    def values(self) -> tuple[str, str]:
        return self.name.text(), self.description.toPlainText()


class TaskDialog(QDialog):
    def __init__(self, parent: QWidget, projects: list[Project], task: Task | None = None,
                 default_project: int | None = None, default_status: str = "todo"):
        super().__init__(parent)
        self.setWindowTitle("Edit task" if task else "New task")
        self.setMinimumWidth(440)
        self.title = QLineEdit(task.title if task else "")
        self.description = QPlainTextEdit(task.description if task else "")
        self.description.setFixedHeight(90)
        self.project = QComboBox()
        for p in projects:
            self.project.addItem(p.name + (" (archived)" if p.archived else ""), p.id)
        wanted = task.project_id if task else default_project
        if wanted is not None and self.project.findData(wanted) >= 0:
            self.project.setCurrentIndex(self.project.findData(wanted))
        self.priority = QComboBox()
        for number, label in PRIORITIES.items():
            self.priority.addItem(label, number)
        self.priority.setCurrentIndex(self.priority.findData(task.priority if task else 2))
        self.status = QComboBox()
        for key in STATUSES:
            self.status.addItem(STATUS_LABELS[key], key)
        self.status.setCurrentIndex(self.status.findData(task.status if task else default_status))
        self.has_deadline = QCheckBox("Set deadline")
        self.deadline = QDateEdit(calendarPopup=True)
        self.deadline.setDisplayFormat("yyyy-MM-dd")
        current = QDate.fromString(task.deadline, "yyyy-MM-dd") if task and task.deadline else None
        self.deadline.setDate(current or QDate.currentDate())
        self.has_deadline.setChecked(current is not None)
        self.deadline.setEnabled(current is not None)
        self.has_deadline.toggled.connect(self.deadline.setEnabled)
        self.tags = QLineEdit(", ".join(task.tags) if task else "")
        self.tags.setPlaceholderText("comma separated")
        deadline_row = QHBoxLayout()
        deadline_row.addWidget(self.has_deadline)
        deadline_row.addWidget(self.deadline, 1)
        form = QFormLayout(self)
        form.addRow("Title", self.title)
        form.addRow("Description", self.description)
        form.addRow("Project", self.project)
        form.addRow("Priority", self.priority)
        form.addRow("Status", self.status)
        form.addRow("Deadline", deadline_row)
        form.addRow("Tags", self.tags)
        form.addRow(_buttons(self))
        self.title.setFocus()

    def values(self) -> dict:
        return {
            "project_id": self.project.currentData(), "title": self.title.text(),
            "description": self.description.toPlainText(), "priority": self.priority.currentData(),
            "status": self.status.currentData(),
            "deadline": self.deadline.date().toString("yyyy-MM-dd") if self.has_deadline.isChecked() else None,
            "tags": self.tags.text(),
        }


class PreferencesDialog(QDialog):
    def __init__(self, parent: QWidget, theme: str, shortcuts: dict[str, str]):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(420, 460)
        self.theme = QComboBox()
        self.theme.addItems(list(PALETTES))
        self.theme.setCurrentText(theme)
        self.table = QTableWidget(len(ACTION_LABELS), 2)
        self.table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 180)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.editors: dict[str, QKeySequenceEdit] = {}
        for row, (action, label) in enumerate(ACTION_LABELS.items()):
            item = QTableWidgetItem(label)
            self.table.setItem(row, 0, item)
            editor = QKeySequenceEdit(QKeySequence(shortcuts.get(action, "")))
            self.table.setCellWidget(row, 1, editor)
            self.editors[action] = editor
        reset = QPushButton("Reset shortcuts")
        reset.clicked.connect(self._reset)
        top = QFormLayout()
        top.addRow("Theme", self.theme)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addWidget(reset)
        layout.addWidget(_buttons(self))

    def _reset(self) -> None:
        for action, editor in self.editors.items():
            editor.setKeySequence(QKeySequence(DEFAULT_SHORTCUTS[action]))

    def shortcuts(self) -> dict[str, str]:
        return {a: e.keySequence().toString() for a, e in self.editors.items()}

    def accept(self) -> None:
        used: dict[str, str] = {}
        for action, key in self.shortcuts().items():
            if key and key in used:
                QMessageBox.warning(
                    self, "Duplicate shortcut",
                    f"{key} is assigned to both '{ACTION_LABELS[used[key]]}' and '{ACTION_LABELS[action]}'.")
                return
            used[key] = action
        super().accept()
