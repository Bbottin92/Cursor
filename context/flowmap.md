# NUSA Context + Flowmap

Generated: `2026-02-20T10:54:10Z`
Trigger: `pre_commit` - auto pre-commit context sync

## Persistent Workflow Rules

1. Before inspecting files: `./scripts/context_guard.sh inspect "what you are checking"`
2. Before changing files: `./scripts/context_guard.sh change "what you are changing"`
3. Read `context/current_task.md` to align active intent before edits
4. Pre-commit hook auto-refreshes this flowmap (install with `npm run context:install-hooks`)
5. Deploy script auto-refreshes context at deploy start and finish

State runs: `17`  
Phase counts: `{"bootstrap": 1, "test": 3, "change": 3, "pre_commit": 7, "inspect": 3}`

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

- `context/activity_log.jsonl` touched `8` checkpoint(s)
- `context/current_task.md` touched `8` checkpoint(s)
- `context/flowmap.json` touched `8` checkpoint(s)
- `context/flowmap.md` touched `8` checkpoint(s)
- `context/state.json` touched `8` checkpoint(s)
- `context/watchlist.json` touched `8` checkpoint(s)
- `README.md` touched `6` checkpoint(s)
- `scripts/context_flowmap.py` touched `6` checkpoint(s)

## Recent Context Activity

- `2026-02-20T10:42:57Z` [pre_commit] auto pre-commit context sync
- `2026-02-20T10:43:27Z` [pre_commit] auto pre-commit context sync
- `2026-02-20T10:43:51Z` [pre_commit] auto pre-commit context sync
- `2026-02-20T10:51:05Z` [inspect] fetch and compare live liquidgov.us rendering sources
- `2026-02-20T10:52:26Z` [change] refine live hero mobile rendering and bump cache-bust tokens
- `2026-02-20T10:53:46Z` [pre_commit] auto pre-commit context sync
- `2026-02-20T10:53:57Z` [test] npm test context sync
- `2026-02-20T10:54:10Z` [pre_commit] auto pre-commit context sync
