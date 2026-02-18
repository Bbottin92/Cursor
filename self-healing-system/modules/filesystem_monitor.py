"""Filesystem health monitoring module.

Checks for read-only filesystems, inode exhaustion, and mount issues.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from .base import BaseModule
from persistence.models import Event, Severity, EventState


class FilesystemMonitorModule(BaseModule):
    name = "filesystem_monitor"

    def _check_readonly_root(self) -> bool:
        """Check if root filesystem is read-only by attempting a write."""
        test_path = "/tmp/.self_healing_fs_check"
        try:
            with open(test_path, "w") as f:
                f.write("test")
            os.remove(test_path)
            return False
        except (OSError, IOError):
            return True

    def _check_inode_usage(self) -> list[dict]:
        """Check inode usage on mounted filesystems."""
        critical = []
        try:
            result = subprocess.run(
                ["df", "-i", "--output=source,ipcent,itotal,iused,iavail,target"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n")[1:]:
                parts = line.split()
                if len(parts) >= 6 and "%" in parts[1]:
                    pct = int(parts[1].replace("%", ""))
                    if pct > 90:
                        critical.append({
                            "filesystem": parts[0],
                            "inode_percent": pct,
                            "mountpoint": parts[5],
                        })
        except Exception:
            pass
        return critical

    def _check_stale_mounts(self) -> list[str]:
        """Check for stale NFS or FUSE mounts."""
        stale = []
        try:
            result = subprocess.run(
                ["mount", "-l"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n"):
                if "nfs" in line.lower() or "fuse" in line.lower():
                    parts = line.split()
                    if len(parts) >= 3:
                        mountpoint = parts[2]
                        try:
                            os.listdir(mountpoint)
                        except (OSError, PermissionError):
                            stale.append(mountpoint)
        except Exception:
            pass
        return stale

    def scan(self) -> list[Event]:
        events = []

        # Check read-only root
        if self._check_readonly_root():
            similar = self.store.find_similar_events("filesystem", "fs:readonly", hours=0.5)
            if not similar:
                events.append(Event(
                    source="fs:readonly",
                    category="filesystem",
                    severity=Severity.CRITICAL.value,
                    summary="Root filesystem appears to be read-only",
                    details={"test_path": "/tmp/.self_healing_fs_check"},
                ))

        # Check inode exhaustion
        inode_issues = self._check_inode_usage()
        for issue in inode_issues:
            similar = self.store.find_similar_events(
                "inode", f"fs:inode:{issue['mountpoint']}", hours=0.5
            )
            if not similar:
                events.append(Event(
                    source=f"fs:inode:{issue['mountpoint']}",
                    category="inode",
                    severity=Severity.ERROR.value,
                    summary=f"Inode usage critical on {issue['mountpoint']}: {issue['inode_percent']}%",
                    details=issue,
                ))

        # Check stale mounts
        stale = self._check_stale_mounts()
        for mount in stale:
            similar = self.store.find_similar_events("mount", f"fs:stale:{mount}", hours=1.0)
            if not similar:
                events.append(Event(
                    source=f"fs:stale:{mount}",
                    category="mount",
                    severity=Severity.WARNING.value,
                    summary=f"Stale mount detected: {mount}",
                    details={"mountpoint": mount},
                ))

        return events
