from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._paths import default_config_path, default_state_dir


def _deep_update(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_update(dst[k], v)
        else:
            dst[k] = v
    return dst


def default_config() -> dict[str, Any]:
    # Defaults are intentionally conservative: only safe, local cleanups enabled.
    return {
        "poll_interval_seconds": 30,
        "thresholds": {
            "disk_usage_percent": 92,
        },
        "cursor": {
            # Cursor / VSCode-style Electron apps often write Crashpad dumps even when
            # stdout/stderr logs aren't persisted. These settings enable detection.
            "crashpad_dirs": ["~/.config/Cursor/Crashpad"],
            "crash_window_minutes": 30,
            "crash_threshold": 2,
        },
        "addons": {
            # Addon system: lets you extend autoheal with new checks/actions.
            "enabled": True,
            "modules": [],
            "paths": ["~/.config/autoheal/addons.d"],
            "module_config": {},
            "fail_open": True,
        },
        "disk": {
            "mountpoints": ["/"],
        },
        "actions": {
            "tmp_cleanup": {
                "enabled": True,
                "paths": ["/tmp"],
                "max_age_hours": 72,
                "max_bytes_per_run": 512 * 1024 * 1024,  # 512 MiB
                "allow_paths_outside_tmp": False,
            },
            "systemd_user_restart_failed_units": {
                # Safe-ish default: user scope only, no root required.
                "enabled": True,
                "restart_all_failed": True,
                "allowlist_units": [],
                "cooldown_seconds": 900,
                "command_timeout_seconds": 30,
            },
            "systemd_restart_failed_units": {
                "enabled": False,
                "allowlist_units": [],
                "cooldown_seconds": 900,
                "command_timeout_seconds": 30,
            },
            "cursor_safe_launcher": {
                # Disabled by default: this modifies/installs a launcher wrapper to
                # apply safer flags automatically when Cursor is started.
                "enabled": False,
                "launcher_path": "~/.local/bin/cursor",
                "backup_suffix": ".autoheal-orig",
                "flags": ["--disable-extensions", "--disable-gpu"],
                "cooldown_seconds": 3600,
            },
            "reboot": {
                "enabled": False,
            },
        },
        "control": {
            "enabled": True,
            "token": None,  # optional; if set, required for control calls
        },
    }


@dataclass(frozen=True)
class LoadedConfig:
    path: Path | None
    data: dict[str, Any]


def load_config(path: str | Path | None) -> LoadedConfig:
    env = os.environ.get("AUTOHEAL_CONFIG")
    cfg_path: Path | None = None
    if path:
        cfg_path = Path(path)
    elif env:
        cfg_path = Path(env)
    else:
        cfg_path = default_config_path()

    base = default_config()
    try:
        if cfg_path.exists():
            raw = cfg_path.read_text(encoding="utf-8")
            user = json.loads(raw) if raw.strip() else {}
            if not isinstance(user, dict):
                raise TypeError("config root must be a JSON object")
            _deep_update(base, user)
            return LoadedConfig(path=cfg_path, data=base)
    except Exception:
        # If config can't be loaded, fall back to defaults (agent should still run).
        return LoadedConfig(path=cfg_path, data=base)

    # No config file: defaults only.
    return LoadedConfig(path=cfg_path if cfg_path else None, data=base)


def ensure_state_dirs(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    # Keep state private for user installs (contains DB, logs, control socket).
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        try:
            os.chmod(state_dir, 0o700)
        except Exception:
            pass
    # Also ensure ~/.config/autoheal exists for convenience (no-op if missing perms).
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        try:
            cfg_dir = Path("~/.config/autoheal").expanduser()
            cfg_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(cfg_dir, 0o700)
            except Exception:
                pass
        except Exception:
            pass


def resolve_state_dir(cli_state_dir: str | Path | None) -> Path:
    env = os.environ.get("AUTOHEAL_STATE_DIR")
    if cli_state_dir:
        return Path(cli_state_dir).expanduser().resolve()
    if env:
        return Path(env).expanduser().resolve()
    return default_state_dir()
