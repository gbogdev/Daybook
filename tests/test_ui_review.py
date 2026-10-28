import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from taskflow.settings import Settings  # noqa: E402
from taskflow.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_checkbox_toggle_marks_done_without_crashing(app, svc, project, tmp_path):
    tid = svc.create_task(project, "A")
    win = MainWindow(svc, Settings(tmp_path / "s.json"))
    win.set_view("list")
    win.table.item(0, 0).setCheckState(Qt.Checked)
    for _ in range(5):
        QCoreApplication.processEvents()
    assert svc.get_task(tid).done
    assert win.table.item(0, 0).checkState() == Qt.Checked


def test_file_operations_blocked_while_job_running(app, svc, project, tmp_path, monkeypatch):
    win = MainWindow(svc, Settings(tmp_path / "s.json"))
    win._jobs.add(object())
    shown = []
    monkeypatch.setattr(win, "_error", shown.append)
    win.restore()
    win.import_data()
    assert len(shown) == 2 and "in progress" in shown[0]
