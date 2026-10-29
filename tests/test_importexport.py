import json
import sqlite3

import pytest

from daybook.backup import backup_database, restore_database
from daybook.importexport import export_csv, export_json, import_file
from daybook.models import DataFileError


@pytest.fixture
def populated(svc):
    p = svc.create_project("Work", "main")
    e = svc.create_project("Empty")
    svc.set_archived(e, True)
    svc.create_task(p, 'Quote "this", ok', "line1\nline2", 3, "doing", "2026-05-01", "a, b")
    svc.create_task(p, "Done one", status="done")
    return svc


def _snapshot(svc):
    return sorted((t.project_name, t.title, t.description, t.priority, t.status, t.deadline,
                   tuple(t.tags)) for t in svc.db.query_tasks(include_archived=True))


@pytest.mark.parametrize("fmt", ["json", "csv"])
def test_round_trip(populated, tmp_path, fmt):
    path = tmp_path / f"out.{fmt}"
    (export_json if fmt == "json" else export_csv)(populated.db, path)
    from daybook.db import Database
    from daybook.service import TaskService
    with Database(tmp_path / "fresh.db") as fresh:
        result = import_file(fresh, path)
        assert result.tasks_created == 2
        assert _snapshot(TaskService(fresh)) == _snapshot(populated)
        if fmt == "json":  # empty archived projects survive JSON only
            assert {p.name for p in fresh.list_projects(True)} == {"Work", "Empty"}


def test_import_merges_into_existing_project(populated, tmp_path):
    path = tmp_path / "x.json"
    export_json(populated.db, path)
    result = import_file(populated.db, path)
    assert result.projects_created == 0 and result.tasks_created == 2
    assert len(populated.db.query_tasks(include_archived=True)) == 4


def test_csv_error_reports_row_and_imports_nothing(svc, tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("project,title,priority\nA,ok,high\nA,broken,extreme\n", encoding="utf-8")
    with pytest.raises(DataFileError, match="Row 3"):
        import_file(svc.db, path)
    assert svc.db.list_projects(True) == []  # all-or-nothing


def test_csv_missing_columns(svc, tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("name,desc\nA,B\n", encoding="utf-8")
    with pytest.raises(DataFileError, match="missing required"):
        import_file(svc.db, path)


@pytest.mark.parametrize("content,message", [
    ("{not json", "not valid JSON"),
    ('{"hello": 1}', "not a Daybook export"),
    ('{"projects": [{"name": "", "tasks": []}]}', "Project #1"),
    ('{"projects": [{"name": "A", "tasks": [{"title": ""}]}]}', "task #1"),
    ('{"version": 99, "projects": []}', "newer"),
])
def test_bad_json(svc, tmp_path, content, message):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DataFileError, match=message):
        import_file(svc.db, path)


def test_unsupported_and_missing_files(svc, tmp_path):
    with pytest.raises(DataFileError, match="Unsupported"):
        import_file(svc.db, tmp_path / "x.txt")
    with pytest.raises(DataFileError, match="Could not read"):
        import_file(svc.db, tmp_path / "missing.json")


def test_export_to_unwritable_path(populated, tmp_path):
    with pytest.raises(DataFileError, match="Could not write"):
        export_json(populated.db, tmp_path / "no_such_dir" / "x.json")


def test_unicode_survives(svc, project, tmp_path):
    svc.create_task(project, "Zażółć gęślą 日本語", tags="ünï")
    path = tmp_path / "u.csv"
    export_csv(svc.db, path)
    assert "日本語" in path.read_text(encoding="utf-8")


# -- backup / restore --------------------------------------------------
def test_backup_and_restore(populated, tmp_path):
    dest = tmp_path / "bk.db"
    backup_database(populated.db.path, dest)
    before = _snapshot(populated)
    populated.db.delete_project(populated.projects()[0].id)
    assert _snapshot(populated) != before
    safety = restore_database(populated.db, dest)
    assert _snapshot(populated) == before
    assert safety.exists() and safety.name.startswith("pre-restore-")
    assert populated.db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_restore_rejects_garbage(populated, tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not a database" * 50)
    with pytest.raises(DataFileError):
        restore_database(populated.db, junk)
    other = tmp_path / "other.db"
    conn = sqlite3.connect(other)
    conn.execute("CREATE TABLE foo (x)")
    conn.commit()
    conn.close()
    with pytest.raises(DataFileError, match="not a Daybook database"):
        restore_database(populated.db, other)
    with pytest.raises(DataFileError, match="does not exist"):
        restore_database(populated.db, tmp_path / "nope.db")
    assert len(populated.db.query_tasks(include_archived=True)) == 2  # untouched


def test_backup_onto_live_db_refused(populated):
    with pytest.raises(DataFileError):
        backup_database(populated.db.path, populated.db.path)
