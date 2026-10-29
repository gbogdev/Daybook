"""Board, list and dashboard widgets. They display data and emit signals only."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QModelIndex, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QProgressBar, QStyle, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..models import PRIORITIES, STATUS_LABELS, STATUSES, Task
from ..service import Stats

ID_ROLE = Qt.UserRole
PRIORITY_ROLE = Qt.UserRole + 2
OVERDUE_ROLE = Qt.UserRole + 3
DUE_ROLE = Qt.UserRole + 4
PROJECT_ROLE = Qt.UserRole + 5
TAGS_ROLE = Qt.UserRole + 6
ARCHIVED_ROLE = Qt.UserRole + 7
COUNT_ROLE = Qt.UserRole + 8
TOTAL_ROLE = Qt.UserRole + 9

PROJECT_DOTS = ["#5b8def", "#4fb286", "#d9a441", "#c76fb0", "#e0675f", "#8a7fe0"]


def _tint(color: str, alpha: int) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c


def _short_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%b %d").replace(" 0", " ")
    except ValueError:
        return iso


class SidebarDelegate(QStyledItemDelegate):
    colors: dict[str, str] = {}

    def sizeHint(self, option, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 34)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        c = self.colors
        r = option.rect.adjusted(6, 1, -6, -1)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        archived = bool(index.data(ARCHIVED_ROLE))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if selected or hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(c["accent"] if selected else c["hover"]))
            painter.drawRoundedRect(QRectF(r), 6, 6)
        pid = index.data(ID_ROLE)
        dot = QColor(c["muted"] if archived else PROJECT_DOTS[pid % len(PROJECT_DOTS)] if pid else c["muted"])
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot if pid is not None else Qt.NoBrush)
        if pid is None:  # "All projects": hollow ring
            painter.setPen(QPen(QColor(c["accent_text"] if selected else c["muted"]), 1.5))
        painter.drawEllipse(r.left() + 10, r.center().y() - 4, 8, 8)
        fg = QColor(c["accent_text"] if selected else c["muted"] if archived else c["text"])
        count = f"{index.data(COUNT_ROLE)}"
        fm = painter.fontMetrics()
        painter.setPen(_tint(fg.name(), 170 if selected else 150) if not selected else fg)
        painter.drawText(QRect(r.right() - 40, r.top(), 32, r.height()),
                         Qt.AlignRight | Qt.AlignVCenter, count)
        painter.setPen(fg)
        label = fm.elidedText(index.data(Qt.DisplayRole), Qt.ElideRight, r.width() - 80)
        painter.drawText(QRect(r.left() + 26, r.top(), r.width() - 70, r.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, label)
        painter.restore()


class CardDelegate(QStyledItemDelegate):
    colors: dict[str, str] = {}

    def sizeHint(self, option, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 74)

    @staticmethod
    def _pill(painter: QPainter, x: int, y: int, h: int, text: str, fg: QColor, bg: QColor,
              limit: int) -> int:
        w = painter.fontMetrics().horizontalAdvance(text) + 14
        if x + w > limit:
            return limit + 1  # no room: stop drawing further pills
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
        painter.setPen(fg)
        painter.drawText(QRect(x, y, w, h), Qt.AlignCenter, text)
        return x + w + 6

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        c = self.colors
        r = option.rect.adjusted(2, 3, -2, -3)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(c["accent"] if selected else c["border"])))
        painter.setBrush(QColor(c["hover"] if hovered and not selected else c["base"]))
        painter.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

        inner = r.adjusted(12, 10, -12, -10)
        title_font = painter.font()
        title_font.setWeight(QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(c["text"]))
        fm = painter.fontMetrics()
        painter.drawText(inner.left(), inner.top() + fm.ascent(),
                         fm.elidedText(index.data(Qt.DisplayRole), Qt.ElideRight, inner.width()))

        small = painter.font()
        small.setWeight(QFont.Normal)
        small.setPointSizeF(max(small.pointSizeF() - 1.5, 7))
        painter.setFont(small)
        pill_h = painter.fontMetrics().height() + 2
        y = inner.bottom() - pill_h + 1
        x, limit = inner.left(), inner.right()
        priority = index.data(PRIORITY_ROLE)
        color = {3: c["danger"], 2: c["warn"]}.get(priority, c["low"])
        x = self._pill(painter, x, y, pill_h, PRIORITIES[priority], QColor(color), _tint(color, 38), limit)
        due = index.data(DUE_ROLE)
        if due:
            overdue = bool(index.data(OVERDUE_ROLE))
            text = ("Overdue " if overdue else "Due ") + _short_date(due)
            fg = QColor(c["danger"] if overdue else c["muted"])
            x = self._pill(painter, x, y, pill_h, text, fg, _tint(fg.name(), 30), limit)
        project = index.data(PROJECT_ROLE)
        if project:
            x = self._pill(painter, x, y, pill_h, project, QColor(c["muted"]), _tint(c["muted"], 30), limit)
        for tag in index.data(TAGS_ROLE) or []:
            x = self._pill(painter, x, y, pill_h, "#" + tag, QColor(c["muted"]), _tint(c["muted"], 30), limit)
            if x > limit:
                break
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

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor(CardDelegate.colors.get("muted", "#888888")))
            painter.drawText(self.viewport().rect(), Qt.AlignHCenter | Qt.AlignTop, "\n  No tasks")
            painter.end()

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
            item.setData(DUE_ROLE, t.deadline)
            item.setData(PROJECT_ROLE, t.project_name if show_project else None)
            item.setData(TAGS_ROLE, t.tags)
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
        SidebarDelegate.colors = colors
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
            if caption == "Overdue" and value:
                number.setStyleSheet(f"color: {CardDelegate.colors.get('danger', '#e0675f')};")
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
