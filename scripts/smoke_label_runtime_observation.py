"""Snapshot, real sampling progress and fixed-error contracts; no paid or device I/O."""
from dataclasses import replace
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from local_inspection_service.runtime.label_identity import LabelRuntimeIdentity, RuntimeUnavailable
from local_inspection_service.runtime.configuration_contract import configuration_capture
from local_inspection_service.runtime.label_observation import RuntimeObservation, RuntimeProgress, observe_progress
from local_inspection_service.runtime import observe_label_runtime


class DatabaseIdentityTests(unittest.TestCase):
    def test_peer_identity_restored_after_success_and_query_failure(self):
        import pwd
        for fail in (False, True):
            calls=[]
            with patch.object(os, 'geteuid', return_value=0), \
                 patch.object(os, 'getegid', return_value=0), \
                 patch.object(os, 'getgroups', return_value=[0, 12]), \
                 patch.object(pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1001,pw_gid=1002)) as lookup, \
                 patch.object(os, 'setgroups', side_effect=lambda value:calls.append(('groups',value))), \
                 patch.object(os, 'setegid', side_effect=lambda value:calls.append(('gid',value))), \
                 patch.object(os, 'seteuid', side_effect=lambda value:calls.append(('uid',value))):
                try:
                    with observe_label_runtime.database_identity():
                        calls.append(('query', None))
                        if fail:raise RuntimeUnavailable('synthetic query failure')
                except RuntimeUnavailable:
                    self.assertTrue(fail)
            lookup.assert_called_once_with('vantaline')
            self.assertEqual(calls,[('groups',[]),('gid',1002),('uid',1001),('query',None),('uid',0),('gid',0),('groups',[0,12])])

    def test_nonroot_or_root_service_account_never_connects(self):
        import pwd
        with patch.object(os,'geteuid',return_value=1001):
            with self.assertRaises(RuntimeUnavailable):
                with observe_label_runtime.database_identity():self.fail('identity accepted')
        with patch.object(os,'geteuid',return_value=0), patch.object(pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=0,pw_gid=0)), patch.object(os,'seteuid') as switch:
            with self.assertRaises(RuntimeUnavailable):
                with observe_label_runtime.database_identity():self.fail('root peer accepted')
            switch.assert_not_called()


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.first = RuntimeObservation("a" * 32, True, True, 3, 0,
                          (("web", "b" * 32, 11, 100), ("label", "c" * 32, 12, 100)))
        self.elapsed = 0

    def sleep(self, seconds):
        self.elapsed += seconds

    def observe(self, values, timeout=8):
        return observe_progress(Mock(side_effect=values), timeout=timeout,
                                clock=lambda: self.elapsed, sleep=self.sleep)

    def test_waits_for_both_periodic_samples_and_preserves_fence(self):
        partial = replace(self.first, roles=(self.first.roles[0], ("label", "c"*32, 12, 101)))
        final = replace(partial, queued=2, roles=(("web", "b"*32, 11, 105), partial.roles[1]))
        self.assertEqual(self.observe([self.first, self.first, partial, final]), RuntimeProgress(self.first, final))
        self.assertTrue(final.paused)
        self.assertTrue(final.maintenance)

    def test_response_clock_does_not_prove_progress(self):
        with self.assertRaisesRegex(RuntimeUnavailable, "did not progress"):
            self.observe([self.first] * 9)

    def test_restarted_process_is_rejected(self):
        for field in ("instance", "pid", "role"):
            role = list(self.first.roles[0])
            role[{"instance": 1, "pid": 2, "role": 0}[field]] = {"instance": "d"*32, "pid": 13, "role": "label"}[field]
            changed = replace(self.first, roles=(tuple(role), self.first.roles[1]))
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeUnavailable, "process changed"):
                self.observe([self.first, changed])

    def test_admission_and_control_revision_must_stay_stable(self):
        for field, value in (("revision", "d"*32), ("paused", False), ("maintenance", False)):
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeUnavailable, "admission changed"):
                self.observe([self.first, replace(self.first, **{field: value})])

    def test_regressing_sample_rejected(self):
        changed = replace(self.first, roles=(("web", "b"*32, 11, 99), self.first.roles[1]))
        with self.assertRaisesRegex(RuntimeUnavailable, "regressed"):
            self.observe([self.first, changed])

    def test_no_read_starts_at_deadline(self):
        read = Mock(return_value=self.first)
        with self.assertRaisesRegex(RuntimeUnavailable, "did not progress"):
            observe_progress(read, timeout=1, clock=lambda: self.elapsed, sleep=self.sleep)
        self.assertEqual(read.call_count, 1)

    def test_late_database_result_is_not_accepted(self):
        progressed = replace(self.first, roles=(("web", "b"*32, 11, 101), ("label", "c"*32, 12, 101)))
        def read():
            if self.elapsed:
                self.elapsed += 100
                return progressed
            return self.first
        with self.assertRaisesRegex(RuntimeUnavailable, "did not progress"):
            observe_progress(read, timeout=5, clock=lambda: self.elapsed, sleep=self.sleep)

    def test_cli_rechecks_active_generation_and_configuration(self):
        config = configuration_capture({"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "synthetic"}, "/synthetic")
        identity = LabelRuntimeIdentity("a"*40, "v2026.10.1", "external", "b"*64)
        driver = SimpleNamespace(connect=Mock(return_value=nullcontext(Mock())))
        with patch.dict(os.environ), patch.dict(sys.modules, psycopg=driver), \
                patch.object(observe_label_runtime, "database_identity", return_value=nullcontext()), \
                patch.object(observe_label_runtime.os, "geteuid", create=True, return_value=0), \
                patch.object(observe_label_runtime, "private_bytes", return_value=json.dumps(config).encode()) as config_read, \
                patch.object(observe_label_runtime, "read_identity", side_effect=[identity, replace(identity, commit="e"*40)]) as identity_read, \
                patch.object(observe_label_runtime, "observe_progress", return_value=RuntimeProgress(self.first, self.first)), \
                patch.object(observe_label_runtime, "print") as output:
            self.assertEqual(observe_label_runtime.main(["--commit", "a"*40, "--release", "v2026.10.1"]), 1)
        self.assertEqual(config_read.call_count, 2)
        self.assertEqual(identity_read.call_count, 2)
        for call in identity_read.call_args_list:
            self.assertIs(call.kwargs['object_reader'], observe_label_runtime.observation_object)
        self.assertEqual(output.call_args.args, ("Runtime database observation failed",))

    def test_cli_redacts_configuration_failure(self):
        with patch.object(observe_label_runtime.os, "geteuid", create=True, return_value=0), \
                patch.object(observe_label_runtime, "private_bytes", side_effect=ValueError("customer-password-secret")), \
                patch.object(observe_label_runtime, "print") as output:
            self.assertEqual(observe_label_runtime.main(["--commit", "a"*40, "--release", "v2026.10.1"]), 1)
        self.assertEqual(output.call_args.args, ("Runtime database observation failed",))
        self.assertEqual(output.call_args_list[0].args,
                         ("Runtime database observation stage=configuration_read reason=unavailable",))

    def test_cli_classifies_authentication_without_driver_details(self):
        class AuthenticationFailure(Exception):
            sqlstate = "28000"
        config = configuration_capture({"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "synthetic"}, "/synthetic")
        identity = LabelRuntimeIdentity("a"*40, "v2026.10.1", "external", "b"*64)
        driver = SimpleNamespace(connect=Mock(side_effect=AuthenticationFailure("customer-password-secret")))
        with patch.dict(os.environ), patch.dict(sys.modules, psycopg=driver), \
                patch.object(observe_label_runtime.os, "geteuid", create=True, return_value=0), \
                patch.object(observe_label_runtime, "private_bytes", return_value=json.dumps(config).encode()), \
                patch.object(observe_label_runtime, "read_identity", return_value=identity), \
                patch.object(observe_label_runtime, "print") as output:
            self.assertEqual(observe_label_runtime.main(["--commit", "a"*40, "--release", "v2026.10.1"]), 1)
        self.assertEqual(output.call_args_list[0].args,
                         ("Runtime database observation stage=database_connect reason=database_authentication",))
        self.assertNotIn("customer-password-secret", str(output.call_args_list))

    def run_cli_with_snapshots(self, configs):
        driver = SimpleNamespace(connect=Mock(return_value=nullcontext(Mock())))
        def identity(root, *, current, configuration_revision, object_reader):
            self.assertIs(object_reader, observe_label_runtime.observation_object)
            return LabelRuntimeIdentity("a"*40, "v2026.10.1", "external", configuration_revision())
        final = replace(self.first, roles=(("web", "b"*32, 11, 105), ("label", "c"*32, 12, 105)))
        with patch.dict(os.environ), patch.dict(sys.modules, psycopg=driver), \
                patch.object(observe_label_runtime, "database_identity", return_value=nullcontext()), \
                patch.object(observe_label_runtime.os, "geteuid", create=True, return_value=0), \
                patch.object(observe_label_runtime, "private_bytes", side_effect=[json.dumps(x).encode() for x in configs]), \
                patch.object(observe_label_runtime, "read_identity", side_effect=identity), \
                patch.object(observe_label_runtime, "observe_progress", return_value=RuntimeProgress(self.first, final)), \
                patch.object(observe_label_runtime, "print") as output:
            result = observe_label_runtime.main(["--commit", "a"*40, "--release", "v2026.10.1"])
        return result, output

    def test_cli_same_generation_success_has_both_sample_sets(self):
        config = configuration_capture({"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "synthetic"}, "/synthetic")
        result, output = self.run_cli_with_snapshots([config, config])
        self.assertEqual(result, 0)
        value = json.loads(output.call_args.args[0])
        self.assertEqual([x["sampled_at"] for x in value["samples_before"]], [100, 100])
        self.assertEqual([x["sampled_at"] for x in value["roles"]], [105, 105])
        self.assertTrue(value["periodic_progress"])
        self.assertNotIn("DATABASE_URL", output.call_args.args[0])

    def test_cli_final_configuration_revision_change_rejected(self):
        old = configuration_capture({"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "synthetic"}, "/synthetic")
        new = configuration_capture({"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "synthetic-new"}, "/synthetic")
        result, output = self.run_cli_with_snapshots([old, new])
        self.assertEqual(result, 1)
        self.assertEqual(output.call_args.args, ("Runtime database observation failed",))


if __name__ == "__main__":
    unittest.main()
