# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ARGOS Absolute (Windows)
#
# Build:  pyinstaller argos.spec
# Output: dist/ARGOS.exe  (single portable executable)

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

block_cipher = None

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Embed the web dashboard
        (str(ROOT / 'index.html'), '.'),
        # Embed buildozer spec so in-app APK build can reference it
        (str(ROOT / 'buildozer.spec'), '.'),
    ],
    hiddenimports=[
        # FastAPI / web stack
        'fastapi',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'starlette',
        'starlette.routing',
        'anyio',
        'anyio._backends._asyncio',
        # Standard lib extras sometimes missed by the hook
        'email.mime.text',
        'email.mime.multipart',
        'ctypes',
        'ctypes.wintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude heavy optional packages not needed for Windows terminal/web mode
    excludes=['kivy', 'pygame', 'numpy', 'torch', 'sklearn'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ARGOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Single-file portable executable
    onefile=True,
    console=True,          # keep console window so REPL/terminal mode is visible
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows metadata shown in file properties
    version_file=None,
    icon=None,
)
