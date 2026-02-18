from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Finding:
    """
    A normalized, structured "something is wrong" signal.

    fingerprint is used for de-duplication across runs.
    """

    fingerprint: str
    type: str
    severity: int  # 1..5
    title: str
    details: dict[str, Any]
    diagnosis: str


@dataclass(frozen=True)
class ActionPlan:
    """
    A proposed remediation for a Finding/Incident.
    """

    name: str
    description: str
    command: list[str] | None = None
    # If True, agent will only run if configured+permitted.
    requires_root: bool = False
    timeout_seconds: int = 30


@dataclass(frozen=True)
class Recommendation:
    """
    A persistent suggestion for the user/operator.

    key is used for de-duplication across runs.
    """

    key: str
    title: str
    message: str
    priority: int = 3  # 1..5
    confidence: float = 0.5  # 0..1
    details: dict[str, Any] = field(default_factory=dict)
