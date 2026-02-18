"""Data models for persistent context."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventState(str, Enum):
    DETECTED = "detected"
    DIAGNOSING = "diagnosing"
    DIAGNOSED = "diagnosed"
    FIXING = "fixing"
    FIXED = "fixed"
    FAILED = "failed"
    ESCALATED = "escalated"
    MONITORING = "monitoring"


class FixResult(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    NEEDS_REBOOT = "needs_reboot"
    ESCALATED = "escalated"


@dataclass
class Event:
    """Represents a detected system error or anomaly."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    category: str = ""
    severity: str = Severity.ERROR.value
    state: str = EventState.DETECTED.value
    summary: str = ""
    details: dict = field(default_factory=dict)
    related_events: list[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["details"] = json.dumps(d["details"])
        d["related_events"] = json.dumps(d["related_events"])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Event:
        d = dict(d)
        if isinstance(d.get("details"), str):
            d["details"] = json.loads(d["details"])
        if isinstance(d.get("related_events"), str):
            d["related_events"] = json.loads(d["related_events"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Diagnosis:
    """Result of diagnosing an event."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str = ""
    timestamp: float = field(default_factory=time.time)
    root_cause: str = ""
    confidence: float = 0.0
    suggested_fixes: list[dict] = field(default_factory=list)
    analysis: dict = field(default_factory=dict)
    context_used: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["suggested_fixes"] = json.dumps(d["suggested_fixes"])
        d["analysis"] = json.dumps(d["analysis"])
        d["context_used"] = json.dumps(d["context_used"])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Diagnosis:
        d = dict(d)
        for key in ("suggested_fixes", "analysis", "context_used"):
            if isinstance(d.get(key), str):
                d[key] = json.loads(d[key])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Fix:
    """Record of an attempted fix."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str = ""
    diagnosis_id: str = ""
    timestamp: float = field(default_factory=time.time)
    fix_type: str = ""
    description: str = ""
    commands_run: list[dict] = field(default_factory=list)
    result: str = FixResult.SUCCESS.value
    output: str = ""
    rollback_info: dict = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["commands_run"] = json.dumps(d["commands_run"])
        d["rollback_info"] = json.dumps(d["rollback_info"])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Fix:
        d = dict(d)
        for key in ("commands_run", "rollback_info"):
            if isinstance(d.get(key), str):
                d[key] = json.loads(d[key])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SystemSnapshot:
    """Point-in-time snapshot of system state."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    load_average: list[float] = field(default_factory=list)
    failed_services: list[str] = field(default_factory=list)
    network_status: str = "unknown"
    open_file_descriptors: int = 0
    zombie_processes: int = 0
    uptime_seconds: float = 0.0
    custom_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["load_average"] = json.dumps(d["load_average"])
        d["failed_services"] = json.dumps(d["failed_services"])
        d["custom_data"] = json.dumps(d["custom_data"])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> SystemSnapshot:
        d = dict(d)
        for key in ("load_average", "failed_services", "custom_data"):
            if isinstance(d.get(key), str):
                d[key] = json.loads(d[key])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
