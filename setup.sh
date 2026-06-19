#!/usr/bin/env bash
#
# setup.sh — end-to-end setup for tts-hub.
#
# Takes a fresh checkout to "ready to run":
#   1. ensure `uv`            (installs it if missing)
#   2. ensure `espeak-ng`     (Kokoro phonemizer fallback; brew/apt)
#   3. install Python deps    (uv sync; uv also provisions Python >=3.10)
#   4. create .env            (auto-selects mps on Apple Silicon)
#   5. download model weights (~330 MB Kokoro-82M, unless --skip-model)
#   6. smoke-test the install (uv run pytest, unless --no-dev/--skip-tests)
#
# Usage:
#   ./setup.sh [--skip-model] [--device cpu|mps|cuda] [--no-dev] [--skip-tests]
#   ./run.sh setup --skip-model          # same thing via the task runner
#
set -euo pipefail

# Always operate from the repo root (this script's directory).
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ----------------------------------------------------------------------------- #
# Logging helpers (colored only when stdout is a TTY).
# ----------------------------------------------------------------------------- #
if [ -t 1 ]; then
  C_BLUE=$'\033[1;34m'; C_GREEN=$'\033[1;32m'; C_YELLOW=$'\033[1;33m'
  C_RED=$'\033[1;31m'; C_DIM=$'\033[2m'; C_RESET=$'\033[0m'
else
  C_BLUE=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_DIM=''; C_RESET=''
fi

STEP=0
step() { STEP=$((STEP + 1)); printf '\n%s[%d/6] %s%s\n' "$C_BLUE" "$STEP" "$1" "$C_RESET"; }
info() { printf '  %s\n' "$1"; }
ok()   { printf '  %s✓ %s%s\n' "$C_GREEN" "$1" "$C_RESET"; }
warn() { printf '  %s! %s%s\n' "$C_YELLOW" "$1" "$C_RESET"; }
err()  { printf '%sError: %s%s\n' "$C_RED" "$1" "$C_RESET" >&2; }

# ----------------------------------------------------------------------------- #
# Flags.
# ----------------------------------------------------------------------------- #
SKIP_MODEL=0
NO_DEV=0
SKIP_TESTS=0
DEVICE=""

usage() {
  cat <<'EOF'
setup.sh — end-to-end setup for tts-hub

Options:
  --skip-model            Don't pre-download the Kokoro weights (fetched lazily on first run)
  --device <cpu|mps|cuda> Force KOKORO_DEVICE in .env (default: mps on Apple Silicon, else cpu)
  --no-dev                Install runtime deps only (skip the dev extras and the smoke test)
  --skip-tests            Skip the final pytest smoke check
  -h, --help              Show this help

Examples:
  ./setup.sh
  ./setup.sh --skip-model --device cpu
  ./setup.sh --device mps
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-model) SKIP_MODEL=1 ;;
    --no-dev)     NO_DEV=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    --device)
      shift
      [ $# -gt 0 ] || { err "--device requires an argument (cpu|mps|cuda)"; exit 2; }
      DEVICE="$1"
      ;;
    --device=*)   DEVICE="${1#*=}" ;;
    -h|--help)    usage; exit 0 ;;
    *)            err "Unknown option: $1"; usage; exit 2 ;;
  esac
  shift
done

if [ -n "$DEVICE" ]; then
  case "$DEVICE" in
    cpu|mps|cuda) ;;
    *) err "--device must be one of: cpu, mps, cuda (got '$DEVICE')"; exit 2 ;;
  esac
fi

# ----------------------------------------------------------------------------- #
# Portable .env editor: set/replace KEY=VALUE without sed -i (differs mac/linux).
# ----------------------------------------------------------------------------- #
update_env() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  if grep -q "^${key}=" .env 2>/dev/null; then
    awk -v k="$key" -v v="$val" -F= 'BEGIN{OFS="="} $1==k{print k"="v; next} {print}' .env >"$tmp"
  else
    cat .env >"$tmp" 2>/dev/null || true
    printf '%s=%s\n' "$key" "$val" >>"$tmp"
  fi
  mv "$tmp" .env
}

# ----------------------------------------------------------------------------- #
# Ask the installed torch whether a device actually works (cuda/mps), so we can
# fall back to cpu instead of writing a device that explodes at runtime.
# Echoes "yes" if usable, "no" otherwise. Always "yes" for cpu.
# ----------------------------------------------------------------------------- #
device_available() {
  local dev="$1"
  [ "$dev" = "cpu" ] && { echo "yes"; return; }
  uv run python - "$dev" <<'PY' 2>/dev/null || echo "no"
import sys
dev = sys.argv[1]
try:
    import torch
    if dev == "cuda":
        ok = torch.cuda.is_available()
    elif dev == "mps":
        ok = torch.backends.mps.is_available()
    else:
        ok = True
except Exception:
    ok = False
print("yes" if ok else "no")
PY
}

# ----------------------------------------------------------------------------- #
# Detect platform.
# ----------------------------------------------------------------------------- #
OS="$(uname -s)"
ARCH="$(uname -m)"
printf '%stts-hub setup%s  %s(%s/%s)%s\n' "$C_GREEN" "$C_RESET" "$C_DIM" "$OS" "$ARCH" "$C_RESET"

# ----------------------------------------------------------------------------- #
# 1. Ensure uv.
# ----------------------------------------------------------------------------- #
step "Checking for uv"
if command -v uv >/dev/null 2>&1; then
  ok "uv already installed ($(uv --version 2>/dev/null || echo present))"
else
  info "uv not found — installing via https://astral.sh/uv ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Make uv available in this shell for the rest of the script.
  for d in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -d "$d" ]; then
      case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac
    fi
  done
  export PATH
  hash -r 2>/dev/null || true
  if command -v uv >/dev/null 2>&1; then
    ok "uv installed ($(uv --version 2>/dev/null || echo present))"
  else
    err "uv install did not land on PATH. See https://docs.astral.sh/uv/ and re-run."
    exit 1
  fi
fi

# ----------------------------------------------------------------------------- #
# 2. Ensure espeak-ng (phonemizer fallback; non-fatal if it can't be installed).
# ----------------------------------------------------------------------------- #
step "Checking for espeak-ng"
if command -v espeak-ng >/dev/null 2>&1; then
  ok "espeak-ng already installed"
else
  case "$OS" in
    Darwin)
      if command -v brew >/dev/null 2>&1; then
        info "Installing espeak-ng via Homebrew ..."
        brew install espeak-ng && ok "espeak-ng installed" \
          || warn "brew install espeak-ng failed; continuing (it's only a fallback)."
      else
        warn "Homebrew not found. Install it from https://brew.sh then run: brew install espeak-ng"
        warn "Continuing — espeak-ng is only a phonemizer fallback for some languages."
      fi
      ;;
    Linux)
      if command -v apt-get >/dev/null 2>&1; then
        info "Installing espeak-ng via apt-get (may prompt for sudo) ..."
        sudo apt-get update && sudo apt-get install -y espeak-ng && ok "espeak-ng installed" \
          || warn "apt-get install espeak-ng failed; continuing (it's only a fallback)."
      else
        warn "No apt-get found. Install espeak-ng with your package manager (it's only a fallback)."
      fi
      ;;
    *)
      warn "Unrecognized OS '$OS'. Install espeak-ng manually if you need the phonemizer fallback."
      ;;
  esac
fi

# ----------------------------------------------------------------------------- #
# 3. Install Python dependencies (uv provisions Python >=3.10 if needed).
# ----------------------------------------------------------------------------- #
step "Installing Python dependencies"
if [ "$NO_DEV" -eq 1 ]; then
  info "uv sync (runtime deps only) ..."
  uv sync
else
  info "uv sync --extra dev ..."
  uv sync --extra dev
fi
ok "Dependencies installed into .venv"

# ----------------------------------------------------------------------------- #
# 4. Create / update .env.
# ----------------------------------------------------------------------------- #
step "Configuring .env"
if [ -f .env ]; then
  ok ".env already exists — leaving it as-is"
else
  cp .env.example .env
  ok "Created .env from .env.example"
fi

# Pick the device we want, then verify it's actually usable — falling back to
# cpu if not. Priority: explicit --device > existing .env value > platform guess
# (mps on Apple Silicon, cuda on Linux, else cpu).
current_device="$(awk -F= '$1=="KOKORO_DEVICE"{print $2}' .env 2>/dev/null || true)"
if [ -n "$DEVICE" ]; then
  want="$DEVICE"
elif [ -n "$current_device" ]; then
  want="$current_device"
elif [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
  want="mps"
elif [ "$OS" = "Linux" ]; then
  want="cuda"
else
  want="cpu"
fi

if [ "$want" != "cpu" ] && [ "$(device_available "$want")" != "yes" ]; then
  warn "$want requested but not usable here (no device / torch can't see it) — falling back to cpu"
  want="cpu"
fi

update_env "KOKORO_DEVICE" "$want"
ok "Set KOKORO_DEVICE=$want"

# ----------------------------------------------------------------------------- #
# 5. Download model weights.
# ----------------------------------------------------------------------------- #
step "Downloading Kokoro model weights"
if [ "$SKIP_MODEL" -eq 1 ]; then
  warn "Skipped (--skip-model). Weights download lazily on first run, or: ./run.sh download-model"
else
  ./run.sh download-model
fi

# ----------------------------------------------------------------------------- #
# 6. Smoke test.
# ----------------------------------------------------------------------------- #
step "Verifying the install"
if [ "$NO_DEV" -eq 1 ] || [ "$SKIP_TESTS" -eq 1 ]; then
  info "Skipping pytest smoke check."
else
  if uv run pytest -q; then
    ok "Tests passed"
  else
    warn "pytest reported failures — the server may still run; review the output above."
  fi
fi

# ----------------------------------------------------------------------------- #
# Done.
# ----------------------------------------------------------------------------- #
printf '\n%sSetup complete.%s\n' "$C_GREEN" "$C_RESET"
cat <<EOF

Next steps:
  ./run.sh dev       # start with auto-reload   (or: uv run tts-hub)
  ./run.sh start     # start without auto-reload
  ./run.sh test      # run the test suite

Then open the tester:  http://localhost:8000/test.html
EOF
