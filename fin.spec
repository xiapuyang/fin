# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Fin — onedir build with Mac BUNDLE.

Build: pyinstaller fin.spec
Output (Mac): dist/Fin.app
Output (Win): dist/Fin/
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, collect_dynamic_libs
from fin._version import __version__ as APP_VERSION

ROOT = Path(SPECPATH)

# ── Data files to bundle ──────────────────────────────────────────────────────
datas = [
    (str(ROOT / "frontend"), "frontend"),
    (str(ROOT / "config"), "config"),
    # assets/ without screenshots — runtime only needs the tray icon and icns
    (str(ROOT / "assets" / "tray_icon.png"), "assets"),
    (str(ROOT / "assets" / "fin.icns"), "assets"),
]

# pandas: full binary collection (collect_dynamic_libs misses some .so files)
binaries_pandas = collect_all("pandas")[0]

# scipy is not used by fin — omit entirely

datas += collect_data_files("exchange_calendars")
datas += collect_all("akshare")[1]  # data files only

binaries = binaries_pandas

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
    # pystray: backend modules are loaded lazily so PyInstaller cannot trace them.
    "pystray._util",
]

# Platform-specific pystray backends (each backend only exists on its target OS)
if sys.platform == "darwin":
    hiddenimports += [
        "pystray._darwin",
        "AppKit",
        "Foundation",
        "objc",
        "PyObjCTools",
        "PyObjCTools.MachSignals",
    ]
elif sys.platform == "win32":
    hiddenimports += ["pystray._win32"]

# pandas hiddenimports handled by hooks/hook-pandas.py

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["hooks"],
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
            "CFBundleShortVersionString": APP_VERSION,
            "LSUIElement": True,  # hide Dock icon — menu bar only
            "NSAppTransportSecurity": {
                "NSAllowsLocalNetworking": True,
            },
        },
    )
