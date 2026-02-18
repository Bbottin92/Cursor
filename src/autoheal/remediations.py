from __future__ import annotations

import logging
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import ActionPlan, Finding
from .subprocess_utils import run

log = logging.getLogger("autoheal.remediations")


@dataclass(frozen=True)
class ActionResult:
    status: str  # success | failed | skipped
    exit_code: int | None
    stdout: str | None
    stderr: str | None
    summary: str


def plan_actions_for_finding(cfg: dict[str, Any], finding: Finding) -> list[ActionPlan]:
    actions_cfg = cfg.get("actions", {})
    plans: list[ActionPlan] = []

    if finding.type == "disk_usage":
        tcfg = actions_cfg.get("tmp_cleanup", {})
        if bool(tcfg.get("enabled", False)):
            plans.append(
                ActionPlan(
                    name="tmp_cleanup",
                    description="Delete old files in configured temporary paths",
                    command=None,
                    requires_root=False,
                    timeout_seconds=120,
                )
            )

    if finding.type == "systemd_failed_unit":
        scfg = actions_cfg.get("systemd_restart_failed_units", {})
        if bool(scfg.get("enabled", False)):
            unit = str(finding.details.get("unit", ""))
            allowlist = set(scfg.get("allowlist_units", []) or [])
            if unit and unit in allowlist:
                plans.append(
                    ActionPlan(
                        name="systemd_restart_unit",
                        description=f"Restart {unit} via systemctl",
                        command=["systemctl", "restart", unit],
                        requires_root=True,
                        timeout_seconds=int(scfg.get("command_timeout_seconds", 30)),
                    )
                )

    if finding.type == "systemd_user_failed_unit":
        ucfg = actions_cfg.get("systemd_user_restart_failed_units", {}) or {}
        if bool(ucfg.get("enabled", False)):
            unit = str(finding.details.get("unit", ""))
            allowlist = set(ucfg.get("allowlist_units", []) or [])
            restart_all = bool(ucfg.get("restart_all_failed", False))
            if unit and (restart_all or unit in allowlist):
                plans.append(
                    ActionPlan(
                        name="systemd_user_restart_unit",
                        description=f"Restart {unit} via systemctl --user",
                        command=["systemctl", "--user", "restart", unit],
                        requires_root=False,
                        timeout_seconds=int(ucfg.get("command_timeout_seconds", 30)),
                    )
                )

    return plans


def execute_plan(cfg: dict[str, Any], plan: ActionPlan, finding: Finding) -> ActionResult:
    if plan.name == "tmp_cleanup":
        return _tmp_cleanup(cfg)

    if plan.command:
        try:
            res = run(plan.command, timeout_seconds=plan.timeout_seconds)
            if res.exit_code == 0:
                return ActionResult(
                    status="success",
                    exit_code=res.exit_code,
                    stdout=res.stdout,
                    stderr=res.stderr,
                    summary="command succeeded",
                )
            return ActionResult(
                status="failed",
                exit_code=res.exit_code,
                stdout=res.stdout,
                stderr=res.stderr,
                summary=f"command failed (exit={res.exit_code})",
            )
        except Exception as e:
            return ActionResult(
                status="failed",
                exit_code=None,
                stdout=None,
                stderr=str(e),
                summary="command execution error",
            )

    return ActionResult(
        status="skipped",
        exit_code=None,
        stdout=None,
        stderr=None,
        summary="no executor for plan",
    )


def _tmp_cleanup(cfg: dict[str, Any]) -> ActionResult:
    tcfg = cfg.get("actions", {}).get("tmp_cleanup", {}) or {}
    paths = [Path(p) for p in (tcfg.get("paths", []) or [])]
    max_age_hours = int(tcfg.get("max_age_hours", 72))
    max_bytes = int(tcfg.get("max_bytes_per_run", 512 * 1024 * 1024))
    allow_outside_tmp = bool(tcfg.get("allow_paths_outside_tmp", False))

    allowed_prefixes = [Path("/tmp"), Path("/var/tmp")]
    forbidden_exact = {
        Path("/"),
        Path("/etc"),
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        Path("/lib"),
        Path("/lib64"),
        Path("/opt"),
        Path("/home"),
        Path("/root"),
        Path("/var"),
    }

    now = time.time()
    cutoff = now - (max_age_hours * 3600)

    deleted_bytes = 0
    deleted_files = 0
    errors: list[str] = []

    def path_is_safe(p: Path) -> bool:
        try:
            rp = p.resolve()
        except Exception:
            return False
        if rp in forbidden_exact:
            return False
        if allow_outside_tmp:
            return True
        return any(
            str(rp).startswith(str(ap) + os.sep) or rp == ap for ap in allowed_prefixes
        )

    for p in paths:
        try:
            rp = p.resolve()
        except Exception:
            errors.append(f"invalid path: {p}")
            continue

        if not path_is_safe(rp):
            errors.append(f"refusing to clean unsafe path: {rp}")
            continue
        if not rp.exists():
            continue
        if not rp.is_dir():
            continue

        # Walk without following symlinks.
        for root, dirs, files in os.walk(rp, topdown=False, followlinks=False):
            if deleted_bytes >= max_bytes:
                break

            # Files
            for name in files:
                if deleted_bytes >= max_bytes:
                    break
                fp = Path(root) / name
                try:
                    st = fp.lstat()
                except Exception:
                    continue
                # Skip symlinks and non-regular files (do not follow links).
                if stat.S_ISLNK(st.st_mode):
                    continue
                if not stat.S_ISREG(st.st_mode):
                    continue
                if st.st_mtime > cutoff:
                    continue

                try:
                    size = int(st.st_size)
                except Exception:
                    size = 0
                if deleted_bytes + size > max_bytes:
                    continue

                try:
                    fp.unlink()
                    deleted_bytes += size
                    deleted_files += 1
                except Exception as e:
                    errors.append(f"unlink failed {fp}: {e}")

            # Try to remove empty dirs
            for d in dirs:
                dp = Path(root) / d
                try:
                    if dp.is_symlink():
                        continue
                    dp.rmdir()
                except Exception:
                    pass

    summary = f"tmp_cleanup deleted {deleted_files} files ({deleted_bytes} bytes)"
    if errors:
        log.debug("tmp_cleanup errors: %s", errors[:5])
        return ActionResult(
            status="failed" if deleted_files == 0 else "success",
            exit_code=0 if deleted_files > 0 else 1,
            stdout=summary,
            stderr="\n".join(errors[:50]),
            summary=summary + f"; {len(errors)} errors",
        )

    return ActionResult(
        status="success",
        exit_code=0,
        stdout=summary,
        stderr="",
        summary=summary,
    )
