#!/bin/bash
# =============================================================================
# GitPublish — build a standalone macOS app (+ .dmg installer)
# Run this ON A MAC (it cannot be cross-built from Linux/Windows).
#
#   bash packaging/build_app.sh            # build dist/GitPublish.app + .dmg
#   INSTALL=1 bash packaging/build_app.sh  # ...and copy it into /Applications
#
# The app is self-contained (bundles Python + a native window), opens the
# dashboard in its own window, shows in the Dock/Launchpad, and quits with Cmd+Q.
#
# Signing + notarization are OPTIONAL (only needed to remove the Gatekeeper
# warning on OTHER people's Macs). Leave DEV_ID blank for an ad-hoc-signed app.
# =============================================================================
set -e
cd "$(dirname "$0")/.."            # repo root (folder with app.py)
ROOT="$(pwd)"
VERSION="$(cat VERSION 2>/dev/null || echo 1.0.0)"

DEV_ID="${DEV_ID:-}"                  # e.g. "Developer ID Application: Your Name (TEAMID)"
NOTARY_PROFILE="${NOTARY_PROFILE:-}"  # keychain profile name (see BUILD.md)

echo "==> GitPublish $VERSION"
[ "$(uname)" = "Darwin" ] || { echo "This script must run on macOS."; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found. Install Xcode CLT: xcode-select --install"; exit 1; }
command -v git >/dev/null || { echo "git not found (xcode-select --install)"; exit 1; }

# ---- private build venv (avoids PEP 668 'externally-managed-environment') ----
VENV="$ROOT/.build-venv"
PY="$VENV/bin/python"
[ -x "$PY" ] || { echo "==> Creating build venv (.build-venv)"; python3 -m venv "$VENV"; }
# Ignore any personal pip config (e.g. an extra index like pypi.ngc.nvidia.com
# that isn't reachable) and always install from the official PyPI.
export PIP_CONFIG_FILE=/dev/null
unset PIP_EXTRA_INDEX_URL
export PIP_INDEX_URL="https://pypi.org/simple"
echo "==> Installing build deps (pyinstaller, pywebview)"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet --upgrade pyinstaller pywebview

# ---- icon: packaging/AppIcon.png -> packaging/AppIcon.icns ------------------
if [ -f packaging/AppIcon.png ] && { [ ! -f packaging/AppIcon.icns ] || [ packaging/AppIcon.png -nt packaging/AppIcon.icns ]; }; then
  echo "==> Building AppIcon.icns"
  SET="$(mktemp -d)/AppIcon.iconset"; mkdir -p "$SET"
  for s in 16 32 128 256 512; do
    sips -z $s $s           packaging/AppIcon.png --out "$SET/icon_${s}x${s}.png"    >/dev/null
    sips -z $((s*2)) $((s*2)) packaging/AppIcon.png --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$SET" -o packaging/AppIcon.icns
fi

echo "==> Cleaning previous build"
rm -rf build dist

echo "==> Building with PyInstaller"
"$PY" -m PyInstaller --noconfirm --distpath dist --workpath build packaging/GitPublish.spec

APP="dist/GitPublish.app"
[ -d "$APP" ] || { echo "Build failed: $APP not produced."; exit 1; }
echo "==> Built $APP"

# ---- signing ---------------------------------------------------------------
if [ -n "$DEV_ID" ]; then
  echo "==> Code-signing (hardened runtime)"
  codesign --deep --force --timestamp --options runtime \
    --entitlements packaging/entitlements.plist --sign "$DEV_ID" "$APP"
  codesign --verify --strict --verbose=2 "$APP"
  if [ -n "$NOTARY_PROFILE" ]; then
    echo "==> Notarizing (uploads to Apple and waits)"
    ZIP="dist/GitPublish.zip"
    /usr/bin/ditto -c -k --keepParent "$APP" "$ZIP"
    xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$APP" && xcrun stapler validate "$APP"
    rm -f "$ZIP"
  fi
else
  echo "==> Ad-hoc signing (no Apple account needed)"
  codesign --force --deep --sign - "$APP" 2>/dev/null || true
fi

# ---- .dmg installer (drag to Applications) ---------------------------------
if [ "${MAKE_DMG:-1}" = "1" ]; then
  DMG="dist/GitPublish-$VERSION.dmg"
  echo "==> Building $DMG"
  STAGE="$(mktemp -d)"
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  hdiutil create -volname "GitPublish $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
  rm -rf "$STAGE"
  [ -n "$DEV_ID" ] && codesign --force --sign "$DEV_ID" "$DMG" || true
fi

# ---- optional: install into /Applications ----------------------------------
if [ "${INSTALL:-0}" = "1" ]; then
  echo "==> Installing to /Applications"
  osascript -e 'quit app "GitPublish"' >/dev/null 2>&1 || true
  rm -rf "/Applications/GitPublish.app"
  cp -R "$APP" /Applications/
  xattr -dr com.apple.quarantine /Applications/GitPublish.app 2>/dev/null || true
  echo "    Installed: /Applications/GitPublish.app (Launchpad / Spotlight: 'GitPublish')"
fi

echo ""
echo "Done:"
echo "  app -> $ROOT/$APP"
ls dist/*.dmg >/dev/null 2>&1 && echo "  dmg -> $ROOT/$(ls dist/*.dmg | head -1)  (open it, drag GitPublish into Applications)"
