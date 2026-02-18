"""Network connectivity monitoring module."""
from __future__ import annotations

import socket
import subprocess
import time

from .base import BaseModule
from persistence.models import Event, Severity, EventState


class NetworkMonitorModule(BaseModule):
    name = "network_monitor"

    CONNECTIVITY_TARGETS = [
        ("8.8.8.8", 53),
        ("1.1.1.1", 53),
    ]

    DNS_TEST_HOSTS = [
        "google.com",
        "cloudflare.com",
    ]

    def _check_tcp_connectivity(self, host: str, port: int, timeout: float = 5.0) -> bool:
        """Check if a TCP connection can be established."""
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            return True
        except (socket.timeout, socket.error, OSError):
            return False

    def _check_dns_resolution(self, hostname: str) -> bool:
        """Check if DNS resolution works."""
        try:
            socket.getaddrinfo(hostname, 80, socket.AF_UNSPEC, socket.SOCK_STREAM)
            return True
        except (socket.gaierror, socket.herror, OSError):
            return False

    def _check_default_gateway(self) -> bool:
        """Check if default gateway is reachable."""
        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return False

            gw = result.stdout.strip().split()[2]
            ping = subprocess.run(
                ["ping", "-c", "1", "-W", "3", gw],
                capture_output=True, text=True, timeout=10,
            )
            return ping.returncode == 0
        except Exception:
            return False

    def _get_network_interfaces(self) -> list[dict]:
        """Get status of network interfaces."""
        interfaces = []
        try:
            result = subprocess.run(
                ["ip", "-j", "link", "show"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                for iface in data:
                    interfaces.append({
                        "name": iface.get("ifname", ""),
                        "state": iface.get("operstate", "unknown"),
                        "flags": iface.get("flags", []),
                    })
        except Exception:
            pass
        return interfaces

    def scan(self) -> list[Event]:
        events = []

        # Check basic connectivity
        connectivity_ok = False
        for host, port in self.CONNECTIVITY_TARGETS:
            if self._check_tcp_connectivity(host, port):
                connectivity_ok = True
                break

        if not connectivity_ok:
            similar = self.store.find_similar_events("network", "network:connectivity", hours=0.1)
            if not similar:
                gw_ok = self._check_default_gateway()
                events.append(Event(
                    source="network:connectivity",
                    category="network",
                    severity=Severity.CRITICAL.value,
                    summary="No internet connectivity detected",
                    details={
                        "gateway_reachable": gw_ok,
                        "interfaces": self._get_network_interfaces(),
                    },
                ))

        # Check DNS
        dns_ok = False
        for host in self.DNS_TEST_HOSTS:
            if self._check_dns_resolution(host):
                dns_ok = True
                break

        if connectivity_ok and not dns_ok:
            similar = self.store.find_similar_events("dns", "network:dns", hours=0.1)
            if not similar:
                events.append(Event(
                    source="network:dns",
                    category="dns",
                    severity=Severity.ERROR.value,
                    summary="DNS resolution failing",
                    details={"tested_hosts": self.DNS_TEST_HOSTS},
                ))

        # Store connectivity status for other modules
        self.store.set_context("network_status", {
            "connectivity": connectivity_ok,
            "dns": dns_ok,
            "gateway": self._check_default_gateway() if not connectivity_ok else True,
            "last_check": time.time(),
        })

        return events
