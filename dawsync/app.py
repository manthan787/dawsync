from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QTableWidgetItem

from .ableton import inspect_set
from .common import SyncError, sha256
from .engine import DATA, publish, receive
from .macos import APP
from .package import ROOT, validate
from .state import State
from .ui import build_window
from .projects import Projects


class Signals(QObject):
    log = Signal(str)
    done = Signal(object)
    error = Signal(str)


class Job(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.signals = Signals()
        self.operation = operation

    def run(self):
        try:
            self.signals.done.emit(self.operation(self.signals.log.emit))
        except Exception as exc:
            DATA.mkdir(parents=True, exist_ok=True)
            with (DATA / "errors.log").open("a", encoding="utf-8") as stream:
                stream.write(datetime.now().isoformat() + "\n" + traceback.format_exc() + "\n")
            self.signals.error.emit(str(exc))


class Window(QMainWindow):
    def __init__(self, source=None, exchange=None):
        super().__init__()
        DATA.mkdir(parents=True, exist_ok=True)
        self.config_path = DATA / "config.json"
        self.projects = Projects(self.config_path)
        self.config = self.projects.current
        if source:
            self.projects.add(source, exchange or self.config.get("exchange", ""))
            self.config = self.projects.current
        if exchange:
            self.config["exchange"] = str(exchange)
        self.busy = False
        self.pending_source = None
        self.last_scan = 0
        self.last_warning = None
        self.rows = []
        self.auto_projects = set()
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(1)
        build_window(self)
        self.refresh_projects()
        self.projects_list.projectSelected.connect(self.project_selected)
        self.source.editingFinished.connect(self.source_edited)
        self.exchange.editingFinished.connect(self.save_config)
        self.loop.toggled.connect(self.save_config)
        self.tail.valueChanged.connect(self.save_config)
        self.auto.toggled.connect(self.auto_changed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.watch)
        self.timer.start(2000)
        self.save_config()
        self.refresh_summary()
        self.refresh_projects()
        self.save_config()
        self.log("Render copies and incoming sets are stored locally. Shared revisions are verified before import.")

    def log(self, message):
        self.activity.append(datetime.now().strftime("%H:%M:%S") + "  " + message)

    def save_config(self, *_):
        self.config.update(source=self.source.text().strip(), exchange=self.exchange.text().strip(),
                           use_loop=self.loop.isChecked(), tail=self.tail.value())
        self.projects.save()

    def refresh_summary(self):
        if not self.source.text().strip():
            self.song_name.setText("Your next session")
            self.summary.setText("Connect a project to get started.")
            return
        self.song_name.setText(self.config.get("project_name") or Path(self.source.text()).stem)
        try:
            info = inspect_set(Path(self.source.text()))
            self.config["project_name"] = info.name
            self.song_name.setText(info.name)
            self.summary.setText(f"{info.bpm:g} BPM  ·  {info.numerator}/{info.denominator}  ·  {sum(t['transfer'] for t in info.tracks)} audio buses & returns  ·  Ableton Live ↔ REAPER")
        except Exception as exc:
            self.summary.setText(str(exc))

    def refresh_projects(self):
        for pid, entry in self.projects.entries.items():
            text = entry.get("project_name") or (Path(entry["source"]).stem if entry.get("source") else "New project")
            self.projects_list.update_project(pid, text, entry.get("source", ""), pid == self.projects.active)

    def add_project(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Add an Ableton project", str(Path.home() / "Music"), "Ableton Live Sets (*.als)")
        if not path:
            return
        self.save_config()
        exchange = self.exchange.text().strip()
        pid = self.projects.add(Path(path), exchange)
        self.activate_project(pid)

    def project_selected(self, pid):
        if not self.busy:
            self.save_config()
            self.activate_project(pid)

    def activate_project(self, pid):
        self.projects.active = pid
        self.config = self.projects.current
        widgets = (self.source, self.exchange, self.loop, self.tail, self.auto)
        for widget in widgets:
            widget.blockSignals(True)
        self.source.setText(self.config.get("source", ""))
        self.exchange.setText(self.config.get("exchange", ""))
        self.loop.setChecked(self.config.get("use_loop", True))
        self.tail.setValue(self.config.get("tail", 4))
        self.auto.setChecked(pid in self.auto_projects)
        for widget in widgets:
            widget.blockSignals(False)
        self.pending_source = None
        self.status.setText("Ready · originals are preserved")
        self.last_scan = 0
        self.last_warning = None
        self.rows = []
        self.table.setRowCount(0)
        self.activity.clear()
        self.refresh_summary()
        self.refresh_projects()
        self.save_config()
        self.log("Opened " + self.config.get("project_name", "project") + ".")
        self.scan()

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose Ableton set", self.source.text(), "Ableton Live Sets (*.als)")
        if path:
            if self.config.get("source") != path:
                self.config.pop("last_source_hash", None)
            self.source.setText(path)
            self.save_config()
            self.refresh_summary()
            self.refresh_projects()

    def source_edited(self):
        path = self.source.text().strip()
        if path != self.config.get("source"):
            self.config.pop("last_source_hash", None)
            self.pending_source = None
        self.save_config()
        self.refresh_summary()
        self.refresh_projects()

    def choose_exchange(self):
        path = QFileDialog.getExistingDirectory(self, "Choose shared Google Drive folder", self.exchange.text())
        if path:
            self.exchange.setText(path)
            self.save_config()

    def inputs(self):
        source, exchange = self.source.text().strip(), self.exchange.text().strip()
        if not source or not exchange:
            raise SyncError("Choose your Ableton set and shared exchange folder first.")
        source, exchange = Path(source).expanduser(), Path(exchange).expanduser()
        if not source.is_file() or not exchange.is_dir():
            raise SyncError("The chosen set and shared folder must exist locally.")
        self.save_config()
        return source, exchange

    def run_job(self, description, operation, complete, *, quiet=False):
        if self.busy:
            return
        self.busy = True
        self.projects_list.setEnabled(False)
        self.add_project_button.setEnabled(False)
        self.source.setEnabled(False)
        self.exchange.setEnabled(False)
        for button in self.setup_buttons:
            button.setEnabled(False)
        self.status.setText(description)
        for b in (self.publish_button, self.check_button, self.import_button, self.open_button):
            b.setEnabled(False)
        job = Job(operation)
        self.current_job = job
        job.signals.log.connect(self.log)
        def finish(result):
            self.busy = False
            self.projects_list.setEnabled(True)
            self.add_project_button.setEnabled(True)
            self.source.setEnabled(True)
            self.exchange.setEnabled(True)
            for button in self.setup_buttons:
                button.setEnabled(True)
            for b in (self.publish_button, self.check_button, self.import_button, self.open_button):
                b.setEnabled(True)
            self.status.setText("Ready · originals are preserved")
            complete(result)
        def failed(message):
            self.busy = False
            self.projects_list.setEnabled(True)
            self.add_project_button.setEnabled(True)
            self.source.setEnabled(True)
            self.exchange.setEnabled(True)
            for button in self.setup_buttons:
                button.setEnabled(True)
            if self.auto.isChecked():
                self.auto.setChecked(False)
                self.log("Automatic sync paused. Resolve the issue and enable it again to retry.")
            for b in (self.publish_button, self.check_button, self.import_button, self.open_button):
                b.setEnabled(True)
            self.status.setText("Paused · " + message.splitlines()[0])
            self.log(message)
            if not quiet:
                QMessageBox.warning(self, "DAWSync paused", message)
        job.signals.done.connect(finish)
        job.signals.error.connect(failed)
        self.threadpool.start(job)

    def publish(self, *_):
        try:
            source, exchange = self.inputs()
        except SyncError as exc:
            QMessageBox.information(self, "Set up DAWSync", str(exc))
            return
        pid, loop, tail = self.config["project_id"], self.loop.isChecked(), self.tail.value()
        def complete(result):
            self.config["last_source_hash"] = result["source_hash"]
            self.config["latest_revision"] = result["folder"]
            self.save_config()
            self.log("Windows handoff ready: " + result["folder"] + "/session.rpp")
            self.pending_source = None
            self.scan()
        self.run_job("Preparing and rendering in Ableton…", lambda log: publish(source, exchange, pid, use_loop=loop, tail=tail, log=log), complete)

    def scan(self, *_):
        if self.busy:
            return
        try:
            _, exchange = self.inputs()
        except SyncError:
            return
        pid = self.config["project_id"]
        def operation(log):
            state = State(DATA / "state.sqlite")
            entries = []
            try:
                head = state.head(pid)
                for folder in sorted((exchange / pid / "revisions").glob("*")):
                    if not (folder / "manifest.json").is_file():
                        continue
                    try:
                        m = validate(folder)
                        state.register(m, folder)
                        imported = state.imported(m["revision_id"])
                        status = "Imported" if imported else ("Published" if m["source_daw"] == "ableton" else ("Ready" if m["parent_revision"] == head else "Separate branch"))
                        entries.append({"folder": folder, "manifest": m, "status": status})
                    except (SyncError, OSError) as exc:
                        entries.append({"folder": folder, "status": "Waiting for Drive", "error": str(exc)})
            finally:
                state.close()
            return entries
        def complete(entries):
            self.rows = entries
            self.table.setRowCount(len(entries))
            for i, entry in enumerate(entries):
                m = entry.get("manifest", {})
                for col, text in enumerate((entry["folder"].name[:12], m.get("source_daw", "—"), str(len(m.get("tracks", []))), entry["status"])):
                    item = self.table.item(i, col)
                    if item is None:
                        item = QTableWidgetItem()
                        self.table.setItem(i, col, item)
                    item.setText(text.upper() if col == 1 else text)
                    if col == 0:
                        item.setFont(QFont("Menlo", 12))
                        item.setForeground(QColor("#ccd4e5"))
                    if col == 3:
                        colors = {"Ready": "#a99cff", "Published": "#8a9cb7", "Imported": "#8fd3bc", "Separate branch": "#e7bc83", "Waiting for Drive": "#e7bc83"}
                        item.setForeground(QColor(colors[entry["status"]]))
            if self.auto.isChecked():
                ready = [e for e in entries if e["status"] == "Ready"]
                if len(ready) == 1:
                    self.import_entry(ready[0], automatic=True)
                elif len(ready) > 1:
                    self.warn_once("Two people published from the same revision. Select which branch to import.")
        self.run_job("Verifying shared revisions…", operation, complete, quiet=True)

    def import_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rows) or "manifest" not in self.rows[row]:
            QMessageBox.information(self, "Choose an update", "Select a verified revision in the list.")
            return
        entry = self.rows[row]
        branch = entry["status"] == "Separate branch"
        if branch and QMessageBox.question(self, "Choose this branch?", "This update diverges from your current revision. Importing it preserves both sets and selects this branch for future exchanges.") != QMessageBox.StandardButton.Yes:
            return
        self.import_entry(entry, allow_branch=branch)

    def import_entry(self, entry, automatic=False, allow_branch=False):
        try:
            source, _ = self.inputs()
        except SyncError:
            return
        baseline = self.config.get("last_source_hash")
        if automatic and baseline and sha256(source) != baseline:
            self.warn_once("Your Ableton set also changed. Publish it or select the incoming revision explicitly; both versions are preserved.")
            return
        def complete(path):
            self.config["latest_return"] = str(path)
            self.log("Ableton return ready: " + str(path))
            self.source.setText(str(path))
            self.config["last_source_hash"] = sha256(path)
            if automatic:
                subprocess.run(["open", "-a", APP, str(path)], check=True)
            self.save_config()
            self.refresh_summary()
            self.refresh_projects()
            self.scan()
        self.run_job("Creating a new Ableton working set…", lambda log: receive(entry["folder"], source, allow_branch=allow_branch), complete, quiet=automatic)

    def open_return(self):
        path = self.config.get("latest_return")
        if path and Path(path).is_file():
            subprocess.run(["open", "-a", APP, path], check=True)
        else:
            QMessageBox.information(self, "No return yet", "Import a verified update first.")

    def open_guide(self):
        helper = DATA / "Windows helper"
        helper.mkdir(exist_ok=True)
        for name in ("DAWSync.lua", "codec.lua"):
            shutil.copyfile(ROOT / "reaper" / name, helper / name)
        guide = ROOT / "docs" / "WINDOWS.md"
        if guide.exists():
            shutil.copyfile(guide, helper / "README.txt")
        subprocess.run(["open", str(helper)], check=True)

    def auto_changed(self, checked):
        if checked:
            self.auto_projects.add(self.projects.active)
        else:
            self.auto_projects.discard(self.projects.active)
        if checked and self.source.text().strip() and Path(self.source.text()).is_file():
            self.config.setdefault("last_source_hash", sha256(Path(self.source.text())))
            self.save_config()
            self.log("Watching saves. Exports wait for Live to stop; generated returns do not trigger another export.")

    def warn_once(self, text):
        if text != self.last_warning:
            self.last_warning = text
            self.log(text)
        self.status.setText("Needs attention · " + text)

    def watch(self):
        if self.busy or not self.auto.isChecked():
            return
        source = Path(self.source.text())
        if not source.is_file():
            return
        signature = (source.stat().st_size, source.stat().st_mtime_ns)
        now = time.monotonic()
        if self.pending_source is None or self.pending_source[0] != signature:
            self.pending_source = (signature, now)
        elif now - self.pending_source[1] >= 8:
            current = sha256(source)
            if current != self.config.get("last_source_hash"):
                self.publish()
                return
        if now - self.last_scan >= 20:
            self.last_scan = now
            self.scan()

    def closeEvent(self, event):
        if self.busy:
            QMessageBox.information(self, "Job in progress", "Wait for the active render or import to finish before closing DAWSync.")
            event.ignore()
        else:
            self.save_config()
            event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--exchange", type=Path)
    args = parser.parse_args()
    application = QApplication(sys.argv[:1])
    application.setStyle("Fusion")
    application.setApplicationName("DAWSync")
    application.setOrganizationName("DAWSync")
    window = Window(args.source, args.exchange)
    window.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
