"""Exercise public default forwarders through the real owned workflow classes."""
from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def auto_method(case, owner, name, callback):
    from local_inspection_service.training.auto_optimization_initialization import AutoOptimizationInitialization
    from local_inspection_service.training.auto_optimization_capture import AutoOptimizationCapture
    from local_inspection_service.training.auto_optimization_dataset import AutoOptimizationDataset
    from local_inspection_service.training.auto_optimization_mask_prompts import AutoOptimizationMaskPrompts
    from local_inspection_service.training.auto_optimization_mask_visuals import AutoOptimizationMaskVisuals
    from local_inspection_service.training.auto_optimization_mask_verification import AutoOptimizationMaskVerification
    from local_inspection_service.training.auto_optimization_label_generation import AutoOptimizationLabelGeneration
    from local_inspection_service.training.auto_optimization_readiness import AutoOptimizationReadiness
    from local_inspection_service.training.auto_optimization_requests import AutoOptimizationRequests
    from local_inspection_service.training.auto_optimization_rendering import AutoOptimizationRendering
    from local_inspection_service.training.auto_optimization_sprites import AutoOptimizationSprites
    from local_inspection_service.training.auto_optimization_sprite_publication import AutoOptimizationSpritePublication
    from local_inspection_service.training.auto_optimization_state_store import AutoOptimizationStateStore
    from local_inspection_service.training.auto_optimization_status import AutoOptimizationStatus
    from local_inspection_service.training.auto_optimization_synthetic_batch import AutoOptimizationSyntheticBatch
    assert type(owner) in (
        AutoOptimizationInitialization, AutoOptimizationCapture, AutoOptimizationDataset,
        AutoOptimizationMaskPrompts, AutoOptimizationMaskVisuals, AutoOptimizationMaskVerification,
        AutoOptimizationLabelGeneration, AutoOptimizationReadiness, AutoOptimizationRequests,
        AutoOptimizationRendering, AutoOptimizationSprites, AutoOptimizationSpritePublication,
        AutoOptimizationStateStore, AutoOptimizationStatus, AutoOptimizationSyntheticBatch,
    )

    def selected(receiver, *args, **kwargs):
        case.assertIs(receiver, owner)
        return callback(*args, **kwargs)

    with patch.object(type(owner), name, autospec=True, side_effect=selected):
        yield


@contextmanager
def auto_port(owner, name, replacement):
    from local_inspection_service.training.auto_optimization_state_store import AutoOptimizationStateStore
    from local_inspection_service.training.auto_optimization_capture import AutoOptimizationCapture
    from local_inspection_service.training.auto_optimization_status import AutoOptimizationStatus
    allowed = {
        AutoOptimizationStateStore: {'storage', 'policy', 'cache'},
        AutoOptimizationCapture: {'ports'},
        AutoOptimizationStatus: {'policy'},
    }
    assert name in allowed[type(owner)]
    original = getattr(owner, name)
    assert type(replacement) is type(original)
    try:
        object.__setattr__(owner, name, replacement)
        yield
    finally:
        object.__setattr__(owner, name, original)


def assert_extra_auto_port(case, server, port, name):
    """Finite witnesses for capture admission and sprite file publication."""
    from pathlib import Path
    from local_inspection_service.training.auto_optimization_capture_ports import AutoOptimizationCapturePorts
    from local_inspection_service.training.auto_optimization_sprite_publication_ports import SpritePublication
    from auto_optimization_test_ports import assert_native_relay
    from canonical_application_source_contract import verify_actual_sources
    verify_actual_sources()
    paths=server._service_paths
    def target(owner, method, args, kwargs=None):
        kwargs={} if kwargs is None else kwargs
        return owner,method,args,kwargs,args,kwargs
    sprite = {
        'safe_record_id': target(server._pose_collection_jobs,'safe_record_id',('record-A',)),
        'write_clean_sprite': target(server._sprite_artifact_writer,'write_clean_sprite',
            (Path('sprite-A'),object(),object(),{})),
        'resolve_service_path': target(paths,'resolve_service_path',('source-A',),{'for_write':False}),
        'public_output_url_for_existing': target(paths,'public_output_url_for_existing',(Path('source-A'),)),
        'public_path_sanitized': target(paths,'public_path_sanitized',('source-A',)),
    }
    capture = {
        'load_auto_optimize_state': target(server._auto_optimization_state_store,'load_auto_optimize_state',('task-A',)),
        'save_auto_optimize_state': target(server._auto_optimization_state_store,'save_auto_optimize_state',({},)),
        'auto_optimize_completed_model_id': target(server._auto_optimization_readiness,'auto_optimize_completed_model_id',({},)),
        'auto_optimize_stop_capture_for_model_locked': target(server._auto_optimization_readiness,'auto_optimize_stop_capture_for_model_locked',({},'model-A'),{'reason':'fixture-A'}),
        'auto_optimize_capture_enabled': target(server._auto_optimization_readiness,'auto_optimize_capture_enabled',({},)),
        'resolve_service_path': target(paths,'resolve_service_path',('source-A',),{'for_write':False}),
        'start_auto_optimize_label_worker': target(server._auto_optimization_label_processing,'start_auto_optimize_label_worker',('task-A',)),
        'start_auto_optimize_shadow_worker': target(server._auto_optimization_shadow_evaluation,'start_auto_optimize_shadow_worker',('task-A','sample-A')),
    }
    targets={SpritePublication:sprite,AutoOptimizationCapturePorts:capture}
    selected=getattr(port,name)()
    if type(port) is AutoOptimizationCapturePorts and name=='current_owner_fields':
        case.assertIs(selected.__self__,server._record_access)
        case.assertIs(selected.__func__,type(server._record_access).current_owner_fields)
        return
    if name in targets[type(port)]:
        witness=targets[type(port)][name]
        # Resolve forwards its keyword default even when the caller omits it.
        if name=='resolve_service_path':
            witness=(*witness[:3],{},*witness[4:])
        assert_native_relay(case,selected,witness)
    else:
        case.assertIs(selected,getattr(server,name))
