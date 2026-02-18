"""System resource monitoring module.

Monitors CPU, memory, disk usage, load average, and file descriptors.
"""
from __future__ import annotations

import os
import subprocess
from .base import BaseModule
from persistence.models import Event, Severity, EventState, SystemSnapshot


class ResourceMonitorModule(BaseModule):
    name = "resource_monitor"

    def _get_cpu_percent(self) -> float:
        """Get CPU usage percent from /proc/stat."""
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
            parts = line.split()
            idle = int(parts[4])
            total = sum(int(x) for x in parts[1:])

            prev = self.store.get_context("cpu_prev", {"idle": 0, "total": 0})
            d_idle = idle - prev["idle"]
            d_total = total - prev["total"]
            self.store.set_context("cpu_prev", {"idle": idle, "total": total})

            if d_total == 0:
                return 0.0
            return round((1.0 - d_idle / d_total) * 100, 2)
        except Exception:
            return 0.0

    def _get_memory_info(self) -> dict:
        """Parse /proc/meminfo."""
        info = {}
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        info[key] = int(parts[1])
            total = info.get("MemTotal", 1)
            available = info.get("MemAvailable", info.get("MemFree", 0))
            used_pct = round((1.0 - available / total) * 100, 2) if total > 0 else 0.0
            return {"total_kb": total, "available_kb": available, "percent": used_pct}
        except Exception:
            return {"total_kb": 0, "available_kb": 0, "percent": 0.0}

    def _get_disk_usage(self) -> dict:
        """Get disk usage for root partition."""
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            free = st.f_bfree * st.f_frsize
            used_pct = round((1.0 - free / total) * 100, 2) if total > 0 else 0.0
            return {
                "total_bytes": total,
                "free_bytes": free,
                "percent": used_pct,
            }
        except Exception:
            return {"total_bytes": 0, "free_bytes": 0, "percent": 0.0}

    def _get_load_average(self) -> list[float]:
        try:
            return list(os.getloadavg())
        except Exception:
            return [0.0, 0.0, 0.0]

    def _get_cpu_count(self) -> int:
        try:
            return os.cpu_count() or 1
        except Exception:
            return 1

    def _get_open_fds(self) -> int:
        try:
            with open("/proc/sys/fs/file-nr", "r") as f:
                parts = f.read().split()
            return int(parts[0])
        except Exception:
            return 0

    def _get_uptime(self) -> float:
        try:
            with open("/proc/uptime", "r") as f:
                return float(f.read().split()[0])
        except Exception:
            return 0.0

    def take_snapshot(self) -> SystemSnapshot:
        """Capture a full system snapshot."""
        cpu = self._get_cpu_percent()
        mem = self._get_memory_info()
        disk = self._get_disk_usage()
        load = self._get_load_average()
        fds = self._get_open_fds()
        uptime = self._get_uptime()

        snap = SystemSnapshot(
            cpu_percent=cpu,
            memory_percent=mem["percent"],
            disk_percent=disk["percent"],
            load_average=load,
            open_file_descriptors=fds,
            uptime_seconds=uptime,
            custom_data={
                "memory_detail": mem,
                "disk_detail": disk,
            },
        )
        return snap

    def scan(self) -> list[Event]:
        events = []
        cpu = self._get_cpu_percent()
        mem = self._get_memory_info()
        disk = self._get_disk_usage()
        load = self._get_load_average()
        cpu_count = self._get_cpu_count()
        fds = self._get_open_fds()

        # High CPU
        if cpu > self.settings.cpu_threshold:
            similar = self.store.find_similar_events("cpu", "resource:cpu", hours=0.25)
            if not similar:
                events.append(Event(
                    source="resource:cpu",
                    category="cpu",
                    severity=Severity.WARNING.value if cpu < 95 else Severity.ERROR.value,
                    summary=f"High CPU usage: {cpu}%",
                    details={"cpu_percent": cpu, "threshold": self.settings.cpu_threshold},
                ))

        # High memory
        if mem["percent"] > self.settings.memory_threshold:
            similar = self.store.find_similar_events("memory", "resource:memory", hours=0.25)
            if not similar:
                sev = Severity.WARNING.value if mem["percent"] < 95 else Severity.CRITICAL.value
                events.append(Event(
                    source="resource:memory",
                    category="memory",
                    severity=sev,
                    summary=f"High memory usage: {mem['percent']}%",
                    details={"memory": mem, "threshold": self.settings.memory_threshold},
                ))

        # High disk usage
        if disk["percent"] > self.settings.disk_threshold:
            similar = self.store.find_similar_events("disk", "resource:disk", hours=0.5)
            if not similar:
                sev = Severity.WARNING.value if disk["percent"] < 95 else Severity.CRITICAL.value
                events.append(Event(
                    source="resource:disk",
                    category="disk",
                    severity=sev,
                    summary=f"High disk usage: {disk['percent']}%",
                    details={"disk": disk, "threshold": self.settings.disk_threshold},
                ))

        # High load average
        load_threshold = cpu_count * self.settings.load_threshold_multiplier
        if load[0] > load_threshold:
            similar = self.store.find_similar_events("load", "resource:load", hours=0.25)
            if not similar:
                events.append(Event(
                    source="resource:load",
                    category="load",
                    severity=Severity.WARNING.value,
                    summary=f"High load average: {load[0]:.2f} (threshold: {load_threshold:.1f})",
                    details={"load": load, "cpu_count": cpu_count, "threshold": load_threshold},
                ))

        # File descriptor exhaustion
        if fds > self.settings.fd_threshold:
            similar = self.store.find_similar_events("filedescriptor", "resource:fd", hours=0.5)
            if not similar:
                events.append(Event(
                    source="resource:fd",
                    category="filedescriptor",
                    severity=Severity.WARNING.value,
                    summary=f"High open file descriptors: {fds}",
                    details={"open_fds": fds, "threshold": self.settings.fd_threshold},
                ))

        return events
