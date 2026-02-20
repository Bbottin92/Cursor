# NUSA Context + Flowmap

Generated: `2026-02-20T10:43:27Z`
Trigger: `pre_commit` - auto pre-commit context sync

## Persistent Workflow Rules

1. Before inspecting files: `./scripts/context_guard.sh inspect "what you are checking"`
2. Before changing files: `./scripts/context_guard.sh change "what you are changing"`
3. Read `context/current_task.md` to align active intent before edits
4. Pre-commit hook auto-refreshes this flowmap (install with `npm run context:install-hooks`)
5. Deploy script auto-refreshes context at deploy start and finish

State runs: `11`  
Phase counts: `{"bootstrap": 1, "test": 2, "change": 2, "pre_commit": 4, "inspect": 2}`

## Frontend Map

- `index.html` -> styles: 1, scripts: 3, links: 8
- `app.html` -> styles: 1, scripts: 3, links: 2
- `legal.html` -> styles: 1, scripts: 0, links: 2
- `login.html` -> styles: 1, scripts: 0, links: 1
- `dashboard.html` -> styles: 0, scripts: 0, links: 1
- `profile.html` -> styles: 0, scripts: 0, links: 1
- `edit-profile.html` -> styles: 0, scripts: 0, links: 1

## API Route Map (top 40)

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/signup`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/session/current`
- `GET /api/auth/me`
- `POST /api/auth/change-name`
- `POST /api/auth/change-password`
- `POST /api/auth/delete`
- `GET /api/accounts`
- `GET /api/stats`
- `GET /api/stats/participants`
- `GET /api/settings`
- `PATCH /api/settings`
- `GET /api/milestone`
- `GET /api/proposals`
- `POST /api/proposals`
- `GET /api/announcements`
- `POST /api/announcements`
- `GET /api/forum/posts`
- `GET /api/meetings`
- `GET /api/social-services`
- `GET /api/users`
- `GET /api/users/me`
- `GET /api/users/:id/profile`
- `PATCH /api/users/me`
- `POST /api/users/me/avatar`
- `PATCH /api/users/:id`
- `PUT /api/users/:id`
- `GET /api/roles`
- `POST /api/roles/claim`
- `POST /api/roles/release`
- `GET /api/listings`
- `POST /api/listings`
- `POST /api/listings/:listingId/close`
- `GET /api/network-posts`
- `POST /api/network-posts`
- `GET /api/notifications/:username`
- `POST /api/notifications`
- ... 6 more routes

## Critical Flow Paths

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


## Deploy Map

- Script: `scripts/deploy_cpanel_no_ssh.sh`
- Required upload files: `13`
- Optional upload files: `10`

## Optimization Watchlist (Auto)

- `README.md` touched `6` checkpoint(s)
- `scripts/context_flowmap.py` touched `6` checkpoint(s)
- `scripts/install_context_hooks.sh` touched `6` checkpoint(s)
- `context/activity_log.jsonl` touched `5` checkpoint(s)
- `context/flowmap.json` touched `5` checkpoint(s)
- `context/flowmap.md` touched `5` checkpoint(s)
- `context/state.json` touched `5` checkpoint(s)
- `context/watchlist.json` touched `5` checkpoint(s)

## Recent Context Activity

- `2026-02-20T10:23:02Z` [pre_commit] auto pre-commit context sync
- `2026-02-20T10:39:57Z` [inspect] collect exact hero requirements from transcript and current files
- `2026-02-20T10:40:48Z` [change] implement auto task-intent template and final hero layout pass
- `2026-02-20T10:42:23Z` [inspect] verify hero pass and regenerate current task template
- `2026-02-20T10:42:38Z` [pre_commit] auto pre-commit context sync
- `2026-02-20T10:42:47Z` [test] npm test context sync
- `2026-02-20T10:42:57Z` [pre_commit] auto pre-commit context sync
- `2026-02-20T10:43:27Z` [pre_commit] auto pre-commit context sync
