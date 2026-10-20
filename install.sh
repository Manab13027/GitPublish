#!/bin/bash
# Build GitPublish as a standalone Mac app and install it into /Applications.
#   ./install.sh
# Afterwards launch it from Launchpad, Spotlight ("GitPublish") or the Dock.
# Re-run this after changing the code to update the installed app.
set -e
cd "$(dirname "$0")"
INSTALL=1 bash packaging/build_app.sh
echo ""
echo "Launching GitPublish…"
open /Applications/GitPublish.app
