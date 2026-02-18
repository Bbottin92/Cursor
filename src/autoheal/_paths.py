 from __future__ import annotations
 
 import os
 from pathlib import Path
 
 
 def _expand(p: str | Path) -> Path:
     return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()
 
 
 def default_state_dir() -> Path:
     """
     Prefer /var/lib for root, ~/.local/state for users.
     """
     if hasattr(os, "geteuid") and os.geteuid() == 0:
         return Path("/var/lib/autoheal")
     return _expand("~/.local/state/autoheal")
 
 
 def default_config_path() -> Path:
     if hasattr(os, "geteuid") and os.geteuid() == 0:
         return Path("/etc/autoheal/config.json")
     return _expand("~/.config/autoheal/config.json")
 
 
 def default_log_path(state_dir: Path) -> Path:
     return state_dir / "autoheal.log"
 
 
 def default_db_path(state_dir: Path) -> Path:
     return state_dir / "autoheal.db"
 
 
 def default_lock_path(state_dir: Path) -> Path:
     return state_dir / "agent.lock"
 
 
 def default_control_socket_path(state_dir: Path) -> Path:
     return state_dir / "control.sock"
