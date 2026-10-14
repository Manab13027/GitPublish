#!/bin/bash
# =============================================================================
# GitPublish — build a standalone, signed, notarized macOS .app
# Run this ON A MAC (it cannot be cross-built from Linux/Windows).
#
#   bash packaging/build_app.sh
#
# Produces: dist/GitPublish.app  (self-contained — bundles Python, no install)
#
# Signing + notarization are OPTIONAL (only needed to remove the Gatekeeper
# warning on OTHER people's Macs). Leave the variables blank for a normal
# unsigned app + .dmg installer — exactly how an app like Sentinel works.
# It's ad-hoc signed and packaged into dist/GitPublish.dmg automatically.
# =============================================================================
set -e
cd "$(dirname "$0")/.."            # repo root (folder with app.py)
ROOT="$(pwd)"

# ---- fill these for a SIGNED + NOTARIZED build (else leave blank) -----------
DEV_ID="${DEV_ID:-}"               # e.g. "Developer ID Application: Your Name (TEAMID)"
NOTARY_PROFILE="${NOTARY_PROFILE:-}"  # a keychain profile name you created (see BUILD.md)
# -----------------------------------------------------------------------------

echo "==> Checking tools"
command -v python3 >/dev/null || { echo "python3 not found. Install Xcode CLT: xcode-select --install"; exit 1; }
command -v git >/dev/null || { echo "git not found (xcode-select --install)"; exit 1; }

# Build inside a private virtual environment — avoids the macOS
# 'externally-managed-environment' (PEP 668) error and keeps system Python clean.
VENV="$ROOT/.build-venv"
PY="$VENV/bin/python"
if [ ! -x "$PY" ]; then
  echo "==> Creating build virtual environment (.build-venv)"
  python3 -m venv "$VENV"
fi
echo "==> Installing PyInstaller into the venv"
"$PY" -m pip install --upgrade pip >/dev/null
"$PY" -m pip install --upgrade pyinstaller >/dev/null

echo "==> Cleaning previous build"
rm -rf build dist GitPublish.spec

echo "==> Building with PyInstaller"
"$PY" -m PyInstaller \
  --name GitPublish \
  --windowed \
  --noconfirm \
  --add-data "templates:templates" \
  ${ICON:+--icon "$ICON"} \
  app.py

APP="dist/GitPublish.app"
[ -d "$APP" ] || { echo "Build failed: $APP not produced."; exit 1; }
echo "==> Built $APP"

if [ -n "$DEV_ID" ]; then
  echo "==> Code-signing (hardened runtime)"
  codesign --deep --force --timestamp --options runtime \
    --entitlements packaging/entitlements.plist \
    --sign "$DEV_ID" "$APP"
  codesign --verify --strict --verbose=2 "$APP"
  echo "==> Signed."

  if [ -n "$NOTARY_PROFILE" ]; then
    echo "==> Notarizing (this uploads to Apple and waits)"
    ZIP="dist/GitPublish.zip"
    /usr/bin/ditto -c -k --keepParent "$APP" "$ZIP"
    xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
    echo "==> Stapling the notarization ticket"
    xcrun stapler staple "$APP"
    xcrun stapler validate "$APP"
    rm -f "$ZIP"
    echo "==> Notarized + stapled. No Gatekeeper warning on any Mac."
  else
    echo "==> Signed but NOT notarized (set NOTARY_PROFILE to notarize)."
  fi
else
  # No paid Apple account needed — ad-hoc sign so it runs cleanly (exactly how
  # an unsigned app like Sentinel works). First open on another Mac may need
  # right-click → Open once; on this Mac it just runs.
  echo "==> Ad-hoc signing (no Apple account needed)"
  codesign --force --deep --sign - "$APP" 2>/dev/null || true
fi

# ---- package as a .dmg installer (like Sentinel), no account needed ---------
if [ "${MAKE_DMG:-1}" = "1" ]; then
  echo "==> Building disk image (GitPublish.dmg)"
  STAGE="$(mktemp -d)"
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  rm -f "dist/GitPublish.dmg"
  hdiutil create -volname "GitPublish" -srcfolder "$STAGE" -ov -format UDZO "dist/GitPublish.dmg" >/dev/null
  rm -rf "$STAGE"
  echo "==> dist/GitPublish.dmg ready — double-click it, then drag GitPublish into Applications."
fi

echo ""
echo "Done:"
echo "  app  -> $ROOT/$APP"
[ -f "dist/GitPublish.dmg" ] && echo "  dmg  -> $ROOT/dist/GitPublish.dmg  (installer — share or keep this)"
echo "Drag the app to /Applications, or open the .dmg and drag it in."
