"""Board, list and dashboard widgets. They display data and emit signals only."""
from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QProgressBar, QStyle, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..models import PRIORITIES, STATUS_LABELS, STATUSES, Task
from ..service import Stats

ID_ROLE = Qt.UserRole
SUB_ROLE = Qt.UserRole + 1
PRIORITY_ROLE = Qt.UserRole + 2
OVERDUE_ROLE = Qt.UserRole + 3


def task_subtitle(t: Task, show_project: bool) -> str:
    parts = [PRIORITIES[t.priority]]
    if t.deadline:
        parts.append(("overdue " if t.is_overdue() else "due ") + t.deadline)
    if show_project:
        parts.append(t.project_name)
    if t.tags:
        parts.append("#" + " #".join(t.tags))
    return "  ·  ".join(parts)


class CardDelegate(QStyledItemDelegate):
    colors: dict[str, str] = {}

    def sizeHint(self, option, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 58)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        c = self.colors
        r = option.rect.adjusted(2, 3, -2, -3)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(c["accent"] if selected else c["border"])))
        painter.setBrush(QColor(c["hover"] if hovered and not selected else c["base"]))
        painter.drawRoundedRect(r.adjusted(0, 0, -1, -1), 6, 6)
        dot = {3: c["danger"], 2: c["warn"]}.get(index.data(PRIORITY_ROLE), c["low"])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(dot))
        painter.drawEllipse(r.left() + 11, r.top() + 13, 8, 8)
        text = QRect(r.left() + 26, r.top() + 8, r.width() - 36, r.height() - 14)
        fm = painter.fontMetrics()
        title_font = painter.font()
        title_font.setWeight(QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(c["text"]))
        painter.drawText(text.left(), text.top() + fm.ascent(),
                         painter.fontMetrics().elidedText(index.data(Qt.DisplayRole), Qt.ElideRight, text.width()))
        small = painter.font()
        small.setWeight(QFont.Normal)
        small.setPointSizeF(max(small.pointSizeF() - 1, 7))
        painter.setFont(small)
        painter.setPen(QColor(c["danger"] if index.data(OVERDUE_ROLE) else c["muted"]))
        sm = painter.fontMetrics()
        painter.drawText(text.left(), text.bottom() - sm.descent(),
                         sm.elidedText(index.data(SUB_ROLE), Qt.ElideRight, text.width()))
        painter.restore()


class KanbanColumn(QListWidget):
    """One status column. Drops are reported, not applied; the owner reloads from the DB."""
    dropped = Signal(int, str, object)  # task id, status, id of task to insert before (or None)

    def __init__(self, status: str):
        super().__init__()
        self.status = status
        self.setObjectName("column")
        self.setMouseTracking(True)
        self.setItemDelegate(CardDelegate(self))
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setSpacing(0)

    def dropEvent(self, event) -> None:
        source = event.source()
        moved = source.currentItem() if isinstance(source, KanbanColumn) else None
        if moved is None:
            event.ignore()
            return
        moved_id = moved.data(ID_ROLE)
        pos = event.position().toPoint()
        target = self.itemAt(pos)
        before = None
        if target is not None:
            row = self.row(target)
            if pos.y() >= self.visualItemRect(target).center().y():
                row += 1
            nxt = self.item(row)
            before = nxt.data(ID_ROLE) if nxt else None
            if before == moved_id:  # dropped onto itself: keep position
                after = self.item(row + 1)
                before = after.data(ID_ROLE) if after else None
        event.setDropAction(Qt.IgnoreAction)  # the DB is the source of truth
        event.accept()
        self.dropped.emit(moved_id, self.status, before)


class BoardView(QWidget):
    taskMoved = Signal(int, str, object)
    taskActivated = Signal(int)
    contextRequested = Signal(int, QPoint)
    selectionChanged = Signal()

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.columns: dict[str, KanbanColumn] = {}
        self.headers: dict[str, QLabel] = {}
        for status in STATUSES:
            col = KanbanColumn(status)
            col.dropped.connect(self.taskMoved)
            col.itemDoubleClicked.connect(lambda i: self.taskActivated.emit(i.data(ID_ROLE)))
            col.itemSelectionChanged.connect(lambda c=col: self._on_select(c))
            col.setContextMenuPolicy(Qt.CustomContextMenu)
            col.customContextMenuRequested.connect(lambda p, c=col: self._context(c, p))
            header = QLabel()
            header.setObjectName("section")
            panel = QWidget()
            panel.setObjectName("columnPanel")
            box = QVBoxLayout(panel)
            box.setContentsMargins(8, 8, 8, 8)
            box.setSpacing(6)
            box.addWidget(header)
            box.addWidget(col, 1)
            layout.addWidget(panel, 1)
            self.columns[status] = col
            self.headers[status] = header

    def _on_select(self, col: KanbanColumn) -> None:
        if col.selectedItems():
            for other in self.columns.values():
                if other is not col:
                    other.blockSignals(True)
                    other.clearSelection()
                    other.blockSignals(False)
        self.selectionChanged.emit()

    def _context(self, col: KanbanColumn, pos: QPoint) -> None:
        item = col.itemAt(pos)
        if item is not None:
            col.setCurrentItem(item)
            self.contextRequested.emit(item.data(ID_ROLE), col.viewport().mapToGlobal(pos))

    def selected_id(self) -> int | None:
        for col in self.columns.values():
            if col.selectedItems():
                return col.selectedItems()[0].data(ID_ROLE)
        return None

    def set_tasks(self, tasks: list[Task], show_project: bool) -> None:
        keep = self.selected_id()
        for status, col in self.columns.items():
            col.blockSignals(True)
            col.clear()
            col.blockSignals(False)
        counts = dict.fromkeys(STATUSES, 0)
        for t in tasks:
            counts[t.status] += 1
            item = QListWidgetItem(t.title)
            item.setData(ID_ROLE, t.id)
            item.setData(SUB_ROLE, task_subtitle(t, show_project))
            item.setData(PRIORITY_ROLE, t.priority)
            item.setData(OVERDUE_ROLE, t.is_overdue())
            item.setToolTip(t.description[:300] if t.description else t.title)
            self.columns[t.status].addItem(item)
            if t.id == keep:
                self.columns[t.status].setCurrentItem(item)
        for status, header in self.headers.items():
            header.setText(f"{STATUS_LABELS[status].upper()}   {counts[status]}")

    def set_colors(self, colors: dict[str, str]) -> None:
        CardDelegate.colors = colors
        for col in self.columns.values():
            col.viewport().update()


class TaskTable(QTableWidget):
    taskActivated = Signal(int)
    doneToggled = Signal(int, bool)
    contextRequested = Signal(int, QPoint)
    sortRequested = Signal(str)

    HEADERS = ["", "Title", "Project", "Priority", "Status", "Deadline", "Tags"]
    SORT_KEYS = {1: "title", 2: "project", 3: "priority", 4: "status", 5: "deadline"}

    def __init__(self):
        super().__init__(0, len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.sectionClicked.connect(
            lambda i: self.sortRequested.emit(self.SORT_KEYS[i]) if i in self.SORT_KEYS else None)
        for col, width in enumerate((28, 300, 120, 80, 100, 90)):
            self.setColumnWidth(col, width)
        self.itemChanged.connect(self._changed)
        self.itemDoubleClicked.connect(lambda i: self.taskActivated.emit(self.item(i.row(), 1).data(ID_ROLE)))
        self.customContextMenuRequested.connect(self._context)
        self.danger = QColor("#c0605a")

    def _changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self.doneToggled.emit(item.data(ID_ROLE), item.checkState() == Qt.Checked)

    def _context(self, pos: QPoint) -> None:
        row = self.rowAt(pos.y())
        if row >= 0:
            self.selectRow(row)
            self.contextRequested.emit(self.item(row, 1).data(ID_ROLE), self.viewport().mapToGlobal(pos))

    def selected_id(self) -> int | None:
        rows = self.selectionModel().selectedRows()
        return self.item(rows[0].row(), 1).data(ID_ROLE) if rows else None

    def set_tasks(self, tasks: list[Task]) -> None:
        keep = self.selected_id()
        self.blockSignals(True)
        self.setRowCount(len(tasks))
        for row, t in enumerate(tasks):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check.setCheckState(Qt.Checked if t.done else Qt.Unchecked)
            check.setData(ID_ROLE, t.id)
            cells = [t.title, t.project_name, PRIORITIES[t.priority], STATUS_LABELS[t.status],
                     t.deadline or "", ", ".join(t.tags)]
            self.setItem(row, 0, check)
            for col, text in enumerate(cells, 1):
                item = QTableWidgetItem(text)
                item.setData(ID_ROLE, t.id)
                if t.is_overdue() and col == 5:
                    item.setForeground(self.danger)
                self.setItem(row, col, item)
            if t.id == keep:
                self.selectRow(row)
        self.blockSignals(False)


class DashboardView(QWidget):
    def __init__(self):
        super().__init__()
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(12, 12, 12, 12)
        self.body = QWidget()
        self.layout_.addWidget(self.body)
        self.layout_.addStretch(1)

    @staticmethod
    def _bar(label: str, value: int, maximum: int) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        name = QLabel(label)
        name.setFixedWidth(130)
        bar = QProgressBar()
        bar.setRange(0, max(maximum, 1))
        bar.setValue(value)
        bar.setFormat(str(value))
        h.addWidget(name)
        h.addWidget(bar, 1)
        return row

    def set_stats(self, s: Stats) -> None:
        self.body.setParent(None)
        self.body.deleteLater()
        self.body = QWidget()
        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(0, 0, 0, 0)
        tile_row = QHBoxLayout()
        tile_row.setSpacing(8)
        outer.addLayout(tile_row)
        grid = QGridLayout()
        grid.setSpacing(16)
        outer.addLayout(grid)
        tiles = [("Total", s.total), ("Open", s.open), ("Done", s.done),
                 ("Overdue", s.overdue), ("Due in 7 days", s.due_this_week)]
        for caption, value in tiles:
            tile = QFrame()
            tile.setObjectName("tile")
            box = QVBoxLayout(tile)
            box.setSpacing(0)
            number = QLabel(str(value))
            number.setObjectName("statValue")
            small = QLabel(caption)
            small.setObjectName("muted")
            box.addWidget(number)
            box.addWidget(small)
            tile_row.addWidget(tile, 1)

        def section(title: str, rows: list[QWidget], col: int, row: int) -> None:
            holder = QWidget()
            v = QVBoxLayout(holder)
            v.setContentsMargins(0, 8, 0, 0)
            head = QLabel(title.upper())
            head.setObjectName("section")
            v.addWidget(head)
            for w in rows or [QLabel("Nothing to show.")]:
                v.addWidget(w)
            v.addStretch(1)
            grid.addWidget(holder, row, col)

        top = max(s.total, 1)
        section("By status", [self._bar(STATUS_LABELS[k], v, top) for k, v in s.by_status.items()], 0, 1)
        top_open = max(s.open, 1)
        section("Open tasks by priority",
                [self._bar(PRIORITIES[k], v, top_open) for k, v in sorted(s.by_priority.items(), reverse=True)], 1, 1)
        section("Projects (done / total)",
                [self._project_bar(n, t, d) for n, t, d in s.projects], 0, 2)
        upcoming = []
        for t in s.upcoming:
            label = QLabel(f"{t.deadline}   {t.title}   ({t.project_name})")
            if t.is_overdue():
                label.setStyleSheet(f"color: {CardDelegate.colors.get('danger', '#c0605a')};")
            upcoming.append(label)
        section("Upcoming deadlines", upcoming, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.layout_.insertWidget(0, self.body)

    @staticmethod
    def _project_bar(name: str, total: int, done: int) -> QWidget:
        row = DashboardView._bar(name, done, total)
        row.findChild(QProgressBar).setFormat(f"{done} / {total}")
        return row
