"""Configuration replay rejects unknown source/fixture changes."""
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
import billing_configuration_source_contract as contract


class ConfigurationSource(unittest.TestCase):
    def test_exact_parent_and_unknown_input(self):
        value=contract.fixture()
        for name,change in value['files'].items():
            actual=(contract.ROOT/name).read_bytes()
            self.assertEqual(contract.checkpoint_bytes(name,actual),change['parent_source'].encode())
            with self.assertRaises(AssertionError):contract.checkpoint_bytes(name,actual+b'\nunreviewed_change\n')

    def test_actual_owner_mutations_are_rejected(self):
        value=contract.fixture();original=Path.read_bytes
        for name in [*value['files'],*value['new_sources']]:
            target=(contract.ROOT/name).resolve()
            def read(path):
                raw=original(path)
                return raw+b'\nunreviewed_change\n' if path.resolve()==target else raw
            with self.subTest(name=name),patch.object(Path,'read_bytes',read),self.assertRaises(AssertionError):contract.fixture()

    def test_original_billing_fixture_and_guard_hash_are_retained(self):
        import billing_source_contract as original
        original.fixture()
        raw=(contract.ROOT/'tests/backend_contract/billing_extension.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),original.FIXTURE_SHA256)


if __name__=='__main__':unittest.main()
