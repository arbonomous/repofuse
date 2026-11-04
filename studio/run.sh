#!/bin/sh
# RepoFuse Studio - one-command local launch.
# Works from anywhere: finds the repo root relative to this script.
cd "$(dirname "$0")/.." || exit 1
echo "Starting RepoFuse Studio at http://127.0.0.1:8317/  (Ctrl+C to stop)"
exec python3 studio/serve.py 8317
