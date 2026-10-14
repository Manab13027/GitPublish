#!/bin/bash
# GitPublish launcher — zero dependencies (Python 3.8+ and git).
cd "$(dirname "$0")"
command -v git >/dev/null 2>&1 || { echo "git is required. Install Xcode command line tools: xcode-select --install"; exit 1; }
# Point it at your projects folder if different:
#   export PROJECTS_ROOT=~/code
echo "[gitpublish] starting on http://localhost:${PORT:-5060}"
python3 app.py
