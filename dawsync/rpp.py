from __future__ import annotations

from pathlib import Path
import re
import uuid

from .common import SyncError


def quote(text: str) -> str:
    # RPP allows backtick-delimited strings, but generated projects use a
    # conservative quoted display label. Original labels survive in JSON.
    return '"' + re.sub(r'["\\\r\n\x00-\x1f]', " ", text) + '"'


def project_text(manifest: dict) -> str:
    tracks = manifest["tracks"]
    tempo = manifest["tempo"]
    lines = [
        '<REAPER_PROJECT 0.1 7 1', '  RIPPLE 0', '  SAMPLERATE %d' % manifest["sample_rate"],
        '  TEMPO %.12g %d %d' % (tempo["bpm"], tempo["numerator"], tempo["denominator"]),
        '  TIMEMODE 1 0 -1', '  TIMELOCKMODE 0', '  MASTER_VOLUME 1',
        '  RECORD_PATH "recordings"', '  <EXTSTATE', '    <DAWSYNC',
        '      project_id ' + quote(manifest["project_id"]),
        '      revision_id ' + quote(manifest["revision_id"]),
        '      content_end_seconds ' + quote(str(manifest.get("content_end_seconds", tracks[0]["duration"]))),
        '    >', '  >',
    ]
    for marker in manifest.get("markers", []):
        lines.append('  MARKER %d %.12g %s 0' % (marker["index"], marker["seconds"], quote(marker["name"])))
    for track in tracks:
        guid = "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, manifest["project_id"] + ":" + track["id"])).upper() + "}"
        muted = 1 if track["role"] == "reference" else 0
        label = "REFERENCE — " + track["name"] if muted else track["name"]
        lines.extend([
            '  <TRACK ' + guid, '    NAME ' + quote(label),
            '    VOLPAN 1 0 1 -1', '    MUTESOLO %d 0 0' % muted,
            '    MAINSEND 1', '    ISBUS 0 0', '    BEAT -1',
            '    REC 0 -1 0 0 0 0 0 0',
            '    <EXT',
            '      DAWSYNC_ID ' + quote(track["id"]),
            '      DAWSYNC_ROLE ' + quote(track["role"]), '    >',
            '    <ITEM', '      POSITION 0', '      SNAPOFFS 0',
            '      LENGTH %.12g' % track["duration"],
            '      VOLPAN 1 0 1 -1', '      SOFFS 0',
            '      FADEIN 1 0 0', '      FADEOUT 1 0 0', '      BEAT 0',
            '      LOOP 0', '      NAME ' + quote(track["name"]),
            '      <EXTI',
            '        DAWSYNC_SOURCE_END ' + quote(str(manifest.get("content_end_seconds", track["duration"]))), '      >',
            '      <SOURCE WAVE', '        FILE ' + quote(track["file"]),
            '      >', '    >', '  >',
        ])
    lines.append('>')
    return "\n".join(lines) + "\n"


def write_project(path: Path, manifest: dict) -> None:
    path.write_text(project_text(manifest), encoding="utf-8", newline="\n")
