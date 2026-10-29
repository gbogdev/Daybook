import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from daybook.settings import Settings  # noqa: E402
from daybook.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_window_loads_and_switches_views(app, svc, project, tmp_path):
    svc.create_task(project, "A", tags="x")
    svc.create_task(project, "B", status="done", deadline="2020-01-01")
    win = MainWindow(svc, Settings(tmp_path / "s.json"))
    assert sum(c.count() for c in win.board.columns.values()) == 2
    win.set_view("list")
    assert win.table.rowCount() == 2
    win.set_view("dashboard")
    win.search.setText("zzz")
    win.set_view("list")
    win._search_timer.timeout.emit()
    assert win.table.rowCount() == 0


def test_board_move_persists(app, svc, project, tmp_path):
    tid = svc.create_task(project, "A")
    win = MainWindow(svc, Settings(tmp_path / "s.json"))
    win._move(tid, "doing", None)
    assert svc.get_task(tid).status == "doing"
    assert win.board.columns["doing"].count() == 1


def test_settings_saved_on_close(app, svc, project, tmp_path):
    settings = Settings(tmp_path / "s.json")
    win = MainWindow(svc, settings)
    win.set_view("list")
    win.close()
    assert Settings(tmp_path / "s.json")["view"] == "list"
