"""SQLite-based persistent context store.

Provides durable storage for events, diagnoses, fixes, system snapshots,
and arbitrary key-value context. Survives reboots and crashes.
Uses WAL mode for concurrent read access and atomic writes.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .models import Event, Diagnosis, Fix, SystemSnapshot, EventState

logger = logging.getLogger("self-healing.persistence")

DEFAULT_DB_PATH = "/var/lib/self-healing/context.db"


class ContextStore:
    """Thread-safe SQLite persistent context store."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_directory()
        self._init_db()

    def _ensure_directory(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS events (
                        id TEXT PRIMARY KEY,
                        timestamp REAL NOT NULL,
                        source TEXT NOT NULL DEFAULT '',
                        category TEXT NOT NULL DEFAULT '',
                        severity TEXT NOT NULL DEFAULT 'error',
                        state TEXT NOT NULL DEFAULT 'detected',
                        summary TEXT NOT NULL DEFAULT '',
                        details TEXT NOT NULL DEFAULT '{}',
                        related_events TEXT NOT NULL DEFAULT '[]',
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        max_retries INTEGER NOT NULL DEFAULT 3,
                        last_updated REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS diagnoses (
                        id TEXT PRIMARY KEY,
                        event_id TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        root_cause TEXT NOT NULL DEFAULT '',
                        confidence REAL NOT NULL DEFAULT 0.0,
                        suggested_fixes TEXT NOT NULL DEFAULT '[]',
                        analysis TEXT NOT NULL DEFAULT '{}',
                        context_used TEXT NOT NULL DEFAULT '{}',
                        FOREIGN KEY (event_id) REFERENCES events(id)
                    );

                    CREATE TABLE IF NOT EXISTS fixes (
                        id TEXT PRIMARY KEY,
                        event_id TEXT NOT NULL,
                        diagnosis_id TEXT NOT NULL DEFAULT '',
                        timestamp REAL NOT NULL,
                        fix_type TEXT NOT NULL DEFAULT '',
                        description TEXT NOT NULL DEFAULT '',
                        commands_run TEXT NOT NULL DEFAULT '[]',
                        result TEXT NOT NULL DEFAULT 'success',
                        output TEXT NOT NULL DEFAULT '',
                        rollback_info TEXT NOT NULL DEFAULT '{}',
                        duration_seconds REAL NOT NULL DEFAULT 0.0,
                        FOREIGN KEY (event_id) REFERENCES events(id)
                    );

                    CREATE TABLE IF NOT EXISTS snapshots (
                        id TEXT PRIMARY KEY,
                        timestamp REAL NOT NULL,
                        cpu_percent REAL DEFAULT 0.0,
                        memory_percent REAL DEFAULT 0.0,
                        disk_percent REAL DEFAULT 0.0,
                        load_average TEXT DEFAULT '[]',
                        failed_services TEXT DEFAULT '[]',
                        network_status TEXT DEFAULT 'unknown',
                        open_file_descriptors INTEGER DEFAULT 0,
                        zombie_processes INTEGER DEFAULT 0,
                        uptime_seconds REAL DEFAULT 0.0,
                        custom_data TEXT DEFAULT '{}'
                    );

                    CREATE TABLE IF NOT EXISTS context (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS cursor_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        direction TEXT NOT NULL DEFAULT 'outbound',
                        message_type TEXT NOT NULL DEFAULT 'info',
                        payload TEXT NOT NULL DEFAULT '{}',
                        processed INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE INDEX IF NOT EXISTS idx_events_state ON events(state);
                    CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
                    CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
                    CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
                    CREATE INDEX IF NOT EXISTS idx_diagnoses_event ON diagnoses(event_id);
                    CREATE INDEX IF NOT EXISTS idx_fixes_event ON fixes(event_id);
                    CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON snapshots(timestamp);
                    CREATE INDEX IF NOT EXISTS idx_cursor_messages_processed ON cursor_messages(processed);
                """)
                conn.commit()
            finally:
                conn.close()

    # --- Event operations ---

    def store_event(self, event: Event) -> str:
        with self._lock:
            conn = self._get_conn()
            try:
                d = event.to_dict()
                conn.execute(
                    """INSERT OR REPLACE INTO events
                       (id, timestamp, source, category, severity, state,
                        summary, details, related_events, retry_count,
                        max_retries, last_updated)
                       VALUES (:id, :timestamp, :source, :category, :severity,
                               :state, :summary, :details, :related_events,
                               :retry_count, :max_retries, :last_updated)""",
                    d,
                )
                conn.commit()
                return event.id
            finally:
                conn.close()

    def get_event(self, event_id: str) -> Optional[Event]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
            return Event.from_dict(dict(row)) if row else None
        finally:
            conn.close()

    def get_events_by_state(self, state: str, limit: int = 100) -> list[Event]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM events WHERE state = ? ORDER BY timestamp DESC LIMIT ?",
                (state, limit),
            ).fetchall()
            return [Event.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    def get_active_events(self, limit: int = 100) -> list[Event]:
        conn = self._get_conn()
        try:
            active_states = [
                EventState.DETECTED.value,
                EventState.DIAGNOSING.value,
                EventState.DIAGNOSED.value,
                EventState.FIXING.value,
                EventState.MONITORING.value,
            ]
            placeholders = ",".join("?" * len(active_states))
            rows = conn.execute(
                f"SELECT * FROM events WHERE state IN ({placeholders}) "
                f"ORDER BY timestamp DESC LIMIT ?",
                active_states + [limit],
            ).fetchall()
            return [Event.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    def get_recent_events(self, hours: float = 24, limit: int = 500) -> list[Event]:
        conn = self._get_conn()
        try:
            cutoff = time.time() - (hours * 3600)
            rows = conn.execute(
                "SELECT * FROM events WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
            return [Event.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    def update_event_state(self, event_id: str, state: str):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE events SET state = ?, last_updated = ? WHERE id = ?",
                    (state, time.time(), event_id),
                )
                conn.commit()
            finally:
                conn.close()

    def increment_retry(self, event_id: str) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE events SET retry_count = retry_count + 1, last_updated = ? WHERE id = ?",
                    (time.time(), event_id),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT retry_count FROM events WHERE id = ?", (event_id,)
                ).fetchone()
                return row["retry_count"] if row else 0
            finally:
                conn.close()

    def find_similar_events(self, category: str, source: str, hours: float = 48) -> list[Event]:
        conn = self._get_conn()
        try:
            cutoff = time.time() - (hours * 3600)
            rows = conn.execute(
                "SELECT * FROM events WHERE category = ? AND source = ? AND timestamp > ? "
                "ORDER BY timestamp DESC LIMIT 50",
                (category, source, cutoff),
            ).fetchall()
            return [Event.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    # --- Diagnosis operations ---

    def store_diagnosis(self, diagnosis: Diagnosis) -> str:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO diagnoses
                       (id, event_id, timestamp, root_cause, confidence,
                        suggested_fixes, analysis, context_used)
                       VALUES (:id, :event_id, :timestamp, :root_cause,
                               :confidence, :suggested_fixes, :analysis,
                               :context_used)""",
                    diagnosis.to_dict(),
                )
                conn.commit()
                return diagnosis.id
            finally:
                conn.close()

    def get_diagnoses_for_event(self, event_id: str) -> list[Diagnosis]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM diagnoses WHERE event_id = ? ORDER BY timestamp DESC",
                (event_id,),
            ).fetchall()
            return [Diagnosis.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    # --- Fix operations ---

    def store_fix(self, fix: Fix) -> str:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO fixes
                       (id, event_id, diagnosis_id, timestamp, fix_type,
                        description, commands_run, result, output,
                        rollback_info, duration_seconds)
                       VALUES (:id, :event_id, :diagnosis_id, :timestamp,
                               :fix_type, :description, :commands_run, :result,
                               :output, :rollback_info, :duration_seconds)""",
                    fix.to_dict(),
                )
                conn.commit()
                return fix.id
            finally:
                conn.close()

    def get_fixes_for_event(self, event_id: str) -> list[Fix]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM fixes WHERE event_id = ? ORDER BY timestamp DESC",
                (event_id,),
            ).fetchall()
            return [Fix.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    def get_fix_history(self, fix_type: str = "", limit: int = 100) -> list[Fix]:
        conn = self._get_conn()
        try:
            if fix_type:
                rows = conn.execute(
                    "SELECT * FROM fixes WHERE fix_type = ? ORDER BY timestamp DESC LIMIT ?",
                    (fix_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM fixes ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
            return [Fix.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    # --- Snapshot operations ---

    def store_snapshot(self, snapshot: SystemSnapshot) -> str:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO snapshots
                       (id, timestamp, cpu_percent, memory_percent, disk_percent,
                        load_average, failed_services, network_status,
                        open_file_descriptors, zombie_processes, uptime_seconds,
                        custom_data)
                       VALUES (:id, :timestamp, :cpu_percent, :memory_percent,
                               :disk_percent, :load_average, :failed_services,
                               :network_status, :open_file_descriptors,
                               :zombie_processes, :uptime_seconds, :custom_data)""",
                    snapshot.to_dict(),
                )
                conn.commit()
                return snapshot.id
            finally:
                conn.close()

    def get_latest_snapshot(self) -> Optional[SystemSnapshot]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM snapshots ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            return SystemSnapshot.from_dict(dict(row)) if row else None
        finally:
            conn.close()

    def get_snapshots(self, hours: float = 1, limit: int = 60) -> list[SystemSnapshot]:
        conn = self._get_conn()
        try:
            cutoff = time.time() - (hours * 3600)
            rows = conn.execute(
                "SELECT * FROM snapshots WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
            return [SystemSnapshot.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    def prune_old_snapshots(self, keep_hours: float = 72):
        with self._lock:
            conn = self._get_conn()
            try:
                cutoff = time.time() - (keep_hours * 3600)
                conn.execute("DELETE FROM snapshots WHERE timestamp < ?", (cutoff,))
                conn.commit()
            finally:
                conn.close()

    # --- Key-value context ---

    def set_context(self, key: str, value: Any):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO context (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, json.dumps(value), time.time()),
                )
                conn.commit()
            finally:
                conn.close()

    def get_context(self, key: str, default: Any = None) -> Any:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT value FROM context WHERE key = ?", (key,)).fetchone()
            return json.loads(row["value"]) if row else default
        finally:
            conn.close()

    def get_all_context(self) -> dict[str, Any]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT key, value FROM context").fetchall()
            return {r["key"]: json.loads(r["value"]) for r in rows}
        finally:
            conn.close()

    # --- Cursor communication ---

    def queue_cursor_message(self, message_type: str, payload: dict, direction: str = "outbound"):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO cursor_messages
                       (timestamp, direction, message_type, payload, processed)
                       VALUES (?, ?, ?, ?, 0)""",
                    (time.time(), direction, message_type, json.dumps(payload)),
                )
                conn.commit()
            finally:
                conn.close()

    def get_unprocessed_messages(self, direction: str = "inbound", limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM cursor_messages
                   WHERE direction = ? AND processed = 0
                   ORDER BY id ASC LIMIT ?""",
                (direction, limit),
            ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["payload"] = json.loads(d["payload"])
                results.append(d)
            return results
        finally:
            conn.close()

    def mark_message_processed(self, message_id: int):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE cursor_messages SET processed = 1 WHERE id = ?",
                    (message_id,),
                )
                conn.commit()
            finally:
                conn.close()

    # --- Statistics ---

    def get_statistics(self) -> dict:
        conn = self._get_conn()
        try:
            stats = {}
            stats["total_events"] = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            stats["active_events"] = len(self.get_active_events(limit=1000))
            stats["total_fixes"] = conn.execute("SELECT COUNT(*) FROM fixes").fetchone()[0]
            stats["successful_fixes"] = conn.execute(
                "SELECT COUNT(*) FROM fixes WHERE result = 'success'"
            ).fetchone()[0]
            stats["failed_fixes"] = conn.execute(
                "SELECT COUNT(*) FROM fixes WHERE result = 'failed'"
            ).fetchone()[0]
            stats["total_snapshots"] = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            stats["pending_cursor_messages"] = conn.execute(
                "SELECT COUNT(*) FROM cursor_messages WHERE processed = 0"
            ).fetchone()[0]

            if stats["total_fixes"] > 0:
                stats["fix_success_rate"] = round(
                    stats["successful_fixes"] / stats["total_fixes"] * 100, 2
                )
            else:
                stats["fix_success_rate"] = 0.0

            return stats
        finally:
            conn.close()
