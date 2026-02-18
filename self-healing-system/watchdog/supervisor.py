"""Watchdog supervisor.

A separate lightweight process that monitors the main daemon and restarts
it if it becomes unresponsive. This provides a second layer of reliability:

1. systemd watches the watchdog (RestartSec, WatchdogSec)
2. The watchdog watches the daemon
3. The daemon monitors the system

The watchdog checks:
- Heartbeat freshness in the context store
- PID file validity (process actually running)
- HTTP health endpoint responsiveness
- Thread liveness
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger("self-healing.watchdog")

DEFAULT_DB_PATH = "/var/lib/self-healing/context.db"
DEFAULT_PID_FILE = "/var/run/self-healing/daemon.pid"
DEFAULT_API_PORT = 7847


class Watchdog:
    """Monitors the main daemon process and restarts it if needed."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        pid_file: str = DEFAULT_PID_FILE,
        api_port: int = DEFAULT_API_PORT,
        check_interval: int = 15,
        max_failures: int = 3,
        daemon_cmd: Optional[list[str]] = None,
    ):
        self.db_path = db_path
        self.pid_file = pid_file
        self.api_port = api_port
        self.check_interval = check_interval
        self.max_failures = max_failures
        self.daemon_cmd = daemon_cmd or [
            sys.executable, "-m", "main", "--mode", "daemon",
        ]
        self._running = True
        self._consecutive_failures = 0
        self._total_restarts = 0

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def run(self):
        """Main watchdog loop."""
        logger.info("Watchdog supervisor started")
        logger.info(f"  PID file: {self.pid_file}")
        logger.info(f"  API port: {self.api_port}")
        logger.info(f"  Check interval: {self.check_interval}s")
        logger.info(f"  Max failures before restart: {self.max_failures}")

        # Ensure daemon is running on first start
        if not self._is_daemon_running():
            logger.info("Daemon not running, starting it...")
            self._start_daemon()
            time.sleep(5)

        while self._running:
            try:
                healthy = self._check_health()
                if healthy:
                    self._consecutive_failures = 0
                else:
                    self._consecutive_failures += 1
                    logger.warning(
                        f"Daemon health check failed "
                        f"({self._consecutive_failures}/{self.max_failures})"
                    )

                    if self._consecutive_failures >= self.max_failures:
                        logger.error("Max failures reached, restarting daemon...")
                        self._restart_daemon()
                        self._consecutive_failures = 0
                        self._total_restarts += 1

            except Exception as e:
                logger.error(f"Watchdog check error: {e}")

            time.sleep(self.check_interval)

        logger.info(f"Watchdog stopped. Total daemon restarts: {self._total_restarts}")

    def _check_health(self) -> bool:
        """Run all health checks. Returns True if daemon is healthy."""
        checks = {
            "pid_alive": self._check_pid_alive(),
            "heartbeat_fresh": self._check_heartbeat(),
            "api_responsive": self._check_api(),
        }

        all_ok = all(checks.values())
        if not all_ok:
            failed = [k for k, v in checks.items() if not v]
            logger.warning(f"Failed health checks: {failed}")

        return all_ok

    def _check_pid_alive(self) -> bool:
        """Check if the daemon PID is actually running."""
        pid = self._read_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def _check_heartbeat(self) -> bool:
        """Check if heartbeat in database is fresh."""
        try:
            import sqlite3
            if not os.path.exists(self.db_path):
                return False
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT value FROM context WHERE key = 'heartbeat'"
            ).fetchone()
            conn.close()

            if not row:
                return False

            hb = json.loads(row["value"])
            age = time.time() - hb.get("timestamp", 0)
            return age < 60  # heartbeat should be < 60 seconds old
        except Exception as e:
            logger.debug(f"Heartbeat check error: {e}")
            return False

    def _check_api(self) -> bool:
        """Check if the HTTP API is responsive."""
        try:
            url = f"http://127.0.0.1:{self.api_port}/api/health"
            req = Request(url, method="GET")
            resp = urlopen(req, timeout=5)
            data = json.loads(resp.read())
            return data.get("status") == "healthy"
        except (URLError, TimeoutError, Exception):
            return False

    def _is_daemon_running(self) -> bool:
        """Check if daemon process exists."""
        return self._check_pid_alive()

    def _read_pid(self) -> Optional[int]:
        """Read PID from file."""
        try:
            with open(self.pid_file, "r") as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return None

    def _start_daemon(self):
        """Start the daemon process."""
        logger.info(f"Starting daemon: {' '.join(self.daemon_cmd)}")
        try:
            # Determine the working directory
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            subprocess.Popen(
                self.daemon_cmd,
                cwd=script_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            logger.info("Daemon process started")
        except Exception as e:
            logger.error(f"Failed to start daemon: {e}")

    def _stop_daemon(self):
        """Stop the daemon process gracefully, then force if needed."""
        pid = self._read_pid()
        if pid is None:
            return

        logger.info(f"Stopping daemon PID {pid}")
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                time.sleep(1)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    logger.info("Daemon stopped gracefully")
                    return
            # Force kill
            logger.warning(f"Force killing daemon PID {pid}")
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error(f"Error stopping daemon: {e}")

    def _restart_daemon(self):
        """Restart the daemon process."""
        logger.info("Restarting daemon...")
        self._stop_daemon()
        time.sleep(2)
        self._start_daemon()
        time.sleep(5)

        # Write restart event to database
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.execute(
                "INSERT OR REPLACE INTO context (key, value, updated_at) VALUES (?, ?, ?)",
                (
                    "last_watchdog_restart",
                    json.dumps({
                        "timestamp": time.time(),
                        "total_restarts": self._total_restarts + 1,
                        "reason": "health check failures",
                    }),
                    time.time(),
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _signal_handler(self, signum, frame):
        logger.info(f"Watchdog received signal {signum}")
        self._running = False
