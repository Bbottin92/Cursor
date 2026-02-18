"""System configuration and settings."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

CONFIG_PATH = "/etc/self-healing/config.json"
DEFAULT_DB_PATH = "/var/lib/self-healing/context.db"
DEFAULT_LOG_PATH = "/var/log/self-healing/daemon.log"
DEFAULT_SOCKET_PATH = "/var/run/self-healing/daemon.sock"
DEFAULT_API_PORT = 7847
DEFAULT_API_HOST = "127.0.0.1"


@dataclass
class Settings:
    """All configurable settings for the self-healing daemon."""

    # Paths
    db_path: str = DEFAULT_DB_PATH
    log_path: str = DEFAULT_LOG_PATH
    socket_path: str = DEFAULT_SOCKET_PATH
    pid_file: str = "/var/run/self-healing/daemon.pid"
    config_path: str = CONFIG_PATH

    # API settings
    api_host: str = DEFAULT_API_HOST
    api_port: int = DEFAULT_API_PORT
    api_token: str = ""

    # Monitoring intervals (seconds)
    scan_interval: int = 30
    snapshot_interval: int = 60
    log_check_interval: int = 10
    service_check_interval: int = 30
    resource_check_interval: int = 30
    network_check_interval: int = 60
    cursor_poll_interval: int = 5
    prune_interval: int = 3600

    # Thresholds
    cpu_threshold: float = 90.0
    memory_threshold: float = 90.0
    disk_threshold: float = 90.0
    load_threshold_multiplier: float = 2.0
    zombie_threshold: int = 10
    fd_threshold: int = 50000
    oom_score_threshold: int = 800

    # Behavior
    auto_fix_enabled: bool = True
    auto_reboot_enabled: bool = False
    max_fix_retries: int = 3
    fix_cooldown_seconds: int = 300
    escalate_after_retries: int = 3
    snapshot_retention_hours: float = 72.0

    # Cursor communication
    cursor_enabled: bool = True
    cursor_api_url: str = ""
    cursor_api_key: str = ""

    # Watchdog
    watchdog_enabled: bool = True
    watchdog_interval: int = 15
    watchdog_max_failures: int = 3

    # Monitored log files
    monitored_logs: list[str] = field(default_factory=lambda: [
        "/var/log/syslog",
        "/var/log/kern.log",
        "/var/log/auth.log",
        "/var/log/dmesg",
    ])

    # Services to monitor
    monitored_services: list[str] = field(default_factory=lambda: [
        "ssh", "cron", "systemd-resolved", "networkd-dispatcher",
    ])

    # Error patterns to watch for in logs
    error_patterns: list[dict] = field(default_factory=lambda: [
        {"pattern": r"Out of memory", "severity": "critical", "category": "memory"},
        {"pattern": r"oom-killer", "severity": "critical", "category": "memory"},
        {"pattern": r"segfault", "severity": "error", "category": "crash"},
        {"pattern": r"kernel panic", "severity": "critical", "category": "kernel"},
        {"pattern": r"I/O error", "severity": "error", "category": "disk"},
        {"pattern": r"No space left on device", "severity": "critical", "category": "disk"},
        {"pattern": r"Connection refused", "severity": "warning", "category": "network"},
        {"pattern": r"failed to start", "severity": "error", "category": "service"},
        {"pattern": r"entered failed state", "severity": "error", "category": "service"},
        {"pattern": r"ACPI Error", "severity": "warning", "category": "hardware"},
        {"pattern": r"Hardware Error", "severity": "critical", "category": "hardware"},
        {"pattern": r"temperature above threshold", "severity": "warning", "category": "hardware"},
        {"pattern": r"EXT4-fs error", "severity": "critical", "category": "filesystem"},
        {"pattern": r"Remounting filesystem read-only", "severity": "critical", "category": "filesystem"},
    ])

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str = ""):
        path = path or self.config_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


def load_settings(config_path: str = CONFIG_PATH) -> Settings:
    """Load settings from file, falling back to defaults."""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
            return Settings.from_dict(data)
        except Exception:
            pass
    return Settings()
