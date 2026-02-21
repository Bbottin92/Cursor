#!/usr/bin/env bash
set -euo pipefail

# NUSA / LiquidGov: local Ollama offload worker
# - You run this on YOUR machine (where Ollama is installed).
# - It pulls "tasks" from this repo, runs them through Ollama, writes "results",
#   commits, and pushes back — so the cloud agent can read them.
#
# Default behavior: loops forever. Set RUN_ONCE=1 to run one pass and exit.
#
# Environment knobs:
#   BRANCH            (default: cursor/liquidgov-website-definition-d045)
#   REMOTE            (default: origin)
#   REPO_URL          (default: auto-detected from current repo)
#   WORKDIR           (default: ~/.nusa_offload_worker)
#   INTERVAL_SECONDS  (default: 8)
#   MAX_PER_PASS      (default: 3)
#   OLLAMA_BASE       (default: http://127.0.0.1:11434)
#   OLLAMA_MODEL      (default: qwen2.5:3b)
#   OLLAMA_TIMEOUT_S  (default: 900)
#
# Task format (one JSON file per task in offload/tasks/*.json):
#   {
#     "id": "any-string",
#     "prompt": "text",
#     "model": "optional-override",
#     "options": { "temperature": 0.2 }
#   }

log() { printf '[offload-worker] %s\n' "$*"; }

need() {
  command -v "$1" >/dev/null 2>&1 || {
    log "Missing required command: $1"
    exit 1
  }
}

need git
need python3
need curl

# Prevent background git processes from stealing your terminal with username/password prompts.
# If git auth isn't configured, pushes will fail fast and the log will tell you what to run.
export GIT_TERMINAL_PROMPT="${GIT_TERMINAL_PROMPT:-0}"

BRANCH="${BRANCH:-cursor/liquidgov-website-definition-d045}"
REMOTE="${REMOTE:-origin}"
WORKDIR="${WORKDIR:-$HOME/.nusa_offload_worker}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-8}"
MAX_PER_PASS="${MAX_PER_PASS:-3}"
OLLAMA_BASE="${OLLAMA_BASE:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:3b}"
OLLAMA_TIMEOUT_S="${OLLAMA_TIMEOUT_S:-900}"
RUN_ONCE="${RUN_ONCE:-0}"
GIT_NAME="${GIT_NAME:-NUSA Offload Worker}"
GIT_EMAIL="${GIT_EMAIL:-offload-worker@localhost}"

ROOT_REPO="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_URL:-}" ]]; then
  if [[ -z "$ROOT_REPO" ]]; then
    log "Run this from inside your repo OR set REPO_URL."
    exit 1
  fi
  REPO_URL="$(git -C "$ROOT_REPO" config --get remote.${REMOTE}.url || true)"
  if [[ -z "$REPO_URL" ]]; then
    REPO_URL="$(git -C "$ROOT_REPO" config --get remote.origin.url || true)"
  fi
fi

if [[ -z "${REPO_URL:-}" ]]; then
  log "Could not determine REPO_URL. Set it like:"
  log "  REPO_URL=\"https://github.com/<you>/<repo>.git\" ./scripts/offload_worker.sh"
  exit 1
fi

CLONE_DIR="${WORKDIR%/}/repo"
mkdir -p "$WORKDIR"

ensure_clone() {
  if [[ -d "$CLONE_DIR/.git" ]]; then
    return 0
  fi

  log "Cloning to: $CLONE_DIR"
  git clone "$REPO_URL" "$CLONE_DIR"
}

ensure_git_identity() {
  local cur_name cur_email
  cur_name="$(git -C "$CLONE_DIR" config user.name 2>/dev/null || true)"
  cur_email="$(git -C "$CLONE_DIR" config user.email 2>/dev/null || true)"

  if [[ -z "$cur_name" ]]; then
    git -C "$CLONE_DIR" config user.name "$GIT_NAME"
  fi
  if [[ -z "$cur_email" ]]; then
    git -C "$CLONE_DIR" config user.email "$GIT_EMAIL"
  fi
}

sync_repo() {
  git -C "$CLONE_DIR" fetch "$REMOTE" "$BRANCH" --prune
  if git -C "$CLONE_DIR" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git -C "$CLONE_DIR" checkout "$BRANCH" >/dev/null 2>&1 || git -C "$CLONE_DIR" checkout -B "$BRANCH"
  else
    git -C "$CLONE_DIR" checkout -B "$BRANCH" "$REMOTE/$BRANCH"
  fi

  # Use rebase so local "results" commits aren't discarded if pushing fails.
  # (Without this, we'd re-run the same tasks over and over when auth is missing.)
  git -C "$CLONE_DIR" pull --rebase --autostash "$REMOTE" "$BRANCH" >/dev/null 2>&1 || \
    git -C "$CLONE_DIR" pull --ff-only "$REMOTE" "$BRANCH" >/dev/null 2>&1 || true

  mkdir -p "$CLONE_DIR/offload/tasks" "$CLONE_DIR/offload/results"

  # Make rebases more reliable if remote changes land while we have local commits.
  git -C "$CLONE_DIR" config rebase.autoStash true
  ensure_git_identity
}

ollama_healthcheck() {
  curl -fsS --max-time 3 "${OLLAMA_BASE%/}/api/tags" >/dev/null
}

process_task_file() {
  local task_path="$1"
  local task_base
  task_base="$(basename "$task_path")"
  local result_path="$CLONE_DIR/offload/results/${task_base%.json}.result.json"

  if [[ -f "$result_path" ]]; then
    return 0
  fi

  log "Running task: $task_base"

  python3 - "$task_path" "$result_path" <<'PY'
import json
import os
import sys
import time
import urllib.request

task_path = sys.argv[1]
result_path = sys.argv[2]

ollama_base = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434").rstrip("/")
default_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
timeout_s = int(os.environ.get("OLLAMA_TIMEOUT_S", "900"))

with open(task_path, "r", encoding="utf-8") as f:
    task = json.load(f)

prompt = task.get("prompt", "")
model = task.get("model") or default_model
options = task.get("options") or {}

payload = {
    "model": model,
    "prompt": prompt,
    "stream": False,
    "options": options,
}

req = urllib.request.Request(
    f"{ollama_base}/api/generate",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

started = time.time()
with urllib.request.urlopen(req, timeout=timeout_s) as resp:
    raw = json.loads(resp.read().decode("utf-8", errors="replace"))
elapsed_s = round(time.time() - started, 3)

result = {
    "id": task.get("id"),
    "task_file": os.path.basename(task_path),
    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "ollama_base": ollama_base,
    "model": model,
    "elapsed_s": elapsed_s,
    "response": raw.get("response", ""),
    "raw": raw,
    "task": task,
}

with open(result_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=True, indent=2)
    f.write("\n")
PY
}

commit_and_push_if_needed() {
  # Only commit results; never accidentally commit your other work.
  local changed_files ahead
  changed_files="$(git -C "$CLONE_DIR" status --porcelain offload/results | wc -l | tr -d ' ')"
  ahead="$(git -C "$CLONE_DIR" rev-list --count "$REMOTE/$BRANCH..HEAD" 2>/dev/null || echo 0)"

  if [[ "$changed_files" != "0" ]]; then
    ensure_git_identity
    git -C "$CLONE_DIR" add offload/results

    if ! git -C "$CLONE_DIR" diff --cached --quiet; then
      if ! git -C "$CLONE_DIR" commit -m "offload: add worker results" >/dev/null 2>&1; then
        log "Could not commit results (git identity missing?)."
        log "Fix once:"
        log "  git config --global user.name \"Your Name\""
        log "  git config --global user.email \"you@example.com\""
        return 1
      fi
    fi
  fi

  ahead="$(git -C "$CLONE_DIR" rev-list --count "$REMOTE/$BRANCH..HEAD" 2>/dev/null || echo 0)"
  if [[ "$ahead" == "0" ]]; then
    return 0
  fi

  # Push with a small retry/rebase loop (handles cloud agent commits landing).
  for attempt in 1 2 3; do
    local push_out
    if push_out="$(git -C "$CLONE_DIR" push "$REMOTE" "$BRANCH" 2>&1)"; then
      log "Pushed results."
      return 0
    fi

    if echo "$push_out" | grep -qiE "terminal prompts disabled|could not read Username|Authentication failed|could not authenticate"; then
      log "Git push auth not configured for GitHub HTTPS."
      log "Fix once (recommended): install + login GitHub CLI:"
      log "  gh auth login"
      log "  gh auth setup-git"
      return 1
    fi

    if echo "$push_out" | grep -qiE "non-fast-forward|fetch first|rejected"; then
      log "Push rejected; rebasing (attempt $attempt/3)..."
      if ! git -C "$CLONE_DIR" pull --rebase --autostash "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
        log "Rebase failed. Run:"
        log "  cd \"$CLONE_DIR\" && git status && git pull --rebase --autostash && git push"
        return 1
      fi
      continue
    fi

    log "Push failed:"
    log "$push_out"
    return 1
  done

  log "Failed to push after retries. Run:"
  log "  cd \"$CLONE_DIR\" && git status && git pull --rebase --autostash && git push"
  return 1
}

ensure_clone

log "Repo:   $REPO_URL"
log "Branch: $BRANCH"
log "Work:   $CLONE_DIR"
log "Ollama: $OLLAMA_BASE (model: $OLLAMA_MODEL)"

if ! ollama_healthcheck; then
  log "Ollama not reachable at $OLLAMA_BASE"
  log "Make sure Ollama is running, then re-run. Quick check:"
  log "  curl -sS \"$OLLAMA_BASE/api/tags\""
  exit 1
fi

while true; do
  sync_repo

  shopt -s nullglob
  tasks=( "$CLONE_DIR"/offload/tasks/*.json )
  shopt -u nullglob

  processed=0
  for t in "${tasks[@]}"; do
    process_task_file "$t"
    processed=$((processed + 1))
    if [[ "$processed" -ge "$MAX_PER_PASS" ]]; then
      break
    fi
  done

  commit_and_push_if_needed || true

  if [[ "$RUN_ONCE" == "1" ]]; then
    log "RUN_ONCE=1 set; exiting."
    exit 0
  fi

  sleep "$INTERVAL_SECONDS"
done

