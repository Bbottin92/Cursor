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
    list_actions_for_incident,
    list_incidents,
    mark_incident_fixed,
)


class McpNotInstalled(RuntimeError):
    pass


def _require_mcp() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as e:  # pragma: no cover
        raise McpNotInstalled(
            "MCP support not installed. Install the extra dependencies for Cursor integration "
            "(see README), e.g. in a venv: pip install -e '.[mcp]'"
        ) from e
    return FastMCP


def _tail_text_file(path: Path, *, max_lines: int = 200, max_bytes: int = 200_000) -> list[str]:
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

    # Split and decode defensively.
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-int(max_lines) :]


def _socket_exists(sock: Path) -> bool:
    try:
        return sock.exists()
    except Exception:
        return False


def create_autoheal_mcp_server(
    *,
    state_dir: Path,
    config_path: str | Path | None,
    token: str | None,
) -> Any:
    """
    Create an MCP server exposing autoheal operations as tools.

    Designed for Cursor integration:
    - transport: stdio
    - auth: optional token (AUTOHEAL_TOKEN)
    - state: persistent SQLite + control socket
    """

    FastMCP = _require_mcp()

    control_sock = default_control_socket_path(state_dir)
    db_path = default_db_path(state_dir)
    log_path = default_log_path(state_dir)

    def _call(method: str, params: dict[str, Any], *, require_token: bool) -> Any:
        if not _socket_exists(control_sock):
            raise RuntimeError(f"agent control socket not found: {control_sock}")
        if require_token and not token:
            raise PermissionError(
                "token required for this operation (set AUTOHEAL_TOKEN or pass --token)"
            )
        resp = call_control(control_sock, method=method, params=params, token=token)
        if not resp.ok:
            raise RuntimeError(resp.error or "control call failed")
        return resp.result

    mcp = FastMCP("autoheal")

    @mcp.tool(
        name="autoheal_status",
        title="autoheal status",
        description="Get agent status (prefers control socket; falls back to DB).",
    )
    def autoheal_status() -> dict[str, Any]:
        if _socket_exists(control_sock):
            try:
                return dict(_call("status", {}, require_token=False))
            except Exception:
                # Fall back to DB.
                pass

        conn = connect(db_path)
        try:
            return {
                "agent_running": False,
                "state_dir": str(state_dir),
                "db_path": str(db_path),
                "control_socket_path": str(control_sock),
                "recent_incidents": list_incidents(conn, limit=5),
            }
        finally:
            conn.close()

    @mcp.tool(
        name="autoheal_incidents_list",
        title="list incidents",
        description="List known incidents from persistent state.",
    )
    def autoheal_incidents_list(limit: int = 50) -> list[dict[str, Any]]:
        if _socket_exists(control_sock):
            try:
                res = _call("incidents.list", {"limit": int(limit)}, require_token=False)
                return list(res)
            except Exception:
                pass
        conn = connect(db_path)
        try:
            return list_incidents(conn, limit=int(limit))
        finally:
            conn.close()

    @mcp.tool(
        name="autoheal_incident_get",
        title="get incident",
        description="Get a single incident (includes recent actions).",
    )
    def autoheal_incident_get(id: str) -> dict[str, Any]:
        if _socket_exists(control_sock):
            try:
                return dict(_call("incidents.get", {"id": str(id)}, require_token=False))
            except Exception:
                pass
        conn = connect(db_path)
        try:
            inc = get_incident(conn, str(id))
            if inc is None:
                raise KeyError("not found")
            inc["actions"] = list_actions_for_incident(conn, str(id), limit=50)
            return inc
        finally:
            conn.close()

    @mcp.tool(
        name="autoheal_report_incident",
        title="report incident",
        description="Create a manual incident (requires AUTOHEAL_TOKEN if configured).",
    )
    def autoheal_report_incident(
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

        if _socket_exists(control_sock):
            return dict(
                _call(
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

        conn = connect(db_path)
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

    @mcp.tool(
        name="autoheal_mark_fixed",
        title="mark incident fixed",
        description="Manually mark an incident fixed (requires AUTOHEAL_TOKEN if configured).",
    )
    def autoheal_mark_fixed(id: str, summary: str = "marked fixed") -> dict[str, Any]:
        if _socket_exists(control_sock):
            return dict(
                _call(
                    "incidents.mark_fixed",
                    {"id": str(id), "summary": str(summary)},
                    require_token=True,
                )
            )

        conn = connect(db_path)
        try:
            if get_incident(conn, str(id)) is None:
                raise KeyError("not found")
            mark_incident_fixed(conn, str(id), str(summary))
            return {"id": str(id), "status": "fixed"}
        finally:
            conn.close()

    @mcp.tool(
        name="autoheal_run_once",
        title="run one cycle",
        description="Trigger the running agent to run a cycle (or run locally if not running).",
    )
    def autoheal_run_once() -> dict[str, Any]:
        # Prefer nudging the long-running agent.
        if _socket_exists(control_sock):
            return dict(_call("agent.run_once", {}, require_token=True))

        # Fallback: run a one-shot cycle in-process (best effort).
        loaded = load_config(config_path)
        cfg = json.loads(json.dumps(loaded.data))
        cfg.setdefault("control", {})["enabled"] = False

        ag = AutohealAgent(cfg=cfg, state_dir=state_dir, db_path=db_path, control_socket_path=control_sock)
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

    @mcp.tool(
        name="autoheal_tail_log",
        title="tail agent log",
        description="Read the last N lines from the agent log file.",
    )
    def autoheal_tail_log(lines: int = 200) -> dict[str, Any]:
        return {
            "path": str(log_path),
            "lines": _tail_text_file(log_path, max_lines=int(lines)),
        }

    return mcp


def mcp_manifest_json(
    *,
    state_dir: Path,
    config_path: str | Path | None,
    token: str | None,
) -> dict[str, Any]:
    """
    Return a JSON-serializable manifest of tools for debugging / setup.
    """
    _require_mcp()
    import anyio  # type: ignore

    mcp = create_autoheal_mcp_server(state_dir=state_dir, config_path=config_path, token=token)

    async def _gather() -> dict[str, Any]:
        tools = await mcp.list_tools()
        # MCPTool is a Pydantic-ish model; serialize to plain dicts.
        tool_dicts = [json.loads(t.model_dump_json()) for t in tools]
        return {"server": "autoheal", "tools": tool_dicts}

    return anyio.run(_gather)


def run_mcp_server(
    *,
    state_dir: Path,
    config_path: str | Path | None,
    token: str | None,
    transport: str = "stdio",
) -> None:
    """
    Start the MCP server (blocking).
    """
    mcp = create_autoheal_mcp_server(state_dir=state_dir, config_path=config_path, token=token)
    mcp.run(transport=transport)
