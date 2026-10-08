# PyInstaller entry point. Only the application logo is bundled as data;
# user databases, Telegram sessions, .env files, and developer files are excluded.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


datas = [("app/assets/vaulthaven_logo.svg", "app/assets")]
binaries = []
hiddenimports = []

for package in ("telethon", "qasync"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests", "pytest", "unittest"],
    noarchive=False,
    optimize=1,
)

# The local build environment can expose Poppler's ICU 78 DLLs on PATH. Those
# DLLs export version-suffixed ICU symbols, while Qt6Core imports the
# Windows-provided, unsuffixed ICU API. Bundling Poppler's copy makes QtCore
# fail to load with ERROR_PROC_NOT_FOUND (WinError 127). Keep ICU DLLs shipped
# by PySide6 itself, but leave unrelated PATH copies out of the application.
a.binaries = [
    binary
    for binary in a.binaries
    if not (
        Path(binary[0]).name.lower().startswith("icu")
        and "pyside6" not in str(binary[1]).lower()
    )
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    [],
    name="VaultHaven",
    icon="app/assets/vaulthaven.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    exclude_binaries=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VaultHaven",
)
