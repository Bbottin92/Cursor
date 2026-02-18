"""Fix engine.

Executes remediation actions based on diagnosis results.
Each fix type maps to a handler that runs specific system commands.
All actions are logged, timed, and recorded for rollback capability.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import Optional

from persistence.context_store import ContextStore
from persistence.models import Event, Diagnosis, Fix, FixResult, EventState
from config.settings import Settings

logger = logging.getLogger("self-healing.fix")


class FixEngine:
    """Executes fix actions and tracks results."""

    def __init__(self, settings: Settings, store: ContextStore):
        self.settings = settings
        self.store = store

    def execute_fixes(self, event: Event, diagnosis: Diagnosis) -> list[Fix]:
        """Execute suggested fixes in priority order."""
        if not self.settings.auto_fix_enabled:
            logger.info(f"Auto-fix disabled, skipping fixes for event {event.id}")
            return []

        self.store.update_event_state(event.id, EventState.FIXING.value)
        fixes = []

        suggested = sorted(diagnosis.suggested_fixes, key=lambda x: x.get("priority", 99))

        for suggestion in suggested:
            fix_type = suggestion.get("type", "")
            if not fix_type:
                continue

            logger.info(f"Attempting fix '{fix_type}' for event {event.id}")
            fix = self._execute_single_fix(event, diagnosis, suggestion)
            fixes.append(fix)

            if fix.result == FixResult.SUCCESS.value:
                self.store.update_event_state(event.id, EventState.MONITORING.value)
                logger.info(f"Fix '{fix_type}' succeeded for event {event.id}")
                break
            elif fix.result == FixResult.NEEDS_REBOOT.value:
                self._handle_reboot_needed(event, fix)
                break
            else:
                logger.warning(f"Fix '{fix_type}' failed for event {event.id}")

        if all(f.result == FixResult.FAILED.value for f in fixes) and fixes:
            retry_count = self.store.increment_retry(event.id)
            evt = self.store.get_event(event.id)
            if evt and retry_count >= evt.max_retries:
                self.store.update_event_state(event.id, EventState.ESCALATED.value)
                self._escalate(event, diagnosis, fixes)
            else:
                self.store.update_event_state(event.id, EventState.DETECTED.value)

        return fixes

    def _execute_single_fix(self, event: Event, diagnosis: Diagnosis, suggestion: dict) -> Fix:
        """Execute a single fix action."""
        fix_type = suggestion["type"]
        start = time.time()
        commands_run = []
        output_parts = []
        result = FixResult.FAILED.value
        rollback_info = {}

        handler = getattr(self, f"_fix_{fix_type}", None)
        if handler is None:
            logger.warning(f"No handler for fix type: {fix_type}")
            fix = Fix(
                event_id=event.id,
                diagnosis_id=diagnosis.id,
                fix_type=fix_type,
                description=f"No handler for fix type: {fix_type}",
                result=FixResult.FAILED.value,
                duration_seconds=0.0,
            )
            self.store.store_fix(fix)
            return fix

        try:
            result, output_parts, commands_run, rollback_info = handler(event, suggestion)
        except Exception as e:
            logger.error(f"Fix handler {fix_type} raised exception: {e}", exc_info=True)
            output_parts.append(f"Exception: {e}")
            result = FixResult.FAILED.value

        duration = time.time() - start
        fix = Fix(
            event_id=event.id,
            diagnosis_id=diagnosis.id,
            fix_type=fix_type,
            description=f"Executed fix: {fix_type}",
            commands_run=commands_run,
            result=result,
            output="\n".join(output_parts),
            rollback_info=rollback_info,
            duration_seconds=round(duration, 3),
        )
        self.store.store_fix(fix)
        return fix

    def _run_cmd(self, cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
        """Run a system command and return (returncode, stdout, stderr)."""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)

    def _handle_reboot_needed(self, event: Event, fix: Fix):
        """Handle the case where a reboot is needed."""
        logger.warning(f"Reboot needed for event {event.id}")
        self.store.set_context("pending_reboot_event", event.id)
        self.store.set_context("reboot_reason", fix.output)
        self.store.queue_cursor_message("reboot_needed", {
            "event_id": event.id,
            "reason": fix.output,
        })

        if self.settings.auto_reboot_enabled:
            logger.critical("Auto-reboot triggered!")
            self.store.set_context("reboot_initiated", time.time())
            self._run_cmd(["shutdown", "-r", "+1", "Self-healing system: auto-reboot for repair"])

    def _escalate(self, event: Event, diagnosis: Diagnosis, fixes: list[Fix]):
        """Escalate an issue that could not be auto-fixed."""
        logger.error(f"Escalating event {event.id} after exhausting retries")
        self.store.queue_cursor_message("escalation", {
            "event_id": event.id,
            "event_summary": event.summary,
            "category": event.category,
            "severity": event.severity,
            "diagnosis": diagnosis.root_cause,
            "attempted_fixes": [f.fix_type for f in fixes],
            "fix_results": [f.result for f in fixes],
        })

    # =========================================================================
    # Fix handlers: each returns (result, output_parts, commands_run, rollback)
    # =========================================================================

    def _fix_service_restart(self, event, suggestion):
        svc = suggestion.get("service", event.details.get("service_name", ""))
        if not svc:
            return FixResult.FAILED.value, ["No service name"], [], {}

        svc_clean = svc.replace(".service", "")
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(["systemctl", "restart", svc_clean])
        cmds.append({"cmd": f"systemctl restart {svc_clean}", "rc": rc})
        outputs.append(f"restart: rc={rc}, out={out.strip()}, err={err.strip()}")

        time.sleep(2)
        rc2, out2, _ = self._run_cmd(["systemctl", "is-active", svc_clean])
        cmds.append({"cmd": f"systemctl is-active {svc_clean}", "rc": rc2})

        if out2.strip() == "active":
            return FixResult.SUCCESS.value, outputs + [f"{svc_clean} is now active"], cmds, {}
        return FixResult.FAILED.value, outputs + [f"{svc_clean} still not active"], cmds, {}

    def _fix_service_reset_failed(self, event, suggestion):
        svc = suggestion.get("service", event.details.get("service_name", ""))
        if not svc:
            return FixResult.FAILED.value, ["No service name"], [], {}

        svc_clean = svc.replace(".service", "")
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(["systemctl", "reset-failed", svc_clean])
        cmds.append({"cmd": f"systemctl reset-failed {svc_clean}", "rc": rc})
        outputs.append(f"reset-failed: rc={rc}")

        rc, out, err = self._run_cmd(["systemctl", "start", svc_clean])
        cmds.append({"cmd": f"systemctl start {svc_clean}", "rc": rc})
        outputs.append(f"start: rc={rc}, err={err.strip()}")

        time.sleep(2)
        rc2, out2, _ = self._run_cmd(["systemctl", "is-active", svc_clean])
        if out2.strip() == "active":
            return FixResult.SUCCESS.value, outputs, cmds, {}
        return FixResult.FAILED.value, outputs, cmds, {}

    def _fix_service_check_deps(self, event, suggestion):
        svc = suggestion.get("service", event.details.get("service_name", ""))
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(["systemctl", "list-dependencies", svc, "--plain"])
        cmds.append({"cmd": f"systemctl list-dependencies {svc}", "rc": rc})
        outputs.append(f"Dependencies:\n{out[:2000]}")
        return FixResult.PARTIAL.value, outputs, cmds, {}

    def _fix_clear_caches(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(["sync"])
        cmds.append({"cmd": "sync", "rc": rc})

        try:
            with open("/proc/sys/vm/drop_caches", "w") as f:
                f.write("3\n")
            cmds.append({"cmd": "echo 3 > /proc/sys/vm/drop_caches", "rc": 0})
            outputs.append("Caches cleared")
            return FixResult.SUCCESS.value, outputs, cmds, {}
        except (OSError, PermissionError) as e:
            rc, out, err = self._run_cmd(["bash", "-c", "echo 3 > /proc/sys/vm/drop_caches"])
            cmds.append({"cmd": "echo 3 > /proc/sys/vm/drop_caches", "rc": rc})
            if rc == 0:
                return FixResult.SUCCESS.value, ["Caches cleared via bash"], cmds, {}
            return FixResult.FAILED.value, [f"Failed to clear caches: {e}"], cmds, {}

    def _fix_kill_top_memory_process(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(["ps", "-eo", "pid,pmem,comm", "--sort=-pmem"])
        cmds.append({"cmd": "ps -eo pid,pmem,comm --sort=-pmem", "rc": rc})

        protected = {"init", "systemd", "sshd", "self-healing", "python3", "bash"}
        lines = out.strip().split("\n")[1:]
        for line in lines:
            parts = line.split(None, 2)
            if len(parts) >= 3:
                pid = parts[0]
                comm = parts[2].strip()
                if comm not in protected and pid != "1":
                    rc, out2, err2 = self._run_cmd(["kill", "-15", pid])
                    cmds.append({"cmd": f"kill -15 {pid} ({comm})", "rc": rc})
                    outputs.append(f"Sent SIGTERM to PID {pid} ({comm})")
                    return FixResult.SUCCESS.value, outputs, cmds, {"killed_pid": pid, "process": comm}

        return FixResult.FAILED.value, ["No suitable process to kill"], cmds, {}

    def _fix_clean_tmp(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(
            ["find", "/tmp", "-type", "f", "-atime", "+7", "-delete"],
            timeout=60,
        )
        cmds.append({"cmd": "find /tmp -type f -atime +7 -delete", "rc": rc})
        outputs.append(f"Cleaned old /tmp files: rc={rc}")

        rc, out, err = self._run_cmd(
            ["find", "/var/tmp", "-type", "f", "-atime", "+7", "-delete"],
            timeout=60,
        )
        cmds.append({"cmd": "find /var/tmp -type f -atime +7 -delete", "rc": rc})
        outputs.append(f"Cleaned old /var/tmp files: rc={rc}")

        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_clean_journal(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(
            ["journalctl", "--vacuum-time=3d", "--vacuum-size=100M"],
            timeout=30,
        )
        cmds.append({"cmd": "journalctl --vacuum-time=3d --vacuum-size=100M", "rc": rc})
        outputs.append(f"Journal cleanup: {out.strip()[:500]}")
        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_clean_old_kernels(self, event, suggestion):
        cmds = []
        outputs = []

        if shutil.which("apt"):
            rc, out, err = self._run_cmd(
                ["apt-get", "autoremove", "-y", "--purge"],
                timeout=120,
            )
            cmds.append({"cmd": "apt-get autoremove -y --purge", "rc": rc})
            outputs.append(f"apt autoremove: rc={rc}")
        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_clean_package_cache(self, event, suggestion):
        cmds = []
        outputs = []

        if shutil.which("apt"):
            rc, out, err = self._run_cmd(["apt-get", "clean"], timeout=30)
            cmds.append({"cmd": "apt-get clean", "rc": rc})
            outputs.append(f"apt-get clean: rc={rc}")

        if shutil.which("pip"):
            rc, out, err = self._run_cmd(["pip", "cache", "purge"], timeout=30)
            cmds.append({"cmd": "pip cache purge", "rc": rc})

        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_emergency_disk_cleanup(self, event, suggestion):
        cmds = []
        outputs = []

        # Aggressively free space
        targets = [
            ("/tmp", ["-type", "f", "-delete"]),
            ("/var/tmp", ["-type", "f", "-atime", "+1", "-delete"]),
            ("/var/log", ["-name", "*.gz", "-delete"]),
            ("/var/log", ["-name", "*.1", "-delete"]),
            ("/var/log", ["-name", "*.old", "-delete"]),
        ]

        for path, args in targets:
            if os.path.exists(path):
                cmd = ["find", path] + args
                rc, out, err = self._run_cmd(cmd, timeout=30)
                cmds.append({"cmd": " ".join(cmd), "rc": rc})

        # Truncate large log files
        log_targets = ["/var/log/syslog", "/var/log/kern.log", "/var/log/auth.log"]
        for log_file in log_targets:
            if os.path.exists(log_file):
                try:
                    size = os.path.getsize(log_file)
                    if size > 100 * 1024 * 1024:  # > 100MB
                        with open(log_file, "w") as f:
                            f.write("")
                        cmds.append({"cmd": f"truncate {log_file}", "rc": 0})
                        outputs.append(f"Truncated {log_file} (was {size} bytes)")
                except Exception:
                    pass

        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_restart_networking(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(["systemctl", "restart", "systemd-networkd"])
        cmds.append({"cmd": "systemctl restart systemd-networkd", "rc": rc})
        outputs.append(f"Restarted systemd-networkd: rc={rc}")

        if shutil.which("nmcli"):
            rc, out, err = self._run_cmd(["systemctl", "restart", "NetworkManager"])
            cmds.append({"cmd": "systemctl restart NetworkManager", "rc": rc})
            outputs.append(f"Restarted NetworkManager: rc={rc}")

        time.sleep(5)
        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_restart_network_manager(self, event, suggestion):
        cmds = []
        outputs = []

        for svc in ["NetworkManager", "systemd-networkd", "networking"]:
            rc, _, _ = self._run_cmd(["systemctl", "restart", svc])
            cmds.append({"cmd": f"systemctl restart {svc}", "rc": rc})
            if rc == 0:
                outputs.append(f"Restarted {svc}")
                break

        time.sleep(5)
        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_dhcp_renew(self, event, suggestion):
        cmds = []
        outputs = []

        if shutil.which("dhclient"):
            rc, out, err = self._run_cmd(["dhclient", "-r"])
            cmds.append({"cmd": "dhclient -r", "rc": rc})
            time.sleep(1)
            rc, out, err = self._run_cmd(["dhclient"])
            cmds.append({"cmd": "dhclient", "rc": rc})
        elif shutil.which("dhcpcd"):
            rc, out, err = self._run_cmd(["dhcpcd", "-n"])
            cmds.append({"cmd": "dhcpcd -n", "rc": rc})

        time.sleep(3)
        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_flush_dns(self, event, suggestion):
        cmds = []
        outputs = []

        if shutil.which("resolvectl"):
            rc, out, err = self._run_cmd(["resolvectl", "flush-caches"])
            cmds.append({"cmd": "resolvectl flush-caches", "rc": rc})
            outputs.append(f"DNS cache flushed: rc={rc}")
        elif shutil.which("systemd-resolve"):
            rc, out, err = self._run_cmd(["systemd-resolve", "--flush-caches"])
            cmds.append({"cmd": "systemd-resolve --flush-caches", "rc": rc})

        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_restart_resolved(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(["systemctl", "restart", "systemd-resolved"])
        cmds.append({"cmd": "systemctl restart systemd-resolved", "rc": rc})
        outputs.append(f"Restarted systemd-resolved: rc={rc}")

        time.sleep(2)
        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_set_fallback_dns(self, event, suggestion):
        cmds = []
        outputs = []
        rollback = {}

        resolv_path = "/etc/resolv.conf"
        try:
            if os.path.exists(resolv_path):
                with open(resolv_path, "r") as f:
                    rollback["original_resolv"] = f.read()

            with open(resolv_path, "w") as f:
                f.write("nameserver 8.8.8.8\nnameserver 1.1.1.1\nnameserver 8.8.4.4\n")
            cmds.append({"cmd": "write /etc/resolv.conf", "rc": 0})
            outputs.append("Set fallback DNS servers (8.8.8.8, 1.1.1.1)")
            return FixResult.SUCCESS.value, outputs, cmds, rollback
        except Exception as e:
            return FixResult.FAILED.value, [f"Failed: {e}"], cmds, {}

    def _fix_check_firewall(self, event, suggestion):
        cmds = []
        outputs = []

        if shutil.which("ufw"):
            rc, out, err = self._run_cmd(["ufw", "status"])
            cmds.append({"cmd": "ufw status", "rc": rc})
            outputs.append(f"UFW status:\n{out[:500]}")
        elif shutil.which("iptables"):
            rc, out, err = self._run_cmd(["iptables", "-L", "-n"])
            cmds.append({"cmd": "iptables -L -n", "rc": rc})
            outputs.append(f"iptables:\n{out[:500]}")

        return FixResult.PARTIAL.value, outputs, cmds, {}

    def _fix_remount_rw(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(["mount", "-o", "remount,rw", "/"])
        cmds.append({"cmd": "mount -o remount,rw /", "rc": rc})
        if rc == 0:
            outputs.append("Root filesystem remounted read-write")
            return FixResult.SUCCESS.value, outputs, cmds, {}
        outputs.append(f"Failed to remount: {err.strip()}")
        return FixResult.NEEDS_REBOOT.value, outputs + ["Reboot may be required for fsck"], cmds, {}

    def _fix_fsck_schedule(self, event, suggestion):
        cmds = []
        outputs = []

        try:
            with open("/forcefsck", "w") as f:
                f.write("")
            cmds.append({"cmd": "touch /forcefsck", "rc": 0})
            outputs.append("Scheduled fsck on next boot")
            return FixResult.NEEDS_REBOOT.value, outputs, cmds, {}
        except Exception as e:
            return FixResult.FAILED.value, [f"Failed: {e}"], cmds, {}

    def _fix_kill_zombie_parents(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(
            ["ps", "-eo", "pid,ppid,stat,comm"],
        )
        cmds.append({"cmd": "ps -eo pid,ppid,stat,comm", "rc": rc})

        parent_pids = set()
        for line in out.strip().split("\n")[1:]:
            parts = line.split(None, 3)
            if len(parts) >= 3 and "Z" in parts[2]:
                ppid = parts[1]
                if ppid != "1":
                    parent_pids.add(ppid)

        for ppid in list(parent_pids)[:5]:
            rc, _, _ = self._run_cmd(["kill", "-SIGCHLD", ppid])
            cmds.append({"cmd": f"kill -SIGCHLD {ppid}", "rc": rc})
            outputs.append(f"Sent SIGCHLD to parent PID {ppid}")

        return FixResult.SUCCESS.value if parent_pids else FixResult.PARTIAL.value, outputs, cmds, {}

    def _fix_nice_cpu_hogs(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(["ps", "-eo", "pid,pcpu,nice,comm", "--sort=-pcpu"])
        cmds.append({"cmd": "ps -eo pid,pcpu,nice,comm --sort=-pcpu", "rc": rc})

        protected = {"init", "systemd", "sshd", "self-healing", "python3"}
        lines = out.strip().split("\n")[1:5]
        for line in lines:
            parts = line.split(None, 3)
            if len(parts) >= 4:
                pid = parts[0]
                comm = parts[3].strip()
                if comm not in protected and float(parts[1]) > 80:
                    rc, _, _ = self._run_cmd(["renice", "19", "-p", pid])
                    cmds.append({"cmd": f"renice 19 -p {pid} ({comm})", "rc": rc})
                    outputs.append(f"Reniced PID {pid} ({comm}) to 19")

        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_identify_cpu_hogs(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(["ps", "-eo", "pid,pcpu,pmem,etime,comm", "--sort=-pcpu"])
        cmds.append({"cmd": "ps -eo pid,pcpu,pmem,etime,comm --sort=-pcpu", "rc": rc})
        outputs.append(f"Top processes:\n{out[:2000]}")
        return FixResult.PARTIAL.value, outputs, cmds, {}

    def _fix_identify_load_sources(self, event, suggestion):
        return self._fix_identify_cpu_hogs(event, suggestion)

    def _fix_identify_fd_hogs(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(
            ["bash", "-c", "for pid in /proc/[0-9]*; do echo \"$(ls $pid/fd 2>/dev/null | wc -l) $pid $(cat $pid/comm 2>/dev/null)\"; done | sort -rn | head -20"],
            timeout=15,
        )
        cmds.append({"cmd": "identify fd hogs", "rc": rc})
        outputs.append(f"Top FD consumers:\n{out[:2000]}")
        return FixResult.PARTIAL.value, outputs, cmds, {}

    def _fix_clean_small_files(self, event, suggestion):
        cmds = []
        outputs = []

        targets = ["/tmp", "/var/tmp", "/var/cache"]
        for d in targets:
            if os.path.exists(d):
                rc, out, err = self._run_cmd(
                    ["find", d, "-type", "f", "-size", "0", "-delete"],
                    timeout=30,
                )
                cmds.append({"cmd": f"find {d} -type f -size 0 -delete", "rc": rc})

        return FixResult.SUCCESS.value, outputs, cmds, {}

    def _fix_find_inode_hogs(self, event, suggestion):
        cmds = []
        outputs = []

        rc, out, err = self._run_cmd(
            ["bash", "-c", "find / -xdev -printf '%h\\n' 2>/dev/null | sort | uniq -c | sort -rn | head -20"],
            timeout=60,
        )
        cmds.append({"cmd": "find inode-heavy directories", "rc": rc})
        outputs.append(f"Directories with most files:\n{out[:2000]}")
        return FixResult.PARTIAL.value, outputs, cmds, {}

    def _fix_lazy_umount(self, event, suggestion):
        mountpoint = suggestion.get("mountpoint", "")
        cmds = []
        outputs = []

        if not mountpoint:
            return FixResult.FAILED.value, ["No mountpoint specified"], [], {}

        rc, out, err = self._run_cmd(["umount", "-l", mountpoint])
        cmds.append({"cmd": f"umount -l {mountpoint}", "rc": rc})
        if rc == 0:
            outputs.append(f"Lazy unmounted {mountpoint}")
            return FixResult.SUCCESS.value, outputs, cmds, {"mountpoint": mountpoint}
        return FixResult.FAILED.value, [f"Failed: {err.strip()}"], cmds, {}

    def _fix_log_crash_details(self, event, suggestion):
        return self._fix_log_details(event, suggestion)

    def _fix_log_kernel_details(self, event, suggestion):
        return self._fix_log_details(event, suggestion)

    def _fix_log_hardware_details(self, event, suggestion):
        return self._fix_log_details(event, suggestion)

    def _fix_log_details(self, event, suggestion):
        logger.info(f"Event details logged: {event.summary} - {event.details}")
        self.store.queue_cursor_message("event_detail_log", {
            "event_id": event.id,
            "summary": event.summary,
            "category": event.category,
            "severity": event.severity,
            "details": event.details,
        })
        return FixResult.PARTIAL.value, [f"Details logged for: {event.summary}"], [], {}
