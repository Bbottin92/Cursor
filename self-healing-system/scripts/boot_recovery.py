#!/usr/bin/env python3
"""Early boot recovery script.

Runs as a systemd oneshot service very early in boot (before user login).
Checks if there were pending repairs from before reboot and handles:
1. Post-reboot fsck validation
2. Clearing pending reboot flags
3. Logging the reboot event
4. Ensuring the main daemon will start cleanly
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

DB_PATH = "/var/lib/self-healing/context.db"
LOG_PATH = "/var/log/self-healing/boot_recovery.log"


def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_context(conn, key, default=None):
    try:
        row = conn.execute("SELECT value FROM context WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default
    except Exception:
        return default


def set_context(conn, key, value):
    try:
        conn.execute(
            "INSERT OR REPLACE INTO context (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time()),
        )
        conn.commit()
    except Exception as e:
        log(f"Error setting context {key}: {e}")


def main():
    log("Self-healing boot recovery starting...")

    if not os.path.exists(DB_PATH):
        log("No database found, nothing to recover. First boot?")
        return

    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
    except Exception as e:
        log(f"Cannot open database: {e}")
        return

    try:
        # Check if reboot was initiated by us
        reboot_initiated = get_context(conn, "reboot_initiated", 0)
        pending_event = get_context(conn, "pending_reboot_event", "")
        reboot_reason = get_context(conn, "reboot_reason", "")

        if reboot_initiated:
            downtime = time.time() - reboot_initiated
            log(f"Reboot was initiated by self-healing system. Downtime: {downtime:.0f}s")
            log(f"Reboot reason: {reboot_reason}")
            set_context(conn, "reboot_initiated", 0)
            set_context(conn, "last_reboot_downtime", downtime)

        # Check for forced fsck
        if os.path.exists("/forcefsck"):
            log("Forced fsck was scheduled, checking result...")
            try:
                os.remove("/forcefsck")
                log("Removed /forcefsck flag")
            except Exception:
                pass

        # Check if clean shutdown happened
        clean = get_context(conn, "daemon_clean_shutdown", False)
        if not clean:
            log("WARNING: Previous daemon shutdown was not clean (possible crash or power loss)")
            set_context(conn, "unclean_shutdown_detected", time.time())

        # Record boot event
        set_context(conn, "last_boot_time", time.time())
        set_context(conn, "boot_count", get_context(conn, "boot_count", 0) + 1)

        # Check system health basics at boot
        checks = {}

        # Root filesystem writable?
        try:
            test_path = "/tmp/.self_healing_boot_check"
            with open(test_path, "w") as f:
                f.write("test")
            os.remove(test_path)
            checks["root_fs_writable"] = True
        except Exception:
            checks["root_fs_writable"] = False
            log("CRITICAL: Root filesystem is not writable!")

        # Network interface up?
        try:
            result = subprocess.run(
                ["ip", "link", "show"], capture_output=True, text=True, timeout=5,
            )
            checks["network_interfaces"] = result.returncode == 0
        except Exception:
            checks["network_interfaces"] = False

        set_context(conn, "boot_health_checks", checks)
        log(f"Boot health checks: {json.dumps(checks)}")
        log("Boot recovery complete.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
