"""Verify project switching and layout without opening the user's DAWs."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication
    from dawsync import app
except ImportError:
    app = None


@unittest.skipIf(app is None, "Install the desktop extra to check the Qt interface")
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setStyle("Fusion")

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.data = patch.object(app, "DATA", Path(self.temp.name))
        self.data.start()
        self.inspect = patch.object(app, "inspect_set", side_effect=lambda p: SimpleNamespace(
            name=p.stem, bpm=120, numerator=4, denominator=4, tracks=[{"transfer": True}]))
        self.inspect.start()
        self.window = app.Window()
        self.window.timer.stop()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()
        self.inspect.stop()
        self.data.stop()
        self.temp.cleanup()

    def test_switch_restores_settings_and_survives_restart(self):
        w = self.window
        first = w.projects.add(Path(self.temp.name) / "First.als", "/first-drive")
        w.activate_project(first)
        w.tail.setValue(14)
        w.loop.setChecked(False)
        second = w.projects.add(Path(self.temp.name) / "Second.als", "/second-drive")
        w.activate_project(second)
        w.tail.setValue(8)
        w.projects_list.buttons[first].click()
        self.assertEqual(w.config["project_id"], first)
        self.assertEqual(w.tail.value(), 14)
        self.assertFalse(w.loop.isChecked())
        self.assertEqual(w.exchange.text(), "/first-drive")
        self.assertEqual(w.song_name.text(), "First")
        w.save_config()
        restored = app.Projects(w.config_path)
        self.assertEqual(len(restored.entries), 2)
        self.assertEqual(restored.entries[second]["tail"], 8)
        self.assertEqual(restored.active, first)
        # Native accessibility clients select a checkable button through its
        # toggle action; that must open the song just like a mouse press.
        w.projects_list.buttons[second].setChecked(True)
        self.assertEqual(w.config["project_id"], second)
        self.assertEqual(w.tail.value(), 8)

    def test_controls_do_not_overlap_when_window_is_smaller(self):
        w = self.window
        w.resize(1180, 720)
        w.show()
        self.application.processEvents()
        self.assertGreaterEqual(w.source.height(), 43)
        self.assertGreaterEqual(w.exchange.height(), 43)
        for field, button in zip((w.source, w.exchange), w.setup_buttons):
            self.assertGreater(button.width(), button.fontMetrics().horizontalAdvance(button.text()))
            self.assertFalse(field.geometry().intersects(button.geometry()))
        table_bottom = w.table.mapTo(w.centralWidget(), QPoint(0, w.table.height())).y()
        action_top = w.import_button.mapTo(w.centralWidget(), QPoint(0, 0)).y()
        self.assertLessEqual(table_bottom, action_top)


if __name__ == "__main__":
    unittest.main()
