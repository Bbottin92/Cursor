"""Base module interface for all monitoring modules."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.settings import Settings
    from persistence.context_store import ContextStore
    from persistence.models import Event


class BaseModule(ABC):
    """Abstract base for all monitoring/detection modules."""

    name: str = "base"

    def __init__(self, settings: Settings, store: ContextStore):
        self.settings = settings
        self.store = store
        self.logger = logging.getLogger(f"self-healing.module.{self.name}")

    @abstractmethod
    def scan(self) -> list[Event]:
        """Scan for issues and return detected events."""
        ...

    def cleanup(self):
        """Optional cleanup when module is stopped."""
        pass
