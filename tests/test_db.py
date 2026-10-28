import sqlite3

import pytest

from taskflow.db import MIGRATIONS, SCHEMA_VERSION, Database
from taskflow.models import NotFoundError, ValidationError


def test_new_database_is_migrated(tmp_path):
    with Database(tmp_path / "a.db") as db:
        assert db.created
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    with Database(tmp_path / "a.db") as db:  # reopening is a no-op
        assert not db.created


def test_migrates_from_older_version(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    for statement in MIGRATIONS[0].split(";"):
        conn.execute(statement)
    conn.execute("INSERT INTO projects (name) VALUES ('Legacy')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    with Database(path) as db:
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert [p.name for p in db.list_projects()] == ["Legacy"]
        names = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_task_tags_tag" in names


def test_newer_schema_is_rejected(tmp_path):
    path = tmp_path / "new.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(ValidationError, match="newer"):
        Database(path)


def test_foreign_keys_enforced(db):
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(NotFoundError):
        db.add_task(999, "orphan")


def test_delete_project_cascades(db):
    pid = db.add_project("P")
    tid = db.add_task(pid, "T", tags=["a"])
    db.delete_project(pid)
    assert db.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM task_tags WHERE task_id=?", (tid,)).fetchone()[0] == 0


def test_duplicate_project_name_case_insensitive(db):
    db.add_project("Alpha")
    with pytest.raises(ValidationError, match="already exists"):
        db.add_project("alpha")


def test_transaction_rolls_back(db):
    pid = db.add_project("P")
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.add_task(pid, "inside")
            raise RuntimeError("boom")
    assert db.query_tasks() == []


def test_nested_transaction_joins_outer(db):
    pid = db.add_project("P")
    with pytest.raises(RuntimeError):
        with db.transaction():
            with db.transaction():
                db.add_task(pid, "inner")
            raise RuntimeError
    assert db.query_tasks() == []


def test_check_constraints(db):
    pid = db.add_project("P")
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute("INSERT INTO tasks (project_id, title, priority) VALUES (?, 'x', 9)", (pid,))
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute("INSERT INTO tasks (project_id, title) VALUES (?, '   ')", (pid,))


def test_move_task_orders_and_completion(db):
    pid = db.add_project("P")
    a, b, c = (db.add_task(pid, n) for n in "abc")
    db.move_task(c, "todo", before_id=a)
    assert [t.title for t in db.query_tasks(status="todo")] == ["c", "a", "b"]
    db.move_task(a, "done")
    done = db.get_task(a)
    assert done.status == "done" and done.completed_at
    db.move_task(a, "doing")
    assert db.get_task(a).completed_at is None


def test_move_unknown_task(db):
    with pytest.raises(NotFoundError):
        db.move_task(123, "done")


def test_search_escapes_wildcards(db):
    pid = db.add_project("P")
    db.add_task(pid, "100% done")
    db.add_task(pid, "other")
    assert [t.title for t in db.query_tasks(search="%")] == ["100% done"]
    assert [t.title for t in db.query_tasks(search="_")] == []


def test_unknown_sort_rejected(db):
    with pytest.raises(ValidationError):
        db.query_tasks(sort="title; DROP TABLE tasks")


def test_archived_projects_hidden_unless_selected(db):
    pid = db.add_project("P")
    db.add_task(pid, "t")
    db.set_project_archived(pid, True)
    assert db.query_tasks() == []
    assert len(db.query_tasks(include_archived=True)) == 1
    assert len(db.query_tasks(project_id=pid)) == 1
