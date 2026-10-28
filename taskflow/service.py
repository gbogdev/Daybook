"""Task and project logic: validation, filtering and dashboard statistics."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Sequence

from .db import Database
from .models import (
    PRIORITIES, STATUSES, Project, Task, ValidationError, clean_deadline, clean_name,
    clean_status, clean_title, normalize_tags, parse_priority,
)


@dataclass
class TaskFilter:
    project_id: int | None = None
    status: str | None = None
    priority: int | None = None
    tag: str | None = None
    search: str = ""
    sort: str = "position"
    descending: bool = False
    hide_done: bool = False
    include_archived: bool = False


@dataclass
class Stats:
    total: int = 0
    open: int = 0
    done: int = 0
    overdue: int = 0
    due_this_week: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    by_priority: dict[int, int] = field(default_factory=dict)
    projects: list[tuple[str, int, int]] = field(default_factory=list)  # name, total, done
    upcoming: list[Task] = field(default_factory=list)


class TaskService:
    def __init__(self, db: Database):
        self.db = db

    # -- projects ------------------------------------------------------
    def create_project(self, name: str, description: str = "") -> int:
        return self.db.add_project(clean_name(name), description.strip())

    def edit_project(self, project_id: int, name: str, description: str = "") -> None:
        self.db.update_project(project_id, clean_name(name), description.strip())

    def set_archived(self, project_id: int, archived: bool) -> None:
        self.db.set_project_archived(project_id, archived)

    def delete_project(self, project_id: int) -> None:
        self.db.delete_project(project_id)

    def projects(self, include_archived: bool = False) -> list[Project]:
        return self.db.list_projects(include_archived)

    # -- tasks ---------------------------------------------------------
    def create_task(self, project_id: int, title: str, description: str = "",
                    priority: int | str = 2, status: str = "todo",
                    deadline: str | None = None, tags: Sequence[str] | str = ()) -> int:
        return self.db.add_task(
            project_id, clean_title(title), description.strip(), parse_priority(priority),
            clean_status(status), clean_deadline(deadline), normalize_tags(tags),
        )

    def edit_task(self, task_id: int, project_id: int, title: str, description: str = "",
                  priority: int | str = 2, status: str = "todo",
                  deadline: str | None = None, tags: Sequence[str] | str = ()) -> None:
        self.db.update_task(
            task_id, project_id, clean_title(title), description.strip(),
            parse_priority(priority), clean_status(status), clean_deadline(deadline),
            normalize_tags(tags),
        )

    def set_done(self, task_id: int, done: bool) -> None:
        self.db.move_task(task_id, "done" if done else "todo")

    def move_task(self, task_id: int, status: str, before_id: int | None = None) -> None:
        self.db.move_task(task_id, clean_status(status), before_id)

    def delete_task(self, task_id: int) -> None:
        self.db.delete_task(task_id)

    def get_task(self, task_id: int) -> Task:
        return self.db.get_task(task_id)

    def tasks(self, flt: TaskFilter | None = None) -> list[Task]:
        f = flt or TaskFilter()
        if f.status is not None:
            clean_status(f.status)
        if f.priority is not None and f.priority not in PRIORITIES:
            raise ValidationError(f"Invalid priority filter {f.priority!r}.")
        return self.db.query_tasks(
            f.project_id, f.status, f.priority, f.tag, f.search, f.sort, f.descending,
            f.hide_done, f.include_archived,
        )

    def tags(self) -> list[str]:
        return self.db.list_tags()

    # -- dashboard -----------------------------------------------------
    def stats(self, project_id: int | None = None, today: date | None = None) -> Stats:
        today = today or date.today()
        week_end = (today + timedelta(days=7)).isoformat()
        tasks = self.db.query_tasks(project_id=project_id, sort="deadline")
        s = Stats(by_status=dict.fromkeys(STATUSES, 0), by_priority=dict.fromkeys(PRIORITIES, 0))
        per_project: dict[str, list[int]] = {}
        for t in tasks:
            s.total += 1
            s.by_status[t.status] += 1
            counts = per_project.setdefault(t.project_name, [0, 0])
            counts[0] += 1
            if t.done:
                s.done += 1
                counts[1] += 1
                continue
            s.open += 1
            s.by_priority[t.priority] += 1
            if t.deadline:
                if t.is_overdue(today):
                    s.overdue += 1
                elif t.deadline <= week_end:
                    s.due_this_week += 1
                s.upcoming.append(t)
        s.upcoming = s.upcoming[:8]  # already sorted by deadline
        s.projects = sorted((n, c[0], c[1]) for n, c in per_project.items())
        return s
