from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .mcp_ops import AutohealOps


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

    mcp = FastMCP("autoheal")
    ops = AutohealOps(state_dir=state_dir, config_path=config_path, token=token)

    @mcp.tool(
        name="autoheal_status",
        title="autoheal status",
        description="Get agent status (prefers control socket; falls back to DB).",
    )
    def autoheal_status() -> dict[str, Any]:
        return ops.status()

    @mcp.tool(
        name="autoheal_incidents_list",
        title="list incidents",
        description="List known incidents from persistent state.",
    )
    def autoheal_incidents_list(limit: int = 50) -> list[dict[str, Any]]:
        return ops.incidents_list(limit=int(limit))

    @mcp.tool(
        name="autoheal_incident_get",
        title="get incident",
        description="Get a single incident (includes recent actions).",
    )
    def autoheal_incident_get(id: str) -> dict[str, Any]:
        return ops.incident_get(str(id))

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
        return ops.report_incident(
            title=str(title),
            incident_type=str(incident_type),
            severity=int(severity),
            diagnosis=str(diagnosis),
            details_json=str(details_json),
        )

    @mcp.tool(
        name="autoheal_mark_fixed",
        title="mark incident fixed",
        description="Manually mark an incident fixed (requires AUTOHEAL_TOKEN if configured).",
    )
    def autoheal_mark_fixed(id: str, summary: str = "marked fixed") -> dict[str, Any]:
        return ops.mark_fixed(id=str(id), summary=str(summary))

    @mcp.tool(
        name="autoheal_run_once",
        title="run one cycle",
        description="Trigger the running agent to run a cycle (or run locally if not running).",
    )
    def autoheal_run_once() -> dict[str, Any]:
        return ops.run_once()

    @mcp.tool(
        name="autoheal_tail_log",
        title="tail agent log",
        description="Read the last N lines from the agent log file.",
    )
    def autoheal_tail_log(lines: int = 200) -> dict[str, Any]:
        return ops.tail_log(lines=int(lines))

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
