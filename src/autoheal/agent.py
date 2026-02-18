from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from . import db
from ._paths import (
    default_control_socket_path,
    default_db_path,
    default_lock_path,
    default_log_path,
)
from .checks import run_all_checks
from .control import ControlRequest, ControlResponse, start_control_server
from .models import Finding
from .remediations import execute_plan, plan_actions_for_finding

log = logging.getLogger("autoheal.agent")


class AgentAlreadyRunning(RuntimeError):
    pass


def _acquire_lock(lock_path: Path) -> Any:
    # Linux-only advisory lock; good enough for "single instance" safety.
    import fcntl

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise AgentAlreadyRunning(f"lock already held: {lock_path}")
    return f


class AutohealAgent:
    def __init__(
        self,
        *,
        cfg: dict[str, Any],
        state_dir: Path,
        db_path: Path | None = None,
        control_socket_path: Path | None = None,
        lock_path: Path | None = None,
    ) -> None:
        self.cfg = cfg
        self.state_dir = state_dir
        self.db_path = db_path or default_db_path(state_dir)
        self.control_socket_path = control_socket_path or default_control_socket_path(
            state_dir
        )
        self.lock_path = lock_path or default_lock_path(state_dir)
        self.log_path = default_log_path(state_dir)

        self.started_ts = time.time()

        import threading

        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self._lock_file = None
        self._control_thread = None

    def start(self) -> None:
        self._lock_file = _acquire_lock(self.lock_path)

        if bool(self.cfg.get("control", {}).get("enabled", True)):
            self._control_thread = start_control_server(
                self.control_socket_path,
                handler=self._handle_control,
                stop_event=self.stop_event,
            )

    def stop(self) -> None:
        self.stop_event.set()
        try:
            if self._lock_file:
                self._lock_file.close()
        except Exception:
            pass

    def _token_required(self) -> str | None:
        token = self.cfg.get("control", {}).get("token", None)
        if token is None:
            return None
        token = str(token).strip()
        return token or None

    def _authorized(self, req: ControlRequest) -> bool:
        required = self._token_required()
        if required is None:
            return True
        return req.token == required

    def _handle_control(self, req: ControlRequest) -> ControlResponse:
        method = req.method
        params = req.params or {}

        if method in {"incidents.create", "agent.run_once"} and not self._authorized(req):
            return ControlResponse(id=req.id, ok=False, error="unauthorized")

        if method == "ping":
            return ControlResponse(id=req.id, ok=True, result="pong")

        if method == "status":
            return ControlResponse(
                id=req.id,
                ok=True,
                result={
                    "started_ts": self.started_ts,
                    "uptime_seconds": int(time.time() - self.started_ts),
                    "state_dir": str(self.state_dir),
                    "db_path": str(self.db_path),
                    "control_socket_path": str(self.control_socket_path),
                },
            )

        if method == "agent.run_once":
            self.wake_event.set()
            return ControlResponse(id=req.id, ok=True, result={"scheduled": True})

        # DB-backed methods
        conn = db.connect(self.db_path)
        try:
            if method == "incidents.list":
                limit = int(params.get("limit", 50))
                return ControlResponse(
                    id=req.id, ok=True, result=db.list_incidents(conn, limit=limit)
                )

            if method == "incidents.get":
                iid = str(params.get("id", ""))
                inc = db.get_incident(conn, iid)
                if inc is None:
                    return ControlResponse(id=req.id, ok=False, error="not found")
                inc["actions"] = db.list_actions_for_incident(conn, iid, limit=50)
                return ControlResponse(id=req.id, ok=True, result=inc)

            if method == "incidents.create":
                incident_type = str(params.get("type", "manual"))
                title = str(params.get("title", "manual incident"))
                severity = int(params.get("severity", 3))
                diagnosis = str(params.get("diagnosis", "reported manually"))
                details = params.get("details", {}) or {}
                if not isinstance(details, dict):
                    details = {"details_raw": str(details)}
                iid = db.create_manual_incident(
                    conn,
                    incident_type=incident_type,
                    title=title,
                    severity=severity,
                    diagnosis=diagnosis,
                    details=details,
                )
                self.wake_event.set()
                return ControlResponse(id=req.id, ok=True, result={"id": iid})

        finally:
            conn.close()

        return ControlResponse(id=req.id, ok=False, error="unknown method")

    def run_forever(self) -> None:
        poll = int(self.cfg.get("poll_interval_seconds", 30))

        self.start()
        log.info("agent started (state_dir=%s, poll=%ss)", self.state_dir, poll)

        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                log.exception("run_once failed: %s", e)

            # Wait, but allow control-triggered wakeups
            self.wake_event.wait(timeout=poll)
            self.wake_event.clear()

        log.info("agent stopped")

    def run_once(self) -> None:
        cycle_started = time.time()
        findings = run_all_checks(self.cfg)
        active_fps = {f.fingerprint for f in findings}

        conn = db.connect(self.db_path)
        try:
            # Upsert active findings => acknowledge them and persist diagnostic context.
            fp_to_incident_id: dict[str, str] = {}
            for f in findings:
                iid = db.upsert_incident_from_finding(conn, f)
                fp_to_incident_id[f.fingerprint] = iid

            # Opportunistically close incidents that are no longer detected.
            # (Persistent context means we can do this without asking the user.)
            for inc in db.list_incidents(conn, limit=500):
                if inc.get("status") != "open":
                    continue
                fp = str(inc.get("fingerprint", ""))
                if fp.startswith("manual:"):
                    continue
                if fp and fp not in active_fps:
                    db.mark_incident_fixed(
                        conn, str(inc["id"]), "No longer detected by checks"
                    )

            # Remediate active findings.
            for f in findings:
                iid = fp_to_incident_id.get(f.fingerprint)
                if not iid:
                    continue
                self._remediate_finding(conn, iid, f)

        finally:
            conn.close()

        log.debug(
            "cycle finished in %.2fs (%d findings)",
            time.time() - cycle_started,
            len(findings),
        )

    def _remediate_finding(self, conn: Any, incident_id: str, finding: Finding) -> None:
        plans = plan_actions_for_finding(self.cfg, finding)
        if not plans:
            return

        euid = os.geteuid() if hasattr(os, "geteuid") else -1
        for plan in plans:
            # Rate limiting for high-impact actions.
            if plan.name == "systemd_restart_unit":
                cooldown = int(
                    self.cfg.get("actions", {})
                    .get("systemd_restart_failed_units", {})
                    .get("cooldown_seconds", 900)
                )
                last_ts = db.last_action_finished_ts(conn, incident_id, plan.name)
                if last_ts and (time.time() - last_ts) < cooldown:
                    db.record_action(
                        conn,
                        incident_id,
                        plan,
                        status="skipped",
                        started_ts=time.time(),
                        finished_ts=time.time(),
                        exit_code=None,
                        stdout=None,
                        stderr=None,
                        notes=f"cooldown active ({cooldown}s)",
                    )
                    continue

            if plan.requires_root and euid != 0:
                db.record_action(
                    conn,
                    incident_id,
                    plan,
                    status="skipped",
                    started_ts=time.time(),
                    finished_ts=time.time(),
                    exit_code=None,
                    stdout=None,
                    stderr=None,
                    notes="requires root",
                )
                continue

            started = time.time()
            result = execute_plan(self.cfg, plan, finding)
            finished = time.time()

            db.record_action(
                conn,
                incident_id,
                plan,
                status=result.status,
                started_ts=started,
                finished_ts=finished,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                notes=result.summary,
            )

            if result.status == "failed":
                db.set_incident_last_error(
                    conn,
                    incident_id,
                    (result.stderr or result.summary or "")[:4000],
                )

            # If an action completes successfully, request an earlier re-check.
            if result.status == "success":
                self.wake_event.set()
