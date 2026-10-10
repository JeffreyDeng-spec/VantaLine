"""Guard actual factory modules and preserve every prior source oracle."""
import ast
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import canonical_application_source_contract as contract


class Contracts(unittest.TestCase):
    def test_exact_actual_sources_and_parent_replay(self):
        source = (contract.ROOT / 'local_inspection_service/server.py').read_text()
        restored = contract.restore_canonical_root(source)
        self.assertEqual(restored, contract.FIXTURE['parent_source'])
        self.assertEqual(contract.source_digest(restored), contract.FIXTURE['parent_ast_sha256'])
        self.assertNotEqual(contract.source_digest(source), contract.source_digest(restored))

    def test_each_actual_module_mutation_cannot_be_hidden_by_parent_replay(self):
        source = (contract.ROOT / 'local_inspection_service/server.py').read_text()
        original_read = Path.read_text
        for relative in sorted(contract.EXPECTED_PATHS):
            target = (contract.ROOT / relative).resolve()
            def read(path, *args, **kwargs):
                value = original_read(path, *args, **kwargs)
                return value + '\nunreviewed_factory_binding = None\n' if path.resolve() == target else value
            with self.subTest(module=relative), patch.object(Path, 'read_text', read), self.assertRaises(AssertionError):
                contract.restore_canonical_root(source)

    def test_incomplete_inventory_and_modified_parent_are_rejected(self):
        for mutation in ('inventory', 'parent', 'parent_hash', 'parent_commit'):
            fixture = copy.deepcopy(contract.FIXTURE)
            if mutation == 'inventory': fixture['actual_source_ast_sha256'].pop(next(iter(fixture['actual_source_ast_sha256'])))
            elif mutation == 'parent': fixture['parent_source'] += '\nunreviewed_parent = None\n'
            elif mutation == 'parent_hash': fixture['parent_source_sha256'] = '0' * 64
            else: fixture['parent_sha'] = '0' * 40
            with self.subTest(mutation=mutation), patch.object(contract, 'FIXTURE', fixture), self.assertRaises(AssertionError):
                contract.verify_actual_sources()


if __name__ == '__main__': unittest.main()
