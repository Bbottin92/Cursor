"""Diagnosis engine.

Analyzes detected events, correlates with system state and historical context,
and produces a diagnosis with suggested fixes. Uses rule-based analysis
with pattern matching against known issues.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from persistence.context_store import ContextStore
from persistence.models import Event, Diagnosis, EventState, Severity
from config.settings import Settings

logger = logging.getLogger("self-healing.diagnosis")


class DiagnosisEngine:
    """Analyzes events and produces diagnoses with fix suggestions."""

    def __init__(self, settings: Settings, store: ContextStore):
        self.settings = settings
        self.store = store

    def diagnose(self, event: Event) -> Diagnosis:
        """Diagnose an event and return fix suggestions."""
        self.store.update_event_state(event.id, EventState.DIAGNOSING.value)
        logger.info(f"Diagnosing event {event.id}: {event.summary}")

        # Gather context
        context = self._gather_context(event)

        # Run diagnosis rules
        root_cause, confidence, suggested_fixes, analysis = self._analyze(event, context)

        diagnosis = Diagnosis(
            event_id=event.id,
            root_cause=root_cause,
            confidence=confidence,
            suggested_fixes=suggested_fixes,
            analysis=analysis,
            context_used=context,
        )

        self.store.store_diagnosis(diagnosis)
        self.store.update_event_state(event.id, EventState.DIAGNOSED.value)
        logger.info(
            f"Diagnosed event {event.id}: root_cause={root_cause}, "
            f"confidence={confidence}, fixes={len(suggested_fixes)}"
        )
        return diagnosis

    def _gather_context(self, event: Event) -> dict:
        """Gather relevant context for diagnosis."""
        context = {}

        # Recent similar events
        similar = self.store.find_similar_events(event.category, event.source, hours=48)
        context["similar_event_count"] = len(similar)
        context["recurrence_pattern"] = self._detect_recurrence(similar)

        # Latest system snapshot
        snap = self.store.get_latest_snapshot()
        if snap:
            context["system_state"] = {
                "cpu": snap.cpu_percent,
                "memory": snap.memory_percent,
                "disk": snap.disk_percent,
                "load": snap.load_average,
            }

        # Previous fix attempts for same category
        recent_events = self.store.get_recent_events(hours=24)
        related_fixes = []
        for e in recent_events:
            if e.category == event.category:
                fixes = self.store.get_fixes_for_event(e.id)
                related_fixes.extend(fixes)
        context["previous_fixes"] = len(related_fixes)
        context["previous_fix_success_rate"] = (
            sum(1 for f in related_fixes if f.result == "success") / len(related_fixes)
            if related_fixes else 0.0
        )

        # Network status
        net_status = self.store.get_context("network_status", {})
        context["network"] = net_status

        return context

    def _detect_recurrence(self, similar_events: list[Event]) -> str:
        """Detect if an issue is recurring."""
        if len(similar_events) == 0:
            return "new"
        elif len(similar_events) <= 2:
            return "occasional"
        elif len(similar_events) <= 5:
            return "recurring"
        else:
            return "chronic"

    def _analyze(self, event: Event, context: dict) -> tuple[str, float, list[dict], dict]:
        """Run rule-based analysis on an event."""
        category = event.category
        details = event.details

        handlers = {
            "service": self._analyze_service,
            "memory": self._analyze_memory,
            "disk": self._analyze_disk,
            "cpu": self._analyze_cpu,
            "load": self._analyze_load,
            "network": self._analyze_network,
            "dns": self._analyze_dns,
            "crash": self._analyze_crash,
            "kernel": self._analyze_kernel,
            "filesystem": self._analyze_filesystem,
            "inode": self._analyze_inode,
            "mount": self._analyze_mount,
            "zombie": self._analyze_zombie,
            "runaway": self._analyze_runaway,
            "oom_risk": self._analyze_oom_risk,
            "filedescriptor": self._analyze_fd,
            "hardware": self._analyze_hardware,
        }

        handler = handlers.get(category, self._analyze_generic)
        return handler(event, context)

    def _analyze_service(self, event, context):
        details = event.details
        svc = details.get("service_name", details.get("unit_name", "unknown"))
        recurrence = context.get("recurrence_pattern", "new")

        if recurrence == "chronic":
            return (
                f"Service {svc} is chronically failing - likely configuration or dependency issue",
                0.7,
                [
                    {"type": "service_restart", "service": svc, "priority": 1},
                    {"type": "service_reset_failed", "service": svc, "priority": 2},
                    {"type": "service_check_deps", "service": svc, "priority": 3},
                ],
                {"recurrence": recurrence, "service": svc},
            )
        return (
            f"Service {svc} has failed or stopped",
            0.85,
            [
                {"type": "service_restart", "service": svc, "priority": 1},
                {"type": "service_reset_failed", "service": svc, "priority": 2},
            ],
            {"service": svc},
        )

    def _analyze_memory(self, event, context):
        mem_pct = event.details.get("memory", {}).get("percent", 0)
        fixes = [{"type": "clear_caches", "priority": 1}]
        if mem_pct > 95:
            fixes.append({"type": "kill_top_memory_process", "priority": 2})
        return (
            f"System memory critically high at {mem_pct}%",
            0.9,
            fixes,
            {"memory_percent": mem_pct},
        )

    def _analyze_disk(self, event, context):
        disk_pct = event.details.get("disk", {}).get("percent", 0)
        fixes = [
            {"type": "clean_tmp", "priority": 1},
            {"type": "clean_journal", "priority": 2},
            {"type": "clean_old_kernels", "priority": 3},
            {"type": "clean_package_cache", "priority": 4},
        ]
        if disk_pct > 98:
            fixes.insert(0, {"type": "emergency_disk_cleanup", "priority": 0})
        return (
            f"Disk usage critically high at {disk_pct}%",
            0.95,
            fixes,
            {"disk_percent": disk_pct},
        )

    def _analyze_cpu(self, event, context):
        cpu_pct = event.details.get("cpu_percent", 0)
        return (
            f"High CPU usage at {cpu_pct}%",
            0.7,
            [
                {"type": "identify_cpu_hogs", "priority": 1},
                {"type": "nice_cpu_hogs", "priority": 2},
            ],
            {"cpu_percent": cpu_pct},
        )

    def _analyze_load(self, event, context):
        load = event.details.get("load", [0, 0, 0])
        return (
            f"System load average is very high: {load}",
            0.7,
            [
                {"type": "identify_load_sources", "priority": 1},
            ],
            {"load": load},
        )

    def _analyze_network(self, event, context):
        gw_ok = event.details.get("gateway_reachable", False)
        if not gw_ok:
            return (
                "Network connectivity lost - gateway unreachable",
                0.9,
                [
                    {"type": "restart_networking", "priority": 1},
                    {"type": "restart_network_manager", "priority": 2},
                    {"type": "dhcp_renew", "priority": 3},
                ],
                {"gateway_reachable": gw_ok},
            )
        return (
            "Internet connectivity lost but gateway is reachable",
            0.8,
            [
                {"type": "flush_dns", "priority": 1},
                {"type": "restart_resolved", "priority": 2},
                {"type": "check_firewall", "priority": 3},
            ],
            {"gateway_reachable": gw_ok},
        )

    def _analyze_dns(self, event, context):
        return (
            "DNS resolution is failing",
            0.85,
            [
                {"type": "flush_dns", "priority": 1},
                {"type": "restart_resolved", "priority": 2},
                {"type": "set_fallback_dns", "priority": 3},
            ],
            {},
        )

    def _analyze_crash(self, event, context):
        return (
            "Process crash (segfault) detected in system logs",
            0.6,
            [{"type": "log_crash_details", "priority": 1}],
            {},
        )

    def _analyze_kernel(self, event, context):
        return (
            "Kernel-level issue detected",
            0.5,
            [{"type": "log_kernel_details", "priority": 1}],
            {},
        )

    def _analyze_filesystem(self, event, context):
        return (
            "Root filesystem is read-only, likely disk error or filesystem corruption",
            0.9,
            [
                {"type": "remount_rw", "priority": 1},
                {"type": "fsck_schedule", "priority": 2},
            ],
            {},
        )

    def _analyze_inode(self, event, context):
        return (
            f"Inode exhaustion on {event.details.get('mountpoint', '/')}",
            0.95,
            [
                {"type": "clean_small_files", "priority": 1},
                {"type": "find_inode_hogs", "priority": 2},
            ],
            {},
        )

    def _analyze_mount(self, event, context):
        return (
            f"Stale mount at {event.details.get('mountpoint', 'unknown')}",
            0.8,
            [{"type": "lazy_umount", "mountpoint": event.details.get("mountpoint"), "priority": 1}],
            {},
        )

    def _analyze_zombie(self, event, context):
        count = event.details.get("count", 0)
        return (
            f"{count} zombie processes detected, parent processes not reaping children",
            0.8,
            [{"type": "kill_zombie_parents", "priority": 1}],
            {"zombie_count": count},
        )

    def _analyze_runaway(self, event, context):
        procs = event.details.get("processes", [])
        return (
            f"{len(procs)} runaway processes consuming excessive CPU",
            0.75,
            [{"type": "nice_cpu_hogs", "priority": 1}],
            {"processes": procs},
        )

    def _analyze_oom_risk(self, event, context):
        procs = event.details.get("processes", [])
        return (
            f"{len(procs)} processes at high risk of OOM killer",
            0.7,
            [{"type": "clear_caches", "priority": 1}],
            {"processes": procs},
        )

    def _analyze_fd(self, event, context):
        fds = event.details.get("open_fds", 0)
        return (
            f"File descriptor count very high: {fds}",
            0.7,
            [{"type": "identify_fd_hogs", "priority": 1}],
            {"open_fds": fds},
        )

    def _analyze_hardware(self, event, context):
        return (
            "Hardware issue detected in system logs",
            0.5,
            [{"type": "log_hardware_details", "priority": 1}],
            {},
        )

    def _analyze_generic(self, event, context):
        return (
            f"Unclassified issue: {event.summary}",
            0.3,
            [{"type": "log_details", "priority": 1}],
            {},
        )
