from __future__ import annotations

from typing import Any

from ..models import ActionPlan, Finding
from ..subprocess_utils import run, which


def register(registry, *, config: dict[str, Any] | None = None) -> None:
    cfg = dict(config or {})
    if not bool(cfg.get("enabled", False)):
        return

    def check(_: dict[str, Any]) -> list[Finding]:
        if which("git") is None:
            return []
        if which("less") is not None:
            return []

        # If core.pager is explicitly set to something else, do not touch it.
        try:
            res = run(["git", "config", "--global", "--get", "core.pager"], timeout_seconds=2)
            if res.exit_code == 0:
                pager = (res.stdout or "").strip()
                if pager and pager != "less":
                    return []
        except Exception:
            # If git config is inaccessible, don't report.
            return []

        return [
            Finding(
                fingerprint="git_pager_less_missing",
                type="git_pager_less_missing",
                severity=2,
                title="git pager uses less but less is missing",
                details={"suggested_pager": "cat"},
                diagnosis="git commonly uses 'less' as a pager, but 'less' is not installed; commands may fail.",
            )
        ]

    def plan(_: dict[str, Any], finding: Finding) -> list[ActionPlan]:
        if finding.type != "git_pager_less_missing":
            return []
        return [
            ActionPlan(
                name="git_set_core_pager_cat",
                description="Set git core.pager=cat (global) to avoid missing less",
                command=["git", "config", "--global", "core.pager", "cat"],
                requires_root=False,
                timeout_seconds=5,
            )
        ]

    registry.add_check(check)
    registry.add_planner(plan)
