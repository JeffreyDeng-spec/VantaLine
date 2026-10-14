"""New summary checkpoint preserves earlier locks and rejects unknown owners."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import billing_volc_summary_source_contract as contract


class SummarySource(unittest.TestCase):
    def test_exact_current_and_parent_only(self):
        value=contract.fixture()
        path=value['provider_path'];parent=value['parent_source'].encode()
        self.assertEqual(contract.checkpoint_bytes(path,(contract.ROOT/path).read_bytes()),parent)
        self.assertEqual(contract.checkpoint_bytes(path,parent),parent)
        earlier=json.loads((contract.ROOT/'tests/backend_contract/billing_configuration_extension.json').read_text())['files'][path]['parent_source'].encode()
        self.assertEqual(contract.checkpoint_bytes(path,earlier),earlier)
        with self.assertRaises(AssertionError):contract.checkpoint_bytes(path,parent+b'\nunreviewed\n')

    def test_actual_source_and_immutable_fixture_mutants_fail(self):
        value=contract.fixture();original=Path.read_bytes
        paths=[value['provider_path'],value['configuration_guard_path'],
               *value['locked_prior_fixtures'],'tests/backend_contract/billing_volc_summary_extension.json']
        for name in paths:
            target=(contract.ROOT/name).resolve()
            def read(path):
                raw=original(path)
                return raw+b'\nunreviewed\n' if path.resolve()==target else raw
            with self.subTest(name=name),patch.object(Path,'read_bytes',read),self.assertRaises(AssertionError):contract.fixture()

    def test_prior_contracts_replay_their_unchanged_fixtures(self):
        import billing_configuration_source_contract as configuration
        import billing_source_contract as original
        configuration.fixture();original.fixture()
        for name,digest in contract.fixture()['locked_prior_fixtures'].items():
            self.assertEqual(hashlib.sha256((contract.ROOT/name).read_bytes()).hexdigest(),digest)


if __name__=='__main__':unittest.main()
