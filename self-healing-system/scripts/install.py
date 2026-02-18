#!/usr/bin/env python3
"""Installer for the self-healing system.

Handles:
1. Copying files to /opt/self-healing-system/
2. Installing systemd service files
3. Creating required directories
4. Generating default configuration
5. Enabling and starting services
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_DIR = "/opt/self-healing-system"
SYSTEMD_DIR = "/etc/systemd/system"
CONFIG_DIR = "/etc/self-healing"
DATA_DIR = "/var/lib/self-healing"
LOG_DIR = "/var/log/self-healing"
RUN_DIR = "/var/run/self-healing"

SERVICE_FILES = [
    "self-healing-daemon.service",
    "self-healing-watchdog.service",
    "self-healing-boot.service",
]


def install(settings=None):
    """Full installation procedure."""
    if os.geteuid() != 0:
        print("ERROR: Installation requires root privileges. Run with sudo.")
        sys.exit(1)

    print("=" * 60)
    print("Self-Healing System Installer")
    print("=" * 60)

    # 1. Create directories
    print("\n[1/6] Creating directories...")
    for d in [INSTALL_DIR, CONFIG_DIR, DATA_DIR, LOG_DIR, RUN_DIR]:
        os.makedirs(d, exist_ok=True)
        print(f"  Created: {d}")

    # 2. Copy application files
    print("\n[2/6] Installing application files...")
    src_dir = Path(__file__).parent.parent
    _copy_tree(src_dir, INSTALL_DIR)
    print(f"  Installed to: {INSTALL_DIR}")

    # Make entry points executable
    for script in ["main.py", "scripts/boot_recovery.py"]:
        path = os.path.join(INSTALL_DIR, script)
        if os.path.exists(path):
            os.chmod(path, 0o755)

    # 3. Install systemd services
    print("\n[3/6] Installing systemd services...")
    scripts_dir = os.path.join(INSTALL_DIR, "scripts")
    for svc_file in SERVICE_FILES:
        src = os.path.join(scripts_dir, svc_file)
        dst = os.path.join(SYSTEMD_DIR, svc_file)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            os.chmod(dst, 0o644)
            print(f"  Installed: {dst}")

    # 4. Generate default config
    print("\n[4/6] Generating configuration...")
    config_path = os.path.join(CONFIG_DIR, "config.json")
    if not os.path.exists(config_path):
        if settings is None:
            from config.settings import Settings
            settings = Settings()
        settings.save(config_path)
        print(f"  Config written to: {config_path}")
    else:
        print(f"  Config already exists: {config_path} (preserved)")

    # 5. Reload systemd and enable services
    print("\n[5/6] Enabling services...")
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    for svc_file in SERVICE_FILES:
        svc_name = svc_file.replace(".service", "")
        subprocess.run(["systemctl", "enable", svc_name], check=False)
        print(f"  Enabled: {svc_name}")

    # 6. Start services
    print("\n[6/6] Starting services...")
    subprocess.run(["systemctl", "start", "self-healing-daemon"], check=False)
    subprocess.run(["systemctl", "start", "self-healing-watchdog"], check=False)
    print("  Started: self-healing-daemon")
    print("  Started: self-healing-watchdog")

    print("\n" + "=" * 60)
    print("Installation complete!")
    print()
    print("The self-healing system is now:")
    print("  - Running as a system daemon")
    print("  - Monitored by a watchdog supervisor")
    print("  - Configured to start on boot (before user login)")
    print("  - Listening for Cursor API on localhost:7847")
    print()
    print("Useful commands:")
    print("  systemctl status self-healing-daemon")
    print("  systemctl status self-healing-watchdog")
    print("  journalctl -u self-healing-daemon -f")
    print(f"  curl http://localhost:7847/api/health")
    print(f"  curl http://localhost:7847/api/status")
    print(f"  python3 {INSTALL_DIR}/main.py --mode status")
    print("=" * 60)


def uninstall():
    """Full uninstallation procedure."""
    if os.geteuid() != 0:
        print("ERROR: Uninstallation requires root privileges. Run with sudo.")
        sys.exit(1)

    print("=" * 60)
    print("Self-Healing System Uninstaller")
    print("=" * 60)

    # Stop services
    print("\n[1/4] Stopping services...")
    subprocess.run(["systemctl", "stop", "self-healing-watchdog"], check=False)
    subprocess.run(["systemctl", "stop", "self-healing-daemon"], check=False)

    # Disable services
    print("\n[2/4] Disabling services...")
    for svc_file in SERVICE_FILES:
        svc_name = svc_file.replace(".service", "")
        subprocess.run(["systemctl", "disable", svc_name], check=False)

    # Remove service files
    print("\n[3/4] Removing service files...")
    for svc_file in SERVICE_FILES:
        path = os.path.join(SYSTEMD_DIR, svc_file)
        if os.path.exists(path):
            os.remove(path)
            print(f"  Removed: {path}")
    subprocess.run(["systemctl", "daemon-reload"], check=False)

    # Remove application (keep data and config)
    print("\n[4/4] Removing application...")
    if os.path.exists(INSTALL_DIR):
        shutil.rmtree(INSTALL_DIR)
        print(f"  Removed: {INSTALL_DIR}")

    print()
    print("Note: Data and configuration preserved at:")
    print(f"  Config: {CONFIG_DIR}")
    print(f"  Data:   {DATA_DIR}")
    print(f"  Logs:   {LOG_DIR}")
    print("Delete them manually if no longer needed.")
    print("=" * 60)


def _copy_tree(src: Path, dst: str):
    """Copy source tree to destination, skipping __pycache__ and .git."""
    skip = {"__pycache__", ".git", ".gitignore", "node_modules", ".venv", "venv"}
    for item in src.iterdir():
        if item.name in skip:
            continue
        dst_path = os.path.join(dst, item.name)
        if item.is_dir():
            os.makedirs(dst_path, exist_ok=True)
            _copy_tree(item, dst_path)
        else:
            shutil.copy2(str(item), dst_path)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "uninstall"])
    args = parser.parse_args()
    if args.action == "install":
        install()
    else:
        uninstall()
