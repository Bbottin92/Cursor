# Local Ollama Offload (token saver)

Goal: let the cloud agent offload “heavy thinking/drafting” to your **local Ollama models** without needing inbound network access.

## One-time setup (you do)

From inside this repo, run:

```bash
chmod +x scripts/offload_worker.sh
nohup ./scripts/offload_worker.sh >"$HOME/.nusa_offload_worker.log" 2>&1 &
```

The worker will:
- `git clone` this repo into `~/.nusa_offload_worker/repo`
- pull tasks from `offload/tasks/*.json`
- run them via Ollama at `http://127.0.0.1:11434`
- write results to `offload/results/*.result.json`
- commit + push results back to this branch

## What the cloud agent does

The cloud agent will create a JSON task file in `offload/tasks/` and push it.
Your worker picks it up, runs it, and pushes the result back.

## Env overrides (optional)

```bash
BRANCH=cursor/liquidgov-website-definition-d045 \
OLLAMA_MODEL=llama3.2:latest \
INTERVAL_SECONDS=5 \
MAX_PER_PASS=2 \
./scripts/offload_worker.sh
```

## Notes

- Avoid putting secrets in task prompts/results (they are committed).
- If pushes fail, check `~/.nusa_offload_worker.log` and resolve like a normal git push/pull.

