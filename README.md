# Crash Triage Tool (Linux)

This repo contains `crashtriage.py`, a **single-file** tool that helps identify why a Linux laptop is throwing lots of errors / crashing / rebooting.

It collects the highest-signal evidence (especially **previous boot** logs), does **basic redaction by default**, and outputs a **paste-ready prompt** you can send to an assistant for concrete fixes.

## Usage

Run on the crashing machine:

```bash
python3 ./crashtriage.py
```

Optional: attempt a small amount of extra collection via `sudo` (may prompt for password):

```bash
python3 ./crashtriage.py --sudo
```

If you’re comfortable sharing unredacted logs:

```bash
python3 ./crashtriage.py --no-redact
```

## Output

The script creates a directory like `crashtriage_YYYYMMDD_HHMMSS/` containing:

- `crashtriage_prompt.md`: **copy/paste this** into chat
- `crashtriage_report.json`: structured data
- `raw/`: per-command raw outputs

## Notes

- If your system doesn’t use `systemd`/`journalctl`, the script falls back to `/var/log/syslog`, `/var/log/kern.log`, and `dmesg` when available.
- If your crashes are hard power-offs (no logs), the next best step is often checking **thermal**, **RAM**, and **disk health** (the script will still collect useful hints).
