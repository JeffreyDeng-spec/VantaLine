"""Environment provenance, complete lock fallback, file integrity and builder scope."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ci_environment as env


class EnvironmentContract(unittest.TestCase):
    def test_every_environment_input_is_bound_to_key(self):
        info=dict(os='Linux',ubuntu='24.04',image='image',architecture='X64',python='3.10.22',interpreter='/python',lock='lock',rules='rules')
        for field in info:
            changed=dict(info);changed[field]+='different';self.assertNotEqual(env.cache_key(info),env.cache_key(changed))

    def test_tampering_or_wrong_environment_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'package.py').write_text('original')
            info={'python':'3.10.22'}
            (root/env.MARKER).write_text(json.dumps(dict(schema=1,descriptor=info,key=env.cache_key(info),files_sha256=env.files_digest(root))))
            with patch.object(env.subprocess,'check_output',return_value='3.10.22\n'):env.validate(root,info)
            with self.assertRaises(AssertionError):env.validate(root,{'python':'3.10.21'})
            (root/'package.py').write_text('tampered')
            with self.assertRaises(AssertionError):env.validate(root,info)

    def test_compiled_package_code_is_also_integrity_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cache=root/'__pycache__';cache.mkdir()
            bytecode=cache/'module.pyc';bytecode.write_bytes(b'original bytecode')
            before=env.files_digest(root);bytecode.write_bytes(b'corrupt bytecode')
            self.assertNotEqual(before,env.files_digest(root))

    def test_cache_miss_and_corruption_install_the_entire_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'venv';root.mkdir();(root/'unexpected').write_text('bad')
            with patch.object(env,'environment_path',return_value=root),patch.object(env,'descriptor',return_value={}),patch.object(env,'validate',side_effect=AssertionError('bad')),patch.object(env.subprocess,'run') as run:
                env.prepare()
                self.assertFalse((root/'unexpected').exists())
                commands=[c.args[0] for c in run.call_args_list]
                self.assertIn(str(env.LOCK),commands[1]);self.assertEqual(commands[1][-2],'-r')
                self.assertIn(str(env.ROOT/'scripts/verify_production_dependencies.py'),commands[2])

    def test_cache_hit_still_installs_and_verifies(self):
        with patch.object(env,'environment_path',return_value=Path('/synthetic')),patch.object(env,'descriptor',return_value={}),patch.object(env,'validate'),patch.object(env.subprocess,'run') as run:
            env.prepare();self.assertEqual(run.call_count,3)
            self.assertIn(str(env.LOCK),run.call_args_list[0].args[0])

    def test_cache_first_miss_defers_all_installation_until_download_cache_recovery(self):
        with patch.object(env,'environment_path',return_value=Path('/synthetic')),patch.object(env,'descriptor',return_value={}),patch.object(env,'validate',side_effect=AssertionError('corrupt')),patch.object(env.subprocess,'run') as run:
            self.assertFalse(env.prepare(cache_only=True));run.assert_not_called()

    def test_cache_first_hit_checks_integrity_and_installs_full_lock_once(self):
        with patch.object(env,'environment_path',return_value=Path('/synthetic')),patch.object(env,'descriptor',return_value={}),patch.object(env,'validate') as verify,patch.object(env.subprocess,'run') as run:
            self.assertTrue(env.prepare(cache_only=True));verify.assert_called_once();self.assertEqual(run.call_count,3)
            self.assertIn(str(env.LOCK),run.call_args_list[0].args[0])

    def test_cached_install_failure_cannot_emit_ready_success(self):
        import subprocess
        with patch.object(env,'environment_path',return_value=Path('/synthetic')),patch.object(env,'descriptor',return_value={}),patch.object(env,'validate'),patch.object(env.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'install')):
            with self.assertRaises(subprocess.CalledProcessError):env.prepare(cache_only=True)

    def test_pr_cannot_seal_or_delete_shared_cache(self):
        with patch.dict(os.environ,{'GITHUB_REF':'refs/pull/2/merge','GITHUB_EVENT_NAME':'pull_request'},clear=True):
            with self.assertRaises(AssertionError):env.seal()
            with self.assertRaises(AssertionError):env.prune()

    def test_cleanup_deletes_only_owned_main_cache_keys(self):
        info={};key=env.cache_key(info)
        entries={'actions_caches':[dict(id=1,key=key),dict(id=2,key=env.PREFIX+'old'),dict(id=3,key='unrelated-pip')]}
        with patch.dict(os.environ,{'GITHUB_REF':'refs/heads/main','GITHUB_REPOSITORY':'owner/repo'},clear=True),patch.object(env,'descriptor',return_value=info),patch.object(env.subprocess,'check_output',return_value=json.dumps(entries)),patch.object(env.subprocess,'run') as run:
            env.prune();self.assertEqual(run.call_count,2)
            self.assertNotIn('3',run.call_args_list[-1].args[0][-1].split('/')[-1])


if __name__=='__main__':unittest.main()
