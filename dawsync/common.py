from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import struct
import unicodedata
import uuid


class SyncError(ValueError):
    """An actionable error that should be shown to the user."""


def safe_name(name: str, limit: int = 48) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9_-]+", "_", text.lower()).strip("_ .")[:limit]
    if not text or re.fullmatch(r"con|prn|aux|nul|com[1-9]|lpt[1-9]", text):
        text = "track_" + (text or "audio")
    return text


def new_id() -> str:
    return uuid.uuid4().hex


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + new_id() + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise SyncError("The manifest is too large.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SyncError(f"Invalid JSON: {path.name}") from exc
    if not isinstance(data, dict):
        raise SyncError("Expected a JSON object.")
    return data


def inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise SyncError("Invalid package path.")
    p = PurePosixPath(relative)
    if p.is_absolute() or any(x in ("..", ".") for x in relative.split("/")):
        raise SyncError(f"Unsafe package path: {relative}")
    if any(not re.fullmatch(r"[a-zA-Z0-9_.-]+", x) for x in p.parts):
        raise SyncError(f"Nonportable package path: {relative}")
    if any(safe_name(x.split(".")[0]) != x.split(".")[0].lower() for x in p.parts):
        raise SyncError(f"Reserved package path: {relative}")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise SyncError(f"Package path escapes its folder: {relative}")
    return target


def finite(value, name: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SyncError(f"{name} must be a number.")
    value = float(value)
    if not math.isfinite(value) or value < minimum:
        raise SyncError(f"Invalid {name}.")
    return value


def wav_info(path: Path) -> dict:
    """Read PCM and float WAVs without decoding or altering audio samples."""
    size = path.stat().st_size
    fmt = None
    data_bytes = None
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise SyncError(f"Expected a RIFF WAV file: {path.name} (RF64 is not supported yet)")
        declared = struct.unpack_from("<I", header, 4)[0] + 8
        if declared > size:
            raise SyncError(f"WAV is incomplete: {path.name}")
        while stream.tell() + 8 <= declared:
            tag, length = struct.unpack("<4sI", stream.read(8))
            pos = stream.tell()
            if pos + length > declared:
                raise SyncError(f"Truncated WAV chunk: {path.name}")
            if tag == b"fmt ":
                block = stream.read(min(length, 64))
                if len(block) < 16:
                    raise SyncError(f"Invalid WAV format: {path.name}")
                encoding, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", block)
                if encoding == 65534:
                    if len(block) < 40 or block[26:40] != bytes.fromhex("000000001000800000aa00389b71"):
                        raise SyncError(f"Unsupported extensible WAV: {path.name}")
                    encoding = struct.unpack_from("<H", block, 24)[0]
                if encoding not in (1, 3) or channels not in (1, 2) or not rate or not align:
                    raise SyncError(f"Only mono/stereo PCM or float WAV is supported: {path.name}")
                if bits not in (8, 16, 24, 32, 64) or (encoding == 3 and bits not in (32, 64)):
                    raise SyncError(f"Unsupported WAV bit depth: {path.name}")
                if align != channels * bits // 8 or byte_rate != rate * align:
                    raise SyncError(f"Invalid WAV sample layout: {path.name}")
                fmt = dict(channels=channels, sample_rate=rate, bits=bits, encoding=encoding, block_align=align)
            elif tag == b"data":
                if data_bytes is not None:
                    raise SyncError(f"Multiple WAV data chunks are not supported: {path.name}")
                data_bytes = length
            stream.seek(pos + length + length % 2)
    if fmt is None or data_bytes is None or data_bytes % fmt["block_align"]:
        raise SyncError(f"WAV is missing valid sample data: {path.name}")
    frames = data_bytes // fmt.pop("block_align")
    if frames == 0:
        raise SyncError(f"Empty WAV: {path.name}")
    return {**fmt, "frames": frames, "duration": frames / fmt["sample_rate"], "size": size}

