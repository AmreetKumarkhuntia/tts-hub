#!/usr/bin/env bash
#
# run.sh — task runner for tts-hub.
#
# Usage: ./run.sh <command> [args]
#
#   setup            Full end-to-end setup (delegates to ./setup.sh; forwards flags)
#   dev              Start the server with auto-reload
#   start            Start the server without auto-reload (foreground)
#   start-bg         Start in the background (nohup), logs -> server.log
#   stop             Stop the background server started by start-bg
#   logs             Tail the background server log (server.log)
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
  sed -n '3,17p' "$0" | sed 's/^# \{0,1\}//; s/^#//'
}

# Background-process bookkeeping (paths are relative to the repo root we cd'd to).
LOG_FILE="server.log"
PID_FILE="server.pid"

start_bg() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Already running (PID $(cat "$PID_FILE")). Stop it with: ./run.sh stop" >&2
    exit 1
  fi
  echo "Starting tts-hub in the background (logs -> $LOG_FILE) ..."
  nohup env RELOAD=false uv run tts-hub >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "Started (PID $(cat "$PID_FILE")). Tail logs: ./run.sh logs"
}

stop_bg() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")" && echo "Stopped (PID $(cat "$PID_FILE"))."
    rm -f "$PID_FILE"
  else
    echo "Not running (no live process in $PID_FILE)." >&2
    rm -f "$PID_FILE"
  fi
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
  start-bg)       start_bg ;;
  stop)           stop_bg ;;
  logs)           exec tail -f "$LOG_FILE" ;;
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
