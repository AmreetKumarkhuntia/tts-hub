#!/usr/bin/env bash
#
# run.sh — task runner for tts-hub.
#
# Usage: ./run.sh <command> [args]
#
#   setup            Full end-to-end setup (delegates to ./setup.sh; forwards flags)
#   dev              Start the server with auto-reload
#   start            Start the server without auto-reload
#   serve            Start via raw uvicorn (uvicorn app.main:app --reload)
#   download-model   Pre-download the Kokoro-82M weights (~330 MB)
#   test             Run the test suite (forwards extra args to pytest)
#   clean            Remove .venv, caches, and __pycache__
#   help             Show this help
#
set -euo pipefail

# Always run from the repo root (this script's directory).
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  sed -n '3,14p' "$0" | sed 's/^# \{0,1\}//; s/^#//'
}

download_model() {
  echo "Downloading Kokoro-82M weights (~330 MB on first run)..."
  # Force CPU for a pure fetch — the Hugging Face weight cache is device-independent,
  # which avoids mps/cuda init quirks. The server still loads onto KOKORO_DEVICE at run.
  uv run python - <<'PY'
import os
os.environ["KOKORO_DEVICE"] = "cpu"
from app.engines.kokoro_engine import KokoroEngine
KokoroEngine().load()
PY
  echo "Kokoro weights are cached and ready."
}

cmd="${1:-help}"
[ $# -gt 0 ] && shift || true

case "$cmd" in
  setup)          exec ./setup.sh "$@" ;;
  dev)            exec env RELOAD=true  uv run tts-hub ;;
  start)          exec env RELOAD=false uv run tts-hub ;;
  serve)          exec uv run uvicorn app.main:app --reload "$@" ;;
  download-model) download_model ;;
  test)           exec uv run pytest "$@" ;;
  clean)
    rm -rf .venv .pytest_cache
    find . -name '__pycache__' -type d -prune -exec rm -rf {} +
    echo "Cleaned .venv, caches, and __pycache__."
    ;;
  -h|--help|help) usage ;;
  *)
    echo "Unknown command: '$cmd'" >&2
    echo "Run './run.sh help' for usage." >&2
    exit 2
    ;;
esac
