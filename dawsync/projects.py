from pathlib import Path

from .common import atomic_json, new_id, read_json


class Projects:
    """Saved song profiles; version 1's single profile migrates without loss."""
    def __init__(self, path: Path):
        self.path = path
        data = read_json(path) if path.is_file() else {}
        if data.get("schema") == 2 and isinstance(data.get("projects"), dict) and data["projects"]:
            self.entries = data["projects"]
            self.active = data.get("active_project_id")
            if self.active not in self.entries:
                self.active = next(iter(self.entries))
        else:
            pid = data.get("project_id") or new_id()
            data["project_id"] = pid
            self.entries = {pid: data}
            self.active = pid

    @property
    def current(self):
        return self.entries[self.active]

    def add(self, source: Path, exchange=""):
        source = str(source.expanduser().resolve())
        for pid, entry in self.entries.items():
            if source in (entry.get("source"), entry.get("original_source")):
                self.active = pid
                return pid
        empty = next((pid for pid, e in self.entries.items() if not e.get("source")), None)
        pid = empty or new_id()
        self.entries[pid] = {"project_id": pid, "source": source, "original_source": source,
                             "project_name": Path(source).stem, "exchange": str(exchange),
                             "use_loop": True, "tail": 4}
        self.active = pid
        return pid

    def save(self):
        atomic_json(self.path, {"schema": 2, "active_project_id": self.active, "projects": self.entries})
