from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

from .models import Finding
from .subprocess_utils import run, which

log = logging.getLogger("autoheal.checks")


def run_all_checks(cfg: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(check_disk_usage(cfg))
    findings.extend(check_cursor_safe_launcher(cfg))
    findings.extend(check_cursor_crashpad(cfg))
    findings.extend(check_systemd_user_failed_units(cfg))
    findings.extend(check_systemd_failed_units(cfg))
    return findings


def check_disk_usage(cfg: dict[str, Any]) -> list[Finding]:
    threshold = int(cfg.get("thresholds", {}).get("disk_usage_percent", 92))
    mountpoints = list(cfg.get("disk", {}).get("mountpoints", ["/"]))

    out: list[Finding] = []
    for mp in mountpoints:
        try:
            du = shutil.disk_usage(mp)
            used_percent = int(round((du.used / du.total) * 100)) if du.total else 0
            if used_percent < threshold:
                continue

            if used_percent >= 98:
                severity = 5
            elif used_percent >= 95:
                severity = 4
            else:
                severity = 3

            out.append(
                Finding(
                    fingerprint=f"disk_usage:{mp}",
                    type="disk_usage",
                    severity=severity,
                    title=f"Disk usage high on {mp} ({used_percent}%)",
                    details={
                        "mountpoint": mp,
                        "used_percent": used_percent,
                        "threshold_percent": threshold,
                        "total_bytes": du.total,
                        "used_bytes": du.used,
                        "free_bytes": du.free,
                    },
                    diagnosis=(
                        f"Disk usage on {mp} is {used_percent}%, above configured threshold "
                        f"{threshold}%. Free bytes: {du.free}."
                    ),
                )
            )
        except Exception as e:
            log.exception("disk usage check failed for %s: %s", mp, e)

    return out


def check_systemd_failed_units(cfg: dict[str, Any]) -> list[Finding]:
    if which("systemctl") is None:
        return []

    try:
        res = run(
            ["systemctl", "--failed", "--no-legend", "--plain"],
            timeout_seconds=10,
        )
    except Exception as e:
        log.debug("systemctl failed: %s", e)
        return []

    if res.exit_code != 0 and not res.stdout.strip():
        # Non-zero without output is frequently a permission/container issue.
        return []

    out: list[Finding] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # UNIT LOAD ACTIVE SUB DESCRIPTION...
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        unit, load, active, sub = parts[0], parts[1], parts[2], parts[3]
        desc = parts[4] if len(parts) >= 5 else ""

        # systemctl --failed should only list failed, but be defensive
        if active != "failed" and sub != "failed":
            continue

        out.append(
            Finding(
                fingerprint=f"systemd_failed_unit:{unit}",
                type="systemd_failed_unit",
                severity=4,
                title=f"systemd unit failed: {unit}",
                details={
                    "unit": unit,
                    "load": load,
                    "active": active,
                    "sub": sub,
                    "description": desc,
                },
                diagnosis=(
                    f"systemd reports {unit} as failed (load={load}, active={active}, sub={sub}). "
                    f"{desc}".strip()
                ),
            )
        )

    return out


def check_systemd_user_failed_units(cfg: dict[str, Any]) -> list[Finding]:
    """
    Detect failed systemd *user* units (does not require root).
    """
    if which("systemctl") is None:
        return []

    try:
        res = run(
            ["systemctl", "--user", "--failed", "--no-legend", "--plain"],
            timeout_seconds=10,
        )
    except Exception as e:
        log.debug("systemctl --user failed: %s", e)
        return []

    if res.exit_code != 0 and not res.stdout.strip():
        return []

    out: list[Finding] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        unit, load, active, sub = parts[0], parts[1], parts[2], parts[3]
        desc = parts[4] if len(parts) >= 5 else ""

        if active != "failed" and sub != "failed":
            continue

        out.append(
            Finding(
                fingerprint=f"systemd_user_failed_unit:{unit}",
                type="systemd_user_failed_unit",
                severity=3,
                title=f"systemd user unit failed: {unit}",
                details={
                    "unit": unit,
                    "load": load,
                    "active": active,
                    "sub": sub,
                    "description": desc,
                },
                diagnosis=(
                    f"systemd --user reports {unit} as failed (load={load}, active={active}, sub={sub}). "
                    f"{desc}".strip()
                ),
            )
        )

    return out


def check_cursor_crashpad(cfg: dict[str, Any]) -> list[Finding]:
    """
    Detect frequent Cursor crashes by scanning Crashpad dumps.

    This is intentionally conservative: it only reports an incident when a
    threshold of recent crash dumps is exceeded.
    """
    ccfg = cfg.get("cursor", {}) or {}
    crashpad_dirs = ccfg.get("crashpad_dirs", ["~/.config/Cursor/Crashpad"]) or []
    try:
        crashpad_dirs = list(crashpad_dirs)
    except Exception:
        crashpad_dirs = ["~/.config/Cursor/Crashpad"]

    window_minutes = int(ccfg.get("crash_window_minutes", 30))
    threshold = int(ccfg.get("crash_threshold", 2))
    if window_minutes <= 0 or threshold <= 0:
        return []

    cutoff = time.time() - (window_minutes * 60)

    crash_count = 0
    samples: list[str] = []
    scanned = 0
    max_scanned = 10_000

    for d in crashpad_dirs:
        p = Path(str(d)).expanduser()
        if not p.exists():
            continue

        for root, _, files in os.walk(p, followlinks=False):
            for fn in files:
                scanned += 1
                if scanned > max_scanned:
                    break
                if not fn.endswith(".dmp"):
                    continue
                fp = Path(root) / fn
                try:
                    st = fp.stat()
                except Exception:
                    continue
                if st.st_mtime < cutoff:
                    continue
                crash_count += 1
                if len(samples) < 5:
                    samples.append(str(fp))
            if scanned > max_scanned:
                break

    if crash_count < threshold:
        return []

    return [
        Finding(
            fingerprint="cursor_crashpad_reports",
            type="cursor_crashpad_reports",
            severity=4,
            title=f"Cursor crash reports detected ({crash_count} recent dumps)",
            details={
                "crashpad_dirs": [str(Path(str(d)).expanduser()) for d in crashpad_dirs],
                "crash_count": crash_count,
                "window_minutes": window_minutes,
                "samples": samples,
                "max_scanned": max_scanned,
            },
            diagnosis=(
                f"Found {crash_count} Cursor Crashpad dump(s) modified in the last "
                f"{window_minutes} minutes. This often indicates a crash loop or unstable configuration."
            ),
        )
    ]


def check_cursor_safe_launcher(cfg: dict[str, Any]) -> list[Finding]:
    """
    If the user explicitly enabled the Cursor safe launcher, ensure it's installed.

    This makes the system more "automatic": enabling the fixer is enough; the
    agent will converge the machine to the desired state on its own.
    """
    actions = cfg.get("actions", {}) or {}
    ccfg = actions.get("cursor_safe_launcher", {}) or {}
    if not bool(ccfg.get("enabled", False)):
        return []

    launcher_path = Path(str(ccfg.get("launcher_path", "~/.local/bin/cursor"))).expanduser()
    backup_suffix = str(ccfg.get("backup_suffix", ".autoheal-orig"))
    backup_path = launcher_path.with_name(launcher_path.name + backup_suffix)
    marker = "autoheal-managed cursor launcher"

    wrapper_installed = False
    exists = launcher_path.exists()
    if exists:
        try:
            wrapper_installed = marker in launcher_path.read_text(
                encoding="utf-8", errors="replace"
            )
        except Exception:
            wrapper_installed = False

    if wrapper_installed:
        return []

    # Only report if we have a plausible original to wrap.
    has_original_candidate = backup_path.exists() or (which("cursor") is not None) or exists
    if not has_original_candidate:
        return []

    return [
        Finding(
            fingerprint=f"cursor_safe_launcher_missing:{launcher_path}",
            type="cursor_safe_launcher_missing",
            severity=2,
            title="Cursor safe launcher enabled but not installed",
            details={
                "launcher_path": str(launcher_path),
                "backup_path": str(backup_path),
                "launcher_exists": exists,
                "backup_exists": backup_path.exists(),
                "wrapper_installed": wrapper_installed,
            },
            diagnosis=(
                "actions.cursor_safe_launcher.enabled is true, but the wrapper is not installed yet. "
                "autoheal will install it to add safer default flags."
            ),
        )
    ]
