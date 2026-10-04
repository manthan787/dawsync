# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
root = Path(SPECPATH)

a = Analysis(
    [str(root / 'scripts/desktop.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'fixtures/live12-seed.als'), 'fixtures'), (str(root / 'reaper/DAWSync.lua'), 'reaper'), (str(root / 'reaper/codec.lua'), 'reaper'), (str(root / 'docs/WINDOWS.md'), 'docs')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DAWSync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DAWSync',
)
app = BUNDLE(
    coll,
    name='DAWSync.app',
    icon=None,
    bundle_identifier='local.dawsync.app',
    info_plist={
        'CFBundleShortVersionString': '0.1.0',
        'NSAppleEventsUsageDescription': 'DAWSync controls Ableton export controls through System Events to render your chosen song.',
        'NSHighResolutionCapable': True,
    },
)
