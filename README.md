# LiquidGov.US Prototype (V1 Scaffold)

This repository now contains a static prototype for LiquidGov.US:

- Public landing page with participant growth counter
- Account creation flow (`Participant` and `Verified Patriot` paths)
- Legal/safety page with minor rules and transparency standards
- Member app shell with communication modules, map scopes, profile customization,
  contribution archive, visitor/notification logs, launch milestone tracker,
  founding assembly role assignment, barter/trade board, and networking board

## Files

- `index.html` - public homepage
- `legal.html` - legal definitions and safety policy
- `app.html` - logged-in member experience shell
- `styles.css` - shared styling
- `store.js` - localStorage data layer
- `main.js` - homepage logic
- `app.js` - member app logic

## Quick start

Open `index.html` directly in a browser, or run a local static server:

```bash
python3 -m http.server 8000
```

Then visit `http://localhost:8000`.

## Current implementation notes

1. Any created account is counted in the participant counter.
2. Under-18 verification requires an existing linked parent account.
3. Proposal archive tracks author + timestamp + status.
4. Implemented ideas include a law reference field for referential credit.
5. Profile visitor logs and guardian-inspection notifications are included in the
   app prototype.
6. Launch Milestone progress and Founding Assembly roles are tracked in-app.
7. Barter/trade listings and networking posts are persisted locally.

## Next build targets

- Backend authentication and moderation
- Real messaging/video infrastructure
- Strong identity verification and anti-sybil controls
- Geographic map integration with real data layers
