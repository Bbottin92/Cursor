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
