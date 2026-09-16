"""Exercise relocated functions, independent runtimes and async snapshot scope."""
import asyncio
import copy
import json
import sys
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.model_profiles.snapshots import pinned, freeze_record
from local_inspection_service.model_profiles.audit import metered, metered_function
from local_inspection_service.model_profiles.service import fingerprint_sources, Service
from local_inspection_service.model_profiles.dependencies import ProfileDependencies


class Resolver:
    def __init__(self, version):
        self.version = version
        self.calls = []
        self._scope = ContextVar('fixture_scope', default=None)

    def current_snapshot(self):
        return self._scope.get()

    def snapshot_for_record(self, record):
        return {'pipeline': {'version': self.version, 'id': 'synthetic'}}

    @contextmanager
    def scope(self, snapshot):
        token = self._scope.set(snapshot)
        try:
            yield
        finally:
            self._scope.reset(token)

    def record_call(self, *args):
        self.calls.append(args)


def main():
    first, second = Resolver(1), Resolver(200)
    record = freeze_record(lambda: first, {'created_at': 1})
    original = copy.deepcopy(record)
    original['model_profiles']['pipeline']['prompt_version'] = 'source-sha256:historical-fixture'
    record = copy.deepcopy(original)
    first.version = 2
    records = {'old': record}

    @pinned(lambda: first, records.get)
    def resumed(identity='old'):
        return first.current_snapshot()

    # Moving source does not require registering its module or a loader name.
    resumed.__wrapped__.__module__ = 'a.module.that.does.not.exist'
    assert resumed() == original['model_profiles']
    assert resumed(identity='old') == original['model_profiles']
    assert record == original
    assert first.current_snapshot() is None
    empty = {'model_profiles': {}}
    assert freeze_record(lambda: first, empty) == empty
    assert pinned(lambda: first)(lambda value: first.current_snapshot())(empty) == {}
    with first.scope(original['model_profiles']):
        nested = pinned(lambda: second)(lambda: second.current_snapshot())()
        assert nested['pipeline']['version'] == 200
        assert freeze_record(lambda: second, {})['model_profiles']['pipeline']['version'] == 200
        assert first.current_snapshot() == original['model_profiles']
    assert second.current_snapshot() is None
    # Use the real Service implementation for nested instance scope isolation.
    dependencies = ProfileDependencies(lambda:None, lambda *a:None, lambda key:'',
        lambda:[], lambda value:None, lambda value:None, lambda value:value)
    service_a, service_b = Service(dependencies), Service(dependencies)
    with service_a.scope({'pipeline': {'version': 10}}):
        assert service_b.current_snapshot() is None
        with service_b.scope({'pipeline': {'version': 20}}):
            assert service_a.current_snapshot()['pipeline']['version'] == 10
            assert service_b.current_snapshot()['pipeline']['version'] == 20
    assert service_a.current_snapshot() is service_b.current_snapshot() is None

    manifest_path = Path(__file__).resolve().parents[1] / 'local_inspection_service/model_profiles/prompt_sources.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert {'label_inspection/manual.py', 'evidence_matching.py', 'accessories/policy.py'} <= set(manifest['sources'])
    with tempfile.TemporaryDirectory(prefix='model-source-contract-') as directory:
        root = Path(directory)
        for name in manifest['sources']:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic original', encoding='utf-8')
        baseline = fingerprint_sources(root, manifest)
        for name in manifest['sources']:
            path = root / name
            path.write_text('synthetic changed', encoding='utf-8')
            assert fingerprint_sources(root, manifest) != baseline, name
            path.write_text('synthetic original', encoding='utf-8')
        assert fingerprint_sources(root, {**manifest, 'version': manifest['version'] + 1}) != baseline
    assert freeze_record(lambda: first, record) == original

    @pinned(lambda: None)
    def unconfigured():
        raise AssertionError('must fail before provider work')

    try:
        unconfigured()
    except RuntimeError as error:
        assert str(error) == 'Model profile resolver is not configured'
    else:
        raise AssertionError('missing resolver bypassed binding')
    try:
        pinned(lambda: first, 'load_task')
    except TypeError:
        pass
    else:
        raise AssertionError('string namespace lookup accepted')

    async def concurrency():
        async def work(resolver, version, fail=False):
            @pinned(lambda: resolver)
            async def task(value):
                await asyncio.sleep(0)
                # Native thread-pool context propagation, no TestClient shim.
                result = await asyncio.to_thread(lambda: copy.deepcopy(resolver.current_snapshot()))
                assert result['pipeline']['version'] == version
                if fail:
                    raise ValueError('synthetic worker error')
                return result
            try:
                return await task({'model_profiles': {'pipeline': {'version': version}}})
            finally:
                assert resolver.current_snapshot() is None
        results = await asyncio.gather(work(first, 1), work(second, 200), work(first, 3, True), return_exceptions=True)
        assert results[0]['pipeline']['version'] == 1
        assert results[1]['pipeline']['version'] == 200
        assert isinstance(results[2], ValueError)
    asyncio.run(concurrency())

    class Provider:
        settings = {'profile_id': 'synthetic'}
        @metered(lambda: first)
        def generate(self):
            return {'usage': {'total_tokens': 2}}
    Provider.generate.__wrapped__.__module__ = 'moved.provider'
    assert Provider().generate()['usage']['total_tokens'] == 2
    assert len(first.calls) == 1 and len(second.calls) == 0

    transports = []
    @metered_function()
    def direct(settings, *, record_usage=None):
        transports.append(1)
        return {}, {'usage': {'total_tokens': 3}}
    try:
        direct(Provider.settings)
    except RuntimeError:
        pass
    else:
        raise AssertionError('profile transport accepted a missing recorder')
    assert not transports
    direct(Provider.settings, record_usage=second.record_call)
    assert len(first.calls) == 1 and len(second.calls) == 1
    def unavailable(*args):
        raise RuntimeError('ledger unavailable')
    direct(Provider.settings, record_usage=unavailable)
    assert len(transports) == 2  # accounting failure cannot replay inference
    print('PASS explicit model dependencies, old/default/empty snapshots, async thread scope, isolation and no accounting replay')


if __name__ == '__main__':
    main()
