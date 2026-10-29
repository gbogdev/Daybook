"""SQLite access: connection, migrations and CRUD. No UI imports here."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from .models import NotFoundError, Project, Task, ValidationError

# Each entry upgrades the schema by one version (PRAGMA user_version).
MIGRATIONS: list[str] = [
    """
    CREATE TABLE projects (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (length(trim(name)) > 0),
        description TEXT NOT NULL DEFAULT '',
        archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        title TEXT NOT NULL CHECK (length(trim(title)) > 0),
        description TEXT NOT NULL DEFAULT '',
        priority INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
        status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'doing', 'done')),
        deadline TEXT,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        completed_at TEXT
    );
    CREATE TABLE task_tags (
        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        tag TEXT NOT NULL,
        PRIMARY KEY (task_id, tag)
    )
    """,
    """
    CREATE INDEX idx_tasks_project ON tasks(project_id);
    CREATE INDEX idx_tasks_status_position ON tasks(status, position);
    CREATE INDEX idx_task_tags_tag ON task_tags(tag)
    """,
]
SCHEMA_VERSION = len(MIGRATIONS)

# {d} is replaced with ASC / DESC. Keys are the only accepted sort names.
SORTS = {
    "position": "t.position {d}",
    "title": "t.title COLLATE NOCASE {d}",
    "priority": "t.priority {d}",
    "deadline": "t.deadline IS NULL, t.deadline {d}",
    "created": "t.created_at {d}",
    "status": "CASE t.status WHEN 'todo' THEN 0 WHEN 'doing' THEN 1 ELSE 2 END {d}",
    "project": "p.name COLLATE NOCASE {d}",
}

_TASK_SELECT = """
    SELECT t.*, p.name AS project_name,
           (SELECT group_concat(tag, char(31))
              FROM (SELECT tag FROM task_tags WHERE task_id = t.id ORDER BY tag)) AS tags
    FROM tasks t JOIN projects p ON p.id = t.project_id
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"], project_id=row["project_id"], title=row["title"],
        description=row["description"], priority=row["priority"], status=row["status"],
        deadline=row["deadline"], tags=row["tags"].split("\x1f") if row["tags"] else [],
        position=row["position"], created_at=row["created_at"],
        completed_at=row["completed_at"], project_name=row["project_name"],
    )


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: transactions are explicit (see transaction()).
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._depth = 0
        try:
            self.created = self.migrate()  # True only if this call built a brand-new database
        except BaseException:
            self.conn.close()  # don't leave the file locked on failure
            raise

    # -- lifecycle -----------------------------------------------------
    def migrate(self) -> bool:
        """Apply pending migrations; return True if the schema was empty."""
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValidationError(
                f"This database was created by a newer Daybook (schema {version}, "
                f"this version supports {SCHEMA_VERSION})."
            )
        was_empty = version == 0
        for number in range(version, SCHEMA_VERSION):
            with self.transaction():
                for statement in MIGRATIONS[number].split(";"):
                    if statement.strip():
                        self.conn.execute(statement)
                self.conn.execute(f"PRAGMA user_version = {number + 1}")
        return was_empty

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Atomic block; nested use joins the outer transaction."""
        if self._depth:
            yield
            return
        self.conn.execute("BEGIN")
        self._depth = 1
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        finally:
            self._depth = 0

    # -- projects ------------------------------------------------------
    def add_project(self, name: str, description: str = "", archived: bool = False) -> int:
        try:
            with self.transaction():
                cur = self.conn.execute(
                    "INSERT INTO projects (name, description, archived) VALUES (?, ?, ?)",
                    (name, description, int(archived)),
                )
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            raise ValidationError(f"A project named '{name}' already exists.") from None

    def update_project(self, project_id: int, name: str, description: str) -> None:
        try:
            with self.transaction():
                cur = self.conn.execute(
                    "UPDATE projects SET name = ?, description = ? WHERE id = ?",
                    (name, description, project_id),
                )
        except sqlite3.IntegrityError:
            raise ValidationError(f"A project named '{name}' already exists.") from None
        if cur.rowcount == 0:
            raise NotFoundError("That project no longer exists.")

    def set_project_archived(self, project_id: int, archived: bool) -> None:
        with self.transaction():
            cur = self.conn.execute(
                "UPDATE projects SET archived = ? WHERE id = ?", (int(archived), project_id)
            )
        if cur.rowcount == 0:
            raise NotFoundError("That project no longer exists.")

    def delete_project(self, project_id: int) -> None:
        """Deletes the project and (via ON DELETE CASCADE) its tasks and tags."""
        with self.transaction():
            cur = self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if cur.rowcount == 0:
            raise NotFoundError("That project no longer exists.")

    def get_project(self, project_id: int) -> Project:
        for project in self.list_projects(include_archived=True):
            if project.id == project_id:
                return project
        raise NotFoundError("That project no longer exists.")

    def find_project_by_name(self, name: str) -> Project | None:
        for project in self.list_projects(include_archived=True):
            if project.name.lower() == name.lower():
                return project
        return None

    def list_projects(self, include_archived: bool = False) -> list[Project]:
        rows = self.conn.execute(
            """
            SELECT p.*, COUNT(t.id) AS total_tasks,
                   COALESCE(SUM(t.status <> 'done'), 0) AS open_tasks
            FROM projects p LEFT JOIN tasks t ON t.project_id = p.id
            WHERE (? OR p.archived = 0)
            GROUP BY p.id ORDER BY p.archived, p.name COLLATE NOCASE
            """,
            (int(include_archived),),
        ).fetchall()
        return [
            Project(r["id"], r["name"], r["description"], bool(r["archived"]),
                    r["created_at"], r["total_tasks"], r["open_tasks"])
            for r in rows
        ]

    # -- tasks ---------------------------------------------------------
    def _set_tags(self, task_id: int, tags: Sequence[str]) -> None:
        self.conn.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
        self.conn.executemany(
            "INSERT INTO task_tags (task_id, tag) VALUES (?, ?)", [(task_id, t) for t in tags]
        )

    def _next_position(self, status: str) -> int:
        return self.conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM tasks WHERE status = ?", (status,)
        ).fetchone()[0]

    def add_task(self, project_id: int, title: str, description: str = "", priority: int = 2,
                 status: str = "todo", deadline: str | None = None,
                 tags: Sequence[str] = ()) -> int:
        try:
            with self.transaction():
                cur = self.conn.execute(
                    """INSERT INTO tasks (project_id, title, description, priority, status,
                                          deadline, position, completed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (project_id, title, description, priority, status, deadline,
                     self._next_position(status), _now() if status == "done" else None),
                )
                task_id = int(cur.lastrowid)
                self._set_tags(task_id, tags)
                return task_id
        except sqlite3.IntegrityError as exc:
            if "FOREIGN KEY" in str(exc):
                raise NotFoundError("That project no longer exists.") from None
            raise ValidationError(f"Task rejected by the database: {exc}") from None

    def update_task(self, task_id: int, project_id: int, title: str, description: str,
                    priority: int, status: str, deadline: str | None,
                    tags: Sequence[str]) -> None:
        try:
            with self.transaction():
                old = self.conn.execute(
                    "SELECT status, completed_at FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()
                if old is None:
                    raise NotFoundError("That task no longer exists.")
                changed = old["status"] != status
                completed_at = (
                    None if status != "done" else (_now() if changed else old["completed_at"])
                )
                position_sql = ", position = ?" if changed else ""
                params: list[object] = [project_id, title, description, priority, status,
                                        deadline, completed_at]
                if changed:
                    params.append(self._next_position(status))
                params.append(task_id)
                self.conn.execute(
                    f"""UPDATE tasks SET project_id = ?, title = ?, description = ?,
                        priority = ?, status = ?, deadline = ?, completed_at = ?{position_sql}
                        WHERE id = ?""",
                    params,
                )
                self._set_tags(task_id, tags)
        except sqlite3.IntegrityError as exc:
            if "FOREIGN KEY" in str(exc):
                raise NotFoundError("That project no longer exists.") from None
            raise ValidationError(f"Task rejected by the database: {exc}") from None

    def move_task(self, task_id: int, status: str, before_id: int | None = None) -> None:
        """Move a task to a status column, placing it before `before_id` (or last)."""
        with self.transaction():
            old = self.conn.execute(
                "SELECT status, completed_at FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if old is None:
                raise NotFoundError("That task no longer exists.")
            ids = [r[0] for r in self.conn.execute(
                "SELECT id FROM tasks WHERE status = ? AND id <> ? ORDER BY position, id",
                (status, task_id))]
            ids.insert(ids.index(before_id) if before_id in ids else len(ids), task_id)
            completed_at = None
            if status == "done":
                completed_at = old["completed_at"] if old["status"] == "done" else _now()
            self.conn.execute(
                "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed_at, task_id),
            )
            self.conn.executemany(
                "UPDATE tasks SET position = ? WHERE id = ?",
                [(pos, tid) for pos, tid in enumerate(ids)],
            )

    def delete_task(self, task_id: int) -> None:
        with self.transaction():
            cur = self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cur.rowcount == 0:
            raise NotFoundError("That task no longer exists.")

    def get_task(self, task_id: int) -> Task:
        row = self.conn.execute(_TASK_SELECT + " WHERE t.id = ?", (task_id,)).fetchone()
        if row is None:
            raise NotFoundError("That task no longer exists.")
        return _task(row)

    def query_tasks(self, project_id: int | None = None, status: str | None = None,
                    priority: int | None = None, tag: str | None = None, search: str = "",
                    sort: str = "position", descending: bool = False,
                    hide_done: bool = False, include_archived: bool = False) -> list[Task]:
        if sort not in SORTS:
            raise ValidationError(f"Unknown sort key {sort!r}.")
        where: list[str] = []
        params: list[object] = []
        if project_id is not None:
            where.append("t.project_id = ?")
            params.append(project_id)
        elif not include_archived:
            where.append("p.archived = 0")
        if status:
            where.append("t.status = ?")
            params.append(status)
        if hide_done:
            where.append("t.status <> 'done'")
        if priority:
            where.append("t.priority = ?")
            params.append(priority)
        if tag:
            where.append("EXISTS (SELECT 1 FROM task_tags g WHERE g.task_id = t.id AND g.tag = ?)")
            params.append(tag)
        if search.strip():
            pattern = _like(search.strip())
            where.append(
                "(t.title LIKE ? ESCAPE '\\' OR t.description LIKE ? ESCAPE '\\' OR EXISTS "
                "(SELECT 1 FROM task_tags g WHERE g.task_id = t.id AND g.tag LIKE ? ESCAPE '\\'))"
            )
            params += [pattern, pattern, pattern]
        sql = _TASK_SELECT
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY " + SORTS[sort].format(d="DESC" if descending else "ASC") + ", t.id"
        return [_task(r) for r in self.conn.execute(sql, params)]

    def list_tags(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT DISTINCT tag FROM task_tags ORDER BY tag")]
