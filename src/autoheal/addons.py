from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from .models import ActionPlan, Finding, Recommendation
from .remediations import ActionResult

log = logging.getLogger("autoheal.addons")

CheckFn = Callable[[dict[str, Any]], list[Finding]]
PlannerFn = Callable[[dict[str, Any], Finding], list[ActionPlan]]
ExecutorFn = Callable[[dict[str, Any], ActionPlan, Finding], ActionResult]
RecommenderFn = Callable[[dict[str, Any], list[Finding]], list[Recommendation]]


@dataclass
class AddonError:
    source: str
    error: str
    tb: str = ""


@dataclass
class AddonRegistry:
    """
    Addons register callbacks here via `register(registry, config=...)`.
    """

    addon_id: str
    config: dict[str, Any]
    checks: list[CheckFn] = field(default_factory=list)
    planners: list[PlannerFn] = field(default_factory=list)
    executors: dict[str, ExecutorFn] = field(default_factory=dict)
    recommenders: list[RecommenderFn] = field(default_factory=list)

    def add_check(self, fn: CheckFn) -> None:
        self.checks.append(fn)

    def add_planner(self, fn: PlannerFn) -> None:
        self.planners.append(fn)

    def add_executor(self, action_name: str, fn: ExecutorFn) -> None:
        action_name = str(action_name)
        if action_name in self.executors:
            raise ValueError(f"executor already registered for action: {action_name}")
        self.executors[action_name] = fn

    def add_recommender(self, fn: RecommenderFn) -> None:
        self.recommenders.append(fn)


@dataclass
class LoadedAddon:
    addon_id: str
    source: str
    registry: AddonRegistry


@dataclass
class AddonManager:
    """
    Loads and runs addon hooks. All addon failures are isolated and recorded.
    """

    addons: list[LoadedAddon] = field(default_factory=list)
    errors: list[AddonError] = field(default_factory=list)
    fail_open: bool = True

    def run_checks(self, cfg: dict[str, Any]) -> list[Finding]:
        out: list[Finding] = []
        for a in self.addons:
            for fn in a.registry.checks:
                try:
                    out.extend(fn(cfg))
                except Exception as e:
                    self._err(a.source, f"check failed ({a.addon_id}): {e}")
        return out

    def plan_actions_for_finding(self, cfg: dict[str, Any], finding: Finding) -> list[ActionPlan]:
        out: list[ActionPlan] = []
        for a in self.addons:
            for fn in a.registry.planners:
                try:
                    out.extend(fn(cfg, finding))
                except Exception as e:
                    self._err(a.source, f"planner failed ({a.addon_id}): {e}")
        return out

    def run_recommendations(self, cfg: dict[str, Any], findings: list[Finding]) -> list[Recommendation]:
        out: list[Recommendation] = []
        for a in self.addons:
            for fn in a.registry.recommenders:
                try:
                    out.extend(fn(cfg, findings))
                except Exception as e:
                    self._err(a.source, f"recommender failed ({a.addon_id}): {e}")
        return out

    def can_execute(self, plan: ActionPlan) -> bool:
        return any(plan.name in a.registry.executors for a in self.addons)

    def execute(self, cfg: dict[str, Any], plan: ActionPlan, finding: Finding) -> ActionResult:
        for a in self.addons:
            fn = a.registry.executors.get(plan.name)
            if fn is None:
                continue
            try:
                return fn(cfg, plan, finding)
            except Exception as e:
                self._err(a.source, f"executor failed ({a.addon_id}, {plan.name}): {e}")
                return ActionResult(
                    status="failed",
                    exit_code=None,
                    stdout=None,
                    stderr=str(e),
                    summary="addon executor failed",
                )

        return ActionResult(
            status="skipped",
            exit_code=None,
            stdout=None,
            stderr=None,
            summary="no addon executor for plan",
        )

    def manifest(self) -> dict[str, Any]:
        return {
            "addons": [
                {
                    "id": a.addon_id,
                    "source": a.source,
                    "checks": len(a.registry.checks),
                    "planners": len(a.registry.planners),
                    "recommenders": len(a.registry.recommenders),
                    "executors": sorted(a.registry.executors.keys()),
                }
                for a in self.addons
            ],
            "errors": [{"source": e.source, "error": e.error} for e in self.errors],
        }

    def _err(self, source: str, msg: str) -> None:
        tb = traceback.format_exc(limit=20)
        self.errors.append(AddonError(source=source, error=msg, tb=tb))
        log.debug("addon error (%s): %s", source, msg)


def load_addons(cfg: dict[str, Any]) -> AddonManager:
    """
    Load addons declared in config.

    Config shape (all optional):
      addons: {
        enabled: bool,
        modules: [ "pkg.module", ... ],
        paths: [ "~/.config/autoheal/addons.d", ... ],
        module_config: { "pkg.module": {...}, ... },
        fail_open: bool
      }
    """
    acfg = cfg.get("addons", {}) or {}
    if not bool(acfg.get("enabled", True)):
        return AddonManager(addons=[], errors=[], fail_open=True)

    fail_open = bool(acfg.get("fail_open", True))
    modules = list(acfg.get("modules", []) or [])
    paths = list(acfg.get("paths", ["~/.config/autoheal/addons.d"]) or [])
    module_config = dict(acfg.get("module_config", {}) or {})

    mgr = AddonManager(addons=[], errors=[], fail_open=fail_open)

    # Import modules
    for mod_name in modules:
        mod_name = str(mod_name).strip()
        if not mod_name:
            continue
        try:
            mod = importlib.import_module(mod_name)
            _register_module(mgr, mod, source=f"module:{mod_name}", addon_id=mod_name, config=module_config.get(mod_name, {}) or {})
        except Exception as e:
            mgr.errors.append(AddonError(source=f"module:{mod_name}", error=str(e), tb=traceback.format_exc(limit=20)))
            if not fail_open:
                break

    # Load single-file addons from paths (non-recursive).
    for p in paths:
        try:
            d = Path(str(p)).expanduser()
        except Exception:
            continue
        if not d.exists() or not d.is_dir():
            continue
        for fp in sorted(d.iterdir()):
            if not fp.is_file() or fp.suffix != ".py":
                continue
            name = f"autoheal_addon_{fp.stem}"
            try:
                mod = _import_file_module(name, fp)
                _register_module(mgr, mod, source=f"file:{fp}", addon_id=name, config=module_config.get(str(fp), {}) or {})
            except Exception as e:
                mgr.errors.append(AddonError(source=f"file:{fp}", error=str(e), tb=traceback.format_exc(limit=20)))
                if not fail_open:
                    break

    return mgr


def _import_file_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load addon from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _register_module(
    mgr: AddonManager,
    mod: ModuleType,
    *,
    source: str,
    addon_id: str,
    config: dict[str, Any],
) -> None:
    reg = AddonRegistry(addon_id=addon_id, config=dict(config or {}))

    register = getattr(mod, "register", None)
    if register is None or not callable(register):
        raise AttributeError("addon module must define register(registry, ...)")

    # Support register(registry) and register(registry, config=...)
    sig = inspect.signature(register)
    kwargs: dict[str, Any] = {}
    if "config" in sig.parameters:
        kwargs["config"] = reg.config

    register(reg, **kwargs)  # type: ignore[misc]
    mgr.addons.append(LoadedAddon(addon_id=addon_id, source=source, registry=reg))
