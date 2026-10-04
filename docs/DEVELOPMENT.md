# DAWSync development guide

The sync engine uses only the Python standard library. The desktop app uses PySide6, and PyInstaller bundles Python, Qt, the REAPER helper, and the sanitized Live schema fixture into a macOS `.app`.

## Run from source

DAWSync requires Python 3.11 or newer.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-desktop.txt
.venv/bin/python -m dawsync.app
```

Run the automated checks with:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

## Build the macOS app

```sh
.venv/bin/python scripts/build.py
```

The result is `dist/DAWSync.app`. This is a local development build, not a notarized public installer. The current build machine produces an Apple Silicon app.

If the default Xcode toolchain requests license acceptance on a machine that already has the Command Line Tools, run the build with:

```sh
DEVELOPER_DIR=/Library/Developer/CommandLineTools .venv/bin/python scripts/build.py
```

## Command-line interface

```sh
python3 -m dawsync.cli inspect /path/to/song.als
python3 -m dawsync.cli prepare /path/to/song.als /path/to/new-job --loop
python3 -m dawsync.cli publish /path/to/song.als /path/to/exchange --project-id song-id
python3 -m dawsync.cli publish-renders /path/to/job /path/to/exchange --project-id song-id
python3 -m dawsync.cli validate /path/to/revision
python3 -m dawsync.cli import /path/to/revision /path/to/local-returns --original /path/to/song.als
```

`publish-renders` can finish a job after manual recovery from an export adapter problem. Rendered WAV files must be in `job/renders`, match the track IDs in `job/plan.json`, and have the requested duration.

## Revision format and integrity

Every song has a persistent project ID. Every revision records a unique ID, source DAW, parent revision, stable track IDs, timing metadata, and a SHA-256 inventory of its files.

Revisions are first staged locally. DAWSync copies `manifest.json` last, but it never assumes that manifest arrival means a Google Drive upload is complete. Consumers verify the presence, size, and checksum of every file before accepting a revision. An existing revision is never overwritten, and altered revision identities are rejected.

No Google Drive API credentials, web server, or hosted service is required. Drive for desktop transports ordinary files between the collaborators' machines.

## Local development data

DAWSync stores settings, revision state, jobs, returns, and logs in:

```text
~/Library/Application Support/DAWSync
```

Set `DAWSYNC_HOME` to an isolated directory for integration tests or development profiles. The repository excludes real songs, generated audio, local settings, packaged builds, and integration-test output. `fixtures/live12-seed.als` is a sanitized schema fixture with no bundled audio.

## Platform validation

The Live schema fixture was generated with Live 12.4.5. Ableton's project format and accessibility control identifiers can change between Live releases, so both generated sets and UI automation require validation after Live updates.

The target bandmate environment is REAPER 7 on Windows. Keep Windows-specific claims limited to behavior actually exercised on Windows; the current implementation has been tested locally on macOS with REAPER 7.81.
