# Current Task Intent (Auto)

Updated: `2026-02-21T03:23:19Z`  
Checkpoint: `pre_commit`  
Intent note: auto pre-commit context sync

## Mandatory Use

Before inspection:
- `./scripts/context_guard.sh inspect "what you are checking"`

Before edits:
- `./scripts/context_guard.sh change "what you are changing"`

## Active Working Context

Branch: `cursor/liquidgov-website-definition-d045`  
Commit: `c06a777`  
Context runs: `66`

### Currently changed files
- `context/activity_log.jsonl`
- `context/current_task.md`
- `context/flowmap.json`
- `context/flowmap.md`
- `context/state.json`
- `context/watchlist.json`
- `scripts/offload_bootstrap.sh`
- `scripts/offload_worker.sh`

### Auto optimization watchlist
- `context/activity_log.jsonl` (37 touches)
- `context/current_task.md` (37 touches)
- `context/flowmap.json` (37 touches)
- `context/flowmap.md` (37 touches)
- `context/state.json` (37 touches)
- `context/watchlist.json` (37 touches)
- `store.js` (15 touches)
- `dataClient.js` (13 touches)

## High Priority Flow References

### Participant join flow
- index.html -> main.js -> dataClient.createAccount
- /api/auth/register (primary) or /api/auth/signup (legacy)
- participant counter refresh via /api/stats/participants

### Announcement visibility flow
- app.html announcement form -> app.js -> dataClient.addAnnouncement
- /api/announcements persists updates
- index.html preview reads /api/announcements

### No-SSH deployment flow
- scripts/deploy_cpanel_no_ssh.sh authenticates with cPanel API
- uploads required frontend files to public_html
- verifies homepage, member app, participant count, announcements


## Pre-change checklist

- [ ] Read `context/flowmap.md`
- [ ] Validate this task intent matches current request
- [ ] Confirm in-scope files only
- [ ] Run context guard before commit/push
