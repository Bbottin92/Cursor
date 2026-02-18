"""Self-healing system daemon.

The main orchestrator that:
1. Initializes all monitoring modules
2. Runs periodic scans to detect issues
3. Passes detected events through diagnosis
4. Executes automatic fixes
5. Manages persistent context across restarts
6. Communicates with Cursor via API
7. Handles graceful shutdown and restart recovery
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

from config.settings import Settings
from persistence.context_store import ContextStore
from persistence.models import Event, EventState, Severity
from modules.log_monitor import LogMonitorModule
from modules.service_monitor import ServiceMonitorModule
from modules.resource_monitor import ResourceMonitorModule
from modules.network_monitor import NetworkMonitorModule
from modules.process_monitor import ProcessMonitorModule
from modules.filesystem_monitor import FilesystemMonitorModule
from modules.diagnosis_engine import DiagnosisEngine
from modules.fix_engine import FixEngine
from api.server import APIServer

logger = logging.getLogger("self-healing.daemon")


class SelfHealingDaemon:
    """Main daemon process orchestrating all self-healing operations."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = ContextStore(db_path=settings.db_path)
        self._running = False
        self._shutdown_event = threading.Event()
        self._scan_trigger = threading.Event()

        # Engines
        self.diagnosis = DiagnosisEngine(settings, self.store)
        self.fix_engine = FixEngine(settings, self.store)

        # Modules
        self.modules = [
            LogMonitorModule(settings, self.store),
            ServiceMonitorModule(settings, self.store),
            ResourceMonitorModule(settings, self.store),
            NetworkMonitorModule(settings, self.store),
            ProcessMonitorModule(settings, self.store),
            FilesystemMonitorModule(settings, self.store),
        ]

        # Resource monitor has snapshot capability
        self._resource_monitor = self.modules[2]

        # API server
        self.api_server = APIServer(settings, self.store, daemon_ref=self)

        # Threads
        self._threads: list[threading.Thread] = []

    def start(self):
        """Start the daemon and all subsystems."""
        logger.info("=" * 60)
        logger.info("Self-Healing System Daemon starting...")
        logger.info("=" * 60)

        self._running = True
        self.store.set_context("daemon_start_time", time.time())
        self.store.set_context("daemon_pid", os.getpid())
        self.store.set_context("daemon_version", "1.0.0")

        # Write PID file
        self._write_pid()

        # Handle startup recovery
        self._recover_from_restart()

        # Register signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGHUP, self._reload_handler)

        # Start API server
        self.api_server.start()

        # Start worker threads
        self._start_thread("scanner", self._scan_loop)
        self._start_thread("snapshot", self._snapshot_loop)
        self._start_thread("cursor_poller", self._cursor_poll_loop)
        self._start_thread("pruner", self._prune_loop)
        self._start_thread("heartbeat", self._heartbeat_loop)

        logger.info("All subsystems started. Daemon is operational.")
        self.store.queue_cursor_message("daemon_started", {
            "pid": os.getpid(),
            "modules": [m.name for m in self.modules],
            "auto_fix_enabled": self.settings.auto_fix_enabled,
        })

        # Main loop - keep alive
        try:
            while self._running:
                self._shutdown_event.wait(timeout=1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Gracefully stop the daemon."""
        logger.info("Daemon shutting down...")
        self._running = False
        self._shutdown_event.set()
        self._scan_trigger.set()

        # Stop API
        self.api_server.stop()

        # Clean up modules
        for mod in self.modules:
            try:
                mod.cleanup()
            except Exception:
                pass

        # Wait for threads
        for t in self._threads:
            t.join(timeout=5)

        # Store shutdown context
        self.store.set_context("daemon_last_shutdown", time.time())
        self.store.set_context("daemon_clean_shutdown", True)

        # Remove PID file
        self._remove_pid()
        logger.info("Daemon stopped cleanly.")

    def trigger_scan(self):
        """Trigger an immediate scan (called by API)."""
        self._scan_trigger.set()

    def trigger_fix(self, event_id: str):
        """Trigger a fix for a specific event (called by API)."""
        event = self.store.get_event(event_id)
        if not event:
            logger.warning(f"Cannot fix unknown event: {event_id}")
            return
        threading.Thread(
            target=self._process_event, args=(event,), daemon=True
        ).start()

    # --- Internal loops ---

    def _start_thread(self, name: str, target):
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        self._threads.append(t)

    def _scan_loop(self):
        """Main scanning loop - runs all modules periodically."""
        while self._running:
            try:
                self._run_scan()
            except Exception as e:
                logger.error(f"Scan loop error: {e}", exc_info=True)

            # Wait for interval or trigger
            self._scan_trigger.wait(timeout=self.settings.scan_interval)
            self._scan_trigger.clear()

    def _run_scan(self):
        """Execute a single scan cycle across all modules."""
        ignored = set(self.store.get_context("ignored_categories", []))
        total_events = 0

        for module in self.modules:
            try:
                events = module.scan()
                for event in events:
                    if event.category in ignored:
                        continue
                    self.store.store_event(event)
                    total_events += 1
                    self._process_event(event)
            except Exception as e:
                logger.error(f"Module {module.name} scan error: {e}", exc_info=True)

        if total_events > 0:
            logger.info(f"Scan complete: {total_events} new events detected")

    def _process_event(self, event: Event):
        """Process a single event through diagnosis and fix."""
        try:
            # Diagnose
            diagnosis = self.diagnosis.diagnose(event)

            if not diagnosis.suggested_fixes:
                logger.info(f"No fixes suggested for event {event.id}")
                self.store.update_event_state(event.id, EventState.MONITORING.value)
                return

            if diagnosis.confidence < 0.3:
                logger.info(
                    f"Low confidence ({diagnosis.confidence}) for event {event.id}, "
                    f"escalating to Cursor"
                )
                self.store.update_event_state(event.id, EventState.ESCALATED.value)
                self.store.queue_cursor_message("low_confidence_event", {
                    "event_id": event.id,
                    "summary": event.summary,
                    "diagnosis": diagnosis.root_cause,
                    "confidence": diagnosis.confidence,
                })
                return

            # Execute fixes
            fixes = self.fix_engine.execute_fixes(event, diagnosis)

            # Report to Cursor
            self.store.queue_cursor_message("event_processed", {
                "event_id": event.id,
                "summary": event.summary,
                "diagnosis": diagnosis.root_cause,
                "confidence": diagnosis.confidence,
                "fixes_attempted": len(fixes),
                "fix_results": [{"type": f.fix_type, "result": f.result} for f in fixes],
                "final_state": self.store.get_event(event.id).state if self.store.get_event(event.id) else "unknown",
            })

        except Exception as e:
            logger.error(f"Error processing event {event.id}: {e}", exc_info=True)
            self.store.update_event_state(event.id, EventState.FAILED.value)

    def _snapshot_loop(self):
        """Periodic system snapshot loop."""
        while self._running:
            try:
                snap = self._resource_monitor.take_snapshot()
                snap.zombie_processes = self.store.get_context("zombie_count", 0)
                net = self.store.get_context("network_status", {})
                snap.network_status = "up" if net.get("connectivity", False) else "down"
                snap.failed_services = self._get_failed_services()
                self.store.store_snapshot(snap)
            except Exception as e:
                logger.error(f"Snapshot error: {e}", exc_info=True)

            self._shutdown_event.wait(timeout=self.settings.snapshot_interval)

    def _cursor_poll_loop(self):
        """Poll for inbound messages from Cursor."""
        while self._running:
            try:
                messages = self.store.get_unprocessed_messages(direction="inbound")
                for msg in messages:
                    self._handle_cursor_message(msg)
                    self.store.mark_message_processed(msg["id"])
            except Exception as e:
                logger.error(f"Cursor poll error: {e}", exc_info=True)

            self._shutdown_event.wait(timeout=self.settings.cursor_poll_interval)

    def _handle_cursor_message(self, msg: dict):
        """Process an inbound message from Cursor."""
        msg_type = msg.get("message_type", "")
        payload = msg.get("payload", {})
        logger.info(f"Processing Cursor message: type={msg_type}")

        if msg_type == "instruction":
            instruction = payload.get("text", "")
            logger.info(f"Cursor instruction: {instruction}")
            self.store.set_context("last_cursor_instruction", {
                "text": instruction,
                "timestamp": time.time(),
            })
        elif msg_type == "force_scan":
            self.trigger_scan()
        elif msg_type == "force_fix":
            event_id = payload.get("event_id", "")
            if event_id:
                self.trigger_fix(event_id)
        elif msg_type == "update_config":
            for key, value in payload.items():
                if hasattr(self.settings, key):
                    setattr(self.settings, key, value)
            self.settings.save()
        else:
            logger.info(f"Unknown cursor message type: {msg_type}")

    def _prune_loop(self):
        """Periodically prune old data."""
        while self._running:
            try:
                self.store.prune_old_snapshots(self.settings.snapshot_retention_hours)
            except Exception as e:
                logger.error(f"Prune error: {e}", exc_info=True)
            self._shutdown_event.wait(timeout=self.settings.prune_interval)

    def _heartbeat_loop(self):
        """Write heartbeat to context store for watchdog monitoring."""
        while self._running:
            try:
                self.store.set_context("heartbeat", {
                    "timestamp": time.time(),
                    "pid": os.getpid(),
                    "threads_alive": sum(1 for t in self._threads if t.is_alive()),
                    "total_threads": len(self._threads),
                })
            except Exception:
                pass
            self._shutdown_event.wait(timeout=10)

    # --- Recovery ---

    def _recover_from_restart(self):
        """Handle recovery after a restart or crash."""
        clean = self.store.get_context("daemon_clean_shutdown", False)
        last_shutdown = self.store.get_context("daemon_last_shutdown", 0)
        pending_reboot = self.store.get_context("pending_reboot_event", "")

        if not clean and last_shutdown > 0:
            logger.warning("Previous shutdown was not clean - possible crash recovery")
            self.store.queue_cursor_message("unclean_restart", {
                "last_shutdown": last_shutdown,
                "current_start": time.time(),
                "gap_seconds": time.time() - last_shutdown,
            })

        if pending_reboot:
            logger.info(f"Resuming after reboot for event: {pending_reboot}")
            event = self.store.get_event(pending_reboot)
            if event:
                self.store.update_event_state(event.id, EventState.MONITORING.value)
                self.store.queue_cursor_message("reboot_completed", {
                    "event_id": pending_reboot,
                    "summary": event.summary,
                })
            self.store.set_context("pending_reboot_event", "")

        # Reset interrupted events
        for state in [EventState.DIAGNOSING.value, EventState.FIXING.value]:
            events = self.store.get_events_by_state(state)
            for event in events:
                logger.info(f"Resetting interrupted event {event.id} from {state} to detected")
                self.store.update_event_state(event.id, EventState.DETECTED.value)

        self.store.set_context("daemon_clean_shutdown", False)

    # --- Helpers ---

    def _get_failed_services(self) -> list[str]:
        import subprocess
        try:
            result = subprocess.run(
                ["systemctl", "--failed", "--no-legend", "--plain", "-q"],
                capture_output=True, text=True, timeout=5,
            )
            return [
                line.split()[0]
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
        except Exception:
            return []

    def _write_pid(self):
        pid_dir = os.path.dirname(self.settings.pid_file)
        os.makedirs(pid_dir, exist_ok=True)
        with open(self.settings.pid_file, "w") as f:
            f.write(str(os.getpid()))

    def _remove_pid(self):
        try:
            os.remove(self.settings.pid_file)
        except OSError:
            pass

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self._running = False
        self._shutdown_event.set()

    def _reload_handler(self, signum, frame):
        logger.info("Received SIGHUP, reloading configuration...")
        from config.settings import load_settings
        new_settings = load_settings(self.settings.config_path)
        for key in vars(new_settings):
            setattr(self.settings, key, getattr(new_settings, key))
        logger.info("Configuration reloaded")
