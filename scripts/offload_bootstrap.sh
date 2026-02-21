#!/usr/bin/env bash
set -euo pipefail

# One-shot bootstrap for the local Ollama offload worker.
# - Installs GitHub CLI ("gh") WITHOUT pacman (downloads release tarball)
# - Authenticates gh and configures git credential helper
# - Ensures repo clone exists under ~/.nusa_offload_worker/repo
# - Starts/restarts scripts/offload_worker.sh
#
# Safe to re-run.

log() { printf '[offload-bootstrap] %s\n' "$*"; }

need() {
  command -v "$1" >/dev/null 2>&1 || {
    log "Missing required command: $1"
    exit 1
  }
}

need git
need curl
need tar
need uname
need install

BRANCH="${BRANCH:-cursor/liquidgov-website-definition-d045}"
REPO_URL="${REPO_URL:-https://github.com/Bbottin92/Cursor.git}"
WORKDIR="${WORKDIR:-$HOME/.nusa_offload_worker}"
REPO_DIR="${REPO_DIR:-$WORKDIR/repo}"
LOG_FILE="${LOG_FILE:-$HOME/.nusa_offload_worker.log}"
OLLAMA_BASE="${OLLAMA_BASE:-http://127.0.0.1:11434}"

GIT_NAME="${GIT_NAME:-Brandon Bottin}"
GIT_EMAIL="${GIT_EMAIL:-founder@liquidgov.us}"

tty_exec() {
  if [[ -r /dev/tty && -w /dev/tty ]]; then
    "$@" </dev/tty >/dev/tty 2>&1
  else
    "$@" 2>&1
  fi
}

log "Checking Ollama at: $OLLAMA_BASE"
if ! curl -fsS --max-time 3 "${OLLAMA_BASE%/}/api/tags" >/dev/null 2>&1; then
  log "ERROR: Ollama not reachable at $OLLAMA_BASE"
  log "Start it, then rerun. Quick check:"
  log "  curl -sS \"$OLLAMA_BASE/api/tags\""
  exit 1
fi

mkdir -p "$WORKDIR"

if [[ ! -d "$REPO_DIR/.git" ]]; then
  log "Cloning repo to: $REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi

log "Setting git identity (global)"
git config --global user.name "$GIT_NAME" || true
git config --global user.email "$GIT_EMAIL" || true

install_gh_to_local_bin() {
  local dest="$HOME/.local/bin/gh"
  mkdir -p "$(dirname "$dest")"

  local arch
  arch="$(uname -m)"
  local gh_arch
  case "$arch" in
    x86_64) gh_arch="amd64" ;;
    aarch64|arm64) gh_arch="arm64" ;;
    *)
      log "Unsupported architecture for gh: $arch"
      return 1
      ;;
  esac

  local ver tmp url folder final_url tag

  # Allow manual override if needed.
  ver="${GH_VERSION:-}"

  # Robust version detection without GitHub API (avoids rate limits / JSON parsing).
  if [[ -z "$ver" ]]; then
    final_url="$(curl -fsSL -o /dev/null -w "%{url_effective}" -L "https://github.com/cli/cli/releases/latest" || true)"
    tag="${final_url##*/}"
    tag="${tag%%\?*}"
    ver="${tag#v}"
  fi

  if [[ -z "$ver" ]]; then
    log "Could not detect gh version."
    log "Set it manually and re-run, e.g.:"
    log "  GH_VERSION=2.86.0 ./scripts/offload_bootstrap.sh"
    return 1
  fi

  url="https://github.com/cli/cli/releases/download/v${ver}/gh_${ver}_linux_${gh_arch}.tar.gz"
  tmp="$(mktemp -d)"

  log "Downloading gh $ver ($gh_arch) ..."
  curl -fsS -L "$url" -o "$tmp/gh.tgz"
  tar -xzf "$tmp/gh.tgz" -C "$tmp"

  folder="$tmp/gh_${ver}_linux_${gh_arch}"
  if [[ ! -x "$folder/bin/gh" ]]; then
    log "Downloaded gh archive missing bin/gh"
    return 1
  fi

  install -m 755 "$folder/bin/gh" "$dest"
  rm -rf "$tmp"

  log "Installed gh to: $dest"
}

if ! command -v gh >/dev/null 2>&1; then
  log "GitHub CLI (gh) not found; installing to ~/.local/bin ..."
  install_gh_to_local_bin
fi

GH_BIN="$(command -v gh || true)"
if [[ -z "$GH_BIN" ]]; then
  GH_BIN="$HOME/.local/bin/gh"
fi

if [[ ! -x "$GH_BIN" ]]; then
  log "ERROR: gh still not available."
  log "Try installing manually, then rerun:"
  log "  https://github.com/cli/cli#installation"
  exit 1
fi

log "Using gh: $GH_BIN"

log "Authenticating gh (one-time; interactive)..."
if ! "$GH_BIN" auth status -h github.com >/dev/null 2>&1; then
  log "Follow the prompts: GitHub.com -> HTTPS -> Login with browser / device code"
  tty_exec "$GH_BIN" auth login -h github.com -p https
fi

log "Configuring git to use gh credentials..."
tty_exec "$GH_BIN" auth setup-git -h github.com || true

log "Stopping existing worker (if running)..."
pkill -f "scripts/offload_worker.sh" >/dev/null 2>&1 || true

log "Updating worker repo..."
git -C "$REPO_DIR" fetch origin "$BRANCH" --prune
git -C "$REPO_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
git -C "$REPO_DIR" pull --ff-only origin "$BRANCH" || true
chmod +x "$REPO_DIR/scripts/offload_worker.sh"

log "Starting worker in background (log: $LOG_FILE)"
nohup "$REPO_DIR/scripts/offload_worker.sh" >"$LOG_FILE" 2>&1 &
sleep 2

log "Worker processes:"
pgrep -af "scripts/offload_worker.sh" || true

log "Log tail:"
tail -n 120 "$LOG_FILE" || true

log "Bootstrap complete."

