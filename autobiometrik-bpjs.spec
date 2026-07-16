# PyInstaller spec — build a single-file Windows executable.
#
#   pip install pyinstaller
#   pyinstaller autobiometrik-bpjs.spec
#
# Output: dist/autobiometrik-bpjs.exe
# Ship config.example.json next to the exe (renamed to config.json) so the
# operator can set executable paths and FRISTA credentials without a rebuild.

from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None

# Single source of truth for the app icon is autobiometrik/icon.png. Generate
# the multi-size icon.ico the Windows exe needs from it at build time, so
# swapping the icon is just "replace icon.png and rebuild" — no hand-kept .ico.
from PIL import Image  # noqa: E402 - build-time only

_icon_png = "autobiometrik/icon.png"
_icon_ico = "autobiometrik/icon.ico"
Image.open(_icon_png).convert("RGBA").resize((256, 256), Image.LANCZOS).save(
    _icon_ico,
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)

# PyAutoIt loads AutoItX3.dll / AutoItX3_x64.dll from its lib/ folder via
# ctypes at import time — invisible to PyInstaller's analysis, so collect
# them explicitly or the frozen exe runs with autoit unavailable.
autoit_binaries = collect_dynamic_libs("autoit")

a = Analysis(
    # run.py is an absolute-import shim: the package __main__.py can't be the
    # entry file because PyInstaller runs it outside the package, breaking its
    # relative import.
    ["run.py"],
    pathex=[],
    binaries=autoit_binaries,
    datas=[("autobiometrik/icon.png", "autobiometrik")],
    hiddenimports=["autoit", "pystray._win32"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
    name="autobiometrik-bpjs",
    icon="autobiometrik/icon.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
