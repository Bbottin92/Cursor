#!/usr/bin/env python3
"""
diagnose_crashes.py

Collects crash / error evidence (primarily Linux + systemd), performs light
heuristic analysis (OOM, GPU, disk, kernel panics, hardware errors), and
prints a ready-to-paste prompt you can send to an assistant.

Design goals:
 - Read-only: does not change system configuration.
 - Safe defaults: redacts common identifiers by default.
 - Works without root: collects what it can; suggests optional follow-ups.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import getpass
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Iterable, Optional


TOOL_VERSION = "0.1.0"


@dataclasses.dataclass(frozen=True)
class CmdResult:
    name: str
    argv: list[str]
    ok: bool
    exit_code: Optional[int]
    duration_ms: int
    stdout: str
    stderr: str
    note: str = ""


@dataclasses.dataclass(frozen=True)
class Finding:
    category: str
    severity: str  # "high" | "medium" | "low"
    count: int
    sample_lines: list[str]
    explanation: str


def _now_utc_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds")


def _which(prog: str) -> Optional[str]:
    return shutil.which(prog)


def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 20] + "\n... [truncated] ...\n"


def _read_text_file(path: Path, max_bytes: int = 256_000) -> Optional[str]:
    try:
        data = path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        return None
    if len(data) > max_bytes:
        data = data[:max_bytes] + b"\n... [truncated] ...\n"
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return data.decode(errors="replace")


def _run_cmd(
    name: str,
    argv: list[str],
    timeout_s: int,
    max_chars: int,
    env: Optional[dict[str, str]] = None,
) -> CmdResult:
    start = _dt.datetime.now(tz=_dt.timezone.utc)
    try:
        proc = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            env=env,
        )
        ok = proc.returncode == 0
        stdout = _truncate(proc.stdout or "", max_chars=max_chars)
        stderr = _truncate(proc.stderr or "", max_chars=max_chars)
        exit_code: Optional[int] = proc.returncode
        note = ""
    except FileNotFoundError:
        ok = False
        stdout = ""
        stderr = ""
        exit_code = None
        note = "command not found"
    except subprocess.TimeoutExpired as e:
        ok = False
        stdout = _truncate((e.stdout or ""), max_chars=max_chars) if isinstance(e.stdout, str) else ""
        stderr = _truncate((e.stderr or ""), max_chars=max_chars) if isinstance(e.stderr, str) else ""
        exit_code = None
        note = f"timed out after {timeout_s}s"
    end = _dt.datetime.now(tz=_dt.timezone.utc)
    duration_ms = int((end - start).total_seconds() * 1000)
    return CmdResult(
        name=name,
        argv=argv,
        ok=ok,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout=stdout,
        stderr=stderr,
        note=note,
    )


def _run_first_ok(
    name: str,
    candidates: list[list[str]],
    timeout_s: int,
    max_chars: int,
) -> CmdResult:
    last: Optional[CmdResult] = None
    for argv in candidates:
        last = _run_cmd(name=name, argv=argv, timeout_s=timeout_s, max_chars=max_chars)
        # Some tools return non-zero when partially successful; accept any output.
        if last.ok or (last.stdout.strip() or last.stderr.strip()):
            return last
    assert last is not None
    return last


def _markdown_codeblock(lang: str, text: str) -> str:
    # Avoid triple-backtick collisions by using indented blocks if needed.
    if "```" in text:
        return "\n".join("    " + line for line in text.splitlines())
    return f"```{lang}\n{text.rstrip()}\n```\n"


def _format_cmd_result_md(r: CmdResult, redact: bool, redactor: "Redactor") -> str:
    argv_str = " ".join(shlex.quote(a) for a in r.argv)
    header = f"### {r.name}\n\n**Command:** `{argv_str}`\n\n"
    meta = f"**OK:** {r.ok}  \n**Exit:** {r.exit_code}  \n**Duration:** {r.duration_ms}ms"
    if r.note:
        meta += f"  \n**Note:** {r.note}"
    meta += "\n\n"
    stdout = r.stdout or ""
    stderr = r.stderr or ""
    if redact:
        stdout = redactor.redact(stdout)
        stderr = redactor.redact(stderr)
    out = ""
    if stdout.strip():
        out += "**STDOUT:**\n\n" + _markdown_codeblock("text", stdout)
    if stderr.strip():
        out += "**STDERR:**\n\n" + _markdown_codeblock("text", stderr)
    if not out:
        out = "_(no output)_\n\n"
    return header + meta + out


class Redactor:
    def __init__(self) -> None:
        self._username = getpass.getuser()
        self._home = str(Path.home())
        self._hostname = platform.node()

        # Order matters: more-specific replacements first.
        self._replacements: list[tuple[re.Pattern[str], str]] = [
            # Emails.
            (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "<EMAIL>"),
            # IPv4.
            (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<IP>"),
            # MAC addresses.
            (re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b"), "<MAC>"),
            # Likely UUIDs.
            (
                re.compile(
                    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
                ),
                "<UUID>",
            ),
        ]

    def redact(self, text: str) -> str:
        if not text:
            return text
        # Direct string redactions (fast, avoids regex surprises).
        out = text.replace(self._home, "~")
        if self._username:
            out = out.replace(self._username, "<USER>")
        if self._hostname:
            out = out.replace(self._hostname, "<HOST>")
        for pat, repl in self._replacements:
            out = pat.sub(repl, out)
        return out


def _detect_platform() -> str:
    s = platform.system().lower()
    if s.startswith("linux"):
        return "linux"
    if s.startswith("darwin"):
        return "macos"
    if s.startswith("windows"):
        return "windows"
    return s or "unknown"


def _list_dir_listing(path: Path, max_entries: int = 80) -> str:
    if not path.exists():
        return "(missing)"
    if not path.is_dir():
        return "(not a directory)"
    try:
        entries = sorted(path.iterdir(), key=lambda p: p.name)
    except PermissionError:
        return "(permission denied)"
    lines: list[str] = []
    for p in entries[:max_entries]:
        try:
            st = p.stat()
            size = st.st_size
        except OSError:
            size = -1
        kind = "dir" if p.is_dir() else "file"
        lines.append(f"{kind:4} {size:>10}  {p.name}")
    if len(entries) > max_entries:
        lines.append(f"... ({len(entries) - max_entries} more)")
    return "\n".join(lines) if lines else "(empty)"


def _parse_keyvals(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def _os_release() -> dict[str, str]:
    p = Path("/etc/os-release")
    txt = _read_text_file(p)
    if not txt:
        return {}
    return _parse_keyvals(txt)


def _kernel_cmdline() -> Optional[str]:
    txt = _read_text_file(Path("/proc/cmdline"), max_bytes=64_000)
    return txt.strip() if txt else None


def _read_meminfo() -> dict[str, int]:
    txt = _read_text_file(Path("/proc/meminfo"), max_bytes=256_000)
    if not txt:
        return {}
    out: dict[str, int] = {}
    for line in txt.splitlines():
        if ":" not in line:
            continue
        k, rest = line.split(":", 1)
        m = re.search(r"(\d+)", rest)
        if not m:
            continue
        out[k.strip()] = int(m.group(1))
    return out


def _kb_to_gib(kb: int) -> float:
    return kb / (1024.0 * 1024.0)


def _select_lines(text: str, *, max_lines: int) -> str:
    lines = (text or "").splitlines()
    if len(lines) <= max_lines:
        return text or ""
    return "\n".join(lines[:max_lines] + ["... [truncated lines] ..."])


def _extract_matching_lines(text: str, patterns: Iterable[re.Pattern[str]], max_lines: int) -> list[str]:
    lines: list[str] = []
    for line in (text or "").splitlines():
        for p in patterns:
            if p.search(line):
                lines.append(line)
                break
        if len(lines) >= max_lines:
            break
    return lines


def _most_common_lines(lines: list[str], max_items: int) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for line in lines:
        counts[line] = counts.get(line, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:max_items]


def _analyze_logs(log_text: str, max_samples: int) -> list[Finding]:
    # Heuristic patterns (best-effort). Prefer kernel-y strings which show up in
    # both dmesg and journalctl -k.
    cats: list[tuple[str, str, list[str], str]] = [
        (
            "kernel_panic_oops",
            "high",
            [
                r"\bKernel panic\b",
                r"\bpanic - not syncing\b",
                r"\bOops:\b",
                r"\bBUG:\b",
                r"\bgeneral protection fault\b",
                r"\bwatchdog: .* (hard|soft) lockup\b",
            ],
            "Kernel bug/oops/panic or lockup indications (can cause reboots/hangs).",
        ),
        (
            "oom_killer",
            "high",
            [
                r"\bOut of memory\b",
                r"\boom-killer\b",
                r"\binvoked oom-killer\b",
                r"\bKilled process\b",
                r"\boom_reaper\b",
            ],
            "Out-of-memory killer activity (often feels like random app kills or freezes).",
        ),
        (
            "storage_io_filesystem",
            "high",
            [
                r"\bBuffer I/O error\b",
                r"\bblk_update_request: I/O error\b",
                r"\bI/O error\b",
                r"\bEXT4-fs error\b",
                r"\bBTRFS (warning|error)\b",
                r"\bXFS.*ERROR\b",
                r"\bnvme.*(reset|timeout|error)\b",
                r"\bata\d+.*(error|failed|timeout)\b",
                r"\bSATA link down\b",
                r"\b(sd[a-z]|nvme\d+n\d+).*timed out\b",
            ],
            "Disk / NVMe / filesystem errors (can trigger freezes, data loss, or kernel crashes).",
        ),
        (
            "gpu_driver",
            "medium",
            [
                r"\bNVRM:\b",
                r"\bXid \(",
                r"\bGPU has fallen off the bus\b",
                r"\bi915\b.*\b(GPU HANG|reset|hangcheck)\b",
                r"\bamdgpu\b.*\b(timeout|reset|ring)\b",
                r"\bdrm\b.*\b(error|hang|reset)\b",
                r"\bnouveau\b.*\b(error|fault)\b",
            ],
            "GPU/graphics driver errors (often cause black screens, display resets, or hard hangs).",
        ),
        (
            "hardware_mce_edac",
            "high",
            [
                r"\bMCE\b",
                r"\bMachine check\b",
                r"\bHardware Error\b",
                r"\bEDAC\b",
                r"\bCorrected error\b",
                r"\bUncorrected error\b",
            ],
            "Hardware-level CPU/RAM errors (can cause seemingly random crashes/reboots).",
        ),
        (
            "thermal_power_acpi",
            "medium",
            [
                r"\bthermal\b.*\b(throttle|trip|over)\b",
                r"\bCPU\d*:.*throttl",
                r"\bACPI (Error|BIOS Error)\b",
                r"\bpower supply\b.*\berror\b",
            ],
            "Thermal/power/ACPI problems (can lead to shutdowns, throttling, or instability).",
        ),
        (
            "segfaults",
            "low",
            [
                r"\bsegfault\b",
                r"\btrap invalid opcode\b",
            ],
            "Application crashes in userspace (usually not full reboots, but can indicate bad RAM/CPU).",
        ),
    ]

    findings: list[Finding] = []
    if not (log_text or "").strip():
        return findings

    for category, severity, pats, explanation in cats:
        compiled = [re.compile(p, re.IGNORECASE) for p in pats]
        matches = _extract_matching_lines(log_text, compiled, max_lines=max_samples * 4)
        if not matches:
            continue
        common = _most_common_lines(matches, max_items=max_samples)
        sample_lines = [f"[{n}x] {line}" if n > 1 else line for line, n in common]
        findings.append(
            Finding(
                category=category,
                severity=severity,
                count=len(matches),
                sample_lines=sample_lines,
                explanation=explanation,
            )
        )

    # Sort by severity then by count.
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (sev_rank.get(f.severity, 99), -f.count, f.category))
    return findings


def _summarize_disk_pressure(df_text: str) -> list[str]:
    # Attempt to spot "almost full" mounts.
    if not df_text.strip():
        return []
    lines = df_text.splitlines()
    if not lines:
        return []
    out: list[str] = []
    # Expect header like: Filesystem Type Size Used Avail Use% Mounted on
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 7:
            continue
        usep = parts[5]
        if not usep.endswith("%"):
            continue
        try:
            pct = int(usep[:-1])
        except ValueError:
            continue
        if pct >= 95:
            out.append(line)
    return out


def _short_system_summary() -> str:
    osr = _os_release()
    pretty = osr.get("PRETTY_NAME") or ""
    kernel = platform.release()
    machine = platform.machine()
    return " / ".join([p for p in [pretty, f"kernel {kernel}", machine] if p]) or platform.platform()


def _linux_collect(
    *,
    since: str,
    timeout_s: int,
    max_chars: int,
    max_log_lines: int,
    redactor: Redactor,
    redact: bool,
) -> tuple[list[CmdResult], dict[str, str]]:
    """
    Returns (cmd_results, named_text_blobs).

    named_text_blobs are additional synthesized sections not tied to a command.
    """
    results: list[CmdResult] = []
    blobs: dict[str, str] = {}

    # Basic info commands (non-root).
    def add_if(cmd_name: str, argv: list[str]) -> None:
        if not argv:
            return
        if _which(argv[0]) is None:
            results.append(
                CmdResult(
                    name=cmd_name,
                    argv=argv,
                    ok=False,
                    exit_code=None,
                    duration_ms=0,
                    stdout="",
                    stderr="",
                    note="command not found",
                )
            )
            return
        results.append(_run_cmd(cmd_name, argv, timeout_s=timeout_s, max_chars=max_chars))

    add_if("uname", ["uname", "-a"])
    add_if("uptime", ["uptime"])

    # CPU/memory/disk snapshot.
    add_if("lscpu", ["lscpu"])
    add_if("free", ["free", "-h"])
    add_if("df", ["df", "-hT"])
    add_if("lsblk", ["lsblk", "-o", "NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,MODEL,TRAN"])

    # Hardware / drivers.
    add_if("lspci", ["lspci", "-nnk"])
    add_if("lsusb", ["lsusb"])

    # Systemd / boot / failures (if present).
    add_if("systemctl_failed", ["systemctl", "--failed", "--no-pager"])
    add_if("journalctl_list_boots", ["journalctl", "--list-boots", "--no-pager"])

    # Reboot history.
    add_if("last_reboots", ["last", "-x"])

    # Kernel cmdline.
    cmdline = _kernel_cmdline()
    if cmdline:
        blobs["kernel_cmdline"] = cmdline

    # Crash dump-related dirs.
    blobs["/var/crash listing"] = _list_dir_listing(Path("/var/crash"))
    blobs["/sys/fs/pstore listing"] = _list_dir_listing(Path("/sys/fs/pstore"))
    blobs["/var/lib/systemd/coredump listing"] = _list_dir_listing(Path("/var/lib/systemd/coredump"))

    # coredumpctl list (best-effort).
    add_if("coredumpctl_list", ["coredumpctl", "list", "--no-pager"])

    # Logs: prefer journalctl -k + priority and since-range. Fall back to dmesg.
    if _which("journalctl"):
        # Current boot kernel errors/warnings.
        results.append(
            _run_cmd(
                "journalctl_kernel_since",
                ["journalctl", "-k", "-S", since, "--no-pager"],
                timeout_s=timeout_s,
                max_chars=max_chars,
            )
        )
        results.append(
            _run_cmd(
                "journalctl_err_since",
                ["journalctl", "-p", "3", "-S", since, "--no-pager"],
                timeout_s=timeout_s,
                max_chars=max_chars,
            )
        )
        # Previous boot errors (often where the crash left traces).
        results.append(
            _run_cmd(
                "journalctl_prevboot_kernel_err",
                ["journalctl", "-b", "-1", "-k", "-p", "3", "--no-pager"],
                timeout_s=timeout_s,
                max_chars=max_chars,
            )
        )
        results.append(
            _run_cmd(
                "journalctl_prevboot_err",
                ["journalctl", "-b", "-1", "-p", "3", "--no-pager"],
                timeout_s=timeout_s,
                max_chars=max_chars,
            )
        )
        # User session errors can point to graphics / compositor failures.
        results.append(
            _run_cmd(
                "journalctl_user_err_since",
                ["journalctl", "--user", "-p", "3", "-S", since, "--no-pager"],
                timeout_s=timeout_s,
                max_chars=max_chars,
            )
        )

    # dmesg is useful even with systemd (and is a fallback if journald is empty).
    dmesg = _run_first_ok(
        "dmesg_errors",
        candidates=[
            ["dmesg", "--color=never", "--ctime", "--level=emerg,alert,crit,err,warn"],
            ["dmesg", "--color=never", "-T"],
            ["dmesg"],
        ],
        timeout_s=timeout_s,
        max_chars=max_chars,
    )
    results.append(dmesg)

    # Synthesize a combined log text for analysis (pull from the most relevant sources).
    log_sources: list[str] = []
    for r in results:
        if r.name.startswith("journalctl_") or r.name.startswith("dmesg"):
            log_sources.append(r.stdout or "")
            log_sources.append(r.stderr or "")
    combined = "\n".join(s for s in log_sources if s.strip())
    if redact:
        combined = redactor.redact(combined)
    blobs["_combined_logs_for_analysis"] = _select_lines(combined, max_lines=max_log_lines)

    return results, blobs


def _non_linux_collect(
    *,
    timeout_s: int,
    max_chars: int,
) -> tuple[list[CmdResult], dict[str, str]]:
    results: list[CmdResult] = []
    blobs: dict[str, str] = {}

    def add(cmd_name: str, argv: list[str]) -> None:
        if _which(argv[0]) is None:
            results.append(
                CmdResult(
                    name=cmd_name,
                    argv=argv,
                    ok=False,
                    exit_code=None,
                    duration_ms=0,
                    stdout="",
                    stderr="",
                    note="command not found",
                )
            )
            return
        results.append(_run_cmd(cmd_name, argv, timeout_s=timeout_s, max_chars=max_chars))

    add("uname", ["uname", "-a"])

    s = _detect_platform()
    if s == "macos":
        add("sw_vers", ["sw_vers"])
        add("uptime", ["uptime"])
        add("system_profiler_basic", ["system_profiler", "SPHardwareDataType"])
        add("log_show_last_hour", ["log", "show", "--style", "syslog", "--last", "1h"])
    elif s == "windows":
        # For Windows, this script is best run from PowerShell; we include minimal instructions.
        blobs["windows_note"] = (
            "Windows detected. This tool currently has Linux-first support.\n\n"
            "For Windows crash loops, capture:\n"
            "- Reliability Monitor summary\n"
            "- Event Viewer -> System/Application -> Critical + Error entries\n"
            "- Any BugCheck/BlueScreen codes\n"
        )
    else:
        add("uptime", ["uptime"])

    return results, blobs


def _excerpt_from_cmd(cmd_results: list[CmdResult], name: str, max_lines: int) -> str:
    for r in cmd_results:
        if r.name == name:
            return _select_lines((r.stdout or r.stderr or "").strip(), max_lines=max_lines).strip()
    return ""


def _systemctl_failed_has_items(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    # "0 loaded units listed." means none. Some versions include a header only.
    if re.search(r"\b0 loaded units listed\b", t):
        return False
    # If a unit line like "foo.service loaded failed ..." exists, treat as present.
    return bool(re.search(r"\b\w+\.service\b", t))


def _render_report_md(
    *,
    platform_kind: str,
    since: str,
    redact: bool,
    cmd_results: list[CmdResult],
    blobs: dict[str, str],
    findings: list[Finding],
    disk_pressure_lines: list[str],
    prompt_text: str,
    redactor: Redactor,
) -> str:
    lines: list[str] = []
    lines.append("# Crash / Error Diagnosis Report\n")
    lines.append(f"- Generated: `{_now_utc_iso()}`\n")
    lines.append(f"- Tool: `diagnose_crashes.py` v{TOOL_VERSION}\n")
    lines.append(f"- Platform: `{platform_kind}`\n")
    lines.append(f"- System summary: `{_short_system_summary()}`\n")
    lines.append(f"- Log window (journalctl): `since={since}`\n")
    lines.append(f"- Redaction: `{redact}`\n\n")

    lines.append("## Quick Findings (heuristic)\n\n")
    if not findings:
        lines.append("_No high-signal patterns detected in the collected log excerpts._\n\n")
    else:
        for f in findings:
            lines.append(f"- **{f.category}** (severity: **{f.severity}**, matches: **{f.count}**)\n")
            lines.append(f"  - {f.explanation}\n")
            for s in f.sample_lines[:8]:
                lines.append(f"  - {s}\n")
        lines.append("\n")

    if disk_pressure_lines:
        lines.append("## Disk pressure (>=95% full mounts)\n\n")
        dp = "\n".join(disk_pressure_lines)
        if redact:
            dp = redactor.redact(dp)
        lines.append(_markdown_codeblock("text", dp))

    if "kernel_cmdline" in blobs:
        kc = blobs["kernel_cmdline"]
        if redact:
            kc = redactor.redact(kc)
        lines.append("## Kernel command line\n\n")
        lines.append(_markdown_codeblock("text", kc))

    # Extra directories / synthetic sections.
    extra_keys = [k for k in blobs.keys() if k.endswith("listing")]
    if extra_keys:
        lines.append("## Crash dump directories (listings)\n\n")
        for k in sorted(extra_keys):
            v = blobs[k]
            if redact:
                v = redactor.redact(v)
            lines.append(f"### {k}\n\n")
            lines.append(_markdown_codeblock("text", v))

    if blobs.get("windows_note"):
        lines.append("## Platform note\n\n")
        lines.append(blobs["windows_note"] + "\n")

    lines.append("## Collected command outputs\n\n")
    for r in cmd_results:
        lines.append(_format_cmd_result_md(r, redact=redact, redactor=redactor))

    lines.append("## Copy/paste prompt\n\n")
    pt = prompt_text
    if redact:
        pt = redactor.redact(pt)
    lines.append(_markdown_codeblock("text", pt))

    return "".join(lines)


def _build_prompt(
    *,
    platform_kind: str,
    since: str,
    findings: list[Finding],
    combined_logs: str,
    failed_units_excerpt: str,
    reboots_excerpt: str,
    coredumps_excerpt: str,
    disk_pressure_excerpt: str,
    extra_notes: list[str],
) -> str:
    # Keep this concise enough to paste into chat, but with high signal.
    findings_lines: list[str] = []
    if findings:
        for f in findings[:6]:
            findings_lines.append(f"- {f.category} (severity={f.severity}, matches={f.count})")
    else:
        findings_lines.append("- No obvious crash signature found in the collected excerpts.")

    notes = "\n".join(f"- {n}" for n in extra_notes) if extra_notes else "- (none)"

    def block(title: str, body: str) -> str:
        body = (body or "").strip()
        if not body:
            return ""
        return f"\n{title}:\n```text\n{body.rstrip()}\n```\n"

    prompt = f"""\
You are helping me debug repeated system errors/crashes. Please:
1) Identify the most likely root cause(s) using the evidence below (prioritize hardware vs driver vs storage vs OOM).
2) Give a minimal, ordered fix plan with concrete commands.
3) If you need more data, ask for *specific* follow-up commands and explain why.

Symptom summary (please ask me to fill in anything missing):
- What exactly happens: freeze? reboot? kernel panic? black screen? BSOD?
- Frequency and triggers: idle vs load, when on battery/AC, sleep/wake, external monitor, games, etc.
- When it started + what changed right before (updates, new drivers, BIOS/UEFI, new peripherals).

Environment:
- Platform: {platform_kind}
- Log window used for collection (journalctl): since={since}

Heuristic findings:
{chr(10).join(findings_lines)}

Extra notes:
{notes}

{block("Failed systemd units (if any)", failed_units_excerpt)}
{block("Reboot history (last output)", reboots_excerpt)}
{block("Coredumps (if any)", coredumps_excerpt)}
{block("Disk pressure (mounts >=95% full)", disk_pressure_excerpt)}

Key log excerpts (combined, truncated):
```text
{combined_logs.rstrip()}
```
"""
    return textwrap.dedent(prompt).strip() + "\n"


def _ensure_parent_dir(path: Path) -> None:
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="diagnose_crashes.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Collect crash evidence and print a prompt to paste to an assistant.",
        epilog=textwrap.dedent(
            """\
Examples:
  python3 tools/diagnose_crashes.py --prompt-only
  python3 tools/diagnose_crashes.py --since "2 days ago" --output report.md
  python3 tools/diagnose_crashes.py --no-redact --prompt-only
"""
        ),
    )
    p.add_argument("--since", default="7 days ago", help='journalctl time window, e.g. "2 days ago"')
    p.add_argument(
        "--output",
        default="crash_diagnosis_report.md",
        help="write full markdown report to this path (default: crash_diagnosis_report.md)",
    )
    p.add_argument("--prompt-only", action="store_true", help="only print the prompt (still collects data)")
    p.add_argument("--no-redact", action="store_true", help="disable redaction (host/user/IPs/emails/UUIDs)")
    p.add_argument("--timeout", type=int, default=12, help="per-command timeout seconds (default: 12)")
    p.add_argument("--max-chars", type=int, default=120_000, help="max characters captured per command output")
    p.add_argument("--max-log-lines", type=int, default=600, help="max lines to include in the combined log excerpt")
    p.add_argument("--max-samples", type=int, default=12, help="max sample lines per finding category")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    redact = not args.no_redact
    redactor = Redactor()
    platform_kind = _detect_platform()

    cmd_results: list[CmdResult] = []
    blobs: dict[str, str] = {}

    if platform_kind == "linux":
        cmd_results, blobs = _linux_collect(
            since=args.since,
            timeout_s=args.timeout,
            max_chars=args.max_chars,
            max_log_lines=args.max_log_lines,
            redactor=redactor,
            redact=redact,
        )
    else:
        cmd_results, blobs = _non_linux_collect(timeout_s=args.timeout, max_chars=args.max_chars)

    combined_logs = blobs.get("_combined_logs_for_analysis", "").strip()
    findings = _analyze_logs(combined_logs, max_samples=args.max_samples)

    # Additional heuristic: disk almost full.
    df_text = ""
    for r in cmd_results:
        if r.name == "df":
            df_text = r.stdout or ""
            break
    disk_pressure_lines = _summarize_disk_pressure(df_text)
    disk_pressure_excerpt = "\n".join(disk_pressure_lines).strip()

    failed_units_excerpt = _excerpt_from_cmd(cmd_results, "systemctl_failed", max_lines=80)
    if not _systemctl_failed_has_items(failed_units_excerpt):
        failed_units_excerpt = ""

    reboots_excerpt = _excerpt_from_cmd(cmd_results, "last_reboots", max_lines=80)
    coredumps_excerpt = _excerpt_from_cmd(cmd_results, "coredumpctl_list", max_lines=80)
    if re.search(r"\bNo coredumps found\b", coredumps_excerpt, re.IGNORECASE):
        coredumps_excerpt = ""

    extra_notes: list[str] = []
    if disk_pressure_lines:
        extra_notes.append("Some filesystems are >=95% full (can cause crashes/app failures).")
    if platform_kind == "linux" and os.geteuid() != 0:
        extra_notes.append("Ran without root; SMART/MCE/firmware details may be missing.")
    if failed_units_excerpt:
        extra_notes.append("systemd has failed units (see excerpt).")
    if coredumps_excerpt:
        extra_notes.append("Found coredumps (see excerpt); they can reveal a crashing process.")

    prompt_text = _build_prompt(
        platform_kind=platform_kind,
        since=args.since,
        findings=findings,
        combined_logs=combined_logs or "(no logs collected)",
        failed_units_excerpt=failed_units_excerpt,
        reboots_excerpt=reboots_excerpt,
        coredumps_excerpt=coredumps_excerpt,
        disk_pressure_excerpt=disk_pressure_excerpt,
        extra_notes=extra_notes,
    )

    report_md = _render_report_md(
        platform_kind=platform_kind,
        since=args.since,
        redact=redact,
        cmd_results=cmd_results,
        blobs=blobs,
        findings=findings,
        disk_pressure_lines=disk_pressure_lines,
        prompt_text=prompt_text,
        redactor=redactor,
    )

    if args.prompt_only:
        sys.stdout.write(prompt_text)
        return 0

    out_path = Path(args.output)
    _ensure_parent_dir(out_path)
    out_path.write_text(report_md, encoding="utf-8")
    sys.stdout.write(f"Wrote report to: {out_path}\n\n")
    sys.stdout.write("Prompt to paste:\n")
    sys.stdout.write(prompt_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

