"""Systemd service monitoring module.

Detects failed or inactive services and generates events.
"""
from __future__ import annotations

import subprocess
from .base import BaseModule
from persistence.models import Event, Severity, EventState


class ServiceMonitorModule(BaseModule):
    name = "service_monitor"

    def _get_service_status(self, service: str) -> dict:
        """Get the status of a systemd service."""
        info = {"name": service, "active": "unknown", "sub": "unknown", "loaded": False}
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True, text=True, timeout=5,
            )
            info["active"] = result.stdout.strip()

            result2 = subprocess.run(
                ["systemctl", "show", service,
                 "--property=LoadState,ActiveState,SubState,MainPID,NRestarts"],
                capture_output=True, text=True, timeout=5,
            )
            if result2.returncode == 0:
                for line in result2.stdout.strip().split("\n"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        info[k.lower()] = v
                info["loaded"] = info.get("loadstate", "") == "loaded"
        except Exception as e:
            self.logger.debug(f"Could not check service {service}: {e}")
        return info

    def _get_all_failed(self) -> list[str]:
        """Get all failed systemd units."""
        try:
            result = subprocess.run(
                ["systemctl", "--failed", "--no-legend", "--plain", "-q"],
                capture_output=True, text=True, timeout=10,
            )
            failed = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.split()
                    if parts:
                        failed.append(parts[0])
            return failed
        except Exception:
            return []

    def scan(self) -> list[Event]:
        events = []

        # Check explicitly monitored services
        for svc in self.settings.monitored_services:
            status = self._get_service_status(svc)
            if status["active"] in ("failed", "inactive", "deactivating"):
                # Check cooldown
                similar = self.store.find_similar_events("service", f"systemd:{svc}", hours=0.15)
                if similar:
                    continue

                severity = Severity.ERROR.value
                if status["active"] == "failed":
                    severity = Severity.CRITICAL.value

                event = Event(
                    source=f"systemd:{svc}",
                    category="service",
                    severity=severity,
                    state=EventState.DETECTED.value,
                    summary=f"Service {svc} is {status['active']}",
                    details={
                        "service_name": svc,
                        "status": status,
                    },
                )
                events.append(event)

        # Check for any failed units system-wide
        failed_units = self._get_all_failed()
        for unit in failed_units:
            unit_base = unit.replace(".service", "")
            if unit_base in self.settings.monitored_services:
                continue  # Already handled above

            similar = self.store.find_similar_events("service", f"systemd:{unit}", hours=0.25)
            if similar:
                continue

            event = Event(
                source=f"systemd:{unit}",
                category="service",
                severity=Severity.ERROR.value,
                state=EventState.DETECTED.value,
                summary=f"System unit {unit} has failed",
                details={"unit_name": unit},
            )
            events.append(event)

        return events
