"""
Built-in addons shipped with autoheal.

Enable them via config:
  "addons": {
    "modules": ["autoheal.addons_builtin.git_pager"],
    "module_config": {"autoheal.addons_builtin.git_pager": {"enabled": true}}
  }

Performance addon (opt-in) can detect load/memory pressure and optionally
renice allowlisted processes:
  "addons": {
    "modules": ["autoheal.addons_builtin.performance"],
    "module_config": {"autoheal.addons_builtin.performance": {"enabled": true}}
  }
"""
