# Cursor
General Cursor Repo

## Crash / error diagnosis tool

If your laptop is crashing, freezing, or rebooting, you can generate a high-signal
diagnostic report + a ready-to-paste prompt for support.

### Run

From the repo root:

```bash
python3 tools/diagnose_crashes.py
```

This writes `crash_diagnosis_report.md` and prints a prompt you can paste into chat.

Common options:

```bash
# Only print the prompt (still collects data)
python3 tools/diagnose_crashes.py --prompt-only

# Narrow log window (systemd/journalctl)
python3 tools/diagnose_crashes.py --since "2 days ago"

# Disable redaction (host/user/IPs/emails/UUIDs)
python3 tools/diagnose_crashes.py --no-redact
```

### What it collects (Linux-first)

- Basic system info (OS/kernel, CPU/memory snapshot, disks, PCI/USB devices)
- Boot/reboot history (when available)
- Kernel + system error logs (journalctl and/or dmesg excerpts)
- Crash dump directory listings (e.g. `/var/crash`, `/sys/fs/pstore`)
- Heuristic summary: OOM kills, kernel panics/oops, GPU errors, storage/filesystem errors, MCE/EDAC, etc.

By default, the tool redacts common identifiers. If you need deeper help, you can
re-run with `--no-redact` (or share the full `crash_diagnosis_report.md` privately).
