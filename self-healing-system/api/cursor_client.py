"""Cursor communication client.

This module provides a Python client for Cursor to interact with the
self-healing daemon. It can be imported directly by Cursor or used
as a standalone script.

Usage from Cursor:
    from api.cursor_client import SelfHealingClient
    client = SelfHealingClient()
    
    # Check system health
    health = client.health()
    
    # Get full status
    status = client.status()
    
    # Get active events
    events = client.active_events()
    
    # Send a directive
    client.directive("monitor_service", {"service": "nginx"})
    
    # Run a command
    result = client.run_command("systemctl status nginx")
    
    # Send an instruction
    client.send_instruction("Focus on monitoring disk usage")
    
    # Trigger a scan
    client.trigger_scan()
"""
from __future__ import annotations

import json
from typing import Any, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError


class SelfHealingClient:
    """Client for communicating with the self-healing daemon API."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7847, token: str = ""):
        self.base_url = f"http://{host}:{port}"
        self.token = token

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data else None
        req = Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            resp = urlopen(req, timeout=10)
            return json.loads(resp.read())
        except URLError as e:
            return {"error": f"Connection failed: {e}", "daemon_reachable": False}

    def _get(self, path: str, **params) -> dict:
        query = "&".join(f"{k}={v}" for k, v in params.items()) if params else ""
        full_path = f"{path}?{query}" if query else path
        return self._request("GET", full_path)

    def _post(self, path: str, data: dict) -> dict:
        return self._request("POST", path, data)

    # --- Read operations ---

    def health(self) -> dict:
        """Check daemon health."""
        return self._get("/api/health")

    def status(self) -> dict:
        """Get full system status including stats and active events."""
        return self._get("/api/status")

    def statistics(self) -> dict:
        """Get event and fix statistics."""
        return self._get("/api/statistics")

    def active_events(self) -> dict:
        """Get currently active events."""
        return self._get("/api/events/active")

    def recent_events(self, hours: float = 24, limit: int = 100) -> dict:
        """Get recent events."""
        return self._get("/api/events", hours=hours, limit=limit)

    def event_detail(self, event_id: str) -> dict:
        """Get full details for an event including diagnoses and fixes."""
        return self._get(f"/api/events/{event_id}")

    def get_context(self, key: str = "") -> dict:
        """Get persistent context values."""
        if key:
            return self._get("/api/context", key=key)
        return self._get("/api/context")

    def get_snapshots(self, hours: float = 1) -> dict:
        """Get system snapshots."""
        return self._get("/api/snapshots", hours=hours)

    def get_messages(self, direction: str = "outbound") -> dict:
        """Get pending messages from the daemon."""
        return self._get("/api/messages", direction=direction)

    def get_config(self) -> dict:
        """Get current configuration."""
        return self._get("/api/config")

    # --- Write operations ---

    def trigger_scan(self) -> dict:
        """Trigger an immediate system scan."""
        return self._post("/api/scan", {})

    def trigger_fix(self, event_id: str) -> dict:
        """Trigger a fix attempt for a specific event."""
        return self._post("/api/fix", {"event_id": event_id})

    def run_command(self, command: str) -> dict:
        """Run a shell command on the system."""
        return self._post("/api/command", {"command": command})

    def send_instruction(self, text: str) -> dict:
        """Send a text instruction to the daemon."""
        return self._post("/api/message", {
            "type": "instruction",
            "payload": {"text": text},
        })

    def send_message(self, message_type: str, payload: dict) -> dict:
        """Send a typed message to the daemon."""
        return self._post("/api/message", {
            "type": message_type,
            "payload": payload,
        })

    def set_context(self, key: str, value: Any) -> dict:
        """Set a persistent context value."""
        return self._post("/api/context", {"key": key, "value": value})

    def update_config(self, **kwargs) -> dict:
        """Update configuration values."""
        return self._post("/api/config", kwargs)

    # --- Directives (high-level commands) ---

    def directive(self, directive_type: str, payload: dict = None) -> dict:
        """Send a high-level directive."""
        return self._post("/api/directive", {
            "directive": directive_type,
            "payload": payload or {},
        })

    def monitor_service(self, service: str) -> dict:
        """Add a service to monitoring."""
        return self.directive("monitor_service", {"service": service})

    def ignore_category(self, category: str) -> dict:
        """Ignore an event category."""
        return self.directive("ignore_category", {"category": category})

    def unignore_category(self, category: str) -> dict:
        """Stop ignoring an event category."""
        return self.directive("unignore_category", {"category": category})

    def enable_auto_fix(self) -> dict:
        """Enable automatic fix execution."""
        return self.directive("enable_auto_fix")

    def disable_auto_fix(self) -> dict:
        """Disable automatic fix execution."""
        return self.directive("disable_auto_fix")

    def authorize_reboot(self) -> dict:
        """Authorize automatic reboots when needed."""
        return self.directive("authorize_reboot")

    def schedule_reboot(self, delay_minutes: int = 5) -> dict:
        """Schedule a system reboot."""
        return self.directive("schedule_reboot", {"delay_minutes": delay_minutes})

    def cancel_reboot(self) -> dict:
        """Cancel a scheduled reboot."""
        return self.directive("cancel_reboot")

    def add_error_pattern(self, pattern: str, severity: str = "error", category: str = "custom") -> dict:
        """Add a new error pattern to monitor."""
        return self.directive("add_error_pattern", {
            "pattern": pattern,
            "severity": severity,
            "category": category,
        })

    def set_threshold(self, key: str, value: float) -> dict:
        """Update a monitoring threshold."""
        return self.directive("set_threshold", {"key": key, "value": value})


def interactive():
    """Interactive CLI for communicating with the daemon."""
    client = SelfHealingClient()

    print("Self-Healing System - Interactive Client")
    print("Type 'help' for commands, 'quit' to exit")
    print()

    commands = {
        "health": lambda: client.health(),
        "status": lambda: client.status(),
        "stats": lambda: client.statistics(),
        "events": lambda: client.active_events(),
        "recent": lambda: client.recent_events(),
        "scan": lambda: client.trigger_scan(),
        "context": lambda: client.get_context(),
        "config": lambda: client.get_config(),
        "messages": lambda: client.get_messages(),
        "snapshots": lambda: client.get_snapshots(),
    }

    while True:
        try:
            inp = input("self-healing> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not inp:
            continue
        if inp in ("quit", "exit", "q"):
            break
        if inp == "help":
            print("Commands: " + ", ".join(sorted(commands.keys())))
            print("  cmd <shell command>  - Run a shell command")
            print("  fix <event_id>       - Trigger fix for event")
            print("  say <text>           - Send instruction")
            continue

        parts = inp.split(None, 1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in commands:
            result = commands[cmd]()
        elif cmd == "cmd" and arg:
            result = client.run_command(arg)
        elif cmd == "fix" and arg:
            result = client.trigger_fix(arg)
        elif cmd == "say" and arg:
            result = client.send_instruction(arg)
        else:
            print(f"Unknown command: {cmd}")
            continue

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    interactive()
