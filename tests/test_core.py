from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from dawsync.ableton import inspect_set, import_revision, load_set, prepare_render, put, save_set, value
from dawsync.common import SyncError, atomic_json, inside, read_json, safe_name, sha256, wav_info
from dawsync.package import ROOT, create_revision, validate
from dawsync.rpp import project_text
from dawsync.state import State


def audio(path, frames=1000, rate=44100):
    with wave.open(str(path), "wb") as w:
        w.setparams((2, 2, rate, 0, "NONE", "not compressed"))
        w.writeframes(struct.pack("<hh", 100, -100) * frames)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.wav = self.root / "input.wav"
        audio(self.wav)
        self.sources = [dict(id="t_one", name='Nord / Piano: 🎹', path=self.wav),
                        dict(id="t_two", name='CON', path=self.wav),
                        dict(id="reference_main", name='Mix', path=self.wav, role="reference")]

    def tearDown(self):
        self.temp.cleanup()

    def package(self, **kwargs):
        return create_revision(self.root / "exchange", project_id="song", project_name="Almost there", sources=self.sources, **kwargs)

    def original(self):
        r = load_set(ROOT / "fixtures/live12-seed.als")
        put(r, "LiveSet/Transport/LoopStart", 0)
        for ref in r.findall(".//SampleRef/FileRef"):
            put(ref, "Path", self.wav)
            put(ref, "RelativePath", "")
            put(ref, "RelativePathType", 0)
        path = self.root / "original.als"
        save_set(path, r)
        return path

    def test_portable_names_and_relative_paths(self):
        p = self.package()
        m = validate(p)
        self.assertIn("track_con", m["tracks"][1]["file"])
        self.assertIn("nord_piano", m["tracks"][0]["file"])
        text = (p / "session.rpp").read_text()
        self.assertNotIn(str(self.root), text)
        self.assertIn('MUTESOLO 1 0 0', text)
        # Captured from REAPER 7.81's native save: API P_EXT properties persist
        # as EXT/EXTI chunks. Raw P_EXT tokens cause warnings and lose identity.
        self.assertIn('    <EXT\n      DAWSYNC_ID "t_one"', text)
        self.assertIn('      <EXTI\n        DAWSYNC_SOURCE_END ', text)
        self.assertNotIn('P_EXT:', text)
        self.assertEqual(sha256(self.wav), m["files"][m["tracks"][0]["file"]]["sha256"])

    def test_same_display_names_keep_distinct_ids(self):
        self.sources[1]["name"] = self.sources[0]["name"]
        m = validate(self.package())
        self.assertNotEqual(m["tracks"][0]["file"], m["tracks"][1]["file"])

    def test_corrupt_audio_is_rejected(self):
        p = self.package()
        m = validate(p)
        media = p / m["tracks"][0]["file"]
        b = bytearray(media.read_bytes()); b[-1] ^= 1; media.write_bytes(b)
        with self.assertRaisesRegex(SyncError, "complete, unmodified"):
            validate(p)

    def test_missing_media_is_rejected(self):
        p = self.package(); m = validate(p)
        (p / m["tracks"][0]["file"]).unlink()
        with self.assertRaises(SyncError):
            validate(p)

    def test_unequal_duration_is_rejected(self):
        short = self.root / "short.wav"; audio(short, frames=999)
        self.sources[1]["path"] = short
        with self.assertRaisesRegex(SyncError, "identical lengths"):
            self.package()

    def test_different_sample_rates_are_rejected(self):
        other = self.root / "other.wav"; audio(other, rate=48000)
        self.sources[1]["path"] = other
        with self.assertRaisesRegex(SyncError, "sample rate"):
            self.package()

    def test_windows_reserved_names(self):
        for name in ("CON", "aux", "NUL", "COM1", "LPT9", "🪕"):
            self.assertTrue(safe_name(name).startswith("track_"))
        self.assertEqual(safe_name("Bass.  "), "bass")

    def test_path_traversal_and_symlink_escape(self):
        for path in ("../x", "/tmp/x", "C:\\x", "audio/../../x", "audio/con.wav"):
            with self.assertRaises(SyncError):
                inside(self.root, path)
        (self.root / "escape").symlink_to(self.root.parent)
        with self.assertRaises(SyncError):
            inside(self.root, "escape/x")

    def test_float_wav_and_truncation(self):
        path = self.root / "float.wav"
        data = struct.pack("<ff", .1, -.1) * 17
        fmt = struct.pack("<HHIIHH", 3, 2, 48000, 48000 * 8, 8, 32)
        chunks = b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data
        path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)
        self.assertEqual(wav_info(path)["frames"], 17)
        self.assertEqual(wav_info(path)["encoding"], 3)
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaisesRegex(SyncError, "incomplete"):
            wav_info(path)

    def test_branch_detection_and_revision_identity(self):
        first = validate(self.package())
        second = validate(self.package(parent_revision=first["revision_id"], source_daw="reaper"))
        branch = validate(self.package(parent_revision=first["revision_id"], source_daw="reaper"))
        state = State(self.root / "state.sqlite")
        try:
            state.register(first, self.root); state.advance(first)
            state.register(second, self.root); state.advance(second)
            with self.assertRaisesRegex(SyncError, "another branch"):
                state.advance(branch)
            self.assertEqual(state.head("song"), second["revision_id"])
            changed = deepcopy(first); changed["project_name"] = "Changed"
            with self.assertRaisesRegex(SyncError, "reused"):
                state.register(changed, self.root)
        finally:
            state.close()

    def test_import_preserves_original_and_neutralizes_prints(self):
        original = self.original(); before = sha256(original)
        folder = self.package(source_daw="reaper")
        result = import_revision(folder, self.root / "returns", original)
        self.assertEqual(sha256(original), before)
        r = load_set(result)
        tracks = list(r.find("LiveSet/Tracks"))
        printed = [t for t in tracks if value(t, "Name/Annotation").startswith("DAWSync track:")]
        self.assertEqual(len(printed), 3)
        for t in printed:
            clip = t.find(".//AudioClip")
            self.assertEqual(value(clip, "IsWarped"), "false")
            self.assertEqual(len(clip.findall("WarpMarkers/WarpMarker")), 2)
            self.assertEqual(value(t, "DeviceChain/Mixer/Volume/Manual"), "1")
            self.assertEqual(value(t, "DeviceChain/Mixer/Speaker/Manual"), "false" if value(t,"Name/Annotation").endswith("role: reference") else "true")
            self.assertTrue(Path(value(clip, "SampleRef/FileRef/Path")).is_file())
            self.assertEqual(value(clip, "SampleRef/DefaultDuration"), "1000")
        for t in tracks:
            if t in printed:
                continue
            self.assertEqual(value(t, "DeviceChain/AudioOutputRouting/Target"), "AudioOut/None")
            self.assertEqual(value(t, "DeviceChain/Mixer/Speaker/Manual"), "false")
        first_return = next(i for i,t in enumerate(tracks) if t.tag == "ReturnTrack")
        self.assertTrue(all(t.tag == "ReturnTrack" for t in tracks[first_return:]))
        self.assertTrue(all(len(t.findall("DeviceChain/Mixer/Sends/TrackSendHolder")) == 2 for t in tracks))
        pointers = [e.get("Id") for e in r.iter() if e.tag in ("Pointee", "AutomationTarget") or e.tag.endswith("ModulationTarget")]
        self.assertEqual(len(pointers), len(set(pointers)))

    def test_repeat_import_has_unique_export_identity(self):
        first = import_revision(self.package(source_daw="reaper"), self.root / "returns", self.original())
        second = import_revision(self.package(source_daw="reaper"), self.root / "returns", first)
        info = inspect_set(second)
        self.assertEqual(len(info.tracks), len({t["id"] for t in info.tracks}))
        self.assertEqual(sum(t["transfer"] for t in info.tracks), 2)

    def test_render_copy_only_and_missing_sample_guard(self):
        original = self.original(); before = sha256(original)
        plan = prepare_render(original, self.root / "job", use_loop=True)
        self.assertEqual(sha256(original), before)
        self.assertEqual(plan["bars"], 6)
        r = load_set(Path(plan["render_set"]))
        self.assertEqual(value(r.find("LiveSet/Tracks/AudioTrack"), "Name/UserName"), "t_als_15")
        self.wav.unlink()
        with self.assertRaisesRegex(SyncError, "Missing source samples"):
            inspect_set(original)

    def test_nonfinite_manifest_and_invalid_parent(self):
        p = self.package(); m = validate(p)
        m["tempo"]["bpm"] = float("nan")
        with self.assertRaises(ValueError):
            atomic_json(p / "manifest.json", m)
        m["tempo"]["bpm"] = 120; m["parent_revision"] = m["revision_id"]
        atomic_json(p / "manifest.json", m)
        with self.assertRaisesRegex(SyncError, "own parent"):
            validate(p)


if __name__ == "__main__":
    unittest.main()
