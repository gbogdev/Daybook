import json

from taskflow.settings import DEFAULT_SHORTCUTS, Settings


def test_defaults_when_missing(tmp_path):
    s = Settings(tmp_path / "s.json")
    assert s["theme"] == "Dark" and s.load_error is None


def test_persists_between_sessions(tmp_path):
    path = tmp_path / "sub" / "s.json"
    s = Settings(path)
    s["theme"] = "Light"
    s["shortcuts"]["new_task"] = "Ctrl+T"
    s.save()
    again = Settings(path)
    assert again["theme"] == "Light"
    assert again["shortcuts"]["new_task"] == "Ctrl+T"
    assert again["shortcuts"]["search"] == DEFAULT_SHORTCUTS["search"]


def test_corrupt_file_falls_back(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{oops", encoding="utf-8")
    s = Settings(path)
    assert s["theme"] == "Dark" and "could not be read" in s.load_error


def test_wrong_types_ignored_and_defaults_not_mutated(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"theme": 5, "hide_done": True, "shortcuts": {"new_task": 3}}))
    s = Settings(path)
    assert s["theme"] == "Dark" and s["hide_done"] is True
    assert s["shortcuts"]["new_task"] == DEFAULT_SHORTCUTS["new_task"]
    s["shortcuts"]["new_task"] = "X"
    assert DEFAULT_SHORTCUTS["new_task"] == "Ctrl+N"
