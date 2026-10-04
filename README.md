# DAWSync

A local macOS app and a dependency-free REAPER Lua helper for audio collaboration
between Ableton Live 12 Standard and REAPER 7 on Windows. Google Drive transports
immutable revisions; native DAW projects remain available for further editing.

## Run on this Mac

Open `dist/DAWSync.app`, choose an Ableton `.als` file and a locally available
shared Google Drive folder, then click **Publish to REAPER**. The app creates an
isolated render copy, controls Live's export dialog, validates the WAV files, and
publishes a portable `.rpp` and manifest. It restores the source set afterward.

Use **Add project** in the sidebar for each song. Select a song to restore its
Ableton working set, shared folder, loop choice, effect tail, and revision history.
Existing single-project settings migrate automatically. New songs can share the
same exchange folder; each has its own persistent project ID.

Live must be stopped and any modal prompt resolved. macOS must allow DAWSync to
control System Events and provide Accessibility access. DAWSync checks named
controls and their resulting values, and never dismisses save/discard, missing
plugin, missing media, or permission prompts.

**Sync saved changes automatically** watches the selected source set. A save is
debounced for eight seconds. Incoming REAPER revisions are verified and imported
into a new Ableton working set. Original tracks remain in the copy with their
outputs disabled; returned audio starts at zero with warp off, unity gain, and
no inherited master processing. Generated imports are marked as seen so they
cannot start an export loop. The untouched original `.als` keeps its full state.

Automatic sync is off on app launch. Failed jobs pause it until the issue is
resolved. It watches the song currently selected in the sidebar. Competing
revisions remain separate and require an explicit selection.

Use the **Bandmate setup** button for the bandmate instructions,
or read [docs/WINDOWS.md](docs/WINDOWS.md).

## Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-desktop.txt
.venv/bin/python -m dawsync.app
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/build.py
```

Core conversion and validation use only the Python standard library. The GUI
uses PySide6; PyInstaller bundles the interpreter, Qt, scripts, and Live schema
fixture into a standalone `.app`.

The schema fixture contains no audio. Generated audio, real songs, local settings,
build outputs, and integration-test files are excluded from version control.

CLI commands:

```sh
python3 -m dawsync.cli inspect /path/to/song.als
python3 -m dawsync.cli prepare /path/to/song.als /path/to/new-job --loop
python3 -m dawsync.cli publish /path/to/song.als /path/to/exchange --project-id song-id
python3 -m dawsync.cli publish-renders /path/to/job /path/to/exchange --project-id song-id
python3 -m dawsync.cli validate /path/to/revision
python3 -m dawsync.cli import /path/to/revision /path/to/local-returns --original /path/to/song.als
```

The `publish-renders` command can finish a job after a manual/export-adapter
recovery. Render WAVs must be in `job/renders` and match the track IDs recorded in
`job/plan.json`; their lengths must match the requested range.

## Format and integrity

Each song has a persistent project ID. Each revision has a unique ID, source DAW,
parent revision, track IDs, timing metadata, and a complete SHA-256 file inventory.

```text
exchange/
  <project-id>/
    revisions/
      <revision-id>/
        manifest.json
        session.rpp
        DAWSync.lua
        codec.lua
        audio/
          t_als_17_bass.wav
          reference_main_main_mix.wav
```

Revisions are staged locally. The manifest is copied last, but Drive can reorder
uploads, so manifest arrival alone does not establish readiness: every file is
checked for presence, size, and checksum. Changed revision identities are rejected.
No Drive API credentials, web server, or external service is required.

Local settings, revision state, jobs, returns, and error logs are stored in
`~/Library/Application Support/DAWSync`. Set `DAWSYNC_HOME` to override this in
integration tests. Private source songs and generated audio are never build assets.

## Supported boundary

This release is audio-first: Arrangement timing, constant tempo/4/4, track labels,
markers, top-level buses, separate wet returns, printed audio, and a muted master
reference. Full editable clip interchange and variable tempo/time signatures are
future adapters. Do not treat baked individual tracks as an exact decomposition
of nonlinear bus or master processing. Compare with the reference mix.

The Live schema fixture was generated locally in Live 12.4.5. Live's project
format is version-specific; both generated `.als` sets and accessibility control
identifiers need validation after Live updates.
