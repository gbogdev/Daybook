"""Database backup and restore using SQLite's online backup API."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from .db import SCHEMA_VERSION, Database
from .models import DataFileError

_REQUIRED_COLUMNS = {
    "projects": {"id", "name", "description", "archived", "created_at"},
    "tasks": {"id", "project_id", "title", "description", "priority", "status", "deadline",
              "position", "created_at", "completed_at"},
    "task_tags": {"task_id", "tag"},
}
_REQUIRED_TABLES = set(_REQUIRED_COLUMNS)


def backup_database(src_path: str | Path, dest: str | Path) -> None:
    """Copy a consistent snapshot of the database at src_path to dest."""
    dest = Path(dest)
    if dest.resolve() == Path(src_path).resolve():
        raise DataFileError("The backup destination is the live database.")
    tmp = dest.with_name(dest.name + ".tmp")  # replace atomically: a failure keeps any old file
    src = dst = None
    try:
        src = sqlite3.connect(src_path)
        dst = sqlite3.connect(tmp)
        src.backup(dst)
        dst.close()
        dst = None
        os.replace(tmp, dest)
    except (sqlite3.Error, OSError) as exc:
        raise DataFileError(f"Backup failed: {exc}") from exc
    finally:
        for conn in (src, dst):
            if conn:
                conn.close()
        tmp.unlink(missing_ok=True)


def _validate_backup(path: Path) -> None:
    if not path.is_file():
        raise DataFileError(f"{path} does not exist.")
    conn = None
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DataFileError(f"{path.name} is damaged (integrity check failed).")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not _REQUIRED_TABLES <= tables:
            raise DataFileError(f"{path.name} is not a TaskFlow database.")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if not 1 <= version <= SCHEMA_VERSION:
            raise DataFileError(
                f"{path.name} has schema version {version}; this TaskFlow supports 1-{SCHEMA_VERSION}.")
        for table, columns in _REQUIRED_COLUMNS.items():
            have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if not columns <= have:
                raise DataFileError(f"{path.name} is not a TaskFlow database (bad '{table}' table).")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise DataFileError(f"{path.name} fails the foreign-key check and cannot be restored.")
    except sqlite3.DatabaseError as exc:
        raise DataFileError(f"{path.name} is not a valid SQLite database ({exc}).") from exc
    finally:
        if conn:
            conn.close()


def restore_database(db: Database, src: str | Path) -> Path:
    """Replace the live database contents with `src`.

    The current data is first saved next to the live database as
    pre-restore-<timestamp>.db; its path is returned.
    """
    src = Path(src)
    if src.exists() and src.resolve() == db.path.resolve():
        raise DataFileError("That is the live database; choose a backup file.")
    _validate_backup(src)
    safety = db.path.with_name(f"pre-restore-{datetime.now():%Y%m%d-%H%M%S}.db")
    backup_database(db.path, safety)
    source = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)
    try:
        source.backup(db.conn)
        db.migrate()
    except sqlite3.Error as exc:
        raise DataFileError(
            f"Restore failed: {exc}. Your previous data is saved at {safety}.") from exc
    finally:
        source.close()
    return safety
