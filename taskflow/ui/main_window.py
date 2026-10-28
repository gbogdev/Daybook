"""Main window: wires the views to the service layer."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QByteArray, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ..backup import backup_database, restore_database
from ..db import Database
from ..importexport import export_csv, export_json, import_file
from ..models import PRIORITIES, STATUS_LABELS, STATUSES, TaskFlowError
from ..service import TaskFilter, TaskService
from ..settings import Settings
from .dialogs import PreferencesDialog, ProjectDialog, TaskDialog
from .theme import apply_theme
from .views import ID_ROLE, BoardView, DashboardView, TaskTable

SORT_CHOICES = [("Manual order", "position"), ("Title", "title"), ("Priority", "priority"),
                ("Deadline", "deadline"), ("Created", "created"), ("Status", "status"),
                ("Project", "project")]
VIEWS = ["board", "list", "dashboard"]


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    """Runs fn on the thread pool; it must open its own Database connection."""

    def __init__(self, fn: Callable[[], object]):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            self.signals.done.emit(self.fn())
        except (TaskFlowError, OSError, sqlite3.Error) as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # last resort: never leave the UI waiting
            self.signals.failed.emit(f"Unexpected error: {exc!r}")


class MainWindow(QMainWindow):
    def __init__(self, service: TaskService, settings: Settings):
        super().__init__()
        self.service = service
        self.settings = settings
        self.setWindowTitle("TaskFlow")
        self.resize(1100, 680)
        self.pool = QThreadPool.globalInstance()
        self._jobs: set[Job] = set()
        self._building = True

        self.board = BoardView()
        self.table = TaskTable()
        self.dashboard = DashboardView()
        self.stack = QStackedWidget()
        for w in (self.board, self.table, self.dashboard):
            self.stack.addWidget(w)

        self._build_sidebar()
        self._build_filters()
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.filter_bar)
        rl.addWidget(self.stack, 1)
        split = QSplitter()
        split.addWidget(self.sidebar_box)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([200, 900])
        split.setChildrenCollapsible(False)
        self.setCentralWidget(split)
        self._build_actions()

        self.board.taskMoved.connect(lambda i, s, b: QTimer.singleShot(0, lambda: self._move(i, s, b)))
        for view in (self.board, self.table):
            view.taskActivated.connect(self.edit_task)
            view.contextRequested.connect(self._task_menu)
        self.table.doneToggled.connect(lambda i, d: self._guard(lambda: self.service.set_done(i, d)))
        self.table.sortRequested.connect(self._header_sort)
        self.apply_settings()
        self._building = False
        self.refresh_all()
        if settings.load_error:
            QMessageBox.warning(self, "Settings", settings.load_error)

    # -- construction --------------------------------------------------
    def _build_sidebar(self) -> None:
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sidebar.customContextMenuRequested.connect(self._project_menu)
        self.sidebar.currentItemChanged.connect(lambda *_: self.refresh())
        self.sidebar.itemDoubleClicked.connect(lambda _: self.edit_project())
        self.show_archived = QCheckBox("Show archived")
        self.show_archived.toggled.connect(lambda _: self.refresh_all())
        self.sidebar_box = QWidget()
        v = QVBoxLayout(self.sidebar_box)
        v.setContentsMargins(0, 0, 0, 6)
        v.setSpacing(4)
        title = QLabel("  Projects")
        title.setObjectName("muted")
        v.addWidget(title)
        v.addWidget(self.sidebar, 1)
        add = QPushButton("New project")
        add.clicked.connect(self.new_project)
        row = QHBoxLayout()
        row.setContentsMargins(6, 0, 6, 0)
        row.addWidget(self.show_archived)
        row.addStretch(1)
        v.addLayout(row)
        row2 = QHBoxLayout()
        row2.setContentsMargins(6, 0, 6, 0)
        row2.addWidget(add)
        v.addLayout(row2)

    def _build_filters(self) -> None:
        self.filter_bar = QWidget()
        h = QHBoxLayout(self.filter_bar)
        h.setContentsMargins(8, 6, 8, 6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tasks")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(200)
        self._search_timer = QTimer(singleShot=True, interval=200)
        self._search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        self.priority = QComboBox()
        self.priority.addItem("Any priority", None)
        for n in sorted(PRIORITIES, reverse=True):
            self.priority.addItem(PRIORITIES[n], n)
        self.tag = QComboBox()
        self.status = QComboBox()
        self.status.addItem("Any status", None)
        for s in STATUSES:
            self.status.addItem(STATUS_LABELS[s], s)
        self.sort = QComboBox()
        for label, key in SORT_CHOICES:
            self.sort.addItem("Sort: " + label, key)
        self.descending = QPushButton("Asc")
        self.descending.setCheckable(True)
        self.descending.setFixedWidth(48)
        self.descending.toggled.connect(lambda on: self.descending.setText("Desc" if on else "Asc"))
        self.hide_done = QCheckBox("Hide done")
        for w in (self.priority, self.tag, self.status, self.sort):
            w.currentIndexChanged.connect(lambda _: self.refresh())
        self.descending.toggled.connect(lambda _: self.refresh())
        self.hide_done.toggled.connect(lambda _: self.refresh())
        for w in (self.search, self.priority, self.tag, self.status, self.sort, self.descending, self.hide_done):
            h.addWidget(w, 1 if w is self.search else 0)

    def _build_actions(self) -> None:
        self.actions: dict[str, QAction] = {}

        def add(menu: QMenu, key: str, text: str, slot: Callable[[], None]) -> None:
            act = QAction(text, self)
            act.triggered.connect(lambda _=False: slot())
            self.actions[key] = act
            self.addAction(act)  # keeps shortcuts live even for hidden menu items
            menu.addAction(act)

        bar = self.menuBar()
        m = bar.addMenu("&File")
        add(m, "new_task", "New &task", self.new_task)
        add(m, "new_project", "New &project", self.new_project)
        m.addSeparator()
        add(m, "import", "&Import...", self.import_data)
        add(m, "export", "&Export...", self.export_data)
        m.addSeparator()
        add(m, "backup", "&Back up database...", self.backup)
        add(m, "restore", "&Restore database...", self.restore)
        m.addSeparator()
        add(m, "preferences", "Pre&ferences...", self.preferences)
        q = m.addAction("&Quit")
        q.triggered.connect(self.close)
        m = bar.addMenu("&Task")
        add(m, "edit_task", "&Edit selected", lambda: self.edit_task(None))
        add(m, "delete_task", "&Delete selected", lambda: self.delete_task(None))
        m = bar.addMenu("&Project")
        self.edit_project_act = m.addAction("&Edit...")
        self.edit_project_act.triggered.connect(self.edit_project)
        self.archive_act = m.addAction("&Archive / unarchive")
        self.archive_act.triggered.connect(self.toggle_archive)
        self.delete_project_act = m.addAction("&Delete...")
        self.delete_project_act.triggered.connect(self.delete_project)
        m = bar.addMenu("&View")
        add(m, "view_board", "&Board", lambda: self.set_view("board"))
        add(m, "view_list", "&List", lambda: self.set_view("list"))
        add(m, "view_dashboard", "&Dashboard", lambda: self.set_view("dashboard"))
        m.addSeparator()
        add(m, "search", "&Search", lambda: (self.search.setFocus(), self.search.selectAll()))
        add(m, "refresh", "&Refresh", self.refresh_all)

    # -- settings ------------------------------------------------------
    def apply_settings(self) -> None:
        self.colors = apply_theme(QApplication.instance(), self.settings["theme"])
        self.board.set_colors(self.colors)
        self.table.danger = QColor(self.colors["danger"])
        for key, act in self.actions.items():
            act.setShortcut(QKeySequence(self.settings["shortcuts"].get(key, "")))
        if self.settings["geometry"]:
            self.restoreGeometry(QByteArray.fromBase64(self.settings["geometry"].encode()))
        self.hide_done.setChecked(self.settings["hide_done"])
        self.show_archived.setChecked(self.settings["show_archived"])
        self.set_view(self.settings["view"])

    def closeEvent(self, event) -> None:
        self.settings["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        self.settings["hide_done"] = self.hide_done.isChecked()
        self.settings["show_archived"] = self.show_archived.isChecked()
        self.settings["view"] = VIEWS[self.stack.currentIndex()]
        try:
            self.settings.save()
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save settings: {exc}")
        super().closeEvent(event)

    def preferences(self) -> None:
        dlg = PreferencesDialog(self, self.settings["theme"], self.settings["shortcuts"])
        if dlg.exec():
            self.settings["theme"] = dlg.theme.currentText()
            self.settings["shortcuts"] = dlg.shortcuts()
            self.apply_settings()
            try:
                self.settings.save()
            except OSError as exc:
                self._error(f"Could not save settings: {exc}")
            self.refresh_all()

    # -- helpers -------------------------------------------------------
    def _error(self, message: str) -> None:
        QMessageBox.critical(self, "TaskFlow", message)

    def _guard(self, fn: Callable[[], object]) -> bool:
        """Run a DB operation; show a readable message on failure and refresh."""
        try:
            fn()
            ok = True
        except TaskFlowError as exc:
            self._error(str(exc))
            ok = False
        except sqlite3.Error as exc:
            self._error(f"Database error: {exc}")
            ok = False
        self.refresh_all()
        return ok

    def _run_job(self, fn: Callable[[], object], on_done: Callable[[object], None], busy: str) -> None:
        job = Job(fn)
        self._jobs.add(job)
        self.statusBar().showMessage(busy)
        self.setCursor(Qt.BusyCursor)

        def finish() -> None:
            self._jobs.discard(job)
            self.statusBar().clearMessage()
            self.unsetCursor()

        def ok(result: object) -> None:
            finish()
            on_done(result)

        def fail(message: str) -> None:
            finish()
            self._error(message)

        job.signals.done.connect(ok)
        job.signals.failed.connect(fail)
        self.pool.start(job)

    def current_project_id(self) -> int | None:
        item = self.sidebar.currentItem()
        return item.data(ID_ROLE) if item else None

    def _active_view(self):
        return self.board if self.stack.currentIndex() == 0 else self.table

    def _selected_task(self, task_id: int | None) -> int | None:
        if task_id is not None:
            return task_id
        if self.stack.currentIndex() == 2:
            return None
        return self._active_view().selected_id()

    # -- refresh -------------------------------------------------------
    def set_view(self, name: str) -> None:
        self.stack.setCurrentIndex(VIEWS.index(name) if name in VIEWS else 0)
        board, lst = self.stack.currentIndex() == 0, self.stack.currentIndex() == 1
        self.sort.setEnabled(lst)
        self.descending.setEnabled(lst)
        self.status.setEnabled(lst)
        self.filter_bar.setVisible(self.stack.currentIndex() != 2)
        if not self._building:
            self.refresh()

    def _header_sort(self, key: str) -> None:
        if self.sort.currentData() == key:
            self.descending.toggle()
        else:
            self.sort.setCurrentIndex(self.sort.findData(key))

    def refresh_all(self) -> None:
        if self._building:
            return
        self._load_sidebar()
        self._load_tags()
        self.refresh()

    def _load_sidebar(self) -> None:
        keep = self.current_project_id()
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        total_open = 0
        projects = self.service.projects(include_archived=self.show_archived.isChecked())
        items = []
        for p in projects:
            label = f"{p.name}  ({p.open_tasks})" + ("  archived" if p.archived else "")
            item = QListWidgetItem(label)
            item.setData(ID_ROLE, p.id)
            item.setData(Qt.UserRole + 1, p.archived)
            if p.archived:
                item.setForeground(Qt.gray)
            else:
                total_open += p.open_tasks
            items.append(item)
        everything = QListWidgetItem(f"All projects  ({total_open})")
        everything.setData(ID_ROLE, None)
        self.sidebar.addItem(everything)
        for item in items:
            self.sidebar.addItem(item)
        row = next((i for i in range(self.sidebar.count())
                    if self.sidebar.item(i).data(ID_ROLE) == keep), 0)
        self.sidebar.setCurrentRow(row)
        self.sidebar.blockSignals(False)
        selected = self.sidebar.currentItem().data(ID_ROLE) is not None
        for act in (self.edit_project_act, self.archive_act, self.delete_project_act):
            act.setEnabled(selected)

    def _load_tags(self) -> None:
        current = self.tag.currentData()
        self.tag.blockSignals(True)
        self.tag.clear()
        self.tag.addItem("Any tag", None)
        for t in self.service.tags():
            self.tag.addItem("#" + t, t)
        self.tag.setCurrentIndex(max(self.tag.findData(current), 0))
        self.tag.blockSignals(False)

    def _filter(self) -> TaskFilter:
        in_board = self.stack.currentIndex() == 0
        return TaskFilter(
            project_id=self.current_project_id(),
            status=None if in_board else self.status.currentData(),
            priority=self.priority.currentData(), tag=self.tag.currentData(),
            search=self.search.text(),
            sort="position" if in_board else self.sort.currentData(),
            descending=False if in_board else self.descending.isChecked(),
            hide_done=self.hide_done.isChecked(),
        )

    def refresh(self) -> None:
        if self._building or self.sidebar.currentItem() is None:
            return
        item = self.sidebar.currentItem()
        archived = bool(item.data(Qt.UserRole + 1))
        for act in (self.edit_project_act, self.archive_act, self.delete_project_act):
            act.setEnabled(item.data(ID_ROLE) is not None)
        self.archive_act.setText("Unarchive" if archived else "&Archive")
        try:
            if self.stack.currentIndex() == 2:
                self.dashboard.set_stats(self.service.stats(self.current_project_id()))
                return
            tasks = self.service.tasks(self._filter())
        except (TaskFlowError, sqlite3.Error) as exc:
            self._error(f"Could not load tasks: {exc}")
            return
        show_project = self.current_project_id() is None
        if self.stack.currentIndex() == 0:
            self.board.set_tasks(tasks, show_project)
        else:
            self.table.set_tasks(tasks)
        self.statusBar().showMessage(f"{len(tasks)} task(s)", 4000)

    # -- projects ------------------------------------------------------
    def new_project(self) -> None:
        dlg = ProjectDialog(self)
        while dlg.exec():
            if self._guard(lambda: self.service.create_project(*dlg.values())):
                return

    def edit_project(self) -> None:
        pid = self.current_project_id()
        if pid is None:
            return
        project = next(p for p in self.service.projects(True) if p.id == pid)
        dlg = ProjectDialog(self, project)
        while dlg.exec():
            if self._guard(lambda: self.service.edit_project(pid, *dlg.values())):
                return

    def toggle_archive(self) -> None:
        pid = self.current_project_id()
        if pid is None:
            return
        archived = bool(self.sidebar.currentItem().data(Qt.UserRole + 1))
        self._guard(lambda: self.service.set_archived(pid, not archived))

    def delete_project(self) -> None:
        pid = self.current_project_id()
        if pid is None:
            return
        project = next(p for p in self.service.projects(True) if p.id == pid)
        answer = QMessageBox.question(
            self, "Delete project",
            f"Delete '{project.name}' and its {project.total_tasks} task(s)? This cannot be undone.\n"
            "Archive the project instead to keep the data.")
        if answer == QMessageBox.Yes:
            self._guard(lambda: self.service.delete_project(pid))

    def _project_menu(self, pos) -> None:
        item = self.sidebar.itemAt(pos)
        if item is None or item.data(ID_ROLE) is None:
            return
        self.sidebar.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction(self.edit_project_act)
        menu.addAction(self.archive_act)
        menu.addAction(self.delete_project_act)
        menu.exec(self.sidebar.viewport().mapToGlobal(pos))

    # -- tasks ---------------------------------------------------------
    def new_task(self, status: str = "todo") -> None:
        projects = self.service.projects()
        if not projects:
            self._error("Create a project first (File > New project).")
            return
        dlg = TaskDialog(self, projects, default_project=self.current_project_id(), default_status=status)
        while dlg.exec():
            if self._guard(lambda: self.service.create_task(**dlg.values())):
                return

    def edit_task(self, task_id: int | None) -> None:
        task_id = self._selected_task(task_id)
        if task_id is None:
            return
        try:
            task = self.service.get_task(task_id)
        except TaskFlowError as exc:
            self._error(str(exc))
            self.refresh_all()
            return
        dlg = TaskDialog(self, self.service.projects(include_archived=True), task)
        while dlg.exec():
            if self._guard(lambda: self.service.edit_task(task_id, **dlg.values())):
                return

    def delete_task(self, task_id: int | None) -> None:
        task_id = self._selected_task(task_id)
        if task_id is None:
            return
        try:
            task = self.service.get_task(task_id)
        except TaskFlowError as exc:
            self._error(str(exc))
            self.refresh_all()
            return
        if QMessageBox.question(self, "Delete task", f"Delete '{task.title}'?") == QMessageBox.Yes:
            self._guard(lambda: self.service.delete_task(task_id))

    def _move(self, task_id: int, status: str, before: int | None) -> None:
        self._guard(lambda: self.service.move_task(task_id, status, before))

    def _task_menu(self, task_id: int, pos) -> None:
        menu = QMenu(self)
        menu.addAction("Edit...", lambda: self.edit_task(task_id))
        move = menu.addMenu("Move to")
        for s in STATUSES:
            move.addAction(STATUS_LABELS[s], lambda s=s: self._move(task_id, s, None))
        menu.addSeparator()
        menu.addAction("Delete...", lambda: self.delete_task(task_id))
        menu.exec(pos)

    # -- files ---------------------------------------------------------
    def _db_path(self) -> Path:
        return self.service.db.path

    def import_data(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import", "", "TaskFlow data (*.json *.csv)")
        if not path:
            return
        db_path = self._db_path()

        def work():
            with closing(Database(db_path)) as db:
                return import_file(db, path)

        def done(result) -> None:
            self.refresh_all()
            QMessageBox.information(
                self, "Import",
                f"Imported {result.tasks_created} task(s); {result.projects_created} new project(s).")

        self._run_job(work, done, "Importing...")

    def export_data(self) -> None:
        path, selected = QFileDialog.getSaveFileName(
            self, "Export", "taskflow-export.json", "JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        as_csv = path.lower().endswith(".csv") or (
            not path.lower().endswith(".json") and "csv" in selected.lower())
        if not path.lower().endswith((".json", ".csv")):
            path += ".csv" if as_csv else ".json"
        db_path = self._db_path()

        def work():
            with closing(Database(db_path)) as db:
                return (export_csv if as_csv else export_json)(db, path)

        self._run_job(work, lambda n: self.statusBar().showMessage(f"Exported {n} task(s) to {path}", 8000),
                      "Exporting...")

    def backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Back up database", "taskflow-backup.db", "SQLite database (*.db)")
        if not path:
            return
        db_path = self._db_path()
        self._run_job(lambda: backup_database(db_path, path),
                      lambda _: self.statusBar().showMessage(f"Backup saved to {path}", 8000),
                      "Backing up...")

    def restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore database", "", "SQLite database (*.db)")
        if not path:
            return
        if QMessageBox.question(
                self, "Restore database",
                "Replace all current data with this backup?\nCurrent data is saved first as a "
                "pre-restore file next to the database.") != QMessageBox.Yes:
            return
        try:
            safety = restore_database(self.service.db, path)
        except (TaskFlowError, sqlite3.Error, OSError) as exc:
            self._error(str(exc))
            return
        self.refresh_all()
        QMessageBox.information(self, "Restore", f"Database restored.\nPrevious data saved to:\n{safety}")
