# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Fin — onedir build with Mac BUNDLE.

Build: pyinstaller fin.spec
Output (Mac): dist/Fin.app
Output (Win): dist/Fin/
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH)

# ── Data files to bundle ──────────────────────────────────────────────────────
datas = [
    (str(ROOT / "frontend"), "frontend"),
    (str(ROOT / "config"), "config"),
    (str(ROOT / "assets"), "assets"),
]

# Heavy packages that ship binary extensions + data
binaries_pandas, datas_pandas, hiddenimports_pandas = collect_all("pandas")
binaries_scipy, datas_scipy, hiddenimports_scipy = collect_all("scipy")

datas += datas_pandas + datas_scipy
datas += collect_data_files("exchange_calendars")
datas += collect_all("akshare")[1]  # data files only

binaries = binaries_pandas + binaries_scipy

# ── Hidden imports ────────────────────────────────────────────────────────────
hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "sqlalchemy.dialects.sqlite",
    "pydantic_core",
    # pystray: _darwin is loaded lazily inside a function so PyInstaller
    # cannot trace it; AppKit/Foundation/objc/PyObjCTools are its imports.
    "pystray._util",
    "pystray._darwin",
    "AppKit",
    "Foundation",
    "objc",
    "PyObjCTools",
    "PyObjCTools.MachSignals",
]
hiddenimports += hiddenimports_pandas + hiddenimports_scipy

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter", "_tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Fin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=sys.platform != "darwin",  # UPX invalidates Mac binary format
    console=False,
    icon=str(ROOT / "assets" / "fin.icns") if sys.platform == "darwin" else str(ROOT / "assets" / "tray_icon.png"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=sys.platform != "darwin",
    upx_exclude=[],
    name="Fin",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Fin.app",
        icon=str(ROOT / "assets" / "fin.icns"),
        bundle_identifier="com.fin.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "1.0.0",
            "LSUIElement": True,  # hide Dock icon — menu bar only
            "NSAppTransportSecurity": {
                "NSAllowsLocalNetworking": True,
            },
        },
    )
