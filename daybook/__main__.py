"""Entry point: python -m daybook [--data-dir DIR]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .settings import Settings, default_data_dir


def _setup_logging(data_dir: Path) -> None:
    """Log to <data dir>/daybook.log and show unhandled errors instead of dying silently."""
    import logging
    from logging.handlers import RotatingFileHandler

    from PySide6.QtWidgets import QMessageBox

    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(data_dir / "daybook.log", maxBytes=512_000, backupCount=2,
                                      encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
    except OSError:
        pass  # logging is best-effort; the app must still start

    def hook(kind, value, tb) -> None:
        logging.getLogger("daybook").error("Unhandled exception", exc_info=(kind, value, tb))
        QMessageBox.critical(None, "Daybook", f"Unexpected error: {value}\n\nDetails are in "
                                               f"{data_dir / 'daybook.log'}")

    sys.excepthook = hook


def main() -> int:
    parser = argparse.ArgumentParser(prog="daybook")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="folder for the database and settings (default: per-user app data)")
    args = parser.parse_args()
    data_dir = args.data_dir or default_data_dir()

    from PySide6.QtWidgets import QApplication, QMessageBox

    from .db import Database
    from .service import TaskService
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Daybook")
    from PySide6.QtGui import QIcon
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "icon.png")))
    _setup_logging(data_dir)
    try:
        db = Database(data_dir / "daybook.db")
    except Exception as exc:  # DaybookError, OSError, sqlite3.Error: all end the same way
        QMessageBox.critical(None, "Daybook", f"Could not open the database in {data_dir}:\n{exc}")
        return 1
    service = TaskService(db)
    if db.created:
        service.create_project("Inbox")
    window = MainWindow(service, Settings(data_dir / "settings.json"))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
