import os
import tempfile
import time
import unittest
from pathlib import Path

from autoheal import db
from autoheal.checks import check_cursor_crashpad, check_cursor_safe_launcher
from autoheal.addons import load_addons
from autoheal.models import ActionPlan, Finding, Recommendation
from autoheal.remediations import execute_plan


class TestDb(unittest.TestCase):
    def test_upsert_incident_increments_occurrences(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            conn = db.connect(Path(td) / "autoheal.db")
            try:
                f = Finding(
                    fingerprint="disk_usage:/",
                    type="disk_usage",
                    severity=3,
                    title="Disk usage high",
                    details={"mountpoint": "/", "used_percent": 99},
                    diagnosis="test",
                )
                iid1 = db.upsert_incident_from_finding(conn, f)
                iid2 = db.upsert_incident_from_finding(conn, f)
                self.assertEqual(iid1, iid2)

                inc = db.get_incident(conn, iid1)
                assert inc is not None
                self.assertEqual(inc["occurrences"], 2)
            finally:
                conn.close()


class TestTmpCleanup(unittest.TestCase):
    def test_tmp_cleanup_deletes_old_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            victim = p / "old.txt"
            victim.write_text("hello", encoding="utf-8")

            # Make file "old"
            old = time.time() - (10 * 3600)
            os.utime(victim, (old, old))

            cfg = {
                "actions": {
                    "tmp_cleanup": {
                        "enabled": True,
                        "paths": [str(p)],
                        "max_age_hours": 1,
                        "max_bytes_per_run": 10_000_000,
                    }
                }
            }
            plan = ActionPlan(
                name="tmp_cleanup",
                description="test",
                command=None,
                requires_root=False,
                timeout_seconds=5,
            )
            res = execute_plan(
                cfg,
                plan,
                finding=Finding(
                    fingerprint="x",
                    type="disk_usage",
                    severity=3,
                    title="x",
                    details={},
                    diagnosis="x",
                ),
            )
            self.assertIn(res.status, {"success", "failed"})
            self.assertFalse(victim.exists())


class TestCursorSafeLauncher(unittest.TestCase):
    def test_cursor_safe_launcher_installs_wrapper_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = td
            try:
                home = Path(td)
                launcher = home / ".local" / "bin" / "cursor"
                launcher.parent.mkdir(parents=True, exist_ok=True)
                launcher.write_text("#!/usr/bin/env bash\necho orig\n", encoding="utf-8")
                os.chmod(launcher, 0o755)

                cfg = {
                    "actions": {
                        "cursor_safe_launcher": {
                            "enabled": True,
                            "launcher_path": "~/.local/bin/cursor",
                            "backup_suffix": ".autoheal-orig",
                            "flags": ["--disable-extensions"],
                        }
                    }
                }
                plan = ActionPlan(
                    name="cursor_safe_launcher_install",
                    description="test",
                    command=None,
                    requires_root=False,
                    timeout_seconds=5,
                )
                res = execute_plan(
                    cfg,
                    plan,
                    finding=Finding(
                        fingerprint="x",
                        type="cursor_crashpad_reports",
                        severity=4,
                        title="x",
                        details={},
                        diagnosis="x",
                    ),
                )
                self.assertEqual(res.status, "success")
                self.assertTrue(launcher.exists())
                backup = home / ".local" / "bin" / "cursor.autoheal-orig"
                self.assertTrue(backup.exists())
                self.assertIn("autoheal-managed cursor launcher", launcher.read_text(encoding="utf-8"))
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home


class TestCursorCrashpadCheck(unittest.TestCase):
    def test_cursor_crashpad_check_detects_recent_dumps(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = td
            try:
                crashpad = Path(td) / ".config" / "Cursor" / "Crashpad" / "reports"
                crashpad.mkdir(parents=True, exist_ok=True)
                dump = crashpad / "test.dmp"
                dump.write_bytes(b"dummy")
                now = time.time()
                os.utime(dump, (now, now))

                cfg = {
                    "cursor": {
                        "crashpad_dirs": ["~/.config/Cursor/Crashpad"],
                        "crash_window_minutes": 60,
                        "crash_threshold": 1,
                    }
                }
                findings = check_cursor_crashpad(cfg)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].type, "cursor_crashpad_reports")
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home


class TestCursorSafeLauncherCheck(unittest.TestCase):
    def test_cursor_safe_launcher_check_reports_missing_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = td
            try:
                # Create an existing launcher without the autoheal marker.
                launcher = Path(td) / ".local" / "bin" / "cursor"
                launcher.parent.mkdir(parents=True, exist_ok=True)
                launcher.write_text("#!/usr/bin/env bash\necho orig\n", encoding="utf-8")
                os.chmod(launcher, 0o755)

                cfg = {
                    "actions": {"cursor_safe_launcher": {"enabled": True, "launcher_path": "~/.local/bin/cursor"}}
                }
                findings = check_cursor_safe_launcher(cfg)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].type, "cursor_safe_launcher_missing")
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home


class TestAddonLoader(unittest.TestCase):
    def test_load_builtin_addon_git_pager_disabled_by_default(self) -> None:
        cfg = {"addons": {"enabled": True, "modules": ["autoheal.addons_builtin.git_pager"], "module_config": {}}}
        mgr = load_addons(cfg)
        # addon is listed but registers nothing unless enabled in module_config
        m = mgr.manifest()
        self.assertEqual(len(m["addons"]), 1)
        self.assertEqual(m["addons"][0]["checks"], 0)

    def test_load_builtin_addon_performance_disabled_by_default(self) -> None:
        cfg = {
            "addons": {
                "enabled": True,
                "modules": ["autoheal.addons_builtin.performance"],
                "module_config": {},
            }
        }
        mgr = load_addons(cfg)
        m = mgr.manifest()
        self.assertEqual(len(m["addons"]), 1)
        self.assertEqual(m["addons"][0]["checks"], 0)


class TestRecommendationsDb(unittest.TestCase):
    def test_recommendations_upsert_and_accept(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            conn = db.connect(Path(td) / "autoheal.db")
            try:
                rid = db.upsert_recommendation(
                    conn,
                    Recommendation(
                        key="perf:low_memory_tuning",
                        title="Test recommendation",
                        message="Try a thing",
                        priority=4,
                        confidence=0.7,
                        details={"k": "v"},
                    ),
                )
                r = db.get_recommendation(conn, rid)
                assert r is not None
                self.assertEqual(r["status"], "open")

                db.set_recommendation_status(conn, rid, status="accepted", note="yep")
                r2 = db.get_recommendation(conn, rid)
                assert r2 is not None
                self.assertEqual(r2["status"], "accepted")
                self.assertTrue(len(r2.get("events") or []) >= 1)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
