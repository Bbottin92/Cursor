#!/usr/bin/env python3
"""Basic tests for the self-healing system components."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from persistence.models import Event, Diagnosis, Fix, SystemSnapshot, EventState, Severity, FixResult
from persistence.context_store import ContextStore
from config.settings import Settings


class TestModels(unittest.TestCase):
    """Test data models serialization."""

    def test_event_roundtrip(self):
        event = Event(
            source="test:source",
            category="test",
            severity=Severity.ERROR.value,
            summary="Test event",
            details={"key": "value", "nested": {"a": 1}},
            related_events=["id1", "id2"],
        )
        d = event.to_dict()
        restored = Event.from_dict(d)
        self.assertEqual(event.id, restored.id)
        self.assertEqual(event.summary, restored.summary)
        self.assertEqual(event.details, restored.details)
        self.assertEqual(event.related_events, restored.related_events)

    def test_diagnosis_roundtrip(self):
        diag = Diagnosis(
            event_id="evt-123",
            root_cause="test cause",
            confidence=0.85,
            suggested_fixes=[{"type": "restart", "priority": 1}],
            analysis={"step": "result"},
        )
        d = diag.to_dict()
        restored = Diagnosis.from_dict(d)
        self.assertEqual(diag.root_cause, restored.root_cause)
        self.assertEqual(diag.suggested_fixes, restored.suggested_fixes)

    def test_fix_roundtrip(self):
        fix = Fix(
            event_id="evt-123",
            fix_type="service_restart",
            commands_run=[{"cmd": "systemctl restart nginx", "rc": 0}],
            result=FixResult.SUCCESS.value,
            rollback_info={"service": "nginx"},
        )
        d = fix.to_dict()
        restored = Fix.from_dict(d)
        self.assertEqual(fix.commands_run, restored.commands_run)

    def test_snapshot_roundtrip(self):
        snap = SystemSnapshot(
            cpu_percent=45.2,
            memory_percent=67.8,
            disk_percent=55.0,
            load_average=[1.5, 1.2, 0.9],
            failed_services=["nginx", "redis"],
            custom_data={"extra": "data"},
        )
        d = snap.to_dict()
        restored = SystemSnapshot.from_dict(d)
        self.assertEqual(snap.load_average, restored.load_average)
        self.assertEqual(snap.failed_services, restored.failed_services)


class TestContextStore(unittest.TestCase):
    """Test persistent context store."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.store = ContextStore(db_path=self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_store_and_retrieve_event(self):
        event = Event(
            source="test",
            category="test",
            summary="Test event",
        )
        self.store.store_event(event)
        retrieved = self.store.get_event(event.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.summary, "Test event")

    def test_event_state_update(self):
        event = Event(source="test", category="test", summary="Test")
        self.store.store_event(event)
        self.store.update_event_state(event.id, EventState.FIXING.value)
        retrieved = self.store.get_event(event.id)
        self.assertEqual(retrieved.state, EventState.FIXING.value)

    def test_active_events(self):
        for i in range(5):
            event = Event(source="test", category="test", summary=f"Event {i}")
            self.store.store_event(event)
        active = self.store.get_active_events()
        self.assertEqual(len(active), 5)

    def test_context_key_value(self):
        self.store.set_context("test_key", {"foo": "bar", "num": 42})
        val = self.store.get_context("test_key")
        self.assertEqual(val["foo"], "bar")
        self.assertEqual(val["num"], 42)

    def test_context_default(self):
        val = self.store.get_context("nonexistent", "default_val")
        self.assertEqual(val, "default_val")

    def test_store_diagnosis(self):
        event = Event(source="test", category="test", summary="Test")
        self.store.store_event(event)
        diag = Diagnosis(
            event_id=event.id,
            root_cause="test cause",
            confidence=0.9,
        )
        self.store.store_diagnosis(diag)
        diagnoses = self.store.get_diagnoses_for_event(event.id)
        self.assertEqual(len(diagnoses), 1)
        self.assertEqual(diagnoses[0].root_cause, "test cause")

    def test_store_fix(self):
        event = Event(source="test", category="test", summary="Test")
        self.store.store_event(event)
        fix = Fix(
            event_id=event.id,
            fix_type="test_fix",
            result=FixResult.SUCCESS.value,
        )
        self.store.store_fix(fix)
        fixes = self.store.get_fixes_for_event(event.id)
        self.assertEqual(len(fixes), 1)

    def test_store_snapshot(self):
        snap = SystemSnapshot(cpu_percent=50.0, memory_percent=60.0)
        self.store.store_snapshot(snap)
        latest = self.store.get_latest_snapshot()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.cpu_percent, 50.0)

    def test_statistics(self):
        event = Event(source="test", category="test", summary="Test")
        self.store.store_event(event)
        stats = self.store.get_statistics()
        self.assertEqual(stats["total_events"], 1)

    def test_cursor_messages(self):
        self.store.queue_cursor_message("test", {"data": "value"})
        msgs = self.store.get_unprocessed_messages(direction="outbound")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["message_type"], "test")
        self.store.mark_message_processed(msgs[0]["id"])
        msgs = self.store.get_unprocessed_messages(direction="outbound")
        self.assertEqual(len(msgs), 0)

    def test_similar_events(self):
        for i in range(3):
            event = Event(source="test:src", category="test_cat", summary=f"Event {i}")
            self.store.store_event(event)
        similar = self.store.find_similar_events("test_cat", "test:src", hours=1)
        self.assertEqual(len(similar), 3)

    def test_retry_increment(self):
        event = Event(source="test", category="test", summary="Test")
        self.store.store_event(event)
        count = self.store.increment_retry(event.id)
        self.assertEqual(count, 1)
        count = self.store.increment_retry(event.id)
        self.assertEqual(count, 2)


class TestSettings(unittest.TestCase):
    """Test configuration management."""

    def test_default_settings(self):
        s = Settings()
        self.assertEqual(s.api_port, 7847)
        self.assertTrue(s.auto_fix_enabled)
        self.assertFalse(s.auto_reboot_enabled)

    def test_save_and_load(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "config.json")
        s = Settings()
        s.api_port = 9999
        s.save(path)

        from config.settings import load_settings
        loaded = load_settings(path)
        self.assertEqual(loaded.api_port, 9999)

        import shutil
        shutil.rmtree(tmpdir)

    def test_from_dict(self):
        s = Settings.from_dict({"api_port": 8888, "unknown_field": "ignored"})
        self.assertEqual(s.api_port, 8888)


if __name__ == "__main__":
    unittest.main()
