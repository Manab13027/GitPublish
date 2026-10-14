# Giving users downloadable installers (.exe / .dmg / AppImage)

GitHub can compile your app on Windows, macOS and Linux for free and attach the
results to a **Release**, so users just click-download the binary for their OS —
no Python, no building. This is how apps like Sentinel ship.

## For a Python app (PyInstaller) — automated here

1. Add the workflow to the app (fills in the app name + entry file):
   ```bash
   cd ~/Documents/Projects_Folder/GitPublish
   ./add_release.sh ../FileOrganizer FileOrganizer FileOrganizerGuiModernV3.py
   ```
2. Publish the app to GitHub (GitPublish, or git push).
3. Tag a version — this is what triggers the build:
   ```bash
   cd ../FileOrganizer
   git add .github && git commit -m "add release workflow" && git push
   git tag v1.0.0 && git push --tags
   ```
4. Watch the repo's **Actions** tab build on all 3 OSes, then check **Releases** —
   you'll have `FileOrganizer-windows.exe`, `FileOrganizer-macos`, `FileOrganizer-linux`.

Re-release later by pushing a new tag (`v1.1.0`, …).

### Notes / limits
- The default workflow builds a **one-file** binary from your entry script. If
  your app bundles data (templates, assets), add
  `--add-data "folder:folder"` to the PyInstaller line in the workflow, the same
  way GitPublish's own `packaging/build_app.sh` does.
- GUI apps: add `--windowed` for no console window.
- The macOS binary from GitHub is **unsigned** — first launch needs right-click →
  Open (same as any unsigned app). Signing needs a paid Apple account.
- The Windows `.exe` may trip SmartScreen until it gains reputation; that's normal
  for unsigned binaries.

## For an Electron app (electron-builder) — like Sentinel

Electron apps don't use PyInstaller. They build with **electron-builder** in CI,
which produces `.exe` (NSIS), `.dmg`, and `.AppImage`. Use a workflow that runs
`npm ci && npm run build:win / build:mac / build:linux` on each OS runner and
uploads the installers — your `sentinel-desktop/github-build.yml` is a working
example to copy.

## What can't be a single downloadable binary
- **Web apps** (FastAPI + React: MarketAnalysis, VideoEditor/ClipForge,
  Nifty_Scalper, ReverseSearchApp) run as a server + frontend, so they're
  *deployed* (or run with their `start.sh`), not shipped as one `.exe`. You can
  still release a zipped bundle or a Docker image via a similar workflow.
- **Swift** (SpaceUtilizer): build with `swift build -c release` in a macOS
  runner and upload the binary.
