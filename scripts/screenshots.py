"""Generate docs/*.png from demo data in a throwaway database.

Usage: python scripts/screenshots.py
"""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from daybook.db import Database  # noqa: E402
from daybook.service import TaskService  # noqa: E402
from daybook.settings import Settings  # noqa: E402
from daybook.ui.main_window import MainWindow  # noqa: E402


def d(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def seed(svc: TaskService) -> None:
    web = svc.create_project("Website redesign", "Marketing site refresh")
    app = svc.create_project("Mobile app")
    home = svc.create_project("Home")
    rows = [
        (web, "Audit current sitemap", 2, "done", d(-6), "research"),
        (web, "Write new landing page copy", 3, "doing", d(2), "content, copy"),
        (web, "Replace hero image", 1, "todo", d(10), "design"),
        (web, "Fix broken links on pricing page", 3, "todo", d(-2), "bug"),
        (web, "Set up redirects", 2, "todo", None, "seo"),
        (app, "Crash on login with expired token", 3, "doing", d(1), "bug, auth"),
        (app, "Offline mode spike", 2, "todo", d(14), "research"),
        (app, "Update store screenshots", 1, "todo", None, "release"),
        (app, "Release 1.2 notes", 2, "done", d(-3), "release"),
        (home, "Renew passport", 3, "todo", d(21), "admin"),
        (home, "Service the bike", 1, "todo", None, ""),
    ]
    for p, title, pri, status, due, tags in rows:
        svc.create_task(p, title, "", pri, status, due, tags)


def main() -> None:
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    app = QApplication([])
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp" if (ROOT / ".tmp").exists() else None) as tmp:
        db = Database(Path(tmp) / "demo.db")
        svc = TaskService(db)
        seed(svc)
        win = MainWindow(svc, Settings(Path(tmp) / "settings.json"))
        win.resize(1100, 640)
        win.show()
        for view in ("board", "list", "dashboard"):
            win.set_view(view)
            app.processEvents()
            win.grab().save(str(out / f"{view}.png"))
        win.close()
        db.close()
    print("wrote", ", ".join(sorted(p.name for p in out.glob("*.png"))))


if __name__ == "__main__":
    main()
