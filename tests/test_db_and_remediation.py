import os
import tempfile
import time
import unittest
from pathlib import Path

from autoheal import db
from autoheal.models import ActionPlan, Finding
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


if __name__ == "__main__":
    unittest.main()
