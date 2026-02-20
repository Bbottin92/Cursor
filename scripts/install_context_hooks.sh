#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -d "${REPO_ROOT}/.git" ]]; then
  echo "Skipping hook install: .git directory not found."
  exit 0
fi

HOOK_PATH="${REPO_ROOT}/.git/hooks/pre-commit"

cat > "$HOOK_PATH" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

if command -v python3 >/dev/null 2>&1; then
  python3 scripts/context_flowmap.py --phase pre_commit --note "auto pre-commit context sync" --quiet
  git add context/flowmap.json context/flowmap.md context/activity_log.jsonl context/state.json context/watchlist.json context/current_task.md
fi
HOOK

chmod +x "$HOOK_PATH"
echo "Installed pre-commit context hook at $HOOK_PATH"
