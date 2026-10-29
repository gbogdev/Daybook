"""JSON / CSV import and export. Imports are all-or-nothing (one transaction)."""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Callable

from .db import Database
from .models import (
    PRIORITIES, DataFileError, ValidationError, clean_deadline, clean_description, clean_name,
    clean_status, clean_title, normalize_tags, parse_priority,
)

JSON_VERSION = 1
MAX_IMPORT_BYTES = 50 * 1024 * 1024
CSV_FIELDS = ["project", "title", "description", "priority", "status", "deadline", "tags"]


@dataclass
class ImportResult:
    projects_created: int = 0
    tasks_created: int = 0


def _all_tasks(db: Database):
    return db.query_tasks(include_archived=True, sort="project")


def export_json(db: Database, path: str | Path) -> int:
    """Write every project (including empty / archived ones). Returns task count."""
    tasks = _all_tasks(db)
    by_project: dict[int, list[dict]] = {}
    for t in tasks:
        by_project.setdefault(t.project_id, []).append({
            "title": t.title, "description": t.description,
            "priority": PRIORITIES[t.priority].lower(), "status": t.status,
            "deadline": t.deadline, "tags": t.tags,
        })
    data = {
        "version": JSON_VERSION,
        "projects": [
            {"name": p.name, "description": p.description, "archived": p.archived,
             "tasks": by_project.get(p.id, [])}
            for p in db.list_projects(include_archived=True)
        ],
    }
    text = json.dumps(data, indent=2, ensure_ascii=False)
    _write_atomic(path, lambda fh: fh.write(text), newline=None)
    return len(tasks)


def export_csv(db: Database, path: str | Path) -> int:
    """One row per task (projects without tasks are not represented in CSV)."""
    tasks = _all_tasks(db)

    def write(fh) -> None:
        writer = csv.DictWriter(fh, CSV_FIELDS)
        writer.writeheader()
        for t in tasks:
            writer.writerow({
                "project": _safe_cell(t.project_name), "title": _safe_cell(t.title),
                "description": _safe_cell(t.description),
                "priority": PRIORITIES[t.priority].lower(), "status": t.status,
                "deadline": t.deadline or "", "tags": _safe_cell(";".join(t.tags)),
            })

    _write_atomic(path, write, newline="")
    return len(tasks)


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: str) -> str:
    """Stop spreadsheets from evaluating text as a formula (CSV injection)."""
    return "'" + value if value.startswith(_FORMULA_START) else value


def _unsafe_cell(value: str) -> str:
    return value[1:] if value.startswith("'") and value[1:].startswith(_FORMULA_START) else value


def _write_atomic(path: str | Path, write: Callable[[IO[str]], object], newline: str | None) -> None:
    """Write to a temp file and rename, so a failure never destroys an existing file."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", newline=newline, encoding="utf-8") as fh:
            write(fh)
        os.replace(tmp, path)
    except OSError as exc:
        raise DataFileError(f"Could not write {path}: {exc.strerror or exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)


def _clean_task(raw: dict, where: str) -> dict:
    def field(name: str, default: object) -> object:
        value = raw.get(name)
        return default if value is None or value == "" else value

    try:
        tags = field("tags", [])
        if isinstance(tags, str):
            tags = tags.replace(";", ",")
        elif not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ValidationError("tags must be text or a list of text.")
        if not isinstance(raw.get("title", ""), str) and raw.get("title") is not None:
            raise ValidationError("title must be text.")
        return {
            "title": clean_title(raw.get("title") or ""),
            "description": clean_description(raw.get("description") or ""),
            "priority": parse_priority(field("priority", 2)),
            "status": clean_status(field("status", "todo")),
            "deadline": clean_deadline(field("deadline", None)),
            "tags": normalize_tags(tags),
        }
    except ValidationError as exc:
        raise DataFileError(f"{where}: {exc}") from None


def _parse_json(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise DataFileError(f"{path.name} is not valid JSON ({exc.msg} at line {exc.lineno}).") from exc
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        raise DataFileError(f"{path.name} is not a Daybook export (missing 'projects' list).")
    if data.get("version", JSON_VERSION) > JSON_VERSION:
        raise DataFileError(f"{path.name} was exported by a newer Daybook version.")
    projects = []
    for i, p in enumerate(data["projects"], 1):
        if not isinstance(p, dict) or not isinstance(p.get("tasks", []), list):
            raise DataFileError(f"Project #{i}: expected an object with a 'tasks' list.")
        try:
            name = clean_name(p.get("name") or "")
        except ValidationError as exc:
            raise DataFileError(f"Project #{i}: {exc}") from None
        tasks = []
        for j, raw in enumerate(p.get("tasks", []), 1):
            if not isinstance(raw, dict):
                raise DataFileError(f"Project '{name}', task #{j}: expected an object.")
            tasks.append(_clean_task(raw, f"Project '{name}', task #{j}"))
        archived = p.get("archived", False)
        if not isinstance(archived, bool):
            raise DataFileError(f"Project '{name}': 'archived' must be true or false.")
        try:
            description = clean_description(p.get("description") or "")
        except ValidationError as exc:
            raise DataFileError(f"Project '{name}': {exc}") from None
        projects.append({"name": name, "description": description,
                         "archived": archived, "tasks": tasks})
    return projects


def _parse_csv(path: Path) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            missing = {"project", "title"} - set(reader.fieldnames or [])
            if missing:
                raise DataFileError(
                    f"{path.name} is missing required column(s): {', '.join(sorted(missing))}.")
            projects: dict[str, dict] = {}
            for row_no, row in enumerate(reader, 2):  # row 1 is the header
                row = {k: _unsafe_cell(v) if isinstance(v, str) and k in
                       ("project", "title", "description", "tags") else v for k, v in row.items()}
                try:
                    name = clean_name(row.get("project") or "")
                except ValidationError as exc:
                    raise DataFileError(f"Row {row_no}: {exc}") from None
                task = _clean_task(row, f"Row {row_no}")
                entry = projects.setdefault(
                    name.lower(), {"name": name, "description": "", "archived": False, "tasks": []})
                entry["tasks"].append(task)
            return list(projects.values())
    except UnicodeDecodeError:
        raise DataFileError(f"{path.name} is not UTF-8 text.") from None
    except csv.Error as exc:
        raise DataFileError(f"{path.name} is not valid CSV: {exc}") from exc


def import_file(db: Database, path: str | Path) -> ImportResult:
    """Import a .json or .csv file, adding to existing data (tasks are never de-duplicated)."""
    path = Path(path)
    parse = {".json": _parse_json, ".csv": _parse_csv}.get(path.suffix.lower())
    if parse is None:
        raise DataFileError("Unsupported file type; choose a .json or .csv file.")
    try:
        if path.stat().st_size > MAX_IMPORT_BYTES:
            raise DataFileError(f"{path.name} is too large to import (limit "
                                f"{MAX_IMPORT_BYTES // (1024 * 1024)} MB).")
        projects = parse(path)
    except OSError as exc:
        raise DataFileError(f"Could not read {path}: {exc.strerror or exc}") from exc

    result = ImportResult()
    with db.transaction():
        for p in projects:
            existing = db.find_project_by_name(p["name"])
            if existing:
                project_id = existing.id
            else:
                project_id = db.add_project(p["name"], p["description"], p["archived"])
                result.projects_created += 1
            for t in p["tasks"]:
                db.add_task(project_id, **t)
                result.tasks_created += 1
    return result
