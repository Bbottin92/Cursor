# LiquidGov.US Prototype

This repository now includes:

- Public website (`index.html`) with participant counter and account creation flow
- Legal/safety page (`legal.html`) with core definitions and minor-protection rules
- Member app (`app.html`) with:
  - communication modules (DM/audio/video/group)
  - scope map views (Neighborhood/Town/State/National/International)
  - launch milestone tracker
  - founding assembly role board
  - proposal archive with attribution
  - barter/trade board
  - networking board
  - profile visitor logs and notifications
- Backend API + SQLite persistence (`server/`)
- Legacy compatibility routes to preserve old LiquidGov API behavior

## Architecture

- Frontend: vanilla HTML/CSS/JS
- Backend: Express + SQLite (`better-sqlite3`)
- Data mode:
  - Uses API + SQLite when backend is running
  - Falls back to localStorage store when backend is unavailable

## Project layout

- `index.html` - public homepage
- `app.html` - member experience shell
- `legal.html` - policy and definitions
- `login.html`, `dashboard.html`, `profile.html`, `edit-profile.html` - legacy route compatibility pages
- `styles.css` - shared styles
- `store.js` - local fallback data layer
- `dataClient.js` - API client with fallback behavior
- `main.js` - homepage logic
- `app.js` - member app logic
- `server/server.js` - Express API server
- `server/db.js` - SQLite schema, seed data, DB utilities
- `data/liquidgov.db` - runtime database file (gitignored)

## Run locally

```bash
npm install
npm run dev
```

Then open:

- `http://localhost:3000/` (public site)
- `http://localhost:3000/app.html` (member app)

## No-SSH cPanel deploy automation

For cPanel environments where SSH/WebDAV are blocked, use:

```bash
./scripts/deploy_cpanel_no_ssh.sh
```

The script uploads frontend files to `public_html/` via cPanel API (port 2083),
then verifies:

- `https://liquidgov.us/`
- `https://liquidgov.us/app.html`
- `/api/stats/participants`
- `/api/announcements`

One-time token setup (stored locally with restricted permissions):

```bash
read -rsp "cPanel API token: " T; echo
printf '%s' "$T" > ~/.liquidgov_cpanel_token
chmod 600 ~/.liquidgov_cpanel_token
unset T
```

## Persistent Context + Flowmap System (Required Workflow)

This repo now includes a dynamic, persistent context system that should be
referenced before inspecting or changing website/code.

- Generator: `scripts/context_flowmap.py`
- Guard wrapper: `scripts/context_guard.sh`
- Outputs:
  - `context/flowmap.json`
  - `context/flowmap.md`
  - `context/current_task.md` (active task intent template)
  - `context/activity_log.jsonl`
  - `context/state.json`
  - `context/watchlist.json` (auto-ranked hotspot files)

### Before inspection

```bash
./scripts/context_guard.sh inspect "what you are checking"
```

### Before code changes

```bash
./scripts/context_guard.sh change "what you are changing"
```

### Redundant automation (already embedded)

1. `npm test` auto-syncs context before validations.
2. `scripts/deploy_cpanel_no_ssh.sh` auto-syncs context at deploy start and deploy verification.
3. Optional pre-commit hook auto-refreshes/stages context files:

```bash
npm run context:install-hooks
```

## API coverage (implemented)

- Auth/session:
  - `POST /api/auth/register`
  - `POST /api/auth/signup` (legacy alias)
  - `POST /api/auth/login`
  - `POST /api/auth/logout`
  - `GET /api/session/current`
  - `GET /api/auth/me` (legacy alias)
- Accounts/stats/settings:
  - `GET /api/accounts`
  - `GET /api/stats`
  - `GET /api/stats/participants` (legacy alias)
  - `GET /api/settings`
  - `PATCH /api/settings`
  - `GET /api/milestone`
- Civic modules:
  - `GET/POST /api/proposals`
  - `GET/POST /api/announcements`
  - `GET /api/forum/posts` (legacy compatibility)
  - `GET /api/meetings` (legacy compatibility)
  - `GET /api/roles`
  - `POST /api/roles/claim`
  - `POST /api/roles/release`
  - `GET/POST /api/listings`
  - `POST /api/listings/:listingId/close`
  - `GET/POST /api/network-posts`
- Safety/transparency:
  - `GET/POST /api/notifications`
  - `GET /api/profile-visits/:username`
  - `POST /api/profile-visits`
  - `POST /api/minor/inspect`
  - `POST /api/minor/approve-contact`
  - `GET /api/minor/can-interact`

## Preserving existing accounts and announcements

The backend now includes legacy-compatible endpoints and a one-time import tool:

```bash
# Optional env vars:
# LEGACY_BASE defaults to https://liquidgov.us
# LEGACY_TOKEN allows importing legacy protected /api/users
LEGACY_BASE=https://liquidgov.us LEGACY_TOKEN=your_token npm run import:legacy
```

What it imports:

- Public legacy announcements -> `announcements` table
- Public legacy forum posts -> `proposals` table
- Legacy users/accounts -> `accounts` table (only when `LEGACY_TOKEN` is provided)

This avoids forcing members to recreate accounts once legacy user export/token access is available.

## Current behavior notes

1. Any created account is counted as a Participant.
2. Under-18 verification requires a linked parent account.
3. Minor/adult interaction checks enforce guardian approval.
4. Guardian inspection events notify the child account.
5. Proposal/archive and referential-law fields are persisted.

## Next build targets

- Hardened authentication (passwords, reset flows, role-based auth)
- Real-time chat/media infrastructure (WebSocket/WebRTC services)
- Production verification pipeline and anti-sybil controls
- Map integrations with real geospatial data + moderation tooling
