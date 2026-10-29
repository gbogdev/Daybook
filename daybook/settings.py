"""Persistent user settings stored as JSON."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_SHORTCUTS = {
    "new_task": "Ctrl+N",
    "new_project": "Ctrl+Shift+N",
    "edit_task": "Ctrl+E",
    "delete_task": "Ctrl+D",
    "search": "Ctrl+F",
    "refresh": "F5",
    "view_board": "Ctrl+1",
    "view_list": "Ctrl+2",
    "view_dashboard": "Ctrl+3",
    "import": "Ctrl+I",
    "export": "Ctrl+Shift+E",
    "backup": "Ctrl+B",
    "restore": "Ctrl+Shift+R",
    "preferences": "Ctrl+,",
}

DEFAULTS: dict[str, Any] = {
    "theme": "Dark",
    "view": "board",
    "hide_done": False,
    "show_archived": False,
    "geometry": "",
    "shortcuts": DEFAULT_SHORTCUTS,
}


def default_data_dir() -> Path:
    override = os.environ.get("DAYBOOK_DATA_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home())) / "Daybook"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "daybook"


class Settings:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {k: (dict(v) if isinstance(v, dict) else v)
                                     for k, v in DEFAULTS.items()}
        self.load_error: str | None = None
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(stored, dict):
                raise ValueError("top level is not an object")
        except (OSError, ValueError) as exc:
            self.load_error = f"Settings file {self.path} could not be read ({exc}); defaults are in use."
            return
        for key, default in DEFAULTS.items():
            value = stored.get(key, default)
            if type(value) is not type(default):
                continue  # ignore wrongly typed values
            if key == "shortcuts":
                value = {**default, **{k: v for k, v in value.items() if isinstance(v, str)}}
            self.data[key] = value

    def save(self) -> None:
        """Atomic write; raises OSError on failure."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value
