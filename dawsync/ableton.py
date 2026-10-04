from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import gzip
import math
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from .common import SyncError, atomic_json, inside, read_json, safe_name, sha256, wav_info
from .package import ROOT, validate


def load_set(path: Path) -> ET.Element:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    if len(raw) > 256 * 1024 * 1024:
        raise SyncError("The Live Set exceeds supported size limits.")
    root = ET.fromstring(raw)
    if root.tag != "Ableton" or not root.get("Creator", "").startswith("Ableton Live 12."):
        raise SyncError("This adapter supports Ableton Live 12 sets.")
    if root.find("LiveSet") is None:
        raise SyncError("Invalid Live Set.")
    return root


def save_set(path: Path, root: ET.Element):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    path.write_bytes(gzip.compress(raw, mtime=0))


def value(node, path: str, default=""):
    item = node.find(path)
    return item.get("Value", default) if item is not None else default


def put(node, path: str, val):
    e = node.find(path)
    if e is None:
        raise SyncError(f"Live schema is missing {path}.")
    e.set("Value", str(val))


def rebase_media(root: ET.Element, source: Path) -> list[Path]:
    missing = []
    found = []
    for ref in root.findall(".//SampleRef/FileRef"):
        absolute = value(ref, "Path")
        relative = value(ref, "RelativePath")
        candidates = [Path(absolute)] if absolute else []
        if relative:
            candidates.append(source.parent / relative)
        resolved = next((p.resolve() for p in candidates if p.is_file()), None)
        if resolved is None:
            missing.append(absolute or relative or "unnamed sample")
            continue
        put(ref, "Path", resolved)
        put(ref, "RelativePath", "")
        put(ref, "RelativePathType", 0)
        found.append(resolved)
    if missing:
        raise SyncError("Missing source samples:\n" + "\n".join(sorted(set(missing))[:12]))
    return sorted(set(found))


@dataclass
class SetInfo:
    source: Path
    name: str
    bpm: float
    end_beats: float
    tracks: list[dict]
    markers: list[dict]
    source_hash: str

    def render_bars(self, tail_seconds: float = 4):
        return max(1, math.ceil((self.end_beats + tail_seconds * self.bpm / 60) / 4))


def inspect_set(source: Path) -> SetInfo:
    source = source.expanduser().resolve()
    root = load_set(source)
    rebase_media(root, source)
    s = root.find("LiveSet")
    main = s.find("MainTrack")
    bpm = float(value(main, "DeviceChain/Mixer/Tempo/Manual", "120"))
    # Never silently flatten tempo automation into the wrong musical grid.
    tempo_target = main.find("DeviceChain/Mixer/Tempo/AutomationTarget").get("Id")
    signature_target = main.find("DeviceChain/Mixer/TimeSignature/AutomationTarget")
    signature_id = signature_target.get("Id") if signature_target is not None else None
    for envelope in main.findall("AutomationEnvelopes/Envelopes/AutomationEnvelope"):
        target = value(envelope, "EnvelopeTarget/PointeeId")
        events = list(envelope.findall("Automation/Events/*"))
        if target == tempo_target and any(abs(float(e.get("Value", bpm)) - bpm) > 1e-7 for e in events):
            raise SyncError("Tempo automation needs a tempo-map adapter; automatic transfer is paused for this set.")
        if target == signature_id and any(e.get("Value") != "201" for e in events):
            raise SyncError("This version supports a constant 4/4 time signature.")
    if value(main, "DeviceChain/Mixer/TimeSignature/Manual", "201") != "201":
        raise SyncError("This version supports a constant 4/4 time signature.")
    tracks = []
    for t in s.findall("Tracks/*"):
        annotation = value(t, "Name/Annotation")
        tid = annotation.split(";", 1)[0].removeprefix("DAWSync track: ") if annotation.startswith("DAWSync track: ") else "t_als_" + t.get("Id")
        name = value(t, "Name/UserName") or value(t, "Name/EffectiveName")
        parent = value(t, "TrackGroupId", "-1")
        route = value(t, "DeviceChain/AudioOutputRouting/Target")
        if parent == "-1" and route not in ("AudioOut/Main", "AudioOut/Master", "AudioOut/None"):
            raise SyncError(f"Custom routing on {name!r} requires an explicit render policy.")
        tracks.append({"id": tid, "name": name, "kind": t.tag, "parent": parent,
                       "render_name": tid, "transfer": parent == "-1" and route != "AudioOut/None" and "; role: reference" not in annotation})
    arrangement = s.findall("Tracks/*/DeviceChain/MainSequencer/*/ArrangerAutomation/Events/*")
    ends = [float(e.get("Value", 0)) for clip in arrangement
            for e in clip.findall("CurrentEnd")]
    end = max(ends, default=0)
    if end <= 0:
        raise SyncError("This set has no Arrangement audio or MIDI clips.")
    markers = []
    for i, loc in enumerate(s.findall("Locators/Locators/Locator"), 1):
        markers.append({"index": i, "name": value(loc, "Name"),
                        "seconds": float(value(loc, "Time", "0")) * 60 / bpm})
    metadata = source.parent / "dawsync.json"
    name = read_json(metadata).get("project_name", source.stem) if metadata.is_file() else source.stem
    return SetInfo(source, name, bpm, end, tracks, markers, sha256(source))


def prepare_render(source: Path, job: Path, tail_seconds: float = 4, use_loop: bool = False) -> dict:
    info = inspect_set(source)
    job.mkdir(parents=True, exist_ok=False)
    root = load_set(source)
    rebase_media(root, source)
    if use_loop:
        start = float(value(root, "LiveSet/Transport/LoopStart", "0"))
        if start != 0:
            raise SyncError("Loop-range export currently requires the loop to start at 1.1.1.")
        info.end_beats = float(value(root, "LiveSet/Transport/LoopLength", "0"))
        if info.end_beats <= 0:
            raise SyncError("The saved loop is empty.")
    for t, meta in zip(root.findall("LiveSet/Tracks/*"), info.tracks):
        put(t, "Name/UserName", meta["render_name"])
        put(t, "Name/EffectiveName", meta["render_name"])
    put(root, "LiveSet/Transport/LoopStart", 0)
    put(root, "LiveSet/Transport/LoopLength", info.render_bars(tail_seconds) * 4)
    put(root, "LiveSet/Transport/CurrentTime", 0)
    render_set = job / "render.als"
    save_set(render_set, root)
    plan = {"source": str(info.source), "source_hash": info.source_hash, "name": info.name,
            "bpm": info.bpm, "bars": info.render_bars(tail_seconds), "tracks": info.tracks,
            "markers": [m for m in info.markers if m["seconds"] <= info.end_beats * 60 / info.bpm],
            "render_set": str(render_set), "tail_seconds": tail_seconds, "use_loop": use_loop,
            "content_end_seconds": info.end_beats * 60 / info.bpm}
    atomic_json(job / "plan.json", plan)
    return plan


def exported_sources(job: Path, plan: dict) -> list[dict]:
    files = list((job / "renders").glob("*.wav"))
    result = []
    for track in plan["tracks"]:
        if not track["transfer"]:
            continue
        candidates = [p for p in files if p.stem.endswith(track["render_name"])]
        if len(candidates) != 1:
            raise SyncError(f"Export is missing a unique render for {track['name']}.")
        result.append({"id": track["id"], "name": track["name"], "path": candidates[0], "role": "stem"})
    reference = [p for p in files if p.name == "print.wav" or p.stem.lower().endswith(("main", "master"))]
    if len(reference) != 1:
        raise SyncError("Export is missing its Main reference mix.")
    result.append({"id": "reference_main", "name": "Main mix", "path": reference[0], "role": "reference"})
    return result


def import_revision(folder: Path, destination: Path, original: Path | None = None) -> Path:
    m = validate(folder)
    target = destination / (safe_name(m["project_name"]) + "_" + m["revision_id"][:12])
    if target.exists():
        raise SyncError("An import with this revision already exists. Use the existing set.")
    target.mkdir(parents=True)
    # The original project stays untouched. Its tracks remain present but
    # route nowhere in the working copy. Their device/clip state is retained.
    root = load_set(original or ROOT / "fixtures" / "live12-seed.als")
    if original:
        rebase_media(root, original)
    s = root.find("LiveSet")
    originals = s.find("Tracks")
    if original:
        for t in list(originals):
            put(t, "DeviceChain/AudioOutputRouting/Target", "AudioOut/None")
            put(t, "DeviceChain/AudioOutputRouting/UpperDisplayString", "No Output")
            put(t, "DeviceChain/AudioOutputRouting/LowerDisplayString", "")
            label = value(t, "Name/UserName") or value(t, "Name/EffectiveName")
            put(t, "Name/UserName", label if label.startswith("ORIGINAL — ") else "ORIGINAL — " + label)
            put(t, "DeviceChain/Mixer/Speaker/Manual", "false")
            put(t, "DeviceChain/Mixer/SoloSink", "false")
            speaker_id = t.find("DeviceChain/Mixer/Speaker/AutomationTarget").get("Id")
            envelopes = t.find("AutomationEnvelopes/Envelopes")
            for envelope in list(envelopes):
                if value(envelope, "EnvelopeTarget/PointeeId") == speaker_id:
                    envelopes.remove(envelope)
            for arm in t.findall(".//Recorder/IsArmed"):
                arm.set("Value", "false")
            if value(t, "Name/Annotation").startswith("DAWSync track:"):
                put(t, "Name/Annotation", "Archived " + value(t, "Name/Annotation"))
    else:
        originals.clear()
    seed = load_set(ROOT / "fixtures" / "live12-seed.als").find("LiveSet/Tracks/AudioTrack")
    if seed is None or seed.find(".//AudioClip") is None:
        raise SyncError("Live 12 schema fixture is missing.")
    return_count = sum(t.tag == "ReturnTrack" for t in originals)
    next_id = max([int(e.get("Id", "-1")) for e in root.iter()] + [int(value(s, "NextPointeeId", "0"))]) + 100
    main = s.find("MainTrack")
    put(main, "DeviceChain/Mixer/Tempo/Manual", m["tempo"]["bpm"])
    if m["tempo"]["numerator"] != 4 or m["tempo"]["denominator"] != 4:
        raise SyncError("Live import currently supports constant 4/4 projects.")
    # Source master processing is already heard in the reference. Audio
    # stems are pre-master, and a new mix must not run through an old master.
    main.find("DeviceChain/DeviceChain/Devices").clear()
    main.find("AutomationEnvelopes/Envelopes").clear()
    put(main, "DeviceChain/Mixer/Volume/Manual", 1)
    put(main, "DeviceChain/Mixer/Pan/Manual", 0)
    put(main, "DeviceChain/Mixer/Speaker/Manual", "true")
    for meta in m["tracks"]:
        t = deepcopy(seed)
        next_id += 1
        t.set("Id", str(next_id))
        pointer_map = {}
        for e in t.iter():
            if e.tag in ("AutomationTarget", "Pointee") or e.tag.endswith("ModulationTarget"):
                old = e.get("Id")
                next_id += 1
                pointer_map[old] = str(next_id)
                e.set("Id", str(next_id))
        for e in t.iter("PointeeId"):
            if e.get("Value") in pointer_map:
                e.set("Value", pointer_map[e.get("Value")])
        name = ("REFERENCE — " if meta["role"] == "reference" else "") + meta["name"]
        put(t, "Name/UserName", name)
        put(t, "Name/EffectiveName", name)
        put(t, "Name/Annotation", "DAWSync track: " + meta["id"] + "; role: " + meta["role"])
        put(t, "TrackGroupId", -1)
        t.find("DeviceChain/DeviceChain/Devices").clear()
        t.find("AutomationEnvelopes/Envelopes").clear()
        for arm in t.findall(".//Recorder/IsArmed"):
            arm.set("Value", "false")
        put(t, "DeviceChain/Mixer/Volume/Manual", 1)
        put(t, "DeviceChain/Mixer/Pan/Manual", 0)
        put(t, "DeviceChain/Mixer/Speaker/Manual", "false" if meta["role"] == "reference" else "true")
        put(t, "DeviceChain/Mixer/SoloSink", "false")
        sends = t.find("DeviceChain/Mixer/Sends")
        template_send = deepcopy(sends.find("TrackSendHolder"))
        sends.clear()
        for index in range(return_count):
            holder = deepcopy(template_send)
            holder.set("Id", str(index))
            # Send parameter IDs also belong to Live's global pointee space.
            for e in holder.iter():
                if e.tag in ("AutomationTarget", "Pointee") or e.tag.endswith("ModulationTarget"):
                    next_id += 1
                    e.set("Id", str(next_id))
            sends.append(holder)
        for manual in t.findall("DeviceChain/Mixer/Sends//Manual"):
            manual.set("Value", "0")
        clip = t.find(".//AudioClip")
        events = t.find("DeviceChain/MainSequencer/Sample/ArrangerAutomation/Events")
        if events is None:
            raise SyncError("Unsupported Live arranger schema.")
        clip = deepcopy(clip)
        events.clear()
        events.append(clip)
        duration_beats = meta["duration"] * m["tempo"]["bpm"] / 60
        clip.set("Time", "0")
        for path, val in {"CurrentStart": 0, "CurrentEnd": duration_beats, "Name": name,
                          "IsWarped": "false", "Loop/LoopOn": "false", "Loop/LoopStart": 0,
                          "Loop/LoopEnd": duration_beats, "Loop/OutMarker": duration_beats,
                          "Loop/HiddenLoopStart": 0, "Loop/HiddenLoopEnd": duration_beats,
                          "Loop/StartRelative": 0, "SampleVolume": 1, "Fade": "false"}.items():
            put(clip, path, val)
        # Live still requires timing anchors when Warp is disabled.
        anchors = clip.find("WarpMarkers")
        anchors.clear()
        ET.SubElement(anchors, "WarpMarker", Id="0", SecTime="0", BeatTime="0")
        ET.SubElement(anchors, "WarpMarker", Id="1", SecTime=str(meta["duration"]), BeatTime=str(duration_beats))
        relative = "audio/" + Path(meta["file"]).name
        media = target / relative
        media.parent.mkdir(exist_ok=True)
        shutil.copyfile(inside(folder, meta["file"]), media)
        ref = clip.find("SampleRef/FileRef")
        for path, val in {"Path": str(media.resolve()), "RelativePath": relative,
                          "RelativePathType": 1, "OriginalFileSize": media.stat().st_size,
                          "OriginalCrc": 0}.items():
            put(ref, path, val)
        put(clip, "SampleRef/DefaultDuration", meta["frames"])
        put(clip, "SampleRef/DefaultSampleRate", m["sample_rate"])
        # Live requires regular tracks before the return-track block.
        at = next((i for i, existing in enumerate(originals) if existing.tag == "ReturnTrack"), len(originals))
        originals.insert(at, t)
    put(s, "NextPointeeId", next_id + 1)
    put(s, "Transport/CurrentTime", 0)
    put(s, "Transport/LoopStart", 0)
    put(s, "Transport/LoopLength", m.get("content_end_seconds", m["tracks"][0]["duration"]) * m["tempo"]["bpm"] / 60)
    put(s, "Transport/LoopOn", "false")
    s.find("Locators/Locators").clear()
    for marker in m.get("markers", []):
        loc = ET.SubElement(s.find("Locators/Locators"), "Locator", Id=str(marker["index"]))
        for tag, val in {"LomId": 0, "Time": marker["seconds"] * m["tempo"]["bpm"] / 60,
                         "Name": marker["name"], "Annotation": "", "IsSongStart": "false"}.items():
            ET.SubElement(loc, tag, Value=str(val))
    result = target / "returned.als"
    save_set(result, root)
    atomic_json(target / "dawsync.json", {"revision_id": m["revision_id"], "project_id": m["project_id"],
                                        "project_name": m["project_name"],
                                        "source_manifest": str(folder / "manifest.json")})
    return result
