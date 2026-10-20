# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the GitPublish desktop app.
# Used by packaging/build_app.sh — run from the repo root:
#   pyinstaller --noconfirm packaging/GitPublish.spec
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
VERSION = open(os.path.join(ROOT, "VERSION")).read().strip() if os.path.exists(os.path.join(ROOT, "VERSION")) else "1.0.0"
ICON = os.path.join(ROOT, "packaging", "AppIcon.icns")
ICON = ICON if os.path.exists(ICON) else None

a = Analysis(
    [os.path.join(ROOT, "desktop.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "templates"), "templates")],
    hiddenimports=["app", "ghcore", "readme_gen", "license_gen", "webview.platforms.cocoa"],
    excludes=["tkinter", "webview.platforms.qt", "webview.platforms.gtk",
              "webview.platforms.winforms", "webview.platforms.edgechromium",
              "webview.platforms.cef", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GitPublish",
    console=False,
    argv_emulation=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="GitPublish")

app = BUNDLE(
    coll,
    name="GitPublish.app",
    icon=ICON,
    bundle_identifier="com.fighter.gitpublish",
    version=VERSION,
    info_plist={
        "CFBundleName": "GitPublish",
        "CFBundleDisplayName": "GitPublish",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSApplicationCategoryType": "public.app-category.developer-tools",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "GitPublish",
        # the window loads the dashboard from its own local server
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    },
)
