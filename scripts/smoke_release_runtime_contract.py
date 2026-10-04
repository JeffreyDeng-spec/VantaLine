"""Deterministic release-runtime protocol checks; no services or network."""
from pathlib import Path
import copy
import tempfile
import unittest

from release_runtime_contract import ContractError, ConsumerState, Topology, read_object

COMMIT = "a" * 40
RELEASE = "v2026.10.1"
REVISION = "b" * 32


class RuntimeContract(unittest.TestCase):
    def manifest(self, mode="embedded"):
        return {"schema": 2, "git_commit": COMMIT, "worker_mode": mode,
                "services": ["vantaline"] + (["vantaline-label-worker"] if mode == "external" else []),
                "runtime_protocol": 1}

    def state(self):
        return {"schema": 1, "git_commit": COMMIT, "release": RELEASE,
                "role": "web", "worker_mode": "embedded", "instance": "c" * 32, "pid": 123,
                "heartbeat": 50.0, "state": "ready", "control_revision": REVISION,
                "active_iterations": 2, "queued_runs": 0, "active_runs": 2,
                "maintenance": False, "config_revision": None}

    def verify(self, state, **options):
        kwargs = dict(topology=Topology.parse(self.manifest(), COMMIT), release=RELEASE,
                      pid=123, now=50.0, control_revision=REVISION)
        kwargs.update(options)
        return ConsumerState.verify(state, **kwargs)

    def test_only_fixed_topologies(self):
        legacy = {"schema": 1, "git_commit": COMMIT, "worker_mode": "embedded", "services": ["vantaline"]}
        self.assertEqual(Topology.parse(legacy, COMMIT).services, ("vantaline",))
        for mode in ("embedded", "external"):
            self.assertEqual(Topology.parse(self.manifest(mode), COMMIT).mode, mode)
        for field, value in (("schema", True), ("git_commit", "b" * 40), ("services", ["arbitrary-service"]),
                             ("worker_mode", "unknown"), ("runtime_protocol", True)):
            doc = self.manifest(); doc[field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                Topology.parse(doc, COMMIT)
        with self.assertRaises(ContractError):
            Topology.parse({**legacy, "runtime_protocol": 1}, COMMIT)

    def test_state_identity_and_monotonic_heartbeat(self):
        state = self.state()
        self.verify(state).require_ready()
        for field, value in (("schema", True), ("git_commit", "d" * 40), ("release", "v2026.09.0"),
                             ("role", "external"), ("instance", "bad"), ("pid", True),
                             ("pid", 456), ("heartbeat", 39.0), ("heartbeat", 52.0),
                             ("heartbeat", float('nan')), ("heartbeat", True),
                             ("control_revision", "f" * 32), ("active_iterations", True),
                             ("active_iterations", 3), ("state", "unknown")):
            altered = copy.deepcopy(state); altered[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ContractError):
                self.verify(altered)
        with self.assertRaises(ContractError):
            self.verify(state, expected_instance="d" * 32)
        with self.assertRaises(ContractError):
            self.verify({**state, "sensitive_extra": "must not propagate"})

    def test_failure_or_timeout_is_never_drained(self):
        for state_name in ("ready", "draining", "failed", "timed_out"):
            state = self.state(); state.update(state=state_name, active_iterations=0)
            with self.subTest(state=state_name), self.assertRaises(ContractError):
                self.verify(state).require_drained()
        state = self.state(); state['state'] = 'drained'
        with self.assertRaises(ContractError):
            self.verify(state)
        state['active_iterations'] = 0
        self.verify(state).require_drained()
        with self.assertRaises(ContractError):
            self.verify(state).require_ready()

    def test_input_is_bounded_and_errors_do_not_leak(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runtime.json'
            for content in ('sensitive-synthetic-token', '[1]', ' ' * 16385):
                path.write_text(content, encoding='utf-8')
                with self.assertRaises(ContractError) as error:
                    read_object(path)
                self.assertNotIn('sensitive', str(error.exception))
                self.assertNotIn(directory, str(error.exception))
            path.write_text('{}', encoding='utf-8')
            self.assertEqual(read_object(path), {})


if __name__ == '__main__':
    unittest.main()
