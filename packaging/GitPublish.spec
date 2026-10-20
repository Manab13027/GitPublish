# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for GitPublish's bundled local server (app.py).
# The Mac app itself is a small native Swift shell (packaging/macos/main.swift)
# that runs this server and shows the dashboard in a WebKit window.
# Used by packaging/build_app.sh:  pyinstaller --noconfirm packaging/GitPublish.spec
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "templates"), "templates")],
    hiddenimports=["ghcore", "readme_gen", "license_gen"],
    excludes=["tkinter", "webview"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="gitpublish-server",
          console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="gitpublish-server")
