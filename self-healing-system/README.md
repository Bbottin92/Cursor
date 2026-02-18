# Self-Healing System

A fully autonomous system daemon that detects errors, diagnoses root causes, and applies fixes automatically -- without requiring any user input. It survives reboots, runs before user login, maintains persistent context across restarts, and exposes an API for Cursor to manage and direct its behavior.

## Architecture

```
                    +---------------------+
                    |      Cursor IDE     |
                    |  (API Client/Agent) |
                    +--------+------------+
                             |
                    HTTP API (localhost:7847)
                             |
+----------------------------+----------------------------+
|                 Self-Healing Daemon                      |
|                                                         |
|  +-------------------+  +-------------------+           |
|  | Detection Modules |  | Diagnosis Engine  |           |
|  |   - Log Monitor   |  |  - Rule-based     |           |
|  |   - Service Mon.  |  |  - Context-aware  |           |
|  |   - Resource Mon. |  |  - History-aware  |           |
|  |   - Network Mon.  |  +--------+----------+           |
|  |   - Process Mon.  |           |                      |
|  |   - Filesystem    |  +--------v----------+           |
|  +--------+----------+  |   Fix Engine      |           |
|           |              |  - Service restart|           |
|           v              |  - Cache clearing |           |
|  +-------------------+  |  - Disk cleanup   |           |
|  | Persistent Context|  |  - Network repair |           |
|  |  (SQLite + WAL)   |  |  - DNS fixes      |           |
|  |  - Events         |  |  - Process mgmt   |           |
|  |  - Diagnoses      |  |  - FS repair      |           |
|  |  - Fixes          |  +-------------------+           |
|  |  - Snapshots      |                                  |
|  |  - Key-Value      |  +-------------------+           |
|  |  - Messages       |  |   Watchdog        |           |
|  +-------------------+  |  - Heartbeat mon. |           |
|                         |  - Auto-restart   |           |
|                         |  - PID tracking   |           |
+-------------------------+-------------------+-----------+
                          |
                    systemd services
              (runs before user login)
```

## Features

### Autonomous Error Handling
- **Detection**: Monitors system logs, services, resources, network, processes, and filesystems
- **Diagnosis**: Rule-based analysis with confidence scoring, historical context, and pattern correlation
- **Fixing**: 25+ automated fix handlers for common system issues
- **Escalation**: Issues that can't be auto-fixed are escalated to Cursor with full context

### Persistent Context
- SQLite database with WAL mode for crash-safe writes
- Survives reboots and power failures
- Tracks: events, diagnoses, fixes, system snapshots, arbitrary key-value context
- Historical awareness: knows what was tried before and what worked

### Auto-Start (Pre-Login)
- Three systemd services:
  - `self-healing-boot`: Runs at early boot (before sysinit) for post-reboot recovery
  - `self-healing-daemon`: Main daemon, starts before multi-user.target
  - `self-healing-watchdog`: Monitors the daemon and restarts it if needed
- No user password required -- runs as system service
- Automatic restart on crash (systemd + watchdog double-layer)

### Cursor Communication
- REST API on `localhost:7847`
- Full CRUD for events, diagnoses, fixes, snapshots, context
- Directive system for Cursor to guide daemon behavior
- Command execution endpoint for remote system management
- Message queue (inbound/outbound) for async communication
- Python client library for easy integration

### Self-Healing of the Healer
- Watchdog process monitors daemon via:
  - PID file validity
  - Heartbeat freshness in database
  - HTTP health endpoint
- Three consecutive failures trigger automatic daemon restart
- systemd watches both daemon and watchdog with auto-restart
- Boot recovery service handles post-reboot cleanup

## Quick Start

### Install
```bash
sudo bash self-healing-system/scripts/setup.sh
```

### Or manual install
```bash
sudo python3 self-healing-system/main.py --mode install
```

### Check Status
```bash
# Via systemd
systemctl status self-healing-daemon
systemctl status self-healing-watchdog

# Via API
curl http://localhost:7847/api/health
curl http://localhost:7847/api/status

# Via CLI
python3 /opt/self-healing-system/main.py --mode status
```

## API Reference

### GET Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/health` | Basic health check |
| `/api/status` | Full status with stats, snapshot, active events |
| `/api/events` | Recent events (`?hours=24&limit=100`) |
| `/api/events/active` | Currently active events |
| `/api/events/{id}` | Event detail with diagnoses and fixes |
| `/api/statistics` | Event and fix statistics |
| `/api/context` | All persistent context (`?key=specific_key`) |
| `/api/snapshots` | System snapshots (`?hours=1`) |
| `/api/messages` | Pending messages (`?direction=outbound`) |
| `/api/config` | Current configuration |

### POST Endpoints

| Endpoint | Body | Description |
|----------|------|-------------|
| `/api/scan` | `{}` | Trigger immediate scan |
| `/api/fix` | `{"event_id": "..."}` | Trigger fix for event |
| `/api/command` | `{"command": "..."}` | Run shell command |
| `/api/message` | `{"type": "...", "payload": {...}}` | Send message to daemon |
| `/api/context` | `{"key": "...", "value": ...}` | Set context value |
| `/api/config` | `{"key": value, ...}` | Update config |
| `/api/directive` | `{"directive": "...", "payload": {...}}` | Send directive |

### Directives

| Directive | Payload | Description |
|-----------|---------|-------------|
| `monitor_service` | `{"service": "nginx"}` | Add service to monitoring |
| `ignore_category` | `{"category": "network"}` | Ignore event category |
| `unignore_category` | `{"category": "network"}` | Stop ignoring category |
| `enable_auto_fix` | `{}` | Enable automatic fixes |
| `disable_auto_fix` | `{}` | Disable automatic fixes |
| `authorize_reboot` | `{}` | Allow auto-reboot |
| `schedule_reboot` | `{"delay_minutes": 5}` | Schedule reboot |
| `cancel_reboot` | `{}` | Cancel scheduled reboot |
| `add_error_pattern` | `{"pattern": "...", "severity": "error", "category": "custom"}` | Add log pattern |
| `set_threshold` | `{"key": "cpu_threshold", "value": 95.0}` | Update threshold |

## Using from Cursor

```python
from api.cursor_client import SelfHealingClient

client = SelfHealingClient()

# Check if the system is healthy
health = client.health()

# Get active issues
events = client.active_events()

# Tell the daemon to monitor a new service
client.monitor_service("nginx")

# Send an instruction
client.send_instruction("Prioritize disk space monitoring")

# Run a diagnostic command
result = client.run_command("df -h")

# Trigger a manual scan
client.trigger_scan()

# Get full event details
detail = client.event_detail("event-uuid-here")

# Adjust thresholds
client.set_threshold("cpu_threshold", 95.0)
```

## Monitored Issues

| Category | What's Detected | Auto-Fix |
|----------|----------------|----------|
| Service failures | Failed/inactive systemd services | Restart, reset-failed, dependency check |
| High CPU | CPU usage above threshold | Identify hogs, renice |
| High memory | Memory usage above threshold | Clear caches, kill top consumer |
| High disk | Disk usage above threshold | Clean tmp/journal/cache, emergency cleanup |
| High load | Load average above threshold | Identify sources |
| Network down | No internet connectivity | Restart networking, DHCP renew |
| DNS failure | DNS resolution failing | Flush cache, restart resolved, set fallback DNS |
| Zombies | Excessive zombie processes | Signal parent processes |
| Runaways | Processes at >95% CPU | Renice to lowest priority |
| OOM risk | High OOM score processes | Clear caches |
| Read-only FS | Root filesystem read-only | Remount rw, schedule fsck |
| Inode exhaustion | >90% inode usage | Clean empty files, find hogs |
| Stale mounts | Unresponsive NFS/FUSE mounts | Lazy unmount |
| Log patterns | OOM, segfault, kernel panic, I/O errors, etc. | Category-specific fixes |

## Configuration

Configuration lives at `/etc/self-healing/config.json`. Generate defaults with:

```bash
python3 /opt/self-healing-system/main.py --mode config
```

Key settings:
- `auto_fix_enabled`: Enable/disable automatic fixes (default: true)
- `auto_reboot_enabled`: Allow automatic reboots (default: false)
- `scan_interval`: Seconds between scans (default: 30)
- `cpu_threshold`, `memory_threshold`, `disk_threshold`: Alert thresholds
- `monitored_services`: List of services to watch
- `monitored_logs`: List of log files to monitor
- `error_patterns`: Regex patterns to match in logs
- `api_port`: API listen port (default: 7847)
- `api_token`: Optional bearer token for API auth

## File Layout

```
/opt/self-healing-system/       # Application code
/etc/self-healing/config.json   # Configuration
/var/lib/self-healing/context.db # Persistent database
/var/log/self-healing/          # Log files
/var/run/self-healing/          # PID file, socket
```

## How It Stays Alive

The system uses three layers of resilience:

1. **systemd** watches both the daemon and watchdog processes. If either crashes, systemd restarts it within 5-10 seconds. `StartLimitBurst` prevents restart storms.

2. **Watchdog process** independently monitors the daemon via three health checks (PID alive, heartbeat freshness, API responsive). Three consecutive failures trigger a restart.

3. **Boot recovery service** runs at early boot to handle post-reboot cleanup, validate filesystem health, and ensure the daemon can start cleanly.

Even in edge cases like:
- Daemon process hangs (watchdog catches via stale heartbeat)
- Daemon crashes repeatedly (systemd rate-limits restarts)
- System reboots unexpectedly (boot recovery + context persistence)
- Database corruption (WAL mode + crash recovery)
- Network outage (continues operating locally, queues Cursor messages)
- Disk full (emergency cleanup runs before other fixes)
