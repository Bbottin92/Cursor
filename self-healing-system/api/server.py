"""HTTP API server for Cursor communication.

Provides REST endpoints for:
- Querying system status, events, diagnoses, fixes
- Sending commands and directives from Cursor
- Retrieving persistent context
- Triggering manual scans and fixes
- Receiving Cursor instructions to guide the daemon

Runs as a lightweight HTTP server on localhost.
"""
from __future__ import annotations

import json
import logging
import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING, Optional, Any
from urllib.parse import urlparse, parse_qs

if TYPE_CHECKING:
    from persistence.context_store import ContextStore
    from config.settings import Settings

logger = logging.getLogger("self-healing.api")


class APIServer:
    """Manages the HTTP API server."""

    def __init__(self, settings: "Settings", store: "ContextStore", daemon_ref=None):
        self.settings = settings
        self.store = store
        self.daemon_ref = daemon_ref
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        handler = _make_handler(self.settings, self.store, self.daemon_ref)
        self._server = HTTPServer(
            (self.settings.api_host, self.settings.api_port), handler
        )
        self._server.timeout = 1
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        logger.info(f"API server started on {self.settings.api_host}:{self.settings.api_port}")

    def _serve(self):
        while self._server:
            try:
                self._server.handle_request()
            except Exception as e:
                logger.error(f"API server error: {e}")
                time.sleep(1)

    def stop(self):
        if self._server:
            self._server.server_close()
            self._server = None
        logger.info("API server stopped")


def _make_handler(settings: "Settings", store: "ContextStore", daemon_ref):
    """Create a request handler class with access to store and settings."""

    class RequestHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.debug(fmt % args)

        def _send_json(self, data: Any, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data, default=str).encode())

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            body = self.rfile.read(length)
            return json.loads(body)

        def _check_auth(self) -> bool:
            if not settings.api_token:
                return True
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            return token == settings.api_token

        def do_GET(self):
            if not self._check_auth():
                self._send_json({"error": "unauthorized"}, 401)
                return

            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            params = parse_qs(parsed.query)

            routes = {
                "/api/health": self._get_health,
                "/api/status": self._get_status,
                "/api/events": self._get_events,
                "/api/events/active": self._get_active_events,
                "/api/statistics": self._get_statistics,
                "/api/context": self._get_context,
                "/api/snapshots": self._get_snapshots,
                "/api/messages": self._get_messages,
                "/api/config": self._get_config,
            }

            handler = routes.get(path)
            if handler:
                try:
                    handler(params)
                except Exception as e:
                    logger.error(f"API error on {path}: {e}", exc_info=True)
                    self._send_json({"error": str(e)}, 500)
            elif path.startswith("/api/events/"):
                self._get_event_detail(path.split("/")[-1])
            else:
                self._send_json({"error": "not found"}, 404)

        def do_POST(self):
            if not self._check_auth():
                self._send_json({"error": "unauthorized"}, 401)
                return

            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")

            routes = {
                "/api/command": self._post_command,
                "/api/scan": self._post_scan,
                "/api/fix": self._post_fix,
                "/api/message": self._post_message,
                "/api/context": self._post_context,
                "/api/config": self._post_config,
                "/api/directive": self._post_directive,
            }

            handler = routes.get(path)
            if handler:
                try:
                    body = self._read_body()
                    handler(body)
                except Exception as e:
                    logger.error(f"API error on POST {path}: {e}", exc_info=True)
                    self._send_json({"error": str(e)}, 500)
            else:
                self._send_json({"error": "not found"}, 404)

        # --- GET handlers ---

        def _get_health(self, params):
            self._send_json({
                "status": "healthy",
                "timestamp": time.time(),
                "uptime": time.time() - store.get_context("daemon_start_time", time.time()),
                "version": "1.0.0",
            })

        def _get_status(self, params):
            stats = store.get_statistics()
            snap = store.get_latest_snapshot()
            active = store.get_active_events(limit=20)
            self._send_json({
                "statistics": stats,
                "latest_snapshot": snap.to_dict() if snap else None,
                "active_events": [e.to_dict() for e in active],
                "daemon_running": True,
                "auto_fix_enabled": settings.auto_fix_enabled,
            })

        def _get_events(self, params):
            hours = float(params.get("hours", [24])[0])
            limit = int(params.get("limit", [100])[0])
            events = store.get_recent_events(hours=hours, limit=limit)
            self._send_json({
                "events": [e.to_dict() for e in events],
                "count": len(events),
            })

        def _get_active_events(self, params):
            events = store.get_active_events()
            self._send_json({
                "events": [e.to_dict() for e in events],
                "count": len(events),
            })

        def _get_event_detail(self, event_id):
            event = store.get_event(event_id)
            if not event:
                self._send_json({"error": "event not found"}, 404)
                return
            diagnoses = store.get_diagnoses_for_event(event_id)
            fixes = store.get_fixes_for_event(event_id)
            self._send_json({
                "event": event.to_dict(),
                "diagnoses": [d.to_dict() for d in diagnoses],
                "fixes": [f.to_dict() for f in fixes],
            })

        def _get_statistics(self, params):
            self._send_json(store.get_statistics())

        def _get_context(self, params):
            key = params.get("key", [None])[0]
            if key:
                self._send_json({"key": key, "value": store.get_context(key)})
            else:
                self._send_json(store.get_all_context())

        def _get_snapshots(self, params):
            hours = float(params.get("hours", [1])[0])
            snaps = store.get_snapshots(hours=hours)
            self._send_json({
                "snapshots": [s.to_dict() for s in snaps],
                "count": len(snaps),
            })

        def _get_messages(self, params):
            direction = params.get("direction", ["outbound"])[0]
            msgs = store.get_unprocessed_messages(direction=direction)
            self._send_json({"messages": msgs, "count": len(msgs)})

        def _get_config(self, params):
            self._send_json(settings.to_dict())

        # --- POST handlers ---

        def _post_command(self, body):
            """Execute an arbitrary command from Cursor."""
            cmd = body.get("command", "")
            if not cmd:
                self._send_json({"error": "no command provided"}, 400)
                return

            import subprocess
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30,
                )
                self._send_json({
                    "returncode": result.returncode,
                    "stdout": result.stdout[:10000],
                    "stderr": result.stderr[:10000],
                })
            except subprocess.TimeoutExpired:
                self._send_json({"error": "command timed out"}, 408)

        def _post_scan(self, body):
            """Trigger an immediate scan."""
            if daemon_ref and hasattr(daemon_ref, "trigger_scan"):
                daemon_ref.trigger_scan()
                self._send_json({"status": "scan triggered"})
            else:
                self._send_json({"error": "daemon not available"}, 503)

        def _post_fix(self, body):
            """Manually trigger a fix for an event."""
            event_id = body.get("event_id", "")
            if not event_id:
                self._send_json({"error": "event_id required"}, 400)
                return
            if daemon_ref and hasattr(daemon_ref, "trigger_fix"):
                daemon_ref.trigger_fix(event_id)
                self._send_json({"status": "fix triggered", "event_id": event_id})
            else:
                self._send_json({"error": "daemon not available"}, 503)

        def _post_message(self, body):
            """Receive a message from Cursor."""
            msg_type = body.get("type", "instruction")
            payload = body.get("payload", {})
            store.queue_cursor_message(msg_type, payload, direction="inbound")
            self._send_json({"status": "message queued"})

        def _post_context(self, body):
            """Set a context value."""
            key = body.get("key", "")
            value = body.get("value")
            if not key:
                self._send_json({"error": "key required"}, 400)
                return
            store.set_context(key, value)
            self._send_json({"status": "context updated", "key": key})

        def _post_config(self, body):
            """Update configuration values."""
            updated = []
            for key, value in body.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)
                    updated.append(key)
            if updated:
                settings.save()
            self._send_json({"status": "config updated", "updated": updated})

        def _post_directive(self, body):
            """Receive a high-level directive from Cursor.

            Directives can include:
            - "monitor": Add a new service/log to monitor
            - "ignore": Ignore specific event categories
            - "priority": Change event priority
            - "fix_strategy": Override fix strategy for a category
            - "reboot": Authorize or schedule a reboot
            """
            directive_type = body.get("directive", "")
            payload = body.get("payload", {})

            if directive_type == "monitor_service":
                svc = payload.get("service", "")
                if svc and svc not in settings.monitored_services:
                    settings.monitored_services.append(svc)
                    settings.save()
                self._send_json({"status": "service added to monitoring", "service": svc})

            elif directive_type == "ignore_category":
                cat = payload.get("category", "")
                ignored = store.get_context("ignored_categories", [])
                if cat not in ignored:
                    ignored.append(cat)
                    store.set_context("ignored_categories", ignored)
                self._send_json({"status": "category ignored", "category": cat})

            elif directive_type == "unignore_category":
                cat = payload.get("category", "")
                ignored = store.get_context("ignored_categories", [])
                if cat in ignored:
                    ignored.remove(cat)
                    store.set_context("ignored_categories", ignored)
                self._send_json({"status": "category unignored", "category": cat})

            elif directive_type == "enable_auto_fix":
                settings.auto_fix_enabled = True
                settings.save()
                self._send_json({"status": "auto-fix enabled"})

            elif directive_type == "disable_auto_fix":
                settings.auto_fix_enabled = False
                settings.save()
                self._send_json({"status": "auto-fix disabled"})

            elif directive_type == "authorize_reboot":
                settings.auto_reboot_enabled = True
                settings.save()
                store.set_context("reboot_authorized", True)
                self._send_json({"status": "reboot authorized"})

            elif directive_type == "schedule_reboot":
                delay = payload.get("delay_minutes", 5)
                import subprocess
                subprocess.run(
                    ["shutdown", "-r", f"+{delay}", "Self-healing: scheduled reboot"],
                    capture_output=True,
                )
                self._send_json({"status": "reboot scheduled", "delay_minutes": delay})

            elif directive_type == "cancel_reboot":
                import subprocess
                subprocess.run(["shutdown", "-c"], capture_output=True)
                self._send_json({"status": "reboot cancelled"})

            elif directive_type == "add_error_pattern":
                pattern = payload.get("pattern", "")
                severity = payload.get("severity", "error")
                category = payload.get("category", "custom")
                if pattern:
                    settings.error_patterns.append({
                        "pattern": pattern,
                        "severity": severity,
                        "category": category,
                    })
                    settings.save()
                self._send_json({"status": "pattern added"})

            elif directive_type == "set_threshold":
                key = payload.get("key", "")
                value = payload.get("value")
                if key and hasattr(settings, key):
                    setattr(settings, key, value)
                    settings.save()
                    self._send_json({"status": "threshold updated", "key": key, "value": value})
                else:
                    self._send_json({"error": f"unknown threshold: {key}"}, 400)

            else:
                store.queue_cursor_message(f"directive:{directive_type}", payload, direction="inbound")
                self._send_json({"status": "directive queued", "type": directive_type})

    return RequestHandler
