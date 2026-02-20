#!/usr/bin/env python3
"""
Dynamic context + flowmap generator for NUSA.

This script is intentionally lightweight and dependency-free so it can run:
- before inspections
- before code changes
- before deploys
- during pre-commit hooks
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_DIR = REPO_ROOT / "context"
FLOWMAP_JSON = CONTEXT_DIR / "flowmap.json"
FLOWMAP_MD = CONTEXT_DIR / "flowmap.md"
ACTIVITY_LOG = CONTEXT_DIR / "activity_log.jsonl"
STATE_JSON = CONTEXT_DIR / "state.json"
WATCHLIST_JSON = CONTEXT_DIR / "watchlist.json"

KNOWN_HTML = [
    "index.html",
    "app.html",
    "legal.html",
    "login.html",
    "dashboard.html",
    "profile.html",
    "edit-profile.html",
]
KNOWN_JS = [
    "main.js",
    "app.js",
    "dataClient.js",
    "store.js",
]
KNOWN_SERVER = [
    "server/server.js",
    "server/db.js",
    "server/import-legacy.js",
]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def git_output(args: List[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def git_changed_files() -> List[str]:
    try:
        result = subprocess.run(
            ["git", "-c", "color.status=false", "status", "--porcelain"],
            cwd=REPO_ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
    except Exception:
        return []

    changed_files: List[str] = []
    for raw in (result.stdout or "").splitlines():
        line = raw.rstrip()
        if len(line) < 4:
            continue
        path_part = line[3:].strip()
        if not path_part:
            continue
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1].strip()
        changed_files.append(path_part)
    return changed_files


def parse_html_dependencies(text: str) -> Tuple[List[str], List[str], List[str]]:
    styles = re.findall(r'<link[^>]+href="([^"]+)"', text)
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', text)
    anchors = re.findall(r'<a[^>]+href="([^"]+)"', text)
    return styles, scripts, anchors


def parse_client_api_refs(text: str) -> List[str]:
    refs = set(re.findall(r'["\'](/api/[^"\']+)', text))
    refs.update(re.findall(r'`(/api/[^`]+)`', text))
    return sorted(refs)


def parse_server_routes(text: str) -> List[Dict[str, str]]:
    pattern = re.compile(r'app\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']')
    routes = []
    for method, route in pattern.findall(text):
        routes.append({"method": method.upper(), "route": route})
    return routes


def parse_deploy_files(script_text: str, array_name: str) -> List[str]:
    pattern = re.compile(rf"{array_name}=\((.*?)\)", re.DOTALL)
    match = pattern.search(script_text)
    if not match:
        return []
    block = match.group(1)
    lines = [line.strip() for line in block.splitlines()]
    values = []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        values.append(line.strip('"').strip("'"))
    return values


def build_flowmap(phase: str, note: str) -> Dict:
    html_nodes = []
    for rel in KNOWN_HTML:
        path = REPO_ROOT / rel
        text = read_text(path)
        styles, scripts, anchors = parse_html_dependencies(text)
        html_nodes.append(
            {
                "file": rel,
                "exists": path.exists(),
                "stylesheets": styles,
                "scripts": scripts,
                "links": anchors,
            }
        )

    js_nodes = []
    client_api = set()
    for rel in KNOWN_JS:
        path = REPO_ROOT / rel
        text = read_text(path)
        refs = parse_client_api_refs(text)
        client_api.update(refs)
        js_nodes.append({"file": rel, "exists": path.exists(), "api_refs": refs})

    server_text = read_text(REPO_ROOT / "server/server.js")
    server_routes = parse_server_routes(server_text)

    deploy_text = read_text(REPO_ROOT / "scripts/deploy_cpanel_no_ssh.sh")
    deploy_required = parse_deploy_files(deploy_text, "FILES")
    deploy_optional = parse_deploy_files(deploy_text, "OPTIONAL_FILES")

    branch = git_output(["rev-parse", "--abbrev-ref", "HEAD"])
    commit = git_output(["rev-parse", "--short", "HEAD"])
    changed_files = git_changed_files()

    flow_paths = [
        {
            "id": "flow_join",
            "name": "Participant join flow",
            "steps": [
                "index.html -> main.js -> dataClient.createAccount",
                "/api/auth/register (primary) or /api/auth/signup (legacy)",
                "participant counter refresh via /api/stats/participants",
            ],
        },
        {
            "id": "flow_updates",
            "name": "Announcement visibility flow",
            "steps": [
                "app.html announcement form -> app.js -> dataClient.addAnnouncement",
                "/api/announcements persists updates",
                "index.html preview reads /api/announcements",
            ],
        },
        {
            "id": "flow_deploy",
            "name": "No-SSH deployment flow",
            "steps": [
                "scripts/deploy_cpanel_no_ssh.sh authenticates with cPanel API",
                "uploads required frontend files to public_html",
                "verifies homepage, member app, participant count, announcements",
            ],
        },
    ]

    return {
        "generated_at": now_iso(),
        "trigger": {"phase": phase, "note": note},
        "git": {"branch": branch, "commit": commit, "changed_files": changed_files},
        "frontend": {
            "html_nodes": html_nodes,
            "js_nodes": js_nodes,
        },
        "api": {
            "server_routes": server_routes,
            "client_api_refs": sorted(client_api),
            "route_count": len(server_routes),
        },
        "deploy": {
            "script": "scripts/deploy_cpanel_no_ssh.sh",
            "required_files": deploy_required,
            "optional_files": deploy_optional,
        },
        "critical_flow_paths": flow_paths,
        "workflow_rule": (
            "Run context guard before inspect/change: "
            "./scripts/context_guard.sh inspect|change \"note\""
        ),
    }


def append_activity(phase: str, note: str, flowmap: Dict) -> None:
    entry = {
        "ts": flowmap["generated_at"],
        "phase": phase,
        "note": note,
        "git": flowmap.get("git", {}),
    }
    lines = []
    if ACTIVITY_LOG.exists():
        lines = [line for line in ACTIVITY_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines.append(json.dumps(entry, separators=(",", ":")))
    lines = lines[-400:]
    ACTIVITY_LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_activity_entries() -> List[Dict]:
    if not ACTIVITY_LOG.exists():
        return []
    entries: List[Dict] = []
    for line in ACTIVITY_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return entries


def compute_hotspots(entries: List[Dict], limit: int = 8) -> List[Dict]:
    counts: Dict[str, int] = {}
    for item in entries:
        git_meta = item.get("git", {}) if isinstance(item, dict) else {}
        changed = git_meta.get("changed_files", []) if isinstance(git_meta, dict) else []
        if not isinstance(changed, list):
            continue
        for rel in changed:
            if not isinstance(rel, str) or not rel:
                continue
            counts[rel] = counts.get(rel, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]
    return [{"file": file_name, "touches": touches} for file_name, touches in ranked]


def write_watchlist(hotspots: List[Dict]) -> None:
    payload = {
        "generated_at": now_iso(),
        "description": "Auto-ranked files touched most often in context checkpoints.",
        "hotspots": hotspots,
    }
    write_json(WATCHLIST_JSON, payload)


def update_state(phase: str, note: str) -> Dict:
    state = read_json(
        STATE_JSON,
        {
            "runs": 0,
            "phase_counts": {},
            "last_run": None,
            "last_note": "",
        },
    )
    state["runs"] = int(state.get("runs", 0)) + 1
    phase_counts = state.get("phase_counts", {})
    phase_counts[phase] = int(phase_counts.get(phase, 0)) + 1
    state["phase_counts"] = phase_counts
    state["last_run"] = now_iso()
    state["last_note"] = note
    write_json(STATE_JSON, state)
    return state


def render_markdown(flowmap: Dict, state: Dict) -> str:
    routes = flowmap["api"]["server_routes"]
    route_lines = "\n".join([f"- `{r['method']} {r['route']}`" for r in routes[:40]])
    if len(routes) > 40:
        route_lines += f"\n- ... {len(routes) - 40} more routes"

    html_lines = []
    for node in flowmap["frontend"]["html_nodes"]:
        html_lines.append(
            f"- `{node['file']}` -> styles: {len(node['stylesheets'])}, scripts: {len(node['scripts'])}, links: {len(node['links'])}"
        )

    flow_lines = []
    for flow in flowmap["critical_flow_paths"]:
        flow_lines.append(f"### {flow['name']}")
        for step in flow["steps"]:
            flow_lines.append(f"- {step}")
        flow_lines.append("")

    recent = []
    if ACTIVITY_LOG.exists():
        rows = [line for line in ACTIVITY_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in rows[-8:]:
            try:
                item = json.loads(line)
                recent.append(
                    f"- `{item.get('ts')}` [{item.get('phase')}] {item.get('note')}"
                )
            except Exception:
                continue

    if not recent:
        recent = ["- No activity logged yet."]

    hotspot_lines = []
    for item in flowmap.get("optimization", {}).get("hotspots", []):
        hotspot_lines.append(f"- `{item['file']}` touched `{item['touches']}` checkpoint(s)")
    if not hotspot_lines:
        hotspot_lines = ["- No hotspots yet (insufficient activity)."]

    return f"""# NUSA Context + Flowmap

Generated: `{flowmap['generated_at']}`
Trigger: `{flowmap['trigger']['phase']}` - {flowmap['trigger']['note']}

## Persistent Workflow Rules

1. Before inspecting files: `./scripts/context_guard.sh inspect "what you are checking"`
2. Before changing files: `./scripts/context_guard.sh change "what you are changing"`
3. Pre-commit hook auto-refreshes this flowmap (install with `npm run context:install-hooks`)
4. Deploy script auto-refreshes context at deploy start and finish

State runs: `{state['runs']}`  
Phase counts: `{json.dumps(state['phase_counts'])}`

## Frontend Map

{chr(10).join(html_lines)}

## API Route Map (top 40)

{route_lines}

## Critical Flow Paths

{chr(10).join(flow_lines)}

## Deploy Map

- Script: `{flowmap['deploy']['script']}`
- Required upload files: `{len(flowmap['deploy']['required_files'])}`
- Optional upload files: `{len(flowmap['deploy']['optional_files'])}`

## Optimization Watchlist (Auto)

{chr(10).join(hotspot_lines)}

## Recent Context Activity

{chr(10).join(recent)}
"""


def print_summary(flowmap: Dict, state: Dict) -> None:
    print("Context flowmap updated.")
    print(f"- Trigger: {flowmap['trigger']['phase']} / {flowmap['trigger']['note']}")
    print(f"- Branch: {flowmap['git']['branch']} @ {flowmap['git']['commit']}")
    print(f"- API routes: {flowmap['api']['route_count']}")
    print(f"- Context runs: {state['runs']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="update")
    parser.add_argument("--note", default="manual update")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    flowmap = build_flowmap(args.phase, args.note)
    write_json(FLOWMAP_JSON, flowmap)
    append_activity(args.phase, args.note, flowmap)
    state = update_state(args.phase, args.note)
    entries = load_activity_entries()
    hotspots = compute_hotspots(entries)
    flowmap["optimization"] = {
        "activity_entries": len(entries),
        "hotspots": hotspots,
    }
    write_json(FLOWMAP_JSON, flowmap)
    write_watchlist(hotspots)
    FLOWMAP_MD.write_text(render_markdown(flowmap, state), encoding="utf-8")

    if args.print_summary or not args.quiet:
        print_summary(flowmap, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
