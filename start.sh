#!/bin/bash
# Stop any old GitPublish, then start fresh on port 5062.
pkill -9 -f "app.py" 2>/dev/null
cd "$(dirname "$0")"
PORT="${PORT:-5062}" python3 app.py
