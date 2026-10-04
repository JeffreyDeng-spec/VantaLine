"""Immutable managed-runtime activation cannot be selected by an environment flag."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.label_identity import LabelRuntimeIdentity, RuntimeUnavailable, read_identity
from local_inspection_service.storage.label_runtime import decode_state


class IdentityContracts(unittest.TestCase):
    def test_checkout_and_legacy_embedded_remain_unmanaged(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertIsNone(read_identity(root))
            (root/'VERSION.json').write_text(json.dumps({'git_commit':'a'*40,'release':'v2026.10.1'}))
            (root/'RUNTIME_TOPOLOGY.json').write_text(json.dumps({'schema':1,'git_commit':'a'*40,
                'worker_mode':'embedded','services':['vantaline']}))
            self.assertIsNone(read_identity(root))

    def test_only_exact_active_embedded_managed_package_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'VERSION.json').write_text(json.dumps({'git_commit':'a'*40,'release':'v2026.10.1'}))
            good={'schema':2,'git_commit':'a'*40,'worker_mode':'embedded','services':['vantaline'],'runtime_protocol':1}
            path=root/'RUNTIME_TOPOLOGY.json'
            path.write_text(json.dumps(good))
            self.assertEqual(read_identity(root,current=root), LabelRuntimeIdentity('a'*40,'v2026.10.1','embedded'))
            with self.assertRaises(RuntimeUnavailable): read_identity(root,current=root/'not-current')
            for altered in ({**good,'runtime_protocol':True}, {**good,'schema':True}, {**good,'git_commit':'b'*40},
                            {**good,'worker_mode':'external','services':['vantaline','vantaline-label-worker']},
                            {**good,'extra':'untrusted'}, {**good,'services':['other']}):
                with self.subTest(altered=altered):
                    path.write_text(json.dumps(altered))
                    with self.assertRaises(RuntimeUnavailable): read_identity(root)

    def test_external_requires_active_package_and_explicit_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'VERSION.json').write_text(json.dumps({'git_commit':'a'*40,'release':'v2026.10.1'}))
            (root/'RUNTIME_TOPOLOGY.json').write_text(json.dumps({'schema':2,'runtime_protocol':1,
                'git_commit':'a'*40,'worker_mode':'external','services':['vantaline','vantaline-label-worker']}))
            with self.assertRaises(RuntimeUnavailable): read_identity(root, current=root)
            self.assertEqual(read_identity(root, current=root, configuration_revision=lambda: 'b'*64),
                LabelRuntimeIdentity('a'*40, 'v2026.10.1', 'external', 'b'*64))
            with self.assertRaises(RuntimeUnavailable):
                read_identity(root, current=root/'foreign', configuration_revision=lambda: 'b'*64)

    def test_corrupt_operational_state_never_resets_to_permissive_defaults(self):
        good={'schema':1,'git_commit':'a'*40,'worker_mode':'embedded','config_revision':None,
              'maintenance':True,'paused':True,'revision':'b'*32}
        self.assertEqual(decode_state(good),good)
        for value in (None,False,[],{}, {**good,'schema':True}, {**good,'paused':1},
                      {**good,'maintenance':'false'}, {**good,'revision':'bad'},
                      {**good,'config_revision':'bad'}, {**good,'worker_mode':'external'},
                      {**good,'unexpected':'synthetic-secret'}, 'not-json'):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeUnavailable) as error: decode_state(value)
                self.assertNotIn('synthetic-secret',str(error.exception))


if __name__ == '__main__': unittest.main()
