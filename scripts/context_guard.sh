#!/usr/bin/env bash
set -euo pipefail

PHASE="${1:-inspect}"
shift || true
NOTE="${*:-manual context checkpoint}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

python3 scripts/context_flowmap.py --phase "$PHASE" --note "$NOTE" --print-summary

echo "Context guard complete. Flowmap: context/flowmap.md"
