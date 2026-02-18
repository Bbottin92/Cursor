from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ._paths import default_control_socket_path, default_db_path, default_log_path
from .agent import AgentAlreadyRunning, AutohealAgent
from .config import load_config
from .control import call_control
from .db import (
    connect,
    create_manual_incident,
    get_incident,
    get_recommendation,
    list_actions_for_incident,
    list_incidents,
    list_recommendations,
    mark_incident_fixed,
    set_recommendation_status,
)


def tool_specs() -> list[dict[str, Any]]:
    """
    Minimal tool specs for MCP stdio fallback, and for manifest output.

    Shape matches MCP tool objects (name/description/inputSchema).
    """
    return [
        {
            "name": "autoheal_status",
            "title": "autoheal status",
            "description": "Get agent status (prefers control socket; falls back to DB).",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "autoheal_incidents_list",
            "title": "list incidents",
            "description": "List known incidents from persistent state.",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 50, "minimum": 1}},
            },
        },
        {
            "name": "autoheal_incident_get",
            "title": "get incident",
            "description": "Get a single incident (includes recent actions).",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
        {
            "name": "autoheal_report_incident",
            "title": "report incident",
            "description": "Create a manual incident (requires AUTOHEAL_TOKEN if configured).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "incident_type": {"type": "string", "default": "manual"},
                    "severity": {"type": "integer", "default": 3, "minimum": 1, "maximum": 5},
                    "diagnosis": {"type": "string", "default": "reported via MCP"},
                    "details_json": {"type": "string", "default": "{}"},
                },
                "required": ["title"],
            },
        },
        {
            "name": "autoheal_mark_fixed",
            "title": "mark incident fixed",
            "description": "Manually mark an incident fixed (requires AUTOHEAL_TOKEN if configured).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "summary": {"type": "string", "default": "marked fixed"},
                },
                "required": ["id"],
            },
        },
        {
            "name": "autoheal_recommendations_list",
            "title": "list recommendations",
            "description": "List persistent optimization/workflow suggestions.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "minimum": 1},
                    "status": {"type": "string", "enum": ["open", "accepted", "dismissed"]},
                },
            },
        },
        {
            "name": "autoheal_recommendation_get",
            "title": "get recommendation",
            "description": "Get a single recommendation (includes events).",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
        {
            "name": "autoheal_recommendation_accept",
            "title": "accept recommendation",
            "description": "Accept a recommendation (records feedback; requires token if configured).",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "note": {"type": "string"}},
                "required": ["id"],
            },
        },
        {
            "name": "autoheal_recommendation_dismiss",
            "title": "dismiss recommendation",
            "description": "Dismiss a recommendation (records feedback; requires token if configured).",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "note": {"type": "string"}},
                "required": ["id"],
            },
        },
        {
            "name": "autoheal_run_once",
            "title": "run one cycle",
            "description": "Trigger the running agent to run a cycle (or run locally if not running).",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "autoheal_tail_log",
            "title": "tail agent log",
            "description": "Read the last N lines from the agent log file.",
            "inputSchema": {
                "type": "object",
                "properties": {"lines": {"type": "integer", "default": 200, "minimum": 1}},
            },
        },
    ]


def _tail_text_file(
    path: Path, *, max_lines: int = 200, max_bytes: int = 200_000
) -> list[str]:
    """
    Best-effort tail without reading entire file.
    """
    if max_lines <= 0:
        return []
    try:
        size = path.stat().st_size
    except Exception:
        return []
    if size <= 0:
        return []

    read_size = min(int(size), int(max_bytes))
    try:
        with path.open("rb") as f:
            f.seek(-read_size, os.SEEK_END)
            data = f.read(read_size)
    except Exception:
        return []

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-int(max_lines) :]


def _socket_exists(sock: Path) -> bool:
    try:
        return sock.exists()
    except Exception:
        return False


class AutohealOps:
    """
    Core operations exposed via MCP. No dependency on the MCP SDK.
    """

    def __init__(self, *, state_dir: Path, config_path: str | Path | None, token: str | None):
        self.state_dir = state_dir
        self.config_path = config_path
        self.token = token

        self.control_sock = default_control_socket_path(state_dir)
        self.db_path = default_db_path(state_dir)
        self.log_path = default_log_path(state_dir)
        self._token_required = self._detect_token_required()

    def _detect_token_required(self) -> bool:
        """
        The agent enforces tokens if configured. MCP should only *require* a token
        when config says it's required; otherwise we allow calls without forcing
        users to set a token unnecessarily.
        """
        try:
            loaded = load_config(self.config_path)
            token = loaded.data.get("control", {}).get("token", None)
            if token is None:
                return False
            token = str(token).strip()
            return bool(token)
        except Exception:
            # If config can't be read, do not hard-fail MCP usage.
            return False

    def _call(self, method: str, params: dict[str, Any], *, require_token: bool) -> Any:
        if not _socket_exists(self.control_sock):
            raise RuntimeError(f"agent control socket not found: {self.control_sock}")
        if require_token and self._token_required and not self.token:
            raise PermissionError("AUTOHEAL_TOKEN required by config for this operation")
        resp = call_control(self.control_sock, method=method, params=params, token=self.token)
        if not resp.ok:
            raise RuntimeError(resp.error or "control call failed")
        return resp.result

    def status(self) -> dict[str, Any]:
        if _socket_exists(self.control_sock):
            try:
                return dict(self._call("status", {}, require_token=False))
            except Exception:
                pass

        conn = connect(self.db_path)
        try:
            return {
                "agent_running": False,
                "state_dir": str(self.state_dir),
                "db_path": str(self.db_path),
                "control_socket_path": str(self.control_sock),
                "recent_incidents": list_incidents(conn, limit=5),
            }
        finally:
            conn.close()

    def incidents_list(self, limit: int = 50) -> list[dict[str, Any]]:
        if _socket_exists(self.control_sock):
            try:
                res = self._call("incidents.list", {"limit": int(limit)}, require_token=False)
                return list(res)
            except Exception:
                pass
        conn = connect(self.db_path)
        try:
            return list_incidents(conn, limit=int(limit))
        finally:
            conn.close()

    def incident_get(self, id: str) -> dict[str, Any]:
        if _socket_exists(self.control_sock):
            try:
                return dict(self._call("incidents.get", {"id": str(id)}, require_token=False))
            except Exception:
                pass
        conn = connect(self.db_path)
        try:
            inc = get_incident(conn, str(id))
            if inc is None:
                raise KeyError("not found")
            inc["actions"] = list_actions_for_incident(conn, str(id), limit=50)
            return inc
        finally:
            conn.close()

    def report_incident(
        self,
        *,
        title: str,
        incident_type: str = "manual",
        severity: int = 3,
        diagnosis: str = "reported via MCP",
        details_json: str = "{}",
    ) -> dict[str, Any]:
        try:
            details = json.loads(details_json) if details_json.strip() else {}
            if not isinstance(details, dict):
                raise TypeError("details_json must be a JSON object string")
        except Exception as e:
            raise ValueError(f"invalid details_json: {e}") from e

        if _socket_exists(self.control_sock):
            return dict(
                self._call(
                    "incidents.create",
                    {
                        "type": str(incident_type),
                        "title": str(title),
                        "severity": int(severity),
                        "diagnosis": str(diagnosis),
                        "details": details,
                    },
                    require_token=True,
                )
            )

        conn = connect(self.db_path)
        try:
            iid = create_manual_incident(
                conn,
                incident_type=str(incident_type),
                title=str(title),
                severity=int(severity),
                diagnosis=str(diagnosis),
                details=details,
            )
            return {"id": iid}
        finally:
            conn.close()

    def mark_fixed(self, *, id: str, summary: str = "marked fixed") -> dict[str, Any]:
        if _socket_exists(self.control_sock):
            return dict(
                self._call(
                    "incidents.mark_fixed",
                    {"id": str(id), "summary": str(summary)},
                    require_token=True,
                )
            )

        conn = connect(self.db_path)
        try:
            if get_incident(conn, str(id)) is None:
                raise KeyError("not found")
            mark_incident_fixed(conn, str(id), str(summary))
            return {"id": str(id), "status": "fixed"}
        finally:
            conn.close()

    def recommendations_list(self, *, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        if _socket_exists(self.control_sock):
            try:
                res = self._call(
                    "recommendations.list",
                    {"limit": int(limit), "status": status},
                    require_token=False,
                )
                return list(res)
            except Exception:
                pass
        conn = connect(self.db_path)
        try:
            return list_recommendations(conn, status=status, limit=int(limit))
        finally:
            conn.close()

    def recommendation_get(self, *, id: str) -> dict[str, Any]:
        rid = str(id)
        if _socket_exists(self.control_sock):
            try:
                return dict(self._call("recommendations.get", {"id": rid}, require_token=False))
            except Exception:
                pass
        conn = connect(self.db_path)
        try:
            r = get_recommendation(conn, rid)
            if r is None:
                raise KeyError("not found")
            return r
        finally:
            conn.close()

    def recommendation_set_status(self, *, id: str, status: str, note: str = "") -> dict[str, Any]:
        rid = str(id)
        status = str(status)
        if _socket_exists(self.control_sock):
            return dict(
                self._call(
                    "recommendations.set_status",
                    {"id": rid, "status": status, "note": str(note or "")},
                    require_token=True,
                )
            )

        conn = connect(self.db_path)
        try:
            if get_recommendation(conn, rid) is None:
                raise KeyError("not found")
            set_recommendation_status(conn, rid, status=status, note=str(note or ""))
            return {"id": rid, "status": status}
        finally:
            conn.close()

    def run_once(self) -> dict[str, Any]:
        if _socket_exists(self.control_sock):
            return dict(self._call("agent.run_once", {}, require_token=True))

        loaded = load_config(self.config_path)
        cfg = json.loads(json.dumps(loaded.data))
        cfg.setdefault("control", {})["enabled"] = False

        ag = AutohealAgent(
            cfg=cfg,
            state_dir=self.state_dir,
            db_path=self.db_path,
            control_socket_path=self.control_sock,
        )
        try:
            ag.start()
        except AgentAlreadyRunning:
            return {
                "ok": False,
                "message": "agent already running (lock held) but control socket not available",
            }

        started = time.time()
        try:
            ag.run_once()
        finally:
            ag.stop()
        return {"ok": True, "ran": True, "duration_seconds": round(time.time() - started, 3)}

    def tail_log(self, *, lines: int = 200) -> dict[str, Any]:
        return {
            "path": str(self.log_path),
            "lines": _tail_text_file(self.log_path, max_lines=int(lines)),
        }

