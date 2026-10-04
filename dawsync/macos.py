from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from .common import SyncError


APP = "/Applications/Ableton Live 12 Standard.app"


def _literal(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def transport_idle() -> bool:
    if sys.platform != "darwin":
        raise SyncError("Ableton UI rendering is available on macOS only.")
    preflight = '''
tell application "System Events"
    if not (exists process "Live") then return "idle"
    tell process "Live"
        if role of front window is "AXDialog" or role of front window is "AXSheet" then error "Resolve the open Live dialog before exporting."
        repeat with elem in entire contents of front window
            try
                set elementId to value of attribute "AXIdentifier" of elem
                if elementId is "Transport.Play" or elementId is "Transport.GlobalRecord" then
                    if (value of elem as text) is not "0" then return "busy"
                end if
            end try
        end repeat
    end tell
end tell
return "idle"
'''
    ready = subprocess.run(["osascript", "-"], input=preflight, text=True, capture_output=True, timeout=30)
    if ready.returncode:
        if "-1719" in ready.stderr or "not allowed assistive access" in ready.stderr:
            raise SyncError("Enable DAWSync in System Settings → Privacy & Security → Accessibility, then try publishing again.") from RuntimeError(ready.stderr)
        if "-1743" in ready.stderr:
            raise SyncError("Allow DAWSync to control System Events in System Settings → Privacy & Security → Automation, then try again.") from RuntimeError(ready.stderr)
        raise SyncError("Cannot control Ableton: " + ready.stderr.strip())
    return ready.stdout.strip() == "idle"


def export_set(plan: dict, renders: Path, log=lambda x: None):
    """Live 12.4 accessibility adapter for an explicitly enabled job.

    A save, missing-plugin, missing-media, or permission prompt stops the job.
    """
    if not transport_idle():
        raise SyncError("Live is playing or recording. Stop its transport, then publish again.")
    renders.mkdir(parents=True, exist_ok=False)
    render_set = Path(plan["render_set"])
    log("Opening the isolated render copy in Ableton…")
    subprocess.run(["open", "-a", APP, str(render_set)], check=True)
    first = next(t["render_name"] for t in plan["tracks"] if t["transfer"])
    script = '''
on elementById(elementId)
    tell application "System Events"
        tell process "Live"
            repeat with elem in entire contents of front window
                try
                    if (value of attribute "AXIdentifier" of elem) is elementId then return contents of elem
                end try
            end repeat
        end tell
    end tell
    error "Live control not found: " & elementId
end elementById

on setControl(elementId, expected)
    set elem to my elementById(elementId)
    tell application "System Events"
        try
            set value of elem to expected
        on error
            perform action "AXPress" of elem
            keystroke "a" using command down
            keystroke expected
            key code 36
        end try
        if (value of elem as text) is not expected then error "Could not verify " & elementId
    end tell
end setControl

on chooseControl(elementId, wanted)
    set elem to my elementById(elementId)
    tell application "System Events"
        if (value of elem as text) is wanted then return
        perform action "AXPress" of elem
        tell process "Live"
            set chosen to false
            repeat with candidate in entire contents of front window
                try
                    if name of candidate is wanted then
                        perform action "AXPress" of candidate
                        set chosen to true
                        exit repeat
                    end if
                end try
            end repeat
            if not chosen then
                key code 53
                error "Export menu option unavailable: " & wanted
            end if
        end tell
        if (value of elem as text) is not wanted then error "Could not verify export setting: " & wanted
    end tell
end chooseControl

on switchControl(elementId, wanted)
    set elem to my elementById(elementId)
    tell application "System Events"
        if (value of elem as text) is not wanted then perform action "AXPress" of elem
        if (value of elem as text) is not wanted then error "Could not verify switch: " & elementId
    end tell
end switchControl

tell application "System Events"
    tell process "Live"
        set frontmost to true
    end tell
end tell

-- Verify the renamed track belongs to the prepared copy before any export.
set loaded to false
repeat 60 times
    tell application "System Events"
        tell process "Live"
            repeat with elem in entire contents of front window
                try
                    if (value of elem as text) is __FIRST__ then set loaded to true
                end try
            end repeat
        end tell
    end tell
    if loaded then exit repeat
    delay 0.5
end repeat
if not loaded then error "Render copy did not load. Resolve any save, plugin, or missing-media prompt in Live and retry."

set playButton to my elementById("Transport.Play")
tell application "System Events"
    if (value of playButton as text) is not "0" then error "Stop Live playback before exporting."
    tell process "Live" to keystroke "r" using {command down, shift down}
end tell
delay 0.3
my chooseControl("Base.RenderedTrack", "All Individual Tracks")
my switchControl("Base.RenderStemsBox.RenderStems", "Off")
my switchControl("Base.RenderAsLoopBox.RenderAsLoop", "Off")
my switchControl("Base.ConvertToMonoBox.ConvertToMono", "Off")
my switchControl("Base.NormalizeBox.Normalize", "Off")
my switchControl("Base.AnalysisFileBox.CreateAnalysisFile", "Off")
my switchControl("Base.EncodePcmBox.EncodePcm", "On")
my switchControl("Base.EncodeMp3Box.EncodeMp3", "Off")
my chooseControl("Base.FileTypeBox.FileType", "WAV")
my chooseControl("Base.FileTypeOptionsBox.FileTypeOptionsCardView.BitDepthBox.BitDepth", "32")
my setControl("Base.RenderStartBox.RenderStart.Bars", "1")
my setControl("Base.RenderStartBox.RenderStart.Beats", "1")
my setControl("Base.RenderStartBox.RenderStart.Subdivisions", "1")
my setControl("Base.RenderLengthBox.RenderLength.Bars", __BARS__)
my setControl("Base.RenderLengthBox.RenderLength.Beats", "0")
my setControl("Base.RenderLengthBox.RenderLength.Subdivisions", "0")
set exportButton to my elementById("Base.FinalButtonsBox.ExportButton")
tell application "System Events" to perform action "AXPress" of exportButton
delay 0.3
set filename to my elementById("saveAsNameTextField")
tell application "System Events" to set value of filename to "print"
tell application "System Events" to tell process "Live" to keystroke "g" using {command down, shift down}
delay 0.3
set pathField to my elementById("PathTextField")
tell application "System Events"
    set value of pathField to __DESTINATION__
    tell process "Live" to key code 36
end tell
delay 0.3
set saveButton to my elementById("OKButton")
tell application "System Events" to perform action "AXPress" of saveButton
return "Render started"
'''
    script = script.replace("__FIRST__", _literal(first)).replace("__BARS__", _literal(str(plan["bars"]))).replace("__DESTINATION__", _literal(str(renders)))
    completed = subprocess.run(["osascript", "-"], input=script, text=True, capture_output=True, timeout=120)
    if completed.returncode:
        raise SyncError("Ableton export stopped: " + completed.stderr.strip() +
                        "\nIf macOS requests Automation or Accessibility access, enable it for DAWSync/Python in System Settings.")
    log("Rendering in Live; waiting for complete WAV files…")
