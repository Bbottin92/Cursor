"""Log file monitoring module.

Watches system log files for error patterns, tracks file positions
across restarts via persistent context.
"""
from __future__ import annotations

import os
import re
import time
from typing import Optional

from .base import BaseModule
from persistence.models import Event, Severity, EventState


class LogMonitorModule(BaseModule):
    name = "log_monitor"

    def __init__(self, settings, store):
        super().__init__(settings, store)
        self._compiled_patterns = []
        for p in self.settings.error_patterns:
            try:
                self._compiled_patterns.append({
                    "regex": re.compile(p["pattern"], re.IGNORECASE),
                    "severity": p.get("severity", "error"),
                    "category": p.get("category", "unknown"),
                    "pattern": p["pattern"],
                })
            except re.error:
                self.logger.warning(f"Invalid regex pattern: {p['pattern']}")

    def _get_file_position(self, filepath: str) -> dict:
        """Get stored file position (inode + offset) for a log file."""
        key = f"log_pos:{filepath}"
        return self.store.get_context(key, {"inode": 0, "offset": 0})

    def _save_file_position(self, filepath: str, inode: int, offset: int):
        key = f"log_pos:{filepath}"
        self.store.set_context(key, {"inode": inode, "offset": offset})

    def _read_new_lines(self, filepath: str) -> list[str]:
        """Read only new lines from a log file since last check."""
        if not os.path.exists(filepath):
            return []

        try:
            stat = os.stat(filepath)
            current_inode = stat.st_ino
            current_size = stat.st_size
        except OSError:
            return []

        pos = self._get_file_position(filepath)
        stored_inode = pos["inode"]
        stored_offset = pos["offset"]

        # File rotated (different inode) or truncated (size < offset)
        if current_inode != stored_inode or current_size < stored_offset:
            stored_offset = 0

        if current_size <= stored_offset:
            return []

        lines = []
        try:
            with open(filepath, "r", errors="replace") as f:
                f.seek(stored_offset)
                lines = f.readlines()
                new_offset = f.tell()
            self._save_file_position(filepath, current_inode, new_offset)
        except (OSError, PermissionError) as e:
            self.logger.warning(f"Cannot read {filepath}: {e}")

        return lines

    def _check_journald(self) -> list[str]:
        """Read recent journal entries as a fallback."""
        lines = []
        try:
            import subprocess
            last_check = self.store.get_context("journal_last_cursor", "")
            cmd = ["journalctl", "--no-pager", "-p", "err", "-n", "200", "--output=short"]
            if last_check:
                cmd.extend(["--after-cursor", last_check])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
            # Get current cursor for next time
            cursor_result = subprocess.run(
                ["journalctl", "--no-pager", "-n", "1", "--show-cursor", "--output=short"],
                capture_output=True, text=True, timeout=5,
            )
            if cursor_result.returncode == 0:
                for line in cursor_result.stdout.strip().split("\n"):
                    if line.startswith("-- cursor:"):
                        cursor = line.split(":", 1)[1].strip()
                        self.store.set_context("journal_last_cursor", cursor)
                        break
        except Exception as e:
            self.logger.debug(f"journalctl fallback failed: {e}")
        return lines

    def scan(self) -> list[Event]:
        events = []
        all_lines = []

        for filepath in self.settings.monitored_logs:
            new_lines = self._read_new_lines(filepath)
            for line in new_lines:
                all_lines.append((filepath, line.strip()))

        journal_lines = self._check_journald()
        for line in journal_lines:
            if line and not line.startswith("--"):
                all_lines.append(("journald", line.strip()))

        seen_patterns = set()
        for source, line in all_lines:
            if not line:
                continue
            for pat in self._compiled_patterns:
                if pat["regex"].search(line):
                    dedup_key = f"{pat['category']}:{pat['pattern']}:{source}"
                    if dedup_key in seen_patterns:
                        continue
                    seen_patterns.add(dedup_key)

                    # Check cooldown: don't fire same event too frequently
                    similar = self.store.find_similar_events(
                        pat["category"], f"log:{source}", hours=0.1
                    )
                    if similar:
                        continue

                    event = Event(
                        source=f"log:{source}",
                        category=pat["category"],
                        severity=pat["severity"],
                        state=EventState.DETECTED.value,
                        summary=f"Log pattern matched: {pat['pattern']}",
                        details={
                            "log_file": source,
                            "matched_line": line[:1000],
                            "pattern": pat["pattern"],
                        },
                    )
                    events.append(event)

        return events
