"""Exercise retained legacy dispatch with synthetic serial and persistence only."""
import ast
import asyncio
from contextlib import ExitStack
from dataclasses import fields
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = os.environ.get('VANTALINE_PLC_LEGACY_DISPATCH_BASELINE_SOURCE')
NAMES = ('dispatch_plc_for_detection', '_run_queued_plc_dispatch', 'dispatch_plc_for_detection_async')


def main():
    with ExitStack() as lifetime:
        run(lifetime)


def run(lifetime):
    if not BASELINE:
        from local_inspection_service.plc import legacy_dispatch
        assert 'local_inspection_service.server' not in sys.modules
    # This fixture creates its own temporary data/static directories before app import.
    from local_inspection_service.scripts import smoke_plc_phase1_hardening as fixture
    default = fixture.server
    if not BASELINE:
        from scripts.plc_legacy_test_composition import build
        fixture.server = build(default)
        lifetime.callback(setattr, fixture, 'server', default)
        lifetime.callback(fixture.server._plc_io_executor.shutdown, wait=True)
    server = fixture.server
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in NAMES]
        assert len(nodes) == 3
        # Original functions must see later fixture patches in the actual root namespace.
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), vars(server))
    else:
        service = server._plc_legacy_dispatch
        assert isinstance(service, legacy_dispatch.LegacyDispatch)
        for group in ('policy', 'configuration', 'records', 'execution'):
            ports = getattr(service, group)
            for field in fields(ports):
                getter = getattr(ports, field.name)
                original = getattr(server, field.name)
                assert getter() is original
                with patch.object(server, field.name, object()) as replacement:
                    assert getter() is replacement
                assert getter() is original
        for name in NAMES:
            result, source, fingerprint = {}, object(), object()
            kwargs = dict(source=source, fingerprint=fingerprint)
            if name == 'dispatch_plc_for_detection':
                kwargs['expected_generation'] = object()
            elif name.endswith('_async'):
                kwargs['inline_fake_transport'] = object()
            # The real default compatibility function must reach its actual
            # native receiver. Fixture reassignment is a separate typed seam.
            with patch.object(type(default._plc_legacy_dispatch), name, autospec=True) as callback:
                callback.return_value = object()
                outcome = getattr(default, name)(result, **kwargs)
                if name.endswith('_async'):
                    outcome = asyncio.run(outcome)
                assert outcome is callback.return_value
                callback.assert_called_once_with(default._plc_legacy_dispatch, result, **kwargs)
                assert callback.call_args.args[0] is default._plc_legacy_dispatch
                if name.endswith('_async'):
                    callback.assert_awaited_once_with(default._plc_legacy_dispatch, result, **kwargs)
        print('PASS standalone import, 43 explicit fixture capabilities and three real default forwarding identities', flush=True)

    # Legacy matrices already provide only ScriptedTransport. Supplying dependency
    # availability models that fixture, without installing or opening real serial I/O.
    with patch.object(server, 'plc_pg_coordination_available', return_value=True), \
            patch.object(server, 'plc_serial_dependency_available', return_value=True):
        for name in ('test_server_terminal_result_contract_matrix', 'test_shared_retry_policy_actual_server_matrix',
                     'test_restart_hydration_cas_and_safe_queue_adoption', 'test_pg_non_owner_queue_and_fenced_adoption',
                     'test_control_state_failures_preserve_ack_evidence', 'test_persisted_duplicate_verifier_and_runtime_paths',
                     'test_identity_and_nested_evidence_lattice'):
            getattr(fixture, name)()
            print('PASS ' + name, flush=True)
        asyncio.run(fixture.test_total_deadline_before_and_after_attempt())
        print('PASS total deadlines before and during synthetic write', flush=True)


if __name__ == '__main__':
    main()
