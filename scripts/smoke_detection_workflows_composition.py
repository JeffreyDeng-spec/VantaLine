"""Exercise the real owned detection/publication/capture graph with synthetic I/O."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from contextvars import ContextVar
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
import sys
import ast
import json
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from local_inspection_service.detection.workflow_composition import (
    DetectionWorkflows, AnalysisAssembly, AnalysisPublication, CaptureAdmission,
    InspectionEvidence, DetectionPolicy, DetectionFeedback,
)
from local_inspection_service.analytics.analysis_composition import AnalysisStorage
from local_inspection_service.analytics.analysis_records import AnalysisNormalization
from local_inspection_service.analytics.analysis_service import AnalysisAccess
from local_inspection_service.analytics.analysis_processing import ProcessingDependencies
from local_inspection_service.analytics.analysis_scope import ScopeDependencies
from local_inspection_service.analytics.analysis_projection import ProjectionDependencies
from local_inspection_service.detection.analysis_ports import (
    AiProfiles, AiInspectionTools, AnalysisInput, AnalysisInference, AnalysisOutput,
)
from local_inspection_service.training.auto_optimization_capture import AutoOptimizationCapture
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable, ArtifactConflict
from smoke_ai_detection_analysis import AiAnalysisFixture
from smoke_detection_analysis import AnalysisFixture
from smoke_analysis_records import normalizer


def port(cls, **overrides):
    values = {f.name: ('default' if f.name.startswith('default_task_') else
                        Mock(side_effect=AssertionError('unexpected external capability: ' + f.name)))
              for f in fields(cls)}
    values.update(overrides)
    return cls(**values)


def compose(root, owner, feedback=DetectionFeedback()):
    f = AiAnalysisFixture()
    ordinary = AnalysisFixture(root)
    f.config.update(image_size=96, confidence_threshold=.2)
    ordinary.scoped = f.config
    ordinary.spec = {'id': 'teacher', 'is_ai_detection': True, 'task_id': 'same-task'}
    ordinary.sanitize.side_effect = lambda value: str(value)
    state = {'settings': {'enabled': True}, 'samples': []}
    ordinary.state_load.side_effect = lambda task: state
    events = []
    identity = ContextVar('detection-owner-' + owner, default={'id': owner})
    capture_lock = threading.RLock()
    path = Path(root) / 'analysis.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    f.model_payload = {'id': 'teacher', 'is_ai_detection': True, 'task_id': 'same-task'}
    f.detections[:] = [{'accessory_id': 'a', 'present': True, 'confidence': .9}]
    original_tool = f.tool.side_effect
    f.tool.side_effect = lambda *a, **k: events.append('tool') or original_tool(*a, **k)
    publication = port(AnalysisPublication,
        current_user=lambda: identity.get(),
        owner_fields=lambda: {'owner_user_id': identity.get()['id'], 'owner_username': owner},
        clean_task_name=lambda value, fallback: str(value or fallback),
        string_list=lambda value, **kw: list(value or []), resolve_path=lambda p: p,
        safe_name=lambda name: name, output_url=lambda p: str(p))
    assembly = AnalysisAssembly(normalizer().__self__.dependencies,
        AnalysisStorage(lambda: path, lambda: None, lambda: events.append('store')),
        port(AnalysisAccess), port(ProcessingDependencies), port(ScopeDependencies),
        port(ProjectionDependencies), publication, nullcontext, 17)
    def save(current):
        assert current is state
        events.append('capture-save')
    def load_capture(task):
        assert len(json.loads(path.read_text())['records']) == 1
        events.append('capture-load')
        return state
    capture = CaptureAdmission(lambda: capture_lock, lambda: load_capture,
        lambda: save, lambda: str, lambda: lambda current: '',
        lambda: lambda *a, **k: None, lambda: lambda current: current['settings']['enabled'],
        lambda: lambda p: p, lambda: lambda v, n: str(v)[:n],
        lambda: lambda: {'owner_user_id': identity.get()['id'], 'owner_username': owner},
        lambda: lambda task: events.append('label-start'),
        lambda: lambda task, sample: events.append('shadow-start'))
    graph = DetectionWorkflows(analysis=assembly, capture=capture,
        profiles=AiProfiles(f.required, f.uid, f.normalize, f.refs, f.payload, f.save),
        tools=AiInspectionTools(lambda: f.tool, lambda: f.settings, f.external, f.mcp_image,
                                lambda: 0, lambda: 512, lambda: 80),
        evidence=InspectionEvidence(f.original, f.failure, f.model),
        inputs=AnalysisInput(ordinary.load, lambda: ordinary.scope, ordinary.selected,
                             lambda: ordinary.sanitize, ordinary.state_load),
        policy=DetectionPolicy(ordinary.retired, lambda: ordinary.text),
        inference=AnalysisInference(lambda: ordinary.model, ordinary.device, ordinary.parse,
                                     ordinary.ocr, ordinary.apply, ordinary.draw),
        output=AnalysisOutput(ordinary.directory, lambda: ordinary.resize, lambda: 640,
                               lambda: ordinary.backend, lambda: 87, ordinary.url),
        runtime_provider=lambda: None, resolver=lambda: f.resolver, feedback=feedback)
    return SimpleNamespace(graph=graph, ai=f, ordinary=ordinary, state=state, events=events,
                           identity=identity, path=path)


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='detection-owned-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.no_paid = patch('requests.sessions.Session.request', side_effect=AssertionError('real provider'))
        self.no_paid.start(); self.addCleanup(self.no_paid.stop)
        self.no_process = patch('subprocess.Popen', side_effect=AssertionError('real process'))
        self.no_process.start(); self.addCleanup(self.no_process.stop)

    def run_graph(self, f, request='same-request'):
        return f.graph.analyze_bgr(f.ai.image, request, 'teacher', image_path=Path('synthetic.png'))

    def test_latest_main_feedback_is_owned_and_runs_after_record_persistence(self):
        for owner in ('alice', 'bob'):
            captured = []
            local = Mock()
            def capture(record, result, request_id, image_path):
                captured.append((record, result, request_id, image_path))
                return True
            f = compose(self.root / owner, owner, DetectionFeedback(local, capture))
            self.assertIs(f.graph.ai.feedback, local)
            self.assertIs(f.graph.detection.feedback, local)
            self.assertIs(f.graph.capture.feedback_capture, capture)
            local.assert_not_called()
            result = self.run_graph(f)
            rows = f.graph.analysis.repository.load_data_analysis_records()
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0][0]['owner_user_id'], owner)
            self.assertEqual(captured[0][0]['record_id'], rows[0]['record_id'])
            self.assertIs(captured[0][1], result)
            local.assert_called_once_with(result, 'same-request', Path('synthetic.png'), f.ai.image)
            self.assertEqual(f.state['samples'], [])
            self.assertNotIn('label-start', f.events)
            self.assertNotIn('shadow-start', f.events)

    def test_parent_derived_wiring_and_wrong_external_port_rejection(self):
        source = (ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8')
        fixture = json.loads((ROOT/'tests/backend_contract/detection_workflows_ports.json').read_text())
        def check(text):
            tree = ast.parse(text)
            calls = [n for n in ast.walk(tree) if isinstance(n,ast.Call)
                     and isinstance(n.func,ast.Name) and n.func.id=='DetectionWorkflows']
            self.assertEqual(len(calls),1)
            actual = {k.arg:k.value for k in calls[0].keywords}
            self.assertEqual(set(actual),set(fixture['expressions']))
            for name,expression in fixture['expressions'].items():
                self.assertEqual(ast.dump(actual[name]),ast.dump(ast.parse(expression,mode='eval').body),name)
            for name,member in [('_analysis','analysis'),('_auto_optimization_capture','capture'),
                                ('_ai_detection_analysis','ai'),('_detection_analysis','detection')]:
                nodes = [n for n in tree.body if isinstance(n,ast.Assign)
                         and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
                self.assertEqual(len(nodes),1)
                self.assertEqual(ast.dump(nodes[0].value),ast.dump(ast.parse('_detection_workflows.'+member,mode='eval').body))
        check(source)
        for mutation in ['resolver','evidence','alias']:
            tree=ast.parse(source)
            graph=next(n for n in ast.walk(tree) if isinstance(n,ast.Call)
                       and isinstance(n.func,ast.Name) and n.func.id=='DetectionWorkflows')
            if mutation=='resolver':
                next(k for k in graph.keywords if k.arg=='resolver').value=ast.parse('lambda: None',mode='eval').body
            elif mutation=='evidence':
                evidence=next(k.value for k in graph.keywords if k.arg=='evidence')
                next(k for k in evidence.keywords if k.arg=='original').value=ast.parse('lambda image, request_id: write_mcp_inspection_image(image, request_id)',mode='eval').body
            else:
                binding=next(n for n in tree.body if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id=='_analysis' for t in n.targets))
                binding.value.attr='capture'
            ast.fix_missing_locations(tree)
            with self.assertRaises(AssertionError):check(ast.unparse(tree))

    def test_inert_constructor_with_all_external_capabilities_poisoned(self):
        poison = Mock(side_effect=AssertionError('constructor external access'))
        assembly = AnalysisAssembly(port(AnalysisNormalization), port(AnalysisStorage),
            port(AnalysisAccess), port(ProcessingDependencies), port(ScopeDependencies),
            port(ProjectionDependencies), port(AnalysisPublication), poison, 17)
        graph = DetectionWorkflows(analysis=assembly, capture=port(CaptureAdmission),
            profiles=port(AiProfiles), tools=port(AiInspectionTools), evidence=port(InspectionEvidence),
            inputs=port(AnalysisInput), policy=port(DetectionPolicy), inference=port(AnalysisInference),
            output=port(AnalysisOutput), runtime_provider=poison, resolver=poison)
        poison.assert_not_called()
        self.assertEqual(graph.capture.ports.auto_optimize_detection_candidates(),
                         graph.capture.auto_optimize_detection_candidates)
        self.assertIs(graph.analysis.publisher.repository, graph.analysis.repository)

    def test_actual_graph_records_before_capture_and_launches_once(self):
        f = compose(self.root, 'alice')
        result = self.run_graph(f)
        rows = f.graph.analysis.repository.load_data_analysis_records()
        self.assertTrue(result['passed']); self.assertEqual(f.ai.tool.call_count, 1)
        self.assertEqual(len(f.ai.resolver.scopes), 1)
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['owner_user_id'], 'alice')
        self.assertEqual(len(f.state['samples']), 1)
        self.assertEqual(f.state['samples'][0]['record_id'], rows[0]['record_id'])
        self.assertLess(f.events.index('store'), f.events.index('capture-save'))
        self.assertEqual(f.events.count('capture-load'), 2)
        self.assertEqual([e for e in f.events if e.endswith('start')], ['label-start', 'shadow-start'])

    def test_persistence_failure_prevents_capture_and_does_not_retry_tool(self):
        f = compose(self.root, 'alice'); failure = OSError('synthetic publication failure')
        with patch.object(f.graph.analysis.repository, 'save_data_analysis_record', side_effect=failure):
            with self.assertRaises(OSError) as caught: self.run_graph(f)
        self.assertIs(caught.exception, failure)
        self.assertEqual(f.ai.tool.call_count, 1); self.assertEqual(f.state['samples'], [])
        self.assertNotIn('label-start', f.events); self.assertNotIn('shadow-start', f.events)

    def test_capture_launch_failure_retains_record_and_sample(self):
        f = compose(self.root, 'alice'); failure = RuntimeError('synthetic label start failure')
        ports = replace(f.graph.capture.ports,
            start_auto_optimize_label_worker=lambda: Mock(side_effect=failure))
        with patch.object(f.graph, 'capture', AutoOptimizationCapture(ports)):
            with self.assertRaises(RuntimeError) as caught: self.run_graph(f)
        self.assertIs(caught.exception, failure); self.assertTrue(f.path.exists())
        self.assertEqual(len(f.state['samples']), 1); self.assertNotIn('shadow-start', f.events)
        self.assertEqual(f.ai.tool.call_count, 1)

    def test_model_scope_survives_configuration_change_and_restores_on_failure(self):
        f = compose(self.root, 'alice'); old = {'pipeline': {'version': 1, 'secret_ref': 'synthetic'}}
        with f.ai.resolver.scope(old):
            f.ai.resolver.version = 2
            self.run_graph(f)
            self.assertEqual(f.ai.resolver.current_snapshot(), old)
        self.assertIsNone(f.ai.resolver.current_snapshot())
        self.assertTrue(all(e[3] == old for e in f.ai.events))
        with patch.object(f.ai, 'resolver', None):
            before = f.ai.tool.call_count
            with self.assertRaises(RuntimeError): self.run_graph(f)
            self.assertEqual(f.ai.tool.call_count, before)

    def test_promoted_success_uses_owned_recursion_without_teacher_or_capture(self):
        f = compose(self.root, 'alice')
        f.state['settings']['serving_mode'] = 'promoted_yolo'
        f.state['active_model_id'] = 'student'
        f.ordinary.selected.side_effect = lambda model, config: ({'id':'student','label':'Student'}
            if model == 'student' else {'id':'teacher','is_ai_detection':True,'task_id':'same-task'})
        result = self.run_graph(f)
        self.assertFalse(result['ai_auto_optimize']['fallback_used'])
        self.assertEqual(result['model']['id'], 'student')
        self.assertEqual(f.ordinary.predict.call_count, 1)
        self.assertEqual([c.args[0] for c in f.ordinary.selected.call_args_list], ['teacher','student'])
        f.ai.tool.assert_not_called(); self.assertFalse(f.path.exists())
        self.assertEqual(f.state['samples'], []); self.assertEqual(f.ai.resolver.scopes, [])

    def test_promoted_failure_uses_owned_teacher_once_and_artifact_failure_never_falls_back(self):
        for exception in (OSError('student unavailable'), ArtifactUnavailable('artifact unavailable'), ArtifactConflict('artifact conflict')):
            f = compose(self.root / type(exception).__name__, 'alice')
            f.state['settings']['serving_mode'] = 'promoted_yolo'
            f.state['active_model_id'] = 'student'
            f.ordinary.selected.side_effect = lambda model, config: ({'id': 'student', 'label': 'Student'}
                if model == 'student' else {'id': 'teacher', 'is_ai_detection': True, 'task_id': 'same-task'})
            f.ordinary.predict.side_effect = exception
            if isinstance(exception, (ArtifactUnavailable, ArtifactConflict)):
                with self.assertRaises(type(exception)) as caught: self.run_graph(f)
                self.assertIs(caught.exception, exception); f.ai.tool.assert_not_called()
                self.assertFalse(f.path.exists())
            else:
                result = self.run_graph(f)
                self.assertTrue(result['ai_auto_optimize']['fallback_used'])
                self.assertEqual(f.ai.tool.call_count, 1); self.assertEqual(len(f.state['samples']), 1)
            self.assertEqual(f.ordinary.predict.call_count, 1)

    def test_two_actual_graphs_concurrent_same_ids_keep_identity_records_and_scopes(self):
        a, b = compose(self.root / 'a', 'alice'), compose(self.root / 'b', 'bob')
        barrier = threading.Barrier(2)
        def run(f):
            previous = f.ai.tool.side_effect
            def tool(*args, **kw): barrier.wait(3); return previous(*args, **kw)
            f.ai.tool.side_effect = tool
            return self.run_graph(f)
        with ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(run, [a, b]))
        self.assertTrue(all(result['passed'] for result in outcomes))
        for f, owner in ((a, 'alice'), (b, 'bob')):
            rows = f.graph.analysis.repository.load_data_analysis_records()
            self.assertEqual([r['owner_user_id'] for r in rows], [owner])
            self.assertEqual(f.state['samples'][0]['owner_user_id'], owner)
            self.assertIsNone(f.ai.resolver.current_snapshot())
        self.assertIsNot(a.graph.analysis.lock, b.graph.analysis.lock)
        self.assertIsNot(a.graph.capture, b.graph.capture)


if __name__ == '__main__': unittest.main()
