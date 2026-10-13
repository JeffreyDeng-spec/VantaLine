"""Financial descendants must not weaken any retained source/API oracle."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import billing_source_contract as contract


class FinancialSource(unittest.TestCase):
    def test_exact_extension_restores_unchanged_parent_sources(self):
        value=contract.fixture()
        self.assertEqual(len(value['openapi']['paths']),5)
        for path,change in value['files'].items():
            actual=(contract.ROOT/path).read_bytes()
            self.assertEqual(contract.checkpoint_bytes(path,actual),change['parent_source'].encode())
            with self.assertRaises(AssertionError):contract.checkpoint_bytes(path,actual+b'\nunreviewed_binding = None\n')

    def test_each_new_owner_mutation_is_rejected(self):
        value=contract.fixture();original=Path.read_bytes
        for path in value['new_sources']:
            target=(contract.ROOT/path).resolve()
            def read(current):
                raw=original(current)
                return raw+b'\nunreviewed_change\n' if current.resolve()==target else raw
            with self.subTest(path=path),patch.object(Path,'read_bytes',read),self.assertRaises(AssertionError):contract.fixture()

    def test_openapi_changes_cannot_be_hidden(self):
        value=contract.fixture()['openapi']
        source={'paths':copy.deepcopy(value['paths']),'components':{'schemas':copy.deepcopy(value['schemas'])}}
        self.assertEqual(contract.openapi_checkpoint(source),{'paths':{},'components':{'schemas':{}}})
        source['paths']['/api/admin/billing/unreviewed']={}
        with self.assertRaises(AssertionError):contract.openapi_checkpoint(source)

    def test_route_metadata_and_registration_position_are_exact(self):
        expected=contract.fixture()['routes']
        before={'path':'/api/admin/api-cost-ledger'};after={'path':'/api/admin/runtime-store/probe'}
        self.assertEqual(contract.routes_checkpoint([before,*expected,after]),[before,after])
        for mutation in ('metadata','order','missing','extra','position'):
            candidate=copy.deepcopy([before,*expected,after])
            if mutation=='metadata':candidate[1]['permission']={}
            elif mutation=='order':candidate[1],candidate[2]=candidate[2],candidate[1]
            elif mutation=='missing':candidate.pop(1)
            elif mutation=='extra':candidate.insert(1,{'path':'/api/admin/billing/unreviewed'})
            else:candidate[0]['path']='/unreviewed'
            with self.subTest(mutation=mutation),self.assertRaises(AssertionError):contract.routes_checkpoint(candidate)


if __name__=='__main__':unittest.main()
