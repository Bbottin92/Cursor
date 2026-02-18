from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .models import ActionPlan, Finding

SCHEMA_VERSION = 1


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS incidents (
          id TEXT PRIMARY KEY,
          fingerprint TEXT UNIQUE,
          type TEXT NOT NULL,
          severity INTEGER NOT NULL,
          title TEXT NOT NULL,
          diagnosis TEXT NOT NULL,
          details_json TEXT NOT NULL,
          status TEXT NOT NULL,
          occurrences INTEGER NOT NULL,
          first_seen_ts REAL NOT NULL,
          last_seen_ts REAL NOT NULL,
          acknowledged_ts REAL,
          fixed_ts REAL,
          last_error TEXT,
          resolution_summary TEXT
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS actions (
          id TEXT PRIMARY KEY,
          incident_id TEXT NOT NULL,
          name TEXT NOT NULL,
          description TEXT NOT NULL,
          command_json TEXT,
          requires_root INTEGER NOT NULL,
          started_ts REAL NOT NULL,
          finished_ts REAL NOT NULL,
          status TEXT NOT NULL,
          exit_code INTEGER,
          stdout TEXT,
          stderr TEXT,
          notes TEXT,
          FOREIGN KEY(incident_id) REFERENCES incidents(id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_actions_incident_name ON actions(incident_id, name, finished_ts);"
    )

    # schema version marker
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )


def upsert_incident_from_finding(conn: sqlite3.Connection, finding: Finding) -> str:
    now = time.time()

    existing = conn.execute(
        "SELECT id, status FROM incidents WHERE fingerprint=?",
        (finding.fingerprint,),
    ).fetchone()

    if existing is None:
        incident_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO incidents(
              id, fingerprint, type, severity, title, diagnosis, details_json,
              status, occurrences, first_seen_ts, last_seen_ts, acknowledged_ts
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, 'open', 1, ?, ?, ?)
            """,
            (
                incident_id,
                finding.fingerprint,
                finding.type,
                int(finding.severity),
                finding.title,
                finding.diagnosis,
                json.dumps(finding.details, sort_keys=True),
                now,
                now,
                now,
            ),
        )
        return incident_id

    incident_id = str(existing["id"])
    status = str(existing["status"])
    # If it was marked fixed previously and re-occurs, reopen.
    if status == "fixed":
        conn.execute(
            """
            UPDATE incidents
            SET status='open', fixed_ts=NULL, resolution_summary=NULL
            WHERE id=?
            """,
            (incident_id,),
        )

    conn.execute(
        """
        UPDATE incidents
        SET severity=?,
            title=?,
            diagnosis=?,
            details_json=?,
            occurrences=occurrences+1,
            last_seen_ts=?
        WHERE id=?
        """,
        (
            int(finding.severity),
            finding.title,
            finding.diagnosis,
            json.dumps(finding.details, sort_keys=True),
            now,
            incident_id,
        ),
    )
    return incident_id


def mark_incident_fixed(conn: sqlite3.Connection, incident_id: str, summary: str) -> None:
    now = time.time()
    conn.execute(
        """
        UPDATE incidents
        SET status='fixed', fixed_ts=?, resolution_summary=?
        WHERE id=?
        """,
        (now, summary, incident_id),
    )


def set_incident_last_error(conn: sqlite3.Connection, incident_id: str, err: str) -> None:
    conn.execute(
        "UPDATE incidents SET last_error=? WHERE id=?",
        (err[:4000], incident_id),
    )


def record_action(
    conn: sqlite3.Connection,
    incident_id: str,
    plan: ActionPlan,
    *,
    status: str,
    started_ts: float,
    finished_ts: float,
    exit_code: int | None,
    stdout: str | None,
    stderr: str | None,
    notes: str | None = None,
) -> str:
    action_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO actions(
          id, incident_id, name, description, command_json, requires_root,
          started_ts, finished_ts, status, exit_code, stdout, stderr, notes
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action_id,
            incident_id,
            plan.name,
            plan.description,
            json.dumps(plan.command) if plan.command else None,
            1 if plan.requires_root else 0,
            started_ts,
            finished_ts,
            status,
            exit_code,
            stdout,
            stderr,
            notes,
        ),
    )
    return action_id


def last_action_finished_ts(
    conn: sqlite3.Connection, incident_id: str, action_name: str
) -> float | None:
    row = conn.execute(
        """
        SELECT finished_ts FROM actions
        WHERE incident_id=? AND name=?
        ORDER BY finished_ts DESC
        LIMIT 1
        """,
        (incident_id, action_name),
    ).fetchone()
    if row is None:
        return None
    return float(row["finished_ts"])


def list_incidents(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          id, fingerprint, type, severity, title, status, occurrences,
          first_seen_ts, last_seen_ts, acknowledged_ts, fixed_ts,
          last_error, resolution_summary
        FROM incidents
        ORDER BY last_seen_ts DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [dict(r) for r in rows]


def get_incident(conn: sqlite3.Connection, incident_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
          id, fingerprint, type, severity, title, diagnosis, details_json, status,
          occurrences, first_seen_ts, last_seen_ts, acknowledged_ts, fixed_ts,
          last_error, resolution_summary
        FROM incidents
        WHERE id=?
        """,
        (incident_id,),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["details"] = json.loads(d.pop("details_json", "{}"))
    except Exception:
        d["details"] = {}
    return d


def list_actions_for_incident(
    conn: sqlite3.Connection, incident_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          id, incident_id, name, description, command_json, requires_root,
          started_ts, finished_ts, status, exit_code, stdout, stderr, notes
        FROM actions
        WHERE incident_id=?
        ORDER BY started_ts DESC
        LIMIT ?
        """,
        (incident_id, int(limit)),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        cmd_json = d.pop("command_json", None)
        try:
            d["command"] = json.loads(cmd_json) if cmd_json else None
        except Exception:
            d["command"] = None
        out.append(d)
    return out


def create_manual_incident(
    conn: sqlite3.Connection,
    *,
    incident_type: str,
    title: str,
    severity: int,
    diagnosis: str,
    details: dict[str, Any],
) -> str:
    now = time.time()
    incident_id = str(uuid.uuid4())
    fingerprint = f"manual:{incident_id}"
    conn.execute(
        """
        INSERT INTO incidents(
          id, fingerprint, type, severity, title, diagnosis, details_json,
          status, occurrences, first_seen_ts, last_seen_ts, acknowledged_ts
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, 'open', 1, ?, ?, ?)
        """,
        (
            incident_id,
            fingerprint,
            incident_type,
            int(severity),
            title,
            diagnosis,
            json.dumps(details, sort_keys=True),
            now,
            now,
            now,
        ),
    )
    return incident_id
