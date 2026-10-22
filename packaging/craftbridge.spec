# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 单文件打包配置。

用法（在项目根目录）：
    python -m PyInstaller --noconfirm --distpath dist/qt --workpath build/qt packaging/craftbridge.spec
产物：dist/qt/OnionMinecraftLauncher.exe

说明：
- Qt 前端使用项目私有 .deps/qt 中的 PySide6 Essentials；旧 Tk 前端不包含在新产物中。
- Python 游戏管理、下载、账号和恢复模块沿用；Pillow 仅用于开发验收，不随 Qt 产品打包。
- 不打包游戏、运行配置或账号：统一数据保存到 exe 旁隐藏的 onionmcl.json，
  游戏默认使用 F:\\.minecraft，runtime 保存在 exe 旁，
  Java 与游戏文件按需下载，保持安装包体积最小。
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # SPECPATH 是 spec 所在目录（packaging/）

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT), str(ROOT / ".deps" / "qt")],
    binaries=[],
    datas=[(str(ROOT / "assets" / "craftbridge.ico"), "assets"),
           (str(ROOT / "assets" / "microsoft-app.json"), "assets")],
    hiddenimports=["PySide6.QtWidgets"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests", "scripts", "pytest", "numpy", "matplotlib", "pandas", "tkinter", "launcher.ui", "PIL", "unittest"],
    noarchive=False,
    optimize=0,
)
# The launcher paints QWidgets/QImages with QPainter and has no OpenGL/Quick
# surface. The 20 MB llvmpipe DLL is an OpenGL implementation, not a QWidget
# raster renderer. Keep all language files and Qt plugins (including alternate
# platforms and image codecs); only omit this unused software OpenGL library.
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower()!='opengl32sw.dll']
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OnionMinecraftLauncher",
    version=str(ROOT / "packaging" / "windows-version.txt"),
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
    icon=str(ROOT / "assets" / "craftbridge.ico"),
)
