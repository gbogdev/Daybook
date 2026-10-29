"""Plain data types, validation helpers and exceptions shared by all layers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

STATUSES = ("todo", "doing", "done")
STATUS_LABELS = {"todo": "To do", "doing": "In progress", "done": "Done"}
PRIORITIES = {1: "Low", 2: "Medium", 3: "High"}
MAX_TAG_LENGTH = 40
MAX_NAME_LENGTH = 100
MAX_TITLE_LENGTH = 300
MAX_DESCRIPTION_LENGTH = 20_000


class DaybookError(Exception):
    """Base class for errors that are safe to show to the user."""


class ValidationError(DaybookError):
    """Input rejected before it reaches the database."""


class NotFoundError(DaybookError):
    """A referenced project or task does not exist."""


class DataFileError(DaybookError):
    """Import, export, backup or restore failed."""


@dataclass
class Project:
    id: int
    name: str
    description: str = ""
    archived: bool = False
    created_at: str = ""
    total_tasks: int = 0
    open_tasks: int = 0


@dataclass
class Task:
    id: int
    project_id: int
    title: str
    description: str = ""
    priority: int = 2
    status: str = "todo"
    deadline: str | None = None
    tags: list[str] = field(default_factory=list)
    position: int = 0
    created_at: str = ""
    completed_at: str | None = None
    project_name: str = ""

    @property
    def done(self) -> bool:
        return self.status == "done"

    def is_overdue(self, today: date | None = None) -> bool:
        if self.done or not self.deadline:
            return False
        return self.deadline < (today or date.today()).isoformat()


def normalize_tags(raw: Iterable[str] | str | None) -> list[str]:
    """Lower-case, trim, de-duplicate (order preserved). Accepts 'a, b' or a list."""
    if raw is None:
        return []
    items = raw.split(",") if isinstance(raw, str) else list(raw)
    seen: dict[str, None] = {}
    for item in items:
        tag = " ".join(str(item).split()).lower()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise ValidationError(f"Tag '{tag[:20]}...' is longer than {MAX_TAG_LENGTH} characters.")
        if "," in tag or not tag.isprintable():
            raise ValidationError("Tags cannot contain commas or control characters.")
        seen[tag] = None
    return list(seen)


def parse_priority(value: object) -> int:
    """Accept 1-3 or 'low' / 'medium' / 'high' (case-insensitive)."""
    if isinstance(value, str):
        text = value.strip().lower()
        for number, label in PRIORITIES.items():
            if text in (label.lower(), str(number)):
                return number
    elif isinstance(value, int) and not isinstance(value, bool) and value in PRIORITIES:
        return value
    raise ValidationError(f"Invalid priority {value!r}; use Low, Medium or High.")


def clean_deadline(value: str | None) -> str | None:
    """Return an ISO date (YYYY-MM-DD) or None for an empty value."""
    if value is None or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise ValidationError(f"Invalid deadline {value!r}; expected YYYY-MM-DD.") from None


def clean_status(value: str) -> str:
    text = str(value).strip().lower()
    if text not in STATUSES:
        raise ValidationError(f"Invalid status {value!r}; use one of {', '.join(STATUSES)}.")
    return text


def clean_title(value: str) -> str:
    title = " ".join(str(value).split())
    if not title:
        raise ValidationError("A task title is required.")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValidationError(f"Task titles are limited to {MAX_TITLE_LENGTH} characters.")
    return title


def clean_description(value: str) -> str:
    text = str(value or "").strip()
    if len(text) > MAX_DESCRIPTION_LENGTH:
        raise ValidationError(f"Descriptions are limited to {MAX_DESCRIPTION_LENGTH} characters.")
    return text


def clean_name(value: str) -> str:
    name = " ".join(str(value).split())
    if not name:
        raise ValidationError("A project name is required.")
    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(f"Project names are limited to {MAX_NAME_LENGTH} characters.")
    return name
