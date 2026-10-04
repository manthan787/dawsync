from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import time

from .ableton import exported_sources, import_revision, prepare_render
from .common import SyncError, new_id, read_json, sha256, wav_info
from .macos import APP, export_set, transport_idle
from .package import create_revision, validate
from .state import State


DATA = Path(os.environ.get("DAWSYNC_HOME", str(Path.home() / "Library/Application Support/DAWSync")))


def publish_completed(job: Path, exchange: Path, project_id: str, state_path: Path) -> Path:
    plan = read_json(job / "plan.json")
    sources = exported_sources(job, plan)
    expected = plan["bars"] * 4 * 60 / plan["bpm"]
    for source in sources:
        info = wav_info(Path(source["path"]))
        if abs(info["duration"] - expected) > 1.5 / info["sample_rate"]:
            raise SyncError("Export duration differs from the requested range. Check Live's export settings.")
    state = State(state_path)
    try:
        folder = create_revision(exchange, project_id=project_id, project_name=plan["name"],
                                 sources=sources, bpm=plan["bpm"], markers=plan["markers"],
                                 content_end_seconds=plan.get("content_end_seconds"),
                                 original_set_hash=plan["source_hash"], parent_revision=state.head(project_id))
        m = validate(folder)
        state.register(m, folder)
        state.advance(m)
    finally:
        state.close()
    return folder


def publish(source: Path, exchange: Path, project_id: str, *, use_loop=True, tail=4, data=DATA, log=lambda x: None):
    idle_deadline = time.monotonic() + 60 * 60
    waiting = False
    while not transport_idle():
        if not waiting:
            log("Waiting for Ableton playback/recording to stop…")
            waiting = True
        if time.monotonic() > idle_deadline:
            raise SyncError("Live stayed busy for an hour. Save your set and publish again when stopped.")
        time.sleep(2)
    job = data / "jobs" / new_id()
    plan = prepare_render(source, job, tail_seconds=tail, use_loop=use_loop)
    export_set(plan, job / "renders", log)
    deadline = time.monotonic() + 60 * 60
    stable_signature, stable_at = None, 0
    while time.monotonic() < deadline:
        try:
            sources = exported_sources(job, plan)
            signature = tuple((str(s["path"]), Path(s["path"]).stat().st_size, Path(s["path"]).stat().st_mtime_ns) for s in sources)
            info = [wav_info(Path(s["path"])) for s in sources]
            expected = plan["bars"] * 4 * 60 / plan["bpm"]
            if any(abs(x["duration"] - expected) > 1.5 / x["sample_rate"] for x in info):
                raise SyncError("Live is still rendering.")
            if signature != stable_signature:
                stable_signature, stable_at = signature, time.monotonic()
            if time.monotonic() - stable_at >= 3:
                break
        except (OSError, SyncError):
            stable_signature = None
        time.sleep(1)
    else:
        raise SyncError(f"Rendering did not finish. The isolated job is preserved at {job}.")
    folder = publish_completed(job, exchange, project_id, data / "state.sqlite")
    log("Published verified revision " + folder.name[:12])
    # A normal open request lets Live show its own unsaved-work prompt if
    # necessary. No save/discard confirmation is ever dismissed by DAWSync.
    subprocess.run(["open", "-a", APP, str(source)], check=True)
    return {"folder": str(folder), "source_hash": plan["source_hash"]}


def receive(folder: Path, original: Path, *, data=DATA, allow_branch=False):
    m = validate(folder)
    state = State(data / "state.sqlite")
    try:
        existing = state.imported(m["revision_id"])
        if existing and existing.exists():
            return existing
        current = state.head(m["project_id"])
        if not allow_branch and current != m["parent_revision"]:
            raise SyncError("This update has a different parent. Both branches are preserved; import it explicitly to choose it.")
        state.register(m, folder)
        result = import_revision(folder, data / "returns", original)
        state.advance(m, allow_branch=allow_branch)
        state.record_import(m["revision_id"], result)
        return result
    finally:
        state.close()
