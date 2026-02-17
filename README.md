# Computer Error & Crash Diagnostic Tool

A diagnostic tool that collects system information, logs, hardware health data, and crash reports from your computer, then formats everything into a structured prompt you can relay to an AI assistant (like Claude, ChatGPT, etc.) to get a targeted diagnosis and fix.

## The Problem

Your computer keeps crashing or throwing errors, and you don't know why. You need an AI to help diagnose and fix it, but the AI needs detailed system data to be useful.

## The Solution

Run one script on your machine. It collects everything relevant, outputs a single text file, and you paste that into an AI conversation. The AI then has full context to tell you exactly what's wrong and how to fix it.

## Quick Start

### Linux / macOS

```bash
# Download and run (basic scan)
chmod +x diagnose.sh
./diagnose.sh

# For a deeper scan (recommended — unlocks SMART data, dmesg, full logs)
sudo ./diagnose.sh
```

### Windows (PowerShell)

```powershell
# Open PowerShell as Administrator (right-click → Run as Administrator)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\diagnose.ps1
```

### After Running

1. Open the generated `diagnostic_report.txt`
2. Copy the entire contents
3. Start a new conversation with your AI assistant
4. Paste the report — the AI will analyze it and provide specific fixes

## What It Collects

| Section | Details |
|---------|---------|
| **System Info** | OS, kernel, CPU, RAM, BIOS, uptime, hardware model |
| **Disk Health** | Space usage, SMART data, filesystem errors, I/O stats |
| **Memory** | Usage, swap, OOM kills, hardware ECC errors |
| **CPU & Thermal** | Temperature, throttling events, load, frequency |
| **GPU** | Driver info, GPU errors in logs |
| **Crash Data** | Kernel panics, BSODs, coredumps, minidumps, unexpected shutdowns |
| **System Logs** | Critical/error entries from the last 7 days across multiple boots |
| **Drivers** | Problem devices, third-party kernel drivers |
| **Network** | Interface errors, DNS resolution |
| **Battery** | Health, cycle count, capacity degradation |
| **Services** | Failed systemd units (Linux) or stopped auto-start services (Windows) |
| **Recent Updates** | Package changes that might have introduced regressions |
| **Processes** | Top CPU and memory consumers |
| **System Integrity** | SFC/CBS corruption log (Windows), kernel taint flags (Linux) |
| **Reliability** | Windows Reliability Monitor records |

## Privacy

The tool collects **system diagnostic data only**. It does NOT collect:
- Personal files or documents
- Passwords or credentials
- Browser history
- Email or messages
- Photos or media

The report stays local on your machine as `diagnostic_report.txt`. You decide what to share.

**Review the report before sharing** — it will contain your hostname, installed software names, and process names, which you may want to redact if posting publicly.

## Requirements

### Linux / macOS
- Bash 4+
- Optional but recommended: `smartmontools` (for SMART data), `lm-sensors` (for temperatures)
- `sudo` access recommended for deeper analysis

### Windows
- PowerShell 5.1+ (comes with Windows 10/11)
- Administrator access recommended for full results

## Troubleshooting the Tool Itself

| Issue | Fix |
|-------|-----|
| `Permission denied` on Linux | Run `chmod +x diagnose.sh` first |
| Missing SMART data | Install `smartmontools`: `sudo apt install smartmontools` or `brew install smartmontools` |
| Missing temperatures | Install `lm-sensors`: `sudo apt install lm-sensors && sudo sensors-detect` |
| PowerShell execution policy error | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| Empty report sections | Run with `sudo` (Linux) or as Administrator (Windows) |

## License

MIT — use however you want.
