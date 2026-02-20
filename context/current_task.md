# Current Task Intent (Auto)

Updated: `2026-02-20T10:42:23Z`  
Checkpoint: `inspect`  
Intent note: verify hero pass and regenerate current task template

## Mandatory Use

Before inspection:
- `./scripts/context_guard.sh inspect "what you are checking"`

Before edits:
- `./scripts/context_guard.sh change "what you are changing"`

## Active Working Context

Branch: `cursor/liquidgov-website-definition-d045`  
Commit: `940fde0`  
Context runs: `7`

### Currently changed files
- `README.md`
- `context/activity_log.jsonl`
- `context/flowmap.json`
- `context/flowmap.md`
- `context/state.json`
- `context/watchlist.json`
- `index.html`
- `scripts/context_flowmap.py`
- `scripts/install_context_hooks.sh`
- `styles.css`

### Auto optimization watchlist
- `README.md` (5 touches)
- `scripts/context_flowmap.py` (5 touches)
- `scripts/install_context_hooks.sh` (5 touches)
- `package.json` (4 touches)
- `scripts/context_guard.sh` (4 touches)
- `scripts/deploy_cpanel_no_ssh.sh` (4 touches)
- `context/` (3 touches)
- `context/activity_log.jsonl` (3 touches)

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
