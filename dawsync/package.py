from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import tempfile
import sys

from .common import SyncError, atomic_json, finite, inside, new_id, read_json, safe_name, sha256, wav_info
from .rpp import write_project


SCHEMA = 1
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise SyncError(f"Invalid {label}.")
    return value


def validate(folder: Path) -> dict:
    folder = folder.resolve()
    m = read_json(folder / "manifest.json")
    if m.get("schema") != SCHEMA or m.get("kind") != "dawsync-revision":
        raise SyncError("Unsupported DAWSync manifest version.")
    for k in ("project_id", "revision_id"):
        identifier(m.get(k), k)
    if m.get("parent_revision") is not None:
        identifier(m["parent_revision"], "parent revision")
        if m["parent_revision"] == m["revision_id"]:
            raise SyncError("A revision cannot be its own parent.")
    if m.get("source_daw") not in ("ableton", "reaper"):
        raise SyncError("Invalid source DAW.")
    tempo = m.get("tempo")
    if not isinstance(tempo, dict) or not 20 <= finite(tempo.get("bpm"), "tempo", 1) <= 999:
        raise SyncError("Invalid tempo.")
    for key in ("numerator", "denominator"):
        value = tempo.get(key)
        if type(value) is not int or not 1 <= value <= 32:
            raise SyncError("Invalid time signature.")
    if tempo["denominator"] not in (1, 2, 4, 8, 16, 32):
        raise SyncError("Invalid time signature denominator.")
    rate = m.get("sample_rate")
    if type(rate) is not int or not 8000 <= rate <= 192000:
        raise SyncError("Invalid project sample rate.")
    tracks, files = m.get("tracks"), m.get("files")
    if not isinstance(tracks, list) or not tracks or not isinstance(files, dict):
        raise SyncError("The package has no tracks or file inventory.")
    if len(tracks) > 1000 or len(files) > 5000:
        raise SyncError("Package inventory exceeds supported limits.")
    seen_paths, seen_ids = set(), set()
    for relative, entry in files.items():
        path = inside(folder, relative)
        folded = relative.casefold()
        if folded in seen_paths:
            raise SyncError("Case-insensitive filename collision.")
        seen_paths.add(folded)
        if not isinstance(entry, dict) or type(entry.get("size")) is not int or entry["size"] < 0:
            raise SyncError(f"Invalid file inventory: {relative}")
        if not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("sha256", ""))):
            raise SyncError(f"Invalid checksum: {relative}")
        if not path.is_file() or path.stat().st_size != entry["size"] or sha256(path) != entry["sha256"]:
            raise SyncError(f"Waiting for a complete, unmodified file: {relative}")
    frames = None
    stem_count = 0
    for t in tracks:
        if not isinstance(t, dict):
            raise SyncError("Invalid track entry.")
        tid = identifier(t.get("id"), "track ID")
        if tid in seen_ids:
            raise SyncError("Duplicate track ID.")
        seen_ids.add(tid)
        if not isinstance(t.get("name"), str) or len(t["name"]) > 4096:
            raise SyncError("Invalid track name.")
        if t.get("role") not in ("stem", "reference"):
            raise SyncError("Invalid track role.")
        stem_count += t["role"] == "stem"
        if t.get("file") not in files:
            raise SyncError("Track media is absent from the inventory.")
        info = wav_info(inside(folder, t["file"]))
        if info["sample_rate"] != rate or type(t.get("frames")) is not int or t["frames"] != info["frames"]:
            raise SyncError("Track sample rate or frame count does not match its manifest.")
        if abs(finite(t.get("duration"), "duration") - info["duration"]) > 0.5 / rate:
            raise SyncError("Track duration does not match its audio.")
        if finite(t.get("start_seconds", 0), "track start") != 0:
            raise SyncError("This version requires tracks aligned to project time zero.")
        if frames is not None and frames != info["frames"]:
            raise SyncError("Rendered tracks must have identical lengths.")
        frames = info["frames"]
    if not stem_count:
        raise SyncError("A revision needs at least one audible stem.")
    if finite(m.get("content_end_seconds", tracks[0]["duration"]), "content end") > tracks[0]["duration"]:
        raise SyncError("The song end exceeds the rendered audio.")
    for marker in m.get("markers", []):
        if not isinstance(marker, dict) or type(marker.get("index")) is not int or not isinstance(marker.get("name"), str):
            raise SyncError("Invalid marker.")
        finite(marker.get("seconds"), "marker position")
    if not isinstance(m.get("project_name"), str):
        raise SyncError("Invalid project name.")
    for key in ("reaper_project",):
        if m.get(key) not in files:
            raise SyncError("The generated project is missing from the inventory.")
    return m


def inventory(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): {"size": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "manifest.json"}


def create_revision(destination: Path, *, project_id: str, project_name: str, sources: list[dict],
                    bpm: float = 120, numerator: int = 4, denominator: int = 4,
                    source_daw: str = "ableton", parent_revision: str | None = None,
                    markers: list | None = None, original_set_hash: str | None = None,
                    content_end_seconds: float | None = None) -> Path:
    """Stage locally and publish once. The manifest validates arrival on Drive."""
    identifier(project_id, "project ID")
    rid = new_id()
    destination = destination.expanduser().resolve()
    revisions = destination / project_id / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    final = revisions / rid
    with tempfile.TemporaryDirectory(prefix="dawsync-") as temporary:
        stage = Path(temporary)
        (stage / "audio").mkdir()
        tracks = []
        for item in sources:
            source = Path(item["path"])
            tid = identifier(item["id"], "track ID")
            name = item["name"]
            filename = "audio/" + tid + "_" + safe_name(name) + ".wav"
            target = inside(stage, filename)
            if target.exists():
                raise SyncError("Duplicate source track ID.")
            shutil.copyfile(source, target)
            info = wav_info(target)
            tracks.append({"id": tid, "name": name, "role": item.get("role", "stem"), "file": filename,
                           "frames": info["frames"], "duration": info["duration"], "start_seconds": 0,
                           "channels": info["channels"]})
        if not tracks:
            raise SyncError("No audio tracks were selected.")
        m = {"schema": SCHEMA, "kind": "dawsync-revision", "project_id": project_id,
             "project_name": project_name, "revision_id": rid, "parent_revision": parent_revision,
             "source_daw": source_daw, "created_at": datetime.now(timezone.utc).isoformat(),
             "sample_rate": wav_info(inside(stage, tracks[0]["file"]))["sample_rate"],
             "tempo": {"bpm": bpm, "numerator": numerator, "denominator": denominator},
             "tracks": tracks, "markers": markers or [], "reaper_project": "session.rpp",
             "original_set_hash": original_set_hash,
             "content_end_seconds": content_end_seconds if content_end_seconds is not None else tracks[0]["duration"],
             "render_policy": "top-level post-fader buses and separate returns; master is a muted reference"}
        write_project(stage / "session.rpp", m)
        for filename in ("DAWSync.lua", "codec.lua"):
            helper = ROOT / "reaper" / filename
            if helper.exists():
                shutil.copyfile(helper, stage / filename)
        m["files"] = inventory(stage)
        atomic_json(stage / "manifest.json", m)
        validate(stage)
        # Never overwrite an existing revision. Copy manifest last; arrivals
        # may still be reordered by Drive, so consumers verify all hashes.
        final.mkdir(exist_ok=False)
        for p in stage.rglob("*"):
            if p.is_file() and p.name != "manifest.json":
                target = final / p.relative_to(stage)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, target)
        atomic_json(final / "manifest.json", m)
    return final
