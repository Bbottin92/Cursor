#!/usr/bin/env python3
"""Self-Healing System - Main entry point.

Usage:
    python -m main --mode daemon        Run the main healing daemon
    python -m main --mode watchdog      Run the watchdog supervisor
    python -m main --mode status        Show current system status
    python -m main --mode install       Install systemd services
    python -m main --mode uninstall     Remove systemd services
    python -m main --mode config        Generate default configuration
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import Settings, load_settings, CONFIG_PATH
from persistence.context_store import ContextStore


def setup_logging(settings: Settings, mode: str):
    """Configure logging to file and console."""
    log_dir = os.path.dirname(settings.log_path)
    os.makedirs(log_dir, exist_ok=True)

    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
    ]

    try:
        file_handler = logging.FileHandler(settings.log_path)
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    except (OSError, PermissionError):
        pass

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=handlers,
    )

    # Reduce noise from HTTP server
    logging.getLogger("self-healing.api").setLevel(logging.WARNING)


def run_daemon(settings: Settings):
    """Run the main self-healing daemon."""
    setup_logging(settings, "daemon")
    from core.daemon import SelfHealingDaemon
    daemon = SelfHealingDaemon(settings)
    daemon.start()


def run_watchdog(settings: Settings):
    """Run the watchdog supervisor."""
    setup_logging(settings, "watchdog")
    from watchdog.supervisor import Watchdog
    wd = Watchdog(
        db_path=settings.db_path,
        pid_file=settings.pid_file,
        api_port=settings.api_port,
        check_interval=settings.watchdog_interval,
        max_failures=settings.watchdog_max_failures,
    )
    wd.run()


def show_status(settings: Settings):
    """Display current system status."""
    try:
        from urllib.request import urlopen, Request
        url = f"http://{settings.api_host}:{settings.api_port}/api/status"
        req = Request(url)
        if settings.api_token:
            req.add_header("Authorization", f"Bearer {settings.api_token}")
        resp = urlopen(req, timeout=5)
        data = json.loads(resp.read())
        print(json.dumps(data, indent=2, default=str))
    except Exception as e:
        print(f"Could not connect to daemon API: {e}")
        print("Checking database directly...")

        store = ContextStore(db_path=settings.db_path)
        stats = store.get_statistics()
        print(json.dumps(stats, indent=2))


def generate_config(settings: Settings):
    """Generate default configuration file."""
    settings.save()
    print(f"Configuration written to {settings.config_path}")


def install_services(settings: Settings):
    """Install systemd service files."""
    from scripts.install import install
    install(settings)


def uninstall_services(settings: Settings):
    """Remove systemd service files."""
    from scripts.install import uninstall
    uninstall()


def main():
    parser = argparse.ArgumentParser(description="Self-Healing System Daemon")
    parser.add_argument(
        "--mode",
        choices=["daemon", "watchdog", "status", "install", "uninstall", "config"],
        default="daemon",
        help="Operating mode",
    )
    parser.add_argument(
        "--config",
        default=CONFIG_PATH,
        help=f"Path to configuration file (default: {CONFIG_PATH})",
    )
    args = parser.parse_args()

    settings = load_settings(args.config)
    settings.config_path = args.config

    modes = {
        "daemon": run_daemon,
        "watchdog": run_watchdog,
        "status": show_status,
        "install": install_services,
        "uninstall": uninstall_services,
        "config": generate_config,
    }

    modes[args.mode](settings)


if __name__ == "__main__":
    main()
