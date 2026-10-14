#!/bin/bash
# Add a cross-platform build-and-release GitHub Actions workflow to an app.
#
# Usage:  ./add_release.sh <app-folder> <AppName> [entry.py]
#   e.g.  ./add_release.sh ~/Documents/Projects_Folder/FileOrganizer FileOrganizer FileOrganizerGuiModernV3.py
#
# After it's added: commit, then tag a version to trigger the build:
#   git add .github && git commit -m "add release workflow" && git push
#   git tag v1.0.0 && git push --tags
# GitHub then builds Windows/macOS/Linux binaries and puts them on Releases.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
APPDIR="$1"; NAME="$2"; ENTRY="${3:-app.py}"

[ -n "$NAME" ] || { echo "Usage: ./add_release.sh <app-folder> <AppName> [entry.py]"; exit 1; }
[ -d "$APPDIR" ] || { echo "folder not found: $APPDIR"; exit 1; }
[ -f "$HERE/packaging/build-release.yml" ] || { echo "template missing: packaging/build-release.yml"; exit 1; }

mkdir -p "$APPDIR/.github/workflows"
sed -e "s|__APP__|$NAME|g" -e "s|__ENTRY__|$ENTRY|g" \
  "$HERE/packaging/build-release.yml" > "$APPDIR/.github/workflows/build-release.yml"

echo "Added: $APPDIR/.github/workflows/build-release.yml  (app=$NAME entry=$ENTRY)"
echo ""
echo "Next, inside that app:"
echo "  git add .github && git commit -m 'add release workflow' && git push"
echo "  git tag v1.0.0 && git push --tags"
echo "→ Windows/macOS/Linux binaries will appear on the repo's Releases page."
