from pathlib import Path
import subprocess
import sys
import os

root = Path(__file__).resolve().parent.parent
args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(root / "DAWSync.spec")]
env = os.environ.copy()
if Path("/Library/Developer/CommandLineTools/usr/bin/lipo").exists():
    env.setdefault("DEVELOPER_DIR", "/Library/Developer/CommandLineTools")
subprocess.run(args, cwd=root, check=True, env=env)
