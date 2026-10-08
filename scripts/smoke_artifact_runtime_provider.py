"""Freeze selector behavior and exercise independent artifact owner concurrency."""
import asyncio
import hashlib
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.artifacts import runtime as module
from local_inspection_service.storage.artifacts.runtime import ArtifactRuntime, ArtifactRuntimeProvider

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'tests/backend_contract/artifact_runtime_baseline.py'
BASELINE_SHA = '06d114318408d4258481af950b85a0dbe250ed0968feb6409f97569284c32852'
REQUIRED = ('VANTALINE_DATA_ROOT', 'VANTALINE_ARTIFACT_WORK_ROOT', 'VANTALINE_ARTIFACT_CACHE_ROOT',
            'VANTALINE_COS_BUCKET', 'DATABASE_URL', 'CREDENTIALS_DIRECTORY')


def configuration():
    return {'VANTALINE_FILE_STORE': 'cos', **{key: 'synthetic-' + str(i) for i, key in enumerate(REQUIRED)}}


def selected():
    return ArtifactRuntime(object(), Path('/synthetic-root'), 'cos')


def frozen(environment, builder):
    source = BASELINE.read_bytes()
    if hashlib.sha256(source).hexdigest() != BASELINE_SHA:
        raise AssertionError('Artifact runtime baseline changed')
    namespace = {'os': SimpleNamespace(environ=environment), 'threading': threading,
                 'ArtifactRuntime': ArtifactRuntime, 'build_runtime': builder}
    exec(compile(source, str(BASELINE), 'exec'), namespace)
    return namespace['get_runtime']


def candidate(environment, builder):
    return ArtifactRuntimeProvider(lambda: environment, builder=builder).get


class Environment(dict):
    def __init__(self, values):
        super().__init__(values); self.reads = []

    def get(self, key, default=None):
        self.reads.append((key, default))
        return super().get(key, default)


class ArtifactRuntimeProviderTests(unittest.TestCase):
    def test_original_validation_arguments_and_reads(self):
        cases = [{}, {'VANTALINE_FILE_STORE': ''}, {'VANTALINE_FILE_STORE': 'wrong'},
                 {'VANTALINE_FILE_STORE': 'cos'}, configuration(),
                 dict(configuration(), VANTALINE_FILE_STORE='hybrid'),
                 dict(configuration(), VANTALINE_ARTIFACT_HARD_LIMITS='1', VANTALINE_ARTIFACT_UPLOAD_ROOT='/synthetic-upload'),
                 dict(configuration(), VANTALINE_ARTIFACT_HARD_LIMITS='bad')]
        cases += [dict(configuration(), **{key: ''}) for key in REQUIRED]
        for values in cases:
            with self.subTest(values=values):
                observations = []
                for build in (frozen, candidate):
                    env = Environment(values); result = selected(); builder = Mock(return_value=result)
                    get = build(env, builder)
                    try:
                        answer = get()
                        outcome = 'none' if answer is None else 'same' if answer is result else 'wrong'
                    except Exception as exc:
                        outcome = type(exc), str(exc)
                    observations.append((outcome, env.reads, builder.call_args_list))
                self.assertEqual(*observations)

    def test_cached_local_bypass_and_original_configuration_reentry(self):
        for build in (frozen, candidate):
            with self.subTest(build=build.__name__):
                env = configuration(); result = selected(); builder = Mock(return_value=result)
                get = build(env, builder)
                self.assertIs(get(), result); self.assertIs(get(), result)
                env['VANTALINE_FILE_STORE'] = 'local'; env['DATABASE_URL'] = ''
                self.assertIsNone(get())
                env.update(configuration()); self.assertIs(get(), result)
                env['VANTALINE_COS_BUCKET'] += '-changed'
                with self.assertRaisesRegex(RuntimeError, 'storage configuration changed; restart is required'): get()
                builder.assert_called_once()

    def test_failed_builder_preserves_exception_and_is_not_cached(self):
        for build in (frozen, candidate):
            with self.subTest(build=build.__name__):
                failure = RuntimeError('synthetic partially completed build'); result = selected()
                effects = []
                def builder(*args, **kwargs):
                    effects.append('builder-side-effect')
                    if len(effects) == 1: raise failure
                    return result
                get = build(configuration(), builder)
                with self.assertRaises(RuntimeError) as caught: get()
                self.assertIs(caught.exception, failure)
                self.assertEqual(effects, ['builder-side-effect'])
                self.assertIs(get(), result); self.assertIs(get(), result)
                self.assertEqual(effects, ['builder-side-effect', 'builder-side-effect'])

    def test_construction_is_inert_and_environment_supplier_is_live(self):
        mappings = [{}]; environment = Mock(side_effect=lambda: mappings[0]); builder = Mock(return_value=selected())
        owner = ArtifactRuntimeProvider(environment, builder=builder)
        environment.assert_not_called(); builder.assert_not_called()
        self.assertIsNone(owner.get()); builder.assert_not_called()
        mappings[0] = configuration(); self.assertIs(owner.get(), builder.return_value)
        self.assertEqual(environment.call_count, 2)

    def test_one_owner_serializes_native_builders(self):
        entered, release = threading.Event(), threading.Event()
        calls, results, errors = [], [], []; result = selected()
        def builder(*args, **kwargs):
            calls.append(args); entered.set()
            if not release.wait(3): raise AssertionError('builder release timed out')
            return result
        owner = ArtifactRuntimeProvider(lambda: configuration(), builder=builder)
        def call():
            try: results.append(owner.get())
            except BaseException as exc: errors.append(exc)
        threads = [threading.Thread(target=call) for _ in range(8)]
        try:
            threads[0].start(); self.assertTrue(entered.wait(2))
            for thread in threads[1:]: thread.start()
        finally:
            release.set()
            for thread in threads:
                if thread.ident is not None: thread.join(2)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(errors, []); self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 8); self.assertTrue(all(value is result for value in results))

    def test_other_owner_builds_while_first_owner_is_blocked(self):
        entered, release, second_done = threading.Event(), threading.Event(), threading.Event()
        first_result, second_result = selected(), selected(); results, errors = {}, []
        def blocked(*args, **kwargs):
            entered.set()
            if not release.wait(3): raise AssertionError('builder release timed out')
            return first_result
        a = ArtifactRuntimeProvider(lambda: configuration(), builder=blocked)
        b = ArtifactRuntimeProvider(lambda: configuration(), builder=Mock(return_value=second_result))
        def call(name, owner):
            try: results[name] = owner.get()
            except BaseException as exc: errors.append(exc)
            finally:
                if name == 'b': second_done.set()
        first = threading.Thread(target=call, args=('a', a)); second = threading.Thread(target=call, args=('b', b))
        try:
            first.start(); self.assertTrue(entered.wait(2)); second.start()
            self.assertTrue(second_done.wait(2)); self.assertIs(results.get('b'), second_result)
            self.assertNotIn('a', results)
        finally:
            release.set(); first.join(2)
            if second.ident is not None: second.join(2)
        self.assertEqual(errors, []); self.assertIs(results.get('a'), first_result)
        self.assertFalse(first.is_alive()); self.assertFalse(second.is_alive())

    def test_concurrent_configuration_change_keeps_first_build_and_rejects_later_caller(self):
        for build in (frozen, candidate):
            with self.subTest(build=build.__name__):
                entered, release, second_read = threading.Event(), threading.Event(), threading.Event()
                class ChangingEnvironment(dict):
                    def get(self, key, default=None):
                        result = super().get(key, default)
                        if key == 'VANTALINE_ARTIFACT_UPLOAD_ROOT' and self['VANTALINE_COS_BUCKET'] == 'changed': second_read.set()
                        return result
                env = ChangingEnvironment(configuration()); result = selected(); results, errors, calls = {}, {}, []
                def builder(*args, **kwargs):
                    calls.append(args); entered.set()
                    if not release.wait(3): raise AssertionError('builder release timed out')
                    return result
                get = build(env, builder)
                def call(name):
                    try: results[name] = get()
                    except BaseException as exc: errors[name] = exc
                first = threading.Thread(target=call, args=('first',)); second = threading.Thread(target=call, args=('second',))
                try:
                    first.start(); self.assertTrue(entered.wait(2)); env['VANTALINE_COS_BUCKET'] = 'changed'; second.start()
                    self.assertTrue(second_read.wait(2)); self.assertNotIn('second', results)
                finally:
                    release.set(); first.join(2)
                    if second.ident is not None: second.join(2)
                self.assertFalse(first.is_alive()); self.assertFalse(second.is_alive())
                self.assertIs(results.get('first'), result); self.assertNotIn('first', errors)
                self.assertEqual(type(errors.get('second')), RuntimeError)
                self.assertEqual(str(errors['second']), 'storage configuration changed; restart is required')
                self.assertEqual(len(calls), 1)

    def test_default_entry_and_default_builder_are_late_bound(self):
        owner = ArtifactRuntimeProvider(lambda: configuration())
        result = selected()
        with patch.object(module, 'build_runtime', return_value=result) as builder, patch.object(module, '_default_provider', owner):
            self.assertIs(module.get_runtime(), result); self.assertIs(module.get_runtime(), result)
            builder.assert_called_once()
        self.assertIs(module._default_provider._environment(), os.environ)

    def test_real_owner_is_usable_as_explicit_http_upload_provider(self):
        from scripts.smoke_http_upload_runtime import Budget, HEADERS, client, shell
        async def run():
            budget = Budget(); built = ArtifactRuntime(SimpleNamespace(budget=budget), Path('/synthetic'), 'cos')
            builder = Mock(return_value=built)
            owner = ArtifactRuntimeProvider(lambda: configuration(), builder=builder)
            app = shell(owner.get); builder.assert_not_called()
            async with client(app) as c:
                for _ in range(2):
                    response = await c.post('/body', content=b'test', headers=HEADERS)
                    self.assertEqual((response.status_code, response.content), (200, b'test'))
            builder.assert_called_once(); self.assertEqual((budget.used, budget.entries, budget.exits), (0, 2, 2))
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
