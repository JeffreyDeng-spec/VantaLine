"""Pure legacy, shared-read and administrator record-policy contracts."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.records.ownership import RecordOwnership


class OwnershipContract(unittest.TestCase):
    def setUp(self):
        self.policy = RecordOwnership("legacy_admin", "system")
        self.alice = {"id": "alice", "role": "user"}
        self.bob = {"id": "bob", "role": "user"}
        self.admin = {"id": "admin", "role": "admin"}

    def test_field_precedence_and_legacy_names(self):
        cases = [
            (None, "legacy_admin", "legacy_admin"),
            ({}, "legacy_admin", "legacy_admin"),
            ({"created_by_user_id": "alice", "created_by_username": "Alice"}, "alice", "Alice"),
            ({"owner_user_id": "  ", "created_by_user_id": "alice"}, "legacy_admin", "legacy_admin"),
            ({"owner_user_id": "alice", "owner_username": "  ", "created_by_username": "Old"}, "alice", "alice"),
            ({"owner_user_id": " system "}, "system", "system"),
            ({"owner_user_id": "legacy"}, "legacy", "legacy"),
        ]
        for record, owner, username in cases:
            with self.subTest(record=record):
                self.assertEqual(self.policy.record_owner_id(record), owner)
                self.assertEqual(self.policy.record_owner_username(record), username)

    def test_shared_is_read_only_and_admin_filter_remains_binding(self):
        for shared, bob_read in [(None, False), ([], False), (["bob"], True), (["*"], True), ("*", False), ({"bob": True}, False)]:
            record = {"owner_user_id": "alice", "shared_with_user_ids": shared}
            self.assertTrue(self.policy.record_visible_to_user(record, self.alice, "unrelated-filter"))
            self.assertTrue(self.policy.record_mutable_by_user(record, self.alice))
            self.assertEqual(self.policy.record_visible_to_user(record, self.bob, "unrelated-filter"), bob_read)
            self.assertFalse(self.policy.record_mutable_by_user(record, self.bob))
            self.assertTrue(self.policy.record_visible_to_user(record, self.admin))
            self.assertTrue(self.policy.record_visible_to_user(record, self.admin, "alice"))
            self.assertFalse(self.policy.record_visible_to_user(record, self.admin, "bob"))
            self.assertTrue(self.policy.record_mutable_by_user(record, self.admin))

    def test_filter_aliases_and_independent_policy_configuration(self):
        cases = [({}, "legacy", True), ({}, "legacy_admin", True), ({}, "system", False),
                 ({"owner_user_id": "system"}, "system", True),
                 ({"owner_user_id": "legacy"}, "legacy", False),
                 ({"owner_user_id": "alice"}, " alice ", True),
                 ({"owner_user_id": "alice"}, None, True),
                 ({"owner_user_id": "alice"}, "", True),
                 ({"owner_user_id": "alice"}, "  ", False)]
        for record, target, expected in cases:
            self.assertEqual(self.policy.record_matches_owner_filter(record, target), expected)
        alternate = RecordOwnership("archive", "robot")
        self.assertEqual(alternate.record_owner_id(None), "archive")
        self.assertEqual(alternate.record_owner_username({"owner_user_id": "robot"}), "system")
        self.assertEqual(self.policy.record_owner_id(None), "legacy_admin")


if __name__ == "__main__":
    unittest.main()
