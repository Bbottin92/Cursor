#!/usr/bin/env python3
"""
crashtriage.py - Collect high-signal Linux crash evidence and generate a paste-ready prompt.

Design goals:
- Zero third-party dependencies (stdlib only)
- Safe by default: basic redaction of common identifiers
- Useful even without root; optionally collect more with --sudo
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


MAX_CAPTURE_BYTES_DEFAULT = 350_000


@dataclass(frozen=True)
class Cmd:
    key: str
    argv: list[str]
    timeout_s: int = 20
    is_sudo: bool = False
    optional: bool = True


def _now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _run(argv: list[str], timeout_s: int) -> tuple[int, str]:
    """
    Return (exit_code, combined_output).
    """
    try:
        p = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as e:
        return (127, f"[command not found] {e}\n")
    except subprocess.TimeoutExpired:
        return (124, f"[timeout after {timeout_s}s] {' '.join(argv)}\n")
    except Exception as e:  # pragma: no cover
        return (1, f"[error running command] {e}\n")

    out = ""
    if p.stdout:
        out += p.stdout
        if not out.endswith("\n"):
            out += "\n"
    if p.stderr:
        out += "\n[stderr]\n" + p.stderr
        if not out.endswith("\n"):
            out += "\n"
    return (p.returncode, out)


def _read_text_file(path: Path, max_bytes: int) -> str:
    try:
        with path.open("rb") as f:
            b = f.read(max_bytes + 1)
        truncated = len(b) > max_bytes
        if truncated:
            b = b[:max_bytes]
        txt = b.decode(errors="replace")
        if truncated:
            txt += "\n\n[truncated]\n"
        return txt
    except FileNotFoundError:
        return f"[missing file] {path}\n"
    except PermissionError:
        return f"[permission denied] {path}\n"
    except Exception as e:  # pragma: no cover
        return f"[error reading file] {path}: {e}\n"


def _clip(s: str, max_bytes: int) -> str:
    b = s.encode(errors="replace")
    if len(b) <= max_bytes:
        return s
    clipped = b[:max_bytes].decode(errors="replace")
    return clipped + "\n\n[truncated]\n"


def _basic_redact(text: str, *, hostname: Optional[str], username: Optional[str]) -> str:
    """
    Best-effort redaction that tries not to destroy debugging value.
    """
    if not text:
        return text

    # Normalize line endings for consistent regex behavior.
    t = text.replace("\r\n", "\n")

    # Host/user/home path redaction
    if hostname:
        t = t.replace(hostname, "<HOSTNAME>")
    if username:
        t = t.replace(username, "<USER>")
        t = t.replace(f"/home/{username}", "/home/<USER>")

    # IPv4 addresses
    t = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<IP>", t)
    # MAC addresses
    t = re.sub(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", "<MAC>", t)
    # Common serial/ID lines
    t = re.sub(r"(?im)^(.*\bSerial(?: Number)?\b\s*:\s*)(.+)$", r"\1<REDACTED>", t)
    t = re.sub(r"(?im)^(.*\bUUID\b\s*[:=]\s*)([0-9a-fA-F-]{8,})$", r"\1<REDACTED>", t)

    return t


SIGNATURE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("kernel_panic_oops", re.compile(r"(?i)\b(kernel panic|Oops:|BUG:|panic - not syncing)\b")),
    ("watchdog_lockup", re.compile(r"(?i)\b(watchdog:|soft lockup|hard LOCKUP)\b")),
    ("oom_killer", re.compile(r"(?i)\b(out of memory|oom-killer|Killed process|invoked oom-killer)\b")),
    ("filesystem_errors", re.compile(r"(?i)\b(EXT4-fs error|BTRFS error|XFS .*corruption|Buffer I/O error)\b")),
    ("disk_nvme_ata", re.compile(r"(?i)\b(nvme|ata\d|I/O error|blk_update_request|rejecting I/O|Medium Error)\b")),
    ("gpu_hang", re.compile(r"(?i)\b(amdgpu|i915|drm:.*hang|GPU HANG|NVRM|Xid)\b")),
    ("mce_edac", re.compile(r"(?i)\b(MCE|mce:|EDAC|Machine check)\b")),
    ("thermal_power", re.compile(r"(?i)\b(thermal thrott|overheat|Temperature above threshold|ACPI Error|power supply)\b")),
    ("segfault", re.compile(r"(?i)\b(segfault|general protection fault)\b")),
]


def _extract_signatures(text: str, max_examples_per_sig: int = 5) -> dict:
    counts: dict[str, int] = {name: 0 for name, _ in SIGNATURE_RULES}
    examples: dict[str, list[str]] = {name: [] for name, _ in SIGNATURE_RULES}

    for line in text.splitlines():
        for name, rx in SIGNATURE_RULES:
            if rx.search(line):
                counts[name] += 1
                if len(examples[name]) < max_examples_per_sig:
                    examples[name].append(line[:400])
    # Drop empty signatures
    counts = {k: v for k, v in counts.items() if v}
    examples = {k: v for k, v in examples.items() if v}
    return {"counts": counts, "examples": examples}


def _journal_available() -> bool:
    return shutil.which("journalctl") is not None


def _systemd_available() -> bool:
    return shutil.which("systemctl") is not None


def _collect_commands(*, allow_sudo: bool) -> list[Cmd]:
    cmds: list[Cmd] = [
        Cmd("date", ["date", "-Is"], optional=False),
        Cmd("uname", ["uname", "-a"], optional=False),
        Cmd("os_release", ["sh", "-lc", "cat /etc/os-release 2>/dev/null || true"], optional=False),
        Cmd("uptime", ["uptime", "-p"]),
        Cmd("cpu", ["lscpu"]),
        Cmd("mem", ["free", "-h"]),
        Cmd("swap", ["swapon", "--show"]),
        Cmd("df", ["df", "-hT"]),
        Cmd("lsblk", ["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL"]),
        Cmd("lspci", ["sh", "-lc", "lspci -nnk 2>/dev/null || true"]),
        Cmd("lsusb", ["sh", "-lc", "lsusb 2>/dev/null || true"]),
        Cmd("modules", ["sh", "-lc", "lsmod 2>/dev/null || true"]),
    ]

    if _systemd_available():
        cmds += [
            Cmd("failed_units", ["systemctl", "--failed", "--no-pager"]),
        ]

    if _journal_available():
        # Current boot high-priority
        cmds += [
            Cmd("journal_current_err", ["journalctl", "-b", "0", "-p", "err..alert", "--no-pager", "-n", "400"]),
            Cmd("journal_current_kernel", ["journalctl", "-b", "0", "-k", "--no-pager", "-n", "700"]),
            # Previous boot (often where the crash evidence is)
            Cmd("journal_prev_err", ["journalctl", "-b", "-1", "-p", "err..alert", "--no-pager", "-n", "500"]),
            Cmd("journal_prev_kernel", ["journalctl", "-b", "-1", "-k", "--no-pager", "-n", "900"]),
            Cmd("journal_boots", ["journalctl", "--list-boots", "--no-pager"]),
        ]
        # coredumpctl is useful but may be missing
        cmds += [
            Cmd("coredumps_prev", ["sh", "-lc", "coredumpctl list -b -1 --no-pager -n 20 2>/dev/null || true"]),
            Cmd("coredumps_current", ["sh", "-lc", "coredumpctl list -b 0 --no-pager -n 20 2>/dev/null || true"]),
        ]
    else:
        # Fallback for non-systemd or missing journalctl.
        cmds += [
            Cmd("syslog_tail", ["sh", "-lc", "tail -n 400 /var/log/syslog 2>/dev/null || true"]),
            Cmd("kernlog_tail", ["sh", "-lc", "tail -n 500 /var/log/kern.log 2>/dev/null || true"]),
            Cmd("dmesg", ["sh", "-lc", "dmesg -T 2>/dev/null | tail -n 800 || true"]),
        ]

    # Optional: thermal sensors (non-root where possible)
    cmds += [
        Cmd("sensors", ["sh", "-lc", "sensors 2>/dev/null || true"]),
        Cmd("thermal_sysfs", ["sh", "-lc", "for f in /sys/class/thermal/thermal_zone*/{type,temp}; do [ -e \"$f\" ] && echo \"# $f\" && cat \"$f\"; done 2>/dev/null || true"]),
    ]

    if allow_sudo:
        # Keep sudo collection narrow: only high-value, not too invasive.
        cmds += [
            Cmd("dmesg_full", ["sudo", "dmesg", "-T"], timeout_s=25, is_sudo=True),
            Cmd("smartctl_scan", ["sudo", "smartctl", "--scan"], timeout_s=25, is_sudo=True),
            # Users can run smartctl -a per device later; scan is a safe start.
        ]

    return cmds


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", errors="replace")


def _make_prompt(report: dict) -> str:
    sysinfo = report.get("system", {})
    sig = report.get("signatures", {})
    counts = sig.get("counts", {})
    examples = sig.get("examples", {})

    suspected = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    suspected_lines = "\n".join([f"- {k}: {v} hits" for k, v in suspected]) or "- (none detected automatically)"

    example_blocks: list[str] = []
    for name, lines in examples.items():
        if not lines:
            continue
        block = "\n".join([f"- {ln}" for ln in lines[:5]])
        example_blocks.append(f"### {name}\n{block}")
    examples_md = "\n\n".join(example_blocks) if example_blocks else "(no signature examples extracted)"

    # Keep this prompt short enough to paste, but structured.
    return f"""You are helping me debug repeated system errors/crashes on my Linux laptop.

Please do ALL of the following:
- Identify the most likely root cause categories (hardware vs driver vs filesystem vs memory pressure vs thermal vs power).
- Explain *why* based on the log evidence below (quote the relevant lines).
- Give a prioritized fix plan with concrete commands/steps I can run.
- If you need more data, list the exact commands and what output you want.

## My symptoms (fill in quickly)
- What I was doing when it crashes:
- Frequency / pattern:
- Any recent changes (updates, drivers, new hardware):
- Does it reboot, freeze, or power off?

## System basics (auto-collected)
- OS: {sysinfo.get("os_release_pretty","(unknown)")}
- Kernel: {sysinfo.get("uname","(unknown)")}
- Time collected: {sysinfo.get("collected_at","(unknown)")}

## Automatic signal summary (auto-collected)
{suspected_lines}

## Key log excerpts (auto-collected)
{examples_md}

## Raw high-priority logs (auto-collected; redacted)
### Current boot errors (journalctl -b 0 -p err..alert)
{report.get("commands",{}).get("journal_current_err",{}).get("output","(missing)")}

### Previous boot kernel (journalctl -b -1 -k)
{report.get("commands",{}).get("journal_prev_kernel",{}).get("output","(missing)")}
"""


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Collect Linux crash evidence and generate a paste-ready prompt.",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write outputs (default: ./crashtriage_<timestamp>)",
    )
    p.add_argument(
        "--no-redact",
        action="store_true",
        help="Disable basic redaction (host/user/IP/MAC/serial-like strings).",
    )
    p.add_argument(
        "--sudo",
        action="store_true",
        help="Attempt to collect a few additional commands via sudo (may prompt).",
    )
    p.add_argument(
        "--max-bytes",
        type=int,
        default=MAX_CAPTURE_BYTES_DEFAULT,
        help=f"Max bytes captured per command/file (default: {MAX_CAPTURE_BYTES_DEFAULT}).",
    )
    args = p.parse_args(argv)

    out_dir = Path(args.output_dir or f"crashtriage_{_now_stamp()}").resolve()
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    hostname = platform.node() or None
    username = os.environ.get("USER") or os.environ.get("LOGNAME") or None

    report: dict = {
        "version": 1,
        "system": {
            "collected_at": _dt.datetime.now().isoformat(),
            "hostname": hostname if args.no_redact else "<REDACTED>",
            "username": username if args.no_redact else "<REDACTED>",
            "platform": platform.platform(),
        },
        "commands": {},
        "files": {},
        "signatures": {},
    }

    # Enrich OS pretty name if present.
    os_release = _read_text_file(Path("/etc/os-release"), max_bytes=50_000)
    pretty = None
    for line in os_release.splitlines():
        if line.startswith("PRETTY_NAME="):
            pretty = line.split("=", 1)[1].strip().strip('"')
            break
    report["system"]["os_release_pretty"] = pretty or "(unknown)"

    # Collect command outputs
    cmds = _collect_commands(allow_sudo=args.sudo)
    combined_logs_for_sig = []
    for cmd in cmds:
        code, out = _run(cmd.argv, cmd.timeout_s)
        out = _clip(out, args.max_bytes)

        if not args.no_redact:
            out = _basic_redact(out, hostname=hostname, username=username)

        report["commands"][cmd.key] = {
            "argv": cmd.argv,
            "exit_code": code,
            "output": out,
            "is_sudo": cmd.is_sudo,
        }

        _write_text(raw_dir / f"{cmd.key}.txt", out)

        if any(k in cmd.key for k in ("journal_", "syslog", "kernlog", "dmesg")):
            combined_logs_for_sig.append(out)

    # Collect a few static files that frequently contain clues.
    files_to_read: Iterable[Path] = [
        Path("/proc/cmdline"),
        Path("/proc/meminfo"),
        Path("/proc/pressure/memory"),
    ]
    for fp in files_to_read:
        content = _read_text_file(fp, max_bytes=min(args.max_bytes, 120_000))
        if not args.no_redact:
            content = _basic_redact(content, hostname=hostname, username=username)
        report["files"][str(fp)] = content
        _write_text(raw_dir / f"file_{fp.as_posix().lstrip('/').replace('/','_')}.txt", content)

    # Populate a few top-level convenience fields
    report["system"]["uname"] = report["commands"].get("uname", {}).get("output", "").strip()

    # Signature extraction
    combined = "\n".join(combined_logs_for_sig)
    report["signatures"] = _extract_signatures(combined)

    # Write final artifacts
    report_path = out_dir / "crashtriage_report.json"
    prompt_path = out_dir / "crashtriage_prompt.md"
    _write_text(report_path, json.dumps(report, indent=2, ensure_ascii=False))
    prompt = _make_prompt(report)
    prompt = _clip(prompt, 1_600_000)  # avoid insane prompts
    _write_text(prompt_path, prompt)

    print(f"Wrote: {report_path}")
    print(f"Wrote: {prompt_path}")
    print("\n===== COPY/PASTE PROMPT BELOW =====\n")
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

