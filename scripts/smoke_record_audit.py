"""Timestamp precedence, stat fallback and shallow audit projection contracts."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.records.audit import RecordAudit, coerce_record_timestamp, path_mtime_timestamp, record_created_at, record_updated_at
from local_inspection_service.records.ownership import RecordOwnership


class AuditContract(unittest.TestCase):
    def test_numeric_coercion_and_precedence(self):
        for value, expected in [(None, 0), ("", 0), ("bad", 0), ({}, 0), (True, 1), ("12.9", 12), (-3.8, -3), ("nan", 0), (0, 0)]:
            self.assertEqual(coerce_record_timestamp(value), expected)
        with self.assertRaises(OverflowError):
            coerce_record_timestamp("inf")
        record = {"created_at": 0, "created": "12.9", "started_at": 700,
                  "updated_at": -3.9, "completed_at": 1000}
        self.assertEqual(record_created_at(record), 12)
        self.assertEqual(record_updated_at(record), -3)
        self.assertEqual(record_created_at({"created_at": "bad", "queued_at": 17, "updated_at": 29}), 17)
        self.assertEqual(record_updated_at({"updated_at": "bad", "failed_at": 15, "created_at": 300}), 15)
        self.assertEqual(record_created_at({"created_at": 0.9, "created": -1.9, "started_at": 900}), -1)
        for function, fields in [(record_created_at, ("created_at", "created", "started_at", "queued_at", "requested_at", "completed_at", "updated_at")),
                                 (record_updated_at, ("updated_at", "completed_at", "failed_at", "confirmed_at", "started_at", "created_at"))]:
            record = {name: 100 - index for index, name in enumerate(fields)}
            for name in fields:
                self.assertEqual(function(record), record[name])
                del record[name]

    def test_mtime_fallback_and_errors(self):
        with tempfile.TemporaryDirectory(prefix="audit-fixture-") as temporary:
            path = Path(temporary) / "record.json"
            path.write_text("synthetic", encoding="utf-8")
            os.utime(path, (123456789, 123456789))
            self.assertEqual(path_mtime_timestamp(path), 123456789)
            self.assertEqual(record_created_at(None, path), 123456789)
            self.assertEqual(record_updated_at({"updated_at": 0}, path), 123456789)
            self.assertEqual(record_created_at({"created_at": 5}, path), 5)
            self.assertEqual(record_updated_at({}, path.with_name("missing")), 0)
        def inaccessible():
            raise PermissionError("synthetic stat denial")
        self.assertEqual(path_mtime_timestamp(SimpleNamespace(stat=inaccessible)), 0)
        self.assertEqual(path_mtime_timestamp(None), 0)
        calls = []
        def stat():
            calls.append(1)
            return SimpleNamespace(st_mtime=11 * len(calls))
        audit = RecordAudit(RecordOwnership("archive", "robot"))
        result = audit.record_audit_fields({}, SimpleNamespace(stat=stat))
        self.assertEqual((result["created_at"], result["updated_at"], result["owner_user_id"]), (11, 22, "archive"))
        self.assertEqual(audit.record_audit_fields({"owner_user_id": "robot"})["owner_username"], "system")

    def test_projection_preserves_input_and_nested_references(self):
        audit = RecordAudit(RecordOwnership("legacy_admin", "system"))
        record = {"created_at": "12.9", "updated_at": -5, "owner_user_id": "alice", "nested": {"value": 1}}
        result = audit.enrich_record_audit_fields(record)
        self.assertIsNot(result, record)
        self.assertIs(result["nested"], record["nested"])
        self.assertEqual(record["created_at"], "12.9")
        self.assertNotIn("owner_username", record)
        self.assertEqual({key: result[key] for key in ("created_at", "updated_at", "owner_user_id", "owner_username")},
                         {"created_at": 12, "updated_at": -5, "owner_user_id": "alice", "owner_username": "alice"})
        self.assertEqual(audit.record_audit_fields(None), {"created_at": 0, "updated_at": 0,
                         "owner_user_id": "legacy_admin", "owner_username": "legacy_admin"})


if __name__ == "__main__":
    unittest.main()
