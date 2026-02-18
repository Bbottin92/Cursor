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

## Cursor integration (MCP)

Cursor works best with an **MCP server** (Model Context Protocol). `autoheal` can run as an MCP server over **stdio**, exposing tools like:

- `autoheal_incidents_list`
- `autoheal_incident_get`
- `autoheal_report_incident`
- `autoheal_run_once`
- `autoheal_tail_log`

Install with MCP support:

```bash
# On distros enforcing PEP 668 (e.g. Arch), install into a venv or via pipx.
python3 -m venv ~/.venvs/autoheal
~/.venvs/autoheal/bin/pip install -U pip

# from the repo root
~/.venvs/autoheal/bin/pip install -e '.[mcp]'
```

Run the MCP server (Cursor will typically launch this for you):

```bash
~/.venvs/autoheal/bin/python -m autoheal mcp serve \
  --state-dir ~/.local/state/autoheal \
  --config ~/.config/autoheal/config.json
```

Example Cursor MCP config is in `cursor-mcp.example.json`.

### Alternative: pipx (also PEP 668 friendly)

If you prefer a global-ish user install:

```bash
sudo pacman -S python-pipx
pipx ensurepath

# from repo root
pipx install --editable '.[mcp]'
```

### Recommended runtime for Cursor control

If you run the agent as a **root system service**, the control socket/DB in `/var/lib/autoheal` may not be accessible to your user (and Cursor).

For best Cursor integration, run `autoheal` as a **user service** and enable lingering so it starts on boot even without login (no password bypass):

```bash
# one-time (may require admin privileges on some systems)
loginctl enable-linger "$USER"

systemctl --user enable --now autoheal-user.service
```

## systemd templates

See `systemd/autoheal.service` for a system-wide unit template and `systemd/autoheal-user.service`
for a user service template.
