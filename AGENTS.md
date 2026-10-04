# DAWSync development

- The user wants focused commits pushed at tested milestones during development.
  Use `origin` (`git@github.com:manthan787/dawsync.git`) and the `main` branch.
  Push completed changes periodically; avoid leaving finished work only locally.
- Keep real songs, generated audio, local settings, diagnostic logs, `.venv`,
  and packaged builds out of commits. The sanitized Live schema fixture is code
  support data, not a source song.
- Run `.venv/bin/python -m unittest discover -s tests -v` for conversion,
  configuration, or desktop behavior changes. Inspect the packaged interface
  after meaningful layout changes.
- Build with `.venv/bin/python scripts/build.py`. On this Mac, use
  `DEVELOPER_DIR=/Library/Developer/CommandLineTools` for Git/build commands when
  the default Xcode toolchain requests license acceptance; do not accept a license
  or change the system's selected developer directory automatically.
- Preserve originals and immutable revisions. Verify platform-specific behavior
  on that platform before claiming it has been tested there.
