"""Entry point: python -m taskflow [--data-dir DIR]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .settings import Settings, default_data_dir


def main() -> int:
    parser = argparse.ArgumentParser(prog="taskflow")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="folder for the database and settings (default: per-user app data)")
    args = parser.parse_args()
    data_dir = args.data_dir or default_data_dir()

    from PySide6.QtWidgets import QApplication, QMessageBox

    from .db import Database
    from .service import TaskService
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("TaskFlow")
    try:
        db = Database(data_dir / "taskflow.db")
    except Exception as exc:  # TaskFlowError, OSError, sqlite3.Error: all end the same way
        QMessageBox.critical(None, "TaskFlow", f"Could not open the database in {data_dir}:\n{exc}")
        return 1
    service = TaskService(db)
    if db.created:
        service.create_project("Inbox")
    window = MainWindow(service, Settings(data_dir / "settings.json"))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
