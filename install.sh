#!/bin/bash
# Install GitPublish as a double-clickable macOS app.
cd "$(dirname "$0")"
APP="GitPublish.app"

if [ ! -d "$APP" ]; then echo "GitPublish.app not found next to this script."; exit 1; fi

# make the launcher executable and clear the 'downloaded' quarantine flag
chmod +x "$APP/Contents/MacOS/GitPublish"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null

echo "GitPublish.app is ready — double-click it in Finder to launch."
echo ""
read -r -p "Also install it to /Applications (so it shows in Launchpad)? [y/N] " a
if [ "$a" = "y" ] || [ "$a" = "Y" ]; then
  rm -rf "/Applications/$APP" 2>/dev/null
  cp -R "$APP" /Applications/ && echo "Installed to /Applications/$APP"
  echo "(The app still runs the code in this folder, so your updates keep working.)"
fi
echo ""
echo "First launch tip: if macOS says 'unidentified developer',"
echo "right-click the app → Open → Open. You only do this once."
