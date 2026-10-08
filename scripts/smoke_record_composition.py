"""Replay record access contracts through explicit per-domain composition."""
from contextlib import ExitStack
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import smoke_record_access as original
from local_inspection_service.records.composition import RecordServices
from local_inspection_service.records import audit
from local_inspection_service.runtime.identity import RequestIdentity


def composed_access(identity, ownership, current_user, find_user):
    return RecordServices(identity=identity, legacy_owner=ownership.legacy_owner,
                          system_owner=ownership.system_owner, current_user=current_user,
                          find_user=find_user).access


class ComposedAccess(original.RecordAccessContract):
    def setUp(self):
        seam = patch.object(original, 'RecordAccess', composed_access)
        seam.start()
        self.addCleanup(seam.stop)


class Composition(unittest.TestCase):
    def test_inert_and_independent_graphs(self):
        fail = Mock(side_effect=AssertionError('constructor called an input'))
        identities = [RequestIdentity(), RequestIdentity()]
        a, b = [RecordServices(identity=identity, legacy_owner='legacy', system_owner='system',
                              current_user=fail, find_user=fail) for identity in identities]
        fail.assert_not_called()
        self.assertIsNot(a.ownership, b.ownership)
        self.assertIsNot(a.access, b.access)
        self.assertIsNot(a.audit, b.audit)
        for graph, identity in zip((a, b), identities):
            self.assertIs(graph.audit.ownership, graph.ownership)
            self.assertIs(graph.access.ownership, graph.ownership)
            self.assertIs(graph.access.identity, identity)
        with identities[0].bind({'id': 'alice'}):
            self.assertEqual(a.access.current_owner_fields(), {'owner_user_id': 'alice', 'owner_username': ''})
            self.assertEqual(b.access.current_owner_fields(), {})
        self.assertEqual(a.access.current_owner_fields(), {})
        self.assertEqual(a.audit.record_audit_fields({})['owner_user_id'], 'legacy')
        fail.assert_not_called()

    def test_actual_entry_captures_chosen_owners_and_full_http(self):
        from scripts import verify_backend_contract as contract
        self.assertEqual(contract.encoded(contract.capture()), contract.BASELINE.read_text(encoding='utf-8'))
        from local_inspection_service import server
        graph = server._record_services
        self.assertIs(graph.access.identity, server._authentication_domain.identity)
        self.assertEqual(graph.access.current_user, server._authentication.access.current_auth_user)
        self.assertEqual(graph.access.find_user.__defaults__,
                         (server._authentication.repository.load_auth_store, server.find_user))
        bindings = {
            'record_owner_id': graph.ownership.record_owner_id,
            'current_owner_fields': graph.access.current_owner_fields,
            'owner_fields_for_new_record': graph.access.owner_fields_for_new_record,
            'coerce_record_timestamp': audit.coerce_record_timestamp,
            'path_mtime_timestamp': audit.path_mtime_timestamp,
            'record_created_at': audit.record_created_at,
            'record_updated_at': audit.record_updated_at,
            'record_owner_username': graph.ownership.record_owner_username,
            'record_audit_fields': graph.audit.record_audit_fields,
            'enrich_record_audit_fields': graph.audit.enrich_record_audit_fields,
            'record_matches_owner_filter': graph.ownership.record_matches_owner_filter,
            'record_visible_to_user': graph.ownership.record_visible_to_user,
            'record_mutable_by_user': graph.ownership.record_mutable_by_user,
            'require_record_access': graph.access.require_record_access,
        }
        for name, expected in bindings.items():
            self.assertEqual(getattr(server, name), expected)
        poison = Mock(side_effect=AssertionError('entry alias was re-read'))
        with ExitStack() as stack:
            for name in ('_record_services', '_record_ownership', '_record_access', '_record_audit',
                         'current_auth_user', 'load_auth_store', 'find_user'):
                stack.enter_context(patch.object(server, name, poison))
            with graph.access.identity.bind({'id': 'alice', 'role': 'user'}):
                self.assertEqual(server.current_owner_fields()['owner_user_id'], 'alice')
                server.require_record_access({'owner_user_id': 'alice'}, write=True)
                self.assertEqual(server.record_audit_fields({'owner_user_id': 'alice'})['owner_user_id'], 'alice')
            self.assertEqual(server.current_owner_fields(), {})
            poison.assert_not_called()


if __name__ == '__main__':
    unittest.main()
