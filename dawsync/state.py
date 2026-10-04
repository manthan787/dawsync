from __future__ import annotations

from pathlib import Path
import sqlite3
import hashlib
import json

from .common import SyncError


class State:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS revisions (id TEXT PRIMARY KEY, project TEXT, parent TEXT, source TEXT, path TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS heads (project TEXT PRIMARY KEY, revision TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS imports (revision TEXT PRIMARY KEY, path TEXT)")
        if "digest" not in [row[1] for row in self.db.execute("PRAGMA table_info(revisions)")]:
            self.db.execute("ALTER TABLE revisions ADD COLUMN digest TEXT")
        self.db.commit()

    def head(self, project):
        row = self.db.execute("SELECT revision FROM heads WHERE project=?", (project,)).fetchone()
        return row[0] if row else None

    def register(self, m: dict, path: Path):
        row = self.db.execute("SELECT project,parent,source,digest FROM revisions WHERE id=?", (m["revision_id"],)).fetchone()
        signature = (m["project_id"], m["parent_revision"], m["source_daw"])
        digest = hashlib.sha256(json.dumps(m, sort_keys=True, allow_nan=False).encode()).hexdigest()
        if row and (row[:3] != signature or row[3] not in (None, digest)):
            raise SyncError("A revision ID was reused with different metadata.")
        self.db.execute("INSERT OR IGNORE INTO revisions VALUES (?,?,?,?,?,?)",
                        (m["revision_id"], *signature, str(path), digest))
        self.db.commit()

    def advance(self, m: dict, *, allow_branch: bool = False):
        current = self.head(m["project_id"])
        if current == m["revision_id"]:
            return
        if not allow_branch and m["parent_revision"] != current:
            raise SyncError("This revision is on another branch. Both versions are preserved; select it explicitly to use it.")
        self.db.execute("INSERT OR REPLACE INTO heads VALUES (?,?)", (m["project_id"], m["revision_id"]))
        self.db.commit()

    def imported(self, rid):
        row = self.db.execute("SELECT path FROM imports WHERE revision=?", (rid,)).fetchone()
        return Path(row[0]) if row else None

    def record_import(self, rid, path):
        self.db.execute("INSERT OR REPLACE INTO imports VALUES (?,?)", (rid, str(path)))
        self.db.commit()

    def close(self):
        self.db.close()
