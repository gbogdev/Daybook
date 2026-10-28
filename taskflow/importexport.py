"""JSON / CSV import and export. Imports are all-or-nothing (one transaction)."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .db import Database
from .models import (
    PRIORITIES, DataFileError, ValidationError, clean_deadline, clean_name, clean_status,
    clean_title, normalize_tags, parse_priority,
)

JSON_VERSION = 1
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
    try:
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        raise DataFileError(f"Could not write {path}: {exc.strerror or exc}") from exc
    return len(tasks)


def export_csv(db: Database, path: str | Path) -> int:
    """One row per task (projects without tasks are not represented in CSV)."""
    tasks = _all_tasks(db)
    try:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, CSV_FIELDS)
            writer.writeheader()
            for t in tasks:
                writer.writerow({
                    "project": t.project_name, "title": t.title, "description": t.description,
                    "priority": PRIORITIES[t.priority].lower(), "status": t.status,
                    "deadline": t.deadline or "", "tags": ";".join(t.tags),
                })
    except OSError as exc:
        raise DataFileError(f"Could not write {path}: {exc.strerror or exc}") from exc
    return len(tasks)


def _clean_task(raw: dict, where: str) -> dict:
    try:
        tags = raw.get("tags") or []
        if isinstance(tags, str):
            tags = tags.replace(";", ",")
        return {
            "title": clean_title(raw.get("title") or ""),
            "description": str(raw.get("description") or "").strip(),
            "priority": parse_priority(raw.get("priority") or 2),
            "status": clean_status(raw.get("status") or "todo"),
            "deadline": clean_deadline(raw.get("deadline")),
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
        raise DataFileError(f"{path.name} is not a TaskFlow export (missing 'projects' list).")
    if data.get("version", JSON_VERSION) > JSON_VERSION:
        raise DataFileError(f"{path.name} was exported by a newer TaskFlow version.")
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
        projects.append({"name": name, "description": str(p.get("description") or ""),
                         "archived": bool(p.get("archived", False)), "tasks": tasks})
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
