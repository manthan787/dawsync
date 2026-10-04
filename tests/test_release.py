from pathlib import Path
import tempfile
import unittest

from dawsync import __version__
from scripts.release import check_tag, project_version


class ReleaseTests(unittest.TestCase):
    def test_project_version_is_the_release_source_of_truth(self):
        self.assertEqual(project_version(), __version__)
        self.assertEqual(check_tag("v" + __version__), "v" + __version__)

    def test_mismatched_or_non_semantic_versions_stop_release(self):
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            check_tag("v9.9.9")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "dawsync").mkdir()
            (root / "dawsync/__init__.py").write_text('__version__ = "preview"\n')
            with self.assertRaisesRegex(RuntimeError, "three-part"):
                project_version(root)
