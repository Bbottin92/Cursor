from __future__ import annotations

import os
import time
from typing import Any

from ..models import ActionPlan, Finding
from ..remediations import ActionResult
from ..subprocess_utils import run, which


def register(registry, *, config: dict[str, Any] | None = None) -> None:
    """
    Performance addon (local, lightweight):
    - Detect high load / low available memory
    - Optionally renice allowlisted processes (disabled by default)
    """
    cfg = dict(config or {})
    if not bool(cfg.get("enabled", False)):
        return

    load_threshold_per_cpu = float(cfg.get("load_threshold_per_cpu", 1.5))
    mem_available_percent_threshold = float(cfg.get("mem_available_percent_threshold", 10.0))
    window_seconds = int(cfg.get("window_seconds", 60))

    renice_enabled = bool(cfg.get("renice_enabled", False))
    renice_nice = int(cfg.get("renice_nice", 10))
    renice_allowlist = set([str(x) for x in (cfg.get("renice_allowlist", []) or [])])
    renice_max_pids = int(cfg.get("renice_max_pids", 3))

    def _meminfo() -> dict[str, int]:
        out: dict[str, int] = {}
        try:
            with open("/proc/meminfo", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    key = parts[0].rstrip(":")
                    try:
                        val = int(parts[1])
                    except Exception:
                        continue
                    # values are kB
                    out[key] = val * 1024
        except Exception:
            return {}
        return out

    def _top_processes(sort: str = "-pcpu", limit: int = 8) -> list[dict[str, Any]]:
        if which("ps") is None:
            return []
        try:
            # comm is just executable name (no spaces).
            res = run(
                ["ps", "-eo", "pid,comm,pcpu,pmem", "--no-headers", f"--sort={sort}"],
                timeout_seconds=2,
            )
        except Exception:
            return []
        if res.exit_code != 0:
            return []
        procs: list[dict[str, Any]] = []
        for line in (res.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 4)
            if len(parts) < 4:
                continue
            try:
                pid = int(parts[0])
                comm = parts[1]
                pcpu = float(parts[2])
                pmem = float(parts[3])
            except Exception:
                continue
            procs.append({"pid": pid, "comm": comm, "pcpu": pcpu, "pmem": pmem})
            if len(procs) >= limit:
                break
        return procs

    # Simple hysteresis per-run (keeps noise down).
    last_triggered: dict[str, float] = {"load": 0.0, "mem": 0.0}

    def check(_: dict[str, Any]) -> list[Finding]:
        findings: list[Finding] = []
        now = time.time()

        # Load average
        try:
            load1, load5, load15 = os.getloadavg()
        except Exception:
            load1 = load5 = load15 = 0.0
        cpus = os.cpu_count() or 1
        per_cpu = float(load1) / float(cpus) if cpus else float(load1)
        if per_cpu >= load_threshold_per_cpu and (now - last_triggered["load"]) >= window_seconds:
            last_triggered["load"] = now
            findings.append(
                Finding(
                    fingerprint="perf:high_load",
                    type="performance_high_load",
                    severity=3 if per_cpu < (load_threshold_per_cpu * 1.5) else 4,
                    title=f"High system load (load1={load1:.2f}, cpus={cpus})",
                    details={
                        "load1": load1,
                        "load5": load5,
                        "load15": load15,
                        "cpus": cpus,
                        "load1_per_cpu": round(per_cpu, 3),
                        "threshold_per_cpu": load_threshold_per_cpu,
                        "top_cpu": _top_processes(sort="-pcpu", limit=8),
                    },
                    diagnosis=(
                        f"1-minute load average is {load1:.2f} across {cpus} CPU(s) "
                        f"({per_cpu:.2f} per CPU), exceeding threshold {load_threshold_per_cpu:.2f}."
                    ),
                )
            )

        # Memory pressure
        mi = _meminfo()
        total = int(mi.get("MemTotal", 0))
        avail = int(mi.get("MemAvailable", 0))
        avail_pct = (avail / total * 100.0) if total else 100.0
        if avail_pct <= mem_available_percent_threshold and (now - last_triggered["mem"]) >= window_seconds:
            last_triggered["mem"] = now
            findings.append(
                Finding(
                    fingerprint="perf:low_mem",
                    type="performance_low_memory",
                    severity=4 if avail_pct < (mem_available_percent_threshold * 0.6) else 3,
                    title=f"Low available memory ({avail_pct:.1f}% available)",
                    details={
                        "mem_total_bytes": total,
                        "mem_available_bytes": avail,
                        "mem_available_percent": round(avail_pct, 2),
                        "threshold_percent": mem_available_percent_threshold,
                        "swap_total_bytes": int(mi.get("SwapTotal", 0)),
                        "swap_free_bytes": int(mi.get("SwapFree", 0)),
                        "top_mem": _top_processes(sort="-pmem", limit=8),
                    },
                    diagnosis=(
                        f"MemAvailable is {avail_pct:.1f}% (threshold {mem_available_percent_threshold:.1f}%). "
                        "This can cause freezes and app crashes."
                    ),
                )
            )

        return findings

    def plan(_: dict[str, Any], finding: Finding) -> list[ActionPlan]:
        if not renice_enabled:
            return []
        if finding.type not in {"performance_high_load", "performance_low_memory"}:
            return []
        if not renice_allowlist:
            return []
        return [
            ActionPlan(
                name="performance_renice_allowlisted",
                description=(
                    f"Increase nice for allowlisted processes to {renice_nice} "
                    f"(max {renice_max_pids} pids)"
                ),
                command=None,
                requires_root=False,
                timeout_seconds=5,
            )
        ]

    def execute(_: dict[str, Any], plan: ActionPlan, finding: Finding) -> ActionResult:
        if plan.name != "performance_renice_allowlisted":
            return ActionResult(
                status="skipped",
                exit_code=None,
                stdout=None,
                stderr=None,
                summary="unknown performance action",
            )

        # Renice is best-effort and user-scope only.
        if os.geteuid() == 0:
            # Running as root? Keep this conservative anyway.
            pass

        # Choose candidates from top_cpu/top_mem in the finding details.
        candidates = []
        if isinstance(finding.details.get("top_cpu"), list):
            candidates.extend(finding.details.get("top_cpu"))
        if isinstance(finding.details.get("top_mem"), list):
            candidates.extend(finding.details.get("top_mem"))

        # De-dup by pid preserving order
        seen = set()
        uniq = []
        for c in candidates:
            try:
                pid = int(c.get("pid"))
                comm = str(c.get("comm", ""))
            except Exception:
                continue
            if pid <= 1:
                continue
            if pid in seen:
                continue
            seen.add(pid)
            uniq.append((pid, comm))

        changed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[str] = []

        import errno

        for pid, comm in uniq:
            if len(changed) >= renice_max_pids:
                break
            if comm not in renice_allowlist:
                continue
            if pid == os.getpid():
                continue

            try:
                cur = os.getpriority(os.PRIO_PROCESS, pid)
            except Exception:
                cur = None

            # Only make it *less* prioritized (higher nice).
            if cur is not None and cur >= renice_nice:
                skipped.append({"pid": pid, "comm": comm, "reason": "already_niced", "nice": cur})
                continue

            try:
                os.setpriority(os.PRIO_PROCESS, pid, renice_nice)
                changed.append({"pid": pid, "comm": comm, "from_nice": cur, "to_nice": renice_nice})
            except PermissionError as e:
                skipped.append({"pid": pid, "comm": comm, "reason": "permission", "error": str(e)})
            except OSError as e:
                if getattr(e, "errno", None) == errno.ESRCH:
                    skipped.append({"pid": pid, "comm": comm, "reason": "gone"})
                else:
                    errors.append(f"setpriority pid={pid} comm={comm}: {e}")
            except Exception as e:
                errors.append(f"setpriority pid={pid} comm={comm}: {e}")

        summary = f"renice changed={len(changed)} skipped={len(skipped)}"
        return ActionResult(
            status="success" if changed else ("failed" if errors else "skipped"),
            exit_code=0 if changed else (1 if errors else 0),
            stdout=str({"changed": changed, "skipped": skipped}),
            stderr="\n".join(errors[:10]),
            summary=summary,
        )

    registry.add_check(check)
    registry.add_planner(plan)
    registry.add_executor("performance_renice_allowlisted", execute)
