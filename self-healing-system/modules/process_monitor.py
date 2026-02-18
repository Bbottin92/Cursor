"""Process monitoring module.

Detects zombie processes, runaway processes, and OOM-risk processes.
"""
from __future__ import annotations

import os
import subprocess

from .base import BaseModule
from persistence.models import Event, Severity, EventState


class ProcessMonitorModule(BaseModule):
    name = "process_monitor"

    def _count_zombies(self) -> tuple[int, list[dict]]:
        """Count zombie processes and return details."""
        zombies = []
        count = 0
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n")[1:]:
                parts = line.split(None, 10)
                if len(parts) >= 8 and parts[7] == "Z":
                    count += 1
                    if count <= 20:
                        zombies.append({
                            "user": parts[0],
                            "pid": parts[1],
                            "command": parts[10] if len(parts) > 10 else "unknown",
                        })
        except Exception:
            pass
        return count, zombies

    def _find_high_oom_score(self) -> list[dict]:
        """Find processes with high OOM scores that might be killed soon."""
        high_oom = []
        try:
            for pid_dir in os.listdir("/proc"):
                if not pid_dir.isdigit():
                    continue
                try:
                    oom_path = f"/proc/{pid_dir}/oom_score"
                    comm_path = f"/proc/{pid_dir}/comm"
                    if os.path.exists(oom_path):
                        with open(oom_path) as f:
                            score = int(f.read().strip())
                        if score > self.settings.oom_score_threshold:
                            name = "unknown"
                            if os.path.exists(comm_path):
                                with open(comm_path) as f:
                                    name = f.read().strip()
                            high_oom.append({
                                "pid": int(pid_dir),
                                "name": name,
                                "oom_score": score,
                            })
                except (OSError, ValueError, PermissionError):
                    continue
        except Exception:
            pass
        return sorted(high_oom, key=lambda x: x["oom_score"], reverse=True)[:10]

    def _find_runaway_processes(self) -> list[dict]:
        """Find processes consuming excessive CPU time."""
        runaways = []
        try:
            result = subprocess.run(
                ["ps", "-eo", "pid,pcpu,pmem,etime,comm", "--sort=-pcpu"],
                capture_output=True, text=True, timeout=10,
            )
            lines = result.stdout.strip().split("\n")[1:]
            for line in lines[:20]:
                parts = line.split(None, 4)
                if len(parts) >= 5:
                    cpu = float(parts[1])
                    if cpu > 95:
                        runaways.append({
                            "pid": parts[0],
                            "cpu_percent": cpu,
                            "mem_percent": float(parts[2]),
                            "elapsed": parts[3],
                            "command": parts[4],
                        })
        except Exception:
            pass
        return runaways

    def scan(self) -> list[Event]:
        events = []

        # Check for zombies
        zombie_count, zombie_details = self._count_zombies()
        if zombie_count > self.settings.zombie_threshold:
            similar = self.store.find_similar_events("zombie", "process:zombie", hours=0.25)
            if not similar:
                events.append(Event(
                    source="process:zombie",
                    category="zombie",
                    severity=Severity.WARNING.value,
                    summary=f"{zombie_count} zombie processes detected",
                    details={
                        "count": zombie_count,
                        "samples": zombie_details[:10],
                        "threshold": self.settings.zombie_threshold,
                    },
                ))

        # Check high OOM score processes
        high_oom = self._find_high_oom_score()
        if high_oom:
            similar = self.store.find_similar_events("oom_risk", "process:oom", hours=0.5)
            if not similar:
                events.append(Event(
                    source="process:oom",
                    category="oom_risk",
                    severity=Severity.WARNING.value,
                    summary=f"{len(high_oom)} processes at high OOM risk",
                    details={"processes": high_oom},
                ))

        # Check runaway processes
        runaways = self._find_runaway_processes()
        if runaways:
            similar = self.store.find_similar_events("runaway", "process:runaway", hours=0.25)
            if not similar:
                events.append(Event(
                    source="process:runaway",
                    category="runaway",
                    severity=Severity.WARNING.value,
                    summary=f"{len(runaways)} runaway processes detected (>95% CPU)",
                    details={"processes": runaways},
                ))

        # Store counts for snapshots
        self.store.set_context("zombie_count", zombie_count)

        return events
