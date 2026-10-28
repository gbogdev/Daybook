"""Regression tests for issues found in the code review."""
import os
import sqlite3

import pytest

from taskflow.backup import backup_database, restore_database
from taskflow.db import SCHEMA_VERSION, Database
from taskflow.importexport import export_csv, export_json, import_file
from taskflow.models import DataFileError, ValidationError, normalize_tags


def test_failed_open_releases_file(tmp_path):
    path = tmp_path / "new.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(ValidationError):
        Database(path)
    os.remove(path)  # fails on Windows if the connection leaked


def test_csv_formula_cells_are_neutralised_and_round_trip(svc, project, tmp_path):
    svc.create_task(project, "=HYPERLINK(\"http://x\")", "+cmd|' /C calc'!A0", tags="@x")
    path = tmp_path / "o.csv"
    export_csv(svc.db, path)
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines()[1:]:
        assert not any(cell.startswith(("=", "+", "-", "@")) for cell in line.split(","))
    from taskflow.db import Database as D
    with D(tmp_path / "f.db") as fresh:
        import_file(fresh, path)
        t = fresh.query_tasks()[0]
        assert t.title == "=HYPERLINK(\"http://x\")" and t.description.startswith("+cmd")


def test_tag_control_characters_rejected():
    assert normalize_tags(["a\x1fb"]) == ["a b"]  # separator char can never reach the DB
    with pytest.raises(ValidationError):
        normalize_tags(["a\x01b"])


@pytest.mark.parametrize("content", [
    '{"projects": [{"name": "A", "tasks": [{"title": "t", "tags": 5}]}]}',
    '{"projects": [{"name": "A", "tasks": [{"title": "t", "priority": 0}]}]}',
    '{"projects": [{"name": "A", "archived": "false", "tasks": []}]}',
])
def test_bad_json_values_give_clean_errors(svc, tmp_path, content):
    path = tmp_path / "b.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DataFileError):
        import_file(svc.db, path)
    assert svc.db.list_projects(True) == []


def test_oversized_import_rejected(svc, tmp_path, monkeypatch):
    import taskflow.importexport as ie
    monkeypatch.setattr(ie, "MAX_IMPORT_BYTES", 10)
    path = tmp_path / "big.json"
    path.write_text('{"projects": []}' + " " * 20)
    with pytest.raises(DataFileError, match="too large"):
        import_file(svc.db, path)


def test_length_limits(svc, project):
    with pytest.raises(ValidationError):
        svc.create_task(project, "x" * 1000)
    with pytest.raises(ValidationError):
        svc.create_project("p" * 500)
    with pytest.raises(ValidationError):
        svc.create_task(project, "ok", "d" * 100_000)


def test_failed_export_leaves_existing_file_intact(svc, project, tmp_path, monkeypatch):
    out = tmp_path / "keep.json"
    out.write_text("precious")
    import json as _json
    monkeypatch.setattr(_json, "dumps", lambda *a, **k: (_ for _ in ()).throw(TypeError("boom")))
    with pytest.raises(Exception):
        export_json(svc.db, out)
    assert out.read_text() == "precious"


def test_failed_backup_leaves_existing_file_intact(svc, tmp_path):
    dest = tmp_path / "keep.db"
    dest.write_text("precious")
    backup_database(svc.db.path, dest)  # success replaces it with a valid db
    assert sqlite3.connect(dest).execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert not list(tmp_path.glob("*.tmp"))


def test_restore_rejects_wrong_columns_and_leaves_data(svc, project, tmp_path):
    svc.create_task(project, "keep me")
    bad = tmp_path / "bad.db"
    conn = sqlite3.connect(bad)
    conn.executescript("CREATE TABLE projects(x); CREATE TABLE tasks(y); CREATE TABLE task_tags(z);"
                       f"PRAGMA user_version = {SCHEMA_VERSION};")
    conn.close()
    with pytest.raises(DataFileError):
        restore_database(svc.db, bad)
    assert [t.title for t in svc.db.query_tasks()] == ["keep me"]


def test_restore_rejects_fk_violations_before_replacing(svc, project, tmp_path):
    svc.create_task(project, "keep me")
    bad = tmp_path / "fk.db"
    backup_database(svc.db.path, bad)
    conn = sqlite3.connect(bad)
    conn.execute("INSERT INTO tasks (project_id, title) VALUES (999, 'orphan')")
    conn.commit()
    conn.close()
    with pytest.raises(DataFileError, match="foreign"):
        restore_database(svc.db, bad)
    assert [t.title for t in svc.db.query_tasks()] == ["keep me"]


def test_restore_from_live_file_refused(svc):
    with pytest.raises(DataFileError):
        restore_database(svc.db, svc.db.path)


def test_restore_path_with_spaces_and_hash(svc, project, tmp_path):
    folder = tmp_path / "my backups #1"
    folder.mkdir()
    dest = folder / "b ackup.db"
    svc.create_task(project, "x")
    backup_database(svc.db.path, dest)
    restore_database(svc.db, dest)
    assert len(svc.db.query_tasks()) == 1
