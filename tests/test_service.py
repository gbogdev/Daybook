from datetime import date, timedelta

import pytest

from taskflow.models import ValidationError, normalize_tags
from taskflow.service import TaskFilter


def test_create_task_normalizes_input(svc, project):
    tid = svc.create_task(project, "  Write   report ", "  notes ", "high", tags="Work, work , Urgent,")
    t = svc.get_task(tid)
    assert (t.title, t.description, t.priority) == ("Write report", "notes", 3)
    assert t.tags == ["urgent", "work"]  # de-duplicated, lower-cased, sorted by query


@pytest.mark.parametrize("kwargs", [
    {"title": "   "},
    {"title": "x", "priority": 7},
    {"title": "x", "priority": "urgent"},
    {"title": "x", "status": "blocked"},
    {"title": "x", "deadline": "2026-13-40"},
    {"title": "x", "deadline": "tomorrow"},
])
def test_invalid_task_rejected(svc, project, kwargs):
    with pytest.raises(ValidationError):
        svc.create_task(project, **kwargs)
    assert svc.tasks() == []


def test_blank_project_name_rejected(svc):
    with pytest.raises(ValidationError):
        svc.create_project("  ")


def test_tag_rules():
    assert normalize_tags(None) == []
    assert normalize_tags(["A", "a", " b "]) == ["a", "b"]
    with pytest.raises(ValidationError):
        normalize_tags(["x" * 41])


def test_edit_task_and_change_project(svc, project):
    other = svc.create_project("Home")
    tid = svc.create_task(project, "a", tags="x")
    svc.edit_task(tid, other, "b", "d", 1, "doing", "2026-01-02", "y")
    t = svc.get_task(tid)
    assert (t.project_id, t.title, t.priority, t.status, t.deadline, t.tags) == (
        other, "b", 1, "doing", "2026-01-02", ["y"])


def test_set_done_toggle(svc, project):
    tid = svc.create_task(project, "a")
    svc.set_done(tid, True)
    assert svc.get_task(tid).done
    svc.set_done(tid, False)
    assert svc.get_task(tid).status == "todo"


def test_filter_sort_search(svc, project):
    svc.create_task(project, "Alpha", priority=1, deadline="2026-03-01", tags="a")
    svc.create_task(project, "beta", "mentions alpha", priority=3, tags="b")
    svc.create_task(project, "Gamma", priority=2, deadline="2026-01-01", status="done")
    assert [t.title for t in svc.tasks(TaskFilter(search="alpha"))] == ["Alpha", "beta"]
    assert [t.title for t in svc.tasks(TaskFilter(priority=3))] == ["beta"]
    assert [t.title for t in svc.tasks(TaskFilter(tag="a"))] == ["Alpha"]
    assert [t.title for t in svc.tasks(TaskFilter(hide_done=True, sort="title"))] == ["Alpha", "beta"]
    by_deadline = [t.title for t in svc.tasks(TaskFilter(sort="deadline"))]
    assert by_deadline == ["Gamma", "Alpha", "beta"]  # no-deadline tasks last
    assert [t.title for t in svc.tasks(TaskFilter(sort="priority", descending=True))][0] == "beta"


def test_invalid_filter_values(svc):
    with pytest.raises(ValidationError):
        svc.tasks(TaskFilter(status="nope"))
    with pytest.raises(ValidationError):
        svc.tasks(TaskFilter(priority=9))


def test_stats(svc, project):
    today = date(2026, 6, 15)
    svc.create_task(project, "late", deadline="2026-06-01")
    svc.create_task(project, "soon", deadline=(today + timedelta(days=3)).isoformat())
    svc.create_task(project, "far", deadline="2026-12-31", priority=3)
    svc.create_task(project, "finished", deadline="2026-01-01", status="done")
    s = svc.stats(today=today)
    assert (s.total, s.open, s.done, s.overdue, s.due_this_week) == (4, 3, 1, 1, 1)
    assert s.by_status == {"todo": 3, "doing": 0, "done": 1}
    assert s.by_priority[3] == 1
    assert s.projects == [("Work", 4, 1)]
    assert [t.title for t in s.upcoming] == ["late", "soon", "far"]


def test_overdue_ignores_done(svc, project):
    tid = svc.create_task(project, "x", deadline="2000-01-01", status="done")
    assert not svc.get_task(tid).is_overdue()
