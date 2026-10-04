from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dawsync.common import atomic_json
from dawsync.projects import Projects


class ProjectsTests(unittest.TestCase):
    def test_migrates_existing_song_and_revision_state(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            legacy = {"project_id": "almost-there", "source": "/song.als", "tail": 12,
                      "latest_return": "/return.als", "last_source_hash": "saved", "exchange": "/drive"}
            atomic_json(path, legacy)
            store = Projects(path)
            self.assertEqual(store.current, legacy)
            store.save()
            self.assertEqual(Projects(path).current, legacy)

    def test_projects_keep_independent_preferences(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            store = Projects(path)
            first = store.add(Path(folder) / "One.als", "/drive")
            store.current["tail"] = 15
            second = store.add(Path(folder) / "Two.als", "/other")
            self.assertNotEqual(first, second)
            self.assertEqual(store.current["tail"], 4)
            store.save()
            restored = Projects(path)
            self.assertEqual(restored.active, second)
            self.assertEqual(restored.entries[first]["tail"], 15)
            self.assertEqual(restored.entries[first]["exchange"], "/drive")

    def test_adding_existing_song_selects_it(self):
        with TemporaryDirectory() as folder:
            store = Projects(Path(folder) / "config.json")
            source = Path(folder) / "Song.als"
            first = store.add(source)
            store.current["source"] = "/working-return.als"
            store.add(Path(folder) / "Other.als")
            self.assertEqual(store.add(source), first)
            self.assertEqual(len(store.entries), 2)


if __name__ == "__main__":
    unittest.main()
