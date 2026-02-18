from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .mcp_ops import AutohealOps, tool_specs


DEFAULT_PROTOCOL_VERSION = "2025-11-25"


def _write(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg, separators=(",", ":"), ensure_ascii=True) + "\n")
    sys.stdout.flush()


def _result(id_: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": int(code), "message": str(message)}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": err}


def _tool_text_result(payload: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True),
            }
        ],
        "isError": False,
    }


def _tool_error_result(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": str(message)}],
        "isError": True,
    }


def manifest_json() -> dict[str, Any]:
    return {"server": "autoheal", "tools": tool_specs()}


def run_stdio_server(
    *,
    state_dir: Path,
    config_path: str | Path | None,
    token: str | None,
) -> None:
    """
    Minimal MCP stdio server (no external dependencies).

    Implements:
    - initialize / initialized
    - tools/list
    - tools/call
    - resources/list (empty)
    - prompts/list (empty)
    """
    ops = AutohealOps(state_dir=state_dir, config_path=config_path, token=token)
    tools = tool_specs()
    tool_names = {t["name"] for t in tools}

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue

        try:
            msg = json.loads(raw)
        except Exception:
            _write(_error(None, -32700, "parse error"))
            continue

        if not isinstance(msg, dict):
            _write(_error(None, -32600, "invalid request"))
            continue

        method = msg.get("method")
        id_ = msg.get("id")
        params = msg.get("params") or {}
        if params is None:
            params = {}

        # Notifications have no id; do not respond.
        is_notification = "id" not in msg

        try:
            if method == "initialize":
                pv = DEFAULT_PROTOCOL_VERSION
                if isinstance(params, dict) and isinstance(params.get("protocolVersion"), str):
                    pv = params["protocolVersion"]
                result = {
                    "protocolVersion": pv,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "autoheal", "version": "0.1.0"},
                }
                if not is_notification:
                    _write(_result(id_, result))
                continue

            if method == "initialized":
                continue

            if method == "tools/list":
                if not is_notification:
                    _write(_result(id_, {"tools": tools}))
                continue

            if method == "tools/call":
                if not isinstance(params, dict):
                    if not is_notification:
                        _write(_result(id_, _tool_error_result("invalid params")))
                    continue
                name = params.get("name")
                arguments = params.get("arguments") or {}
                if not isinstance(arguments, dict):
                    arguments = {}
                if not isinstance(name, str) or name not in tool_names:
                    if not is_notification:
                        _write(_result(id_, _tool_error_result("unknown tool")))
                    continue

                try:
                    payload = _dispatch_tool(ops, name, arguments)
                    if not is_notification:
                        _write(_result(id_, _tool_text_result(payload)))
                except Exception as e:
                    if not is_notification:
                        _write(_result(id_, _tool_error_result(str(e))))
                continue

            if method == "resources/list":
                if not is_notification:
                    _write(_result(id_, {"resources": []}))
                continue

            if method == "prompts/list":
                if not is_notification:
                    _write(_result(id_, {"prompts": []}))
                continue

            if not is_notification:
                _write(_error(id_, -32601, "method not found"))

        except Exception as e:
            if not is_notification:
                _write(_error(id_, -32000, "server error", data=str(e)))


def _dispatch_tool(ops: AutohealOps, name: str, args: dict[str, Any]) -> Any:
    if name == "autoheal_status":
        return ops.status()
    if name == "autoheal_incidents_list":
        return ops.incidents_list(limit=int(args.get("limit", 50)))
    if name == "autoheal_incident_get":
        return ops.incident_get(str(args.get("id", "")))
    if name == "autoheal_report_incident":
        return ops.report_incident(
            title=str(args.get("title", "")),
            incident_type=str(args.get("incident_type", "manual")),
            severity=int(args.get("severity", 3)),
            diagnosis=str(args.get("diagnosis", "reported via MCP")),
            details_json=str(args.get("details_json", "{}")),
        )
    if name == "autoheal_mark_fixed":
        return ops.mark_fixed(
            id=str(args.get("id", "")),
            summary=str(args.get("summary", "marked fixed")),
        )
    if name == "autoheal_recommendations_list":
        return ops.recommendations_list(
            limit=int(args.get("limit", 50)),
            status=(str(args.get("status")) if args.get("status") else None),
        )
    if name == "autoheal_recommendation_get":
        return ops.recommendation_get(id=str(args.get("id", "")))
    if name == "autoheal_recommendation_accept":
        return ops.recommendation_set_status(
            id=str(args.get("id", "")),
            status="accepted",
            note=str(args.get("note", "")),
        )
    if name == "autoheal_recommendation_dismiss":
        return ops.recommendation_set_status(
            id=str(args.get("id", "")),
            status="dismissed",
            note=str(args.get("note", "")),
        )
    if name == "autoheal_run_once":
        return ops.run_once()
    if name == "autoheal_tail_log":
        return ops.tail_log(lines=int(args.get("lines", 200)))
    raise RuntimeError("unknown tool")

