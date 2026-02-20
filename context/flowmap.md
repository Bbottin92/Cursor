# NUSA Context + Flowmap

Generated: `2026-02-20T14:24:37Z`
Trigger: `pre_commit` - auto pre-commit context sync

## Persistent Workflow Rules

1. Before inspecting files: `./scripts/context_guard.sh inspect "what you are checking"`
2. Before changing files: `./scripts/context_guard.sh change "what you are changing"`
3. Read `context/current_task.md` to align active intent before edits
4. Pre-commit hook auto-refreshes this flowmap (install with `npm run context:install-hooks`)
5. Deploy script auto-refreshes context at deploy start and finish

State runs: `34`  
Phase counts: `{"bootstrap": 1, "test": 7, "change": 8, "pre_commit": 14, "inspect": 4}`

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
- `PATCH /api/proposals/:proposalId`
- `DELETE /api/proposals/:proposalId`
- `GET /api/announcements`
- `POST /api/announcements`
- `PATCH /api/announcements/:announcementId`
- `DELETE /api/announcements/:announcementId`
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
- `DELETE /api/users/:id`
- `GET /api/roles`
- `POST /api/roles/claim`
- `POST /api/roles/release`
- `GET /api/listings`
- `POST /api/listings`
- ... 16 more routes

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

- `context/activity_log.jsonl` touched `18` checkpoint(s)
- `context/current_task.md` touched `18` checkpoint(s)
- `context/flowmap.json` touched `18` checkpoint(s)
- `context/flowmap.md` touched `18` checkpoint(s)
- `context/state.json` touched `18` checkpoint(s)
- `context/watchlist.json` touched `18` checkpoint(s)
- `index.html` touched `9` checkpoint(s)
- `server/server.js` touched `7` checkpoint(s)

## Recent Context Activity

- `2026-02-20T14:21:23Z` [change] implement signup fix admin controls and portrait editor
- `2026-02-20T14:21:32Z` [pre_commit] auto pre-commit context sync
- `2026-02-20T14:21:51Z` [test] npm test context sync
- `2026-02-20T14:22:12Z` [pre_commit] auto pre-commit context sync
- `2026-02-20T14:23:45Z` [change] expand Brandon admin bootstrap username aliases
- `2026-02-20T14:23:55Z` [pre_commit] auto pre-commit context sync
- `2026-02-20T14:24:12Z` [test] npm test context sync
- `2026-02-20T14:24:37Z` [pre_commit] auto pre-commit context sync
