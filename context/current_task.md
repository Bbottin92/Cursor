# Current Task Intent (Auto)

Updated: `2026-02-20T15:50:52Z`  
Checkpoint: `pre_commit`  
Intent note: auto pre-commit context sync

## Mandatory Use

Before inspection:
- `./scripts/context_guard.sh inspect "what you are checking"`

Before edits:
- `./scripts/context_guard.sh change "what you are changing"`

## Active Working Context

Branch: `cursor/liquidgov-website-definition-d045`  
Commit: `ef695c1`  
Context runs: `51`

### Currently changed files
- `context/activity_log.jsonl`
- `context/current_task.md`
- `context/flowmap.json`
- `context/flowmap.md`
- `context/state.json`
- `context/watchlist.json`

### Auto optimization watchlist
- `context/activity_log.jsonl` (30 touches)
- `context/current_task.md` (30 touches)
- `context/flowmap.json` (30 touches)
- `context/flowmap.md` (30 touches)
- `context/state.json` (30 touches)
- `context/watchlist.json` (30 touches)
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
