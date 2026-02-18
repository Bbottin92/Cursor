# autoheal (opt-in)

`autoheal` is a small, **opt-in** agent + CLI that:

1. **Acknowledges** errors by persisting incidents (SQLite) as soon as they’re detected or reported.
2. **Diagnoses** via structured checks (disk pressure, failed systemd units, etc.).
3. **Fixes** automatically using **allowlisted** remediations (safe defaults).
4. **Survives reboots** and keeps running when installed as a `systemd` service (`Restart=always`).

## Important security note (no password bypass)

This project does **not** attempt to bypass user passwords or “run without authorization”.
If you want it to run at boot *before a user logs in*, install it as a **system service** (requires admin rights once during installation). After that, `systemd` starts it automatically without interactive prompts.

## Quickstart (local)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .

# write a default config (adjust allowlists before enabling higher-impact fixes)
autoheal config init --path ./config.json

# run a single check+remediation cycle
autoheal agent once --config ./config.json --state-dir ./state

# inspect persistent context
autoheal incidents list --state-dir ./state
```

## Control channel (for Cursor / automation)

When the agent is running, it exposes a **local Unix control socket** under the state dir:

```bash
autoheal control ping --state-dir ./state
autoheal control incidents.list --state-dir ./state
```

You can set a token (recommended when multiple users share a host):

```bash
export AUTOHEAL_TOKEN="…"
autoheal control incidents.create --params-json '{"title":"hello","type":"manual"}' --token "$AUTOHEAL_TOKEN"
```

## systemd templates

See `systemd/autoheal.service` for a system-wide unit template and `systemd/autoheal-user.service`
for a user service template.
