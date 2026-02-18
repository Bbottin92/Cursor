from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from ._paths import default_control_socket_path, default_db_path, default_log_path
from .agent import AutohealAgent
from .config import default_config, ensure_state_dirs, load_config, resolve_state_dir
from .control import call_control
from .db import (
    connect,
    create_manual_incident,
    get_incident,
    list_actions_for_incident,
    list_incidents,
)
from .logging_setup import setup_logging


def _pjson(obj: object) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="Path to config.json (optional)")
    common.add_argument("--state-dir", help="State directory (db/log/socket)")
    common.add_argument("--verbose", action="store_true")

    parser = argparse.ArgumentParser(prog="autoheal", parents=[common])
    parser.add_argument("--version", action="version", version=f"autoheal {__version__}")

    sub = parser.add_subparsers(dest="cmd", required=True)

    agent_p = sub.add_parser("agent", parents=[common], help="Run the autoheal agent")
    agent_sub = agent_p.add_subparsers(dest="agent_cmd", required=True)
    agent_run = agent_sub.add_parser(
        "run", parents=[common], help="Run forever (daemon mode)"
    )
    agent_run.add_argument(
        "--no-control", action="store_true", help="Disable control socket"
    )
    agent_sub.add_parser(
        "once", parents=[common], help="Run a single cycle and exit"
    )

    sub.add_parser(
        "status",
        parents=[common],
        help="Show agent status (via control socket if running)",
    )

    inc_p = sub.add_parser(
        "incidents",
        parents=[common],
        help="Inspect incident history (persistent context)",
    )
    inc_sub = inc_p.add_subparsers(dest="inc_cmd", required=True)
    inc_list = inc_sub.add_parser("list", parents=[common], help="List incidents")
    inc_list.add_argument("--limit", type=int, default=50)
    inc_show = inc_sub.add_parser("show", parents=[common], help="Show incident")
    inc_show.add_argument("id")

    rep_p = sub.add_parser("report", parents=[common], help="Create a manual incident")
    rep_p.add_argument("--type", default="manual")
    rep_p.add_argument("--title", required=True)
    rep_p.add_argument("--severity", type=int, default=3)
    rep_p.add_argument("--diagnosis", default="reported manually")
    rep_p.add_argument(
        "--details-json", default="{}", help='JSON object string, e.g. \'{"k":"v"}\''
    )

    cfg_p = sub.add_parser("config", parents=[common], help="Config utilities")
    cfg_sub = cfg_p.add_subparsers(dest="cfg_cmd", required=True)
    cfg_init = cfg_sub.add_parser(
        "init", parents=[common], help="Write a default config.json"
    )
    cfg_init.add_argument(
        "--path", help="Where to write (defaults to --config or auto default)"
    )
    cfg_init.add_argument("--force", action="store_true")

    ctl_p = sub.add_parser(
        "control",
        parents=[common],
        help="Call the running agent via control socket",
    )
    ctl_p.add_argument("method")
    ctl_p.add_argument("--params-json", default="{}", help="JSON object string for params")
    ctl_p.add_argument("--token", default=os.environ.get("AUTOHEAL_TOKEN"))

    mcp_p = sub.add_parser(
        "mcp",
        parents=[common],
        help="Run an MCP server for Cursor integration",
    )
    mcp_sub = mcp_p.add_subparsers(dest="mcp_cmd", required=True)
    mcp_serve = mcp_sub.add_parser(
        "serve",
        parents=[common],
        help="Serve MCP over stdio (recommended for Cursor)",
    )
    mcp_serve.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport",
    )
    mcp_serve.add_argument(
        "--token",
        default=os.environ.get("AUTOHEAL_TOKEN"),
        help="Token for privileged control calls (defaults to AUTOHEAL_TOKEN)",
    )
    mcp_manifest = mcp_sub.add_parser(
        "manifest",
        parents=[common],
        help="Print MCP tool manifest as JSON",
    )
    mcp_manifest.add_argument(
        "--token",
        default=os.environ.get("AUTOHEAL_TOKEN"),
        help="Token for privileged control calls (defaults to AUTOHEAL_TOKEN)",
    )

    args = parser.parse_args(argv)

    state_dir = resolve_state_dir(args.state_dir)
    ensure_state_dirs(state_dir)

    log_path = default_log_path(state_dir)
    setup_logging(log_path, verbose=bool(args.verbose))

    loaded = load_config(args.config)
    cfg = loaded.data

    control_sock = default_control_socket_path(state_dir)
    db_path = default_db_path(state_dir)

    if args.cmd == "mcp" and args.mcp_cmd == "serve":
        try:
            from .mcp_server import run_mcp_server
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 2

        run_mcp_server(
            state_dir=state_dir,
            config_path=args.config,
            token=getattr(args, "token", None),
            transport=str(getattr(args, "transport", "stdio")),
        )
        return 0

    if args.cmd == "mcp" and args.mcp_cmd == "manifest":
        try:
            from .mcp_server import mcp_manifest_json
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 2

        _pjson(
            mcp_manifest_json(
                state_dir=state_dir,
                config_path=args.config,
                token=getattr(args, "token", None),
            )
        )
        return 0

    if args.cmd == "agent" and args.agent_cmd == "run":
        # Convenience: allow disabling control socket from CLI.
        if getattr(args, "no_control", False):
            cfg = json.loads(json.dumps(cfg))  # shallow-ish copy via JSON
            cfg.setdefault("control", {})["enabled"] = False

        AutohealAgent(
            cfg=cfg,
            state_dir=state_dir,
            db_path=db_path,
            control_socket_path=control_sock,
        ).run_forever()
        return 0

    if args.cmd == "agent" and args.agent_cmd == "once":
        ag = AutohealAgent(
            cfg=cfg,
            state_dir=state_dir,
            db_path=db_path,
            control_socket_path=control_sock,
        )
        ag.start()
        try:
            ag.run_once()
        finally:
            ag.stop()
        return 0

    if args.cmd == "status":
        if control_sock.exists():
            resp = call_control(control_sock, method="status", params={}, token=None)
            if resp.ok:
                _pjson(resp.result)
                return 0
        # Fallback: read last incidents directly.
        conn = connect(db_path)
        try:
            _pjson({"db_path": str(db_path), "incidents": list_incidents(conn, limit=5)})
        finally:
            conn.close()
        return 0

    if args.cmd == "incidents" and args.inc_cmd == "list":
        if control_sock.exists():
            resp = call_control(
                control_sock,
                method="incidents.list",
                params={"limit": int(args.limit)},
                token=None,
            )
            if resp.ok:
                _pjson(resp.result)
                return 0
        conn = connect(db_path)
        try:
            _pjson(list_incidents(conn, limit=int(args.limit)))
        finally:
            conn.close()
        return 0

    if args.cmd == "incidents" and args.inc_cmd == "show":
        iid = str(args.id)
        if control_sock.exists():
            resp = call_control(
                control_sock, method="incidents.get", params={"id": iid}, token=None
            )
            if resp.ok:
                _pjson(resp.result)
                return 0
        conn = connect(db_path)
        try:
            inc = get_incident(conn, iid)
            if inc is None:
                print("not found", file=sys.stderr)
                return 2
            inc["actions"] = list_actions_for_incident(conn, iid)
            _pjson(inc)
        finally:
            conn.close()
        return 0

    if args.cmd == "report":
        try:
            details = json.loads(args.details_json)
            if not isinstance(details, dict):
                raise TypeError("details-json must be a JSON object")
        except Exception as e:
            print(f"invalid --details-json: {e}", file=sys.stderr)
            return 2

        # Prefer to report via control socket (wakes agent immediately).
        if control_sock.exists():
            resp = call_control(
                control_sock,
                method="incidents.create",
                params={
                    "type": args.type,
                    "title": args.title,
                    "severity": int(args.severity),
                    "diagnosis": args.diagnosis,
                    "details": details,
                },
                token=os.environ.get("AUTOHEAL_TOKEN"),
            )
            if resp.ok:
                _pjson(resp.result)
                return 0

        conn = connect(db_path)
        try:
            iid = create_manual_incident(
                conn,
                incident_type=args.type,
                title=args.title,
                severity=int(args.severity),
                diagnosis=args.diagnosis,
                details=details,
            )
            _pjson({"id": iid})
        finally:
            conn.close()
        return 0

    if args.cmd == "config" and args.cfg_cmd == "init":
        out_path = (
            Path(args.path or args.config or "").expanduser()
            if (args.path or args.config)
            else None
        )
        if out_path is None or str(out_path) == "":
            # default: match load_config() location
            from ._paths import default_config_path

            out_path = default_config_path()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and not args.force:
            print(f"refusing to overwrite existing config: {out_path}", file=sys.stderr)
            return 2
        out_path.write_text(
            json.dumps(default_config(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(str(out_path))
        return 0

    if args.cmd == "control":
        try:
            params = json.loads(args.params_json)
            if not isinstance(params, dict):
                raise TypeError("params-json must be a JSON object")
        except Exception as e:
            print(f"invalid --params-json: {e}", file=sys.stderr)
            return 2

        if not control_sock.exists():
            print(f"control socket not found: {control_sock}", file=sys.stderr)
            return 2

        resp = call_control(
            control_sock,
            method=str(args.method),
            params=params,
            token=args.token,
        )
        if not resp.ok:
            print(resp.error or "error", file=sys.stderr)
            return 2
        _pjson(resp.result)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
