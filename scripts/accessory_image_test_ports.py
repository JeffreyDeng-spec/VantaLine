"""Replace actual image-domain operation ports, preserving original assertions."""
import ast
from contextlib import contextmanager
from types import ModuleType
from pathlib import Path
from local_inspection_service.accessories import image_composition


def queue_target(server,name):
    owner=server._image_jobs
    targets={
        '_candidate_store_lock':(owner,'lock'),
        'load_accessory_candidate':(owner.candidates,'load_accessory_candidate'),
        'save_accessory_candidate':(owner.candidates,'save_accessory_candidate'),
        'list_accessory_candidate_records':(owner.candidates,'list_accessory_candidate_records'),
        'ensure_image_job_task_id':(image_composition,'ensure_image_job_task_id'),
        'ensure_candidate_image_job_task_ids':(owner.metadata,'ensure_candidate_image_job_task_ids'),
        'candidate_image_jobs':(image_composition,'candidate_image_jobs'),
        'store_candidate_image_job':(owner.metadata,'store_candidate_image_job'),
        'image_job_output_path':(owner.diagnostics,'image_job_output_path'),
        '_image_worker_runtime':(owner,'worker'),
        'next_queued_image_job':(owner.queue,'next_queued_image_job'),
        'update_image_worker_status':(owner.queue,'update_image_worker_status'),
        'run_image_generation_job':(owner,'run_image_generation_job'),
    }
    if hasattr(server,'_default_application'):
        from local_inspection_service.runtime.wiring import inspection
        targets.update({
            'CONFIG_PATH':(server._default_application.values,'CONFIG_PATH'),
            'IMAGE_JOB_QUEUED_STATUSES':(server._default_application.values,'IMAGE_JOB_QUEUED_STATUSES'),
            'MAX_PARALLEL_IMAGE_WORKERS':(server._default_application.values,'MAX_PARALLEL_IMAGE_WORKERS'),
            '_business_files':(server._default_application.artifacts,'files'),
            'HTTPException':(inspection,'HTTPException'),
            'file_stem_identifier':(inspection,'file_stem_identifier'),
        })
    return targets.get(name,(server,name))


def assert_queue_relay(test, server, name, getter):
    """Witness only the enumerated native external callbacks."""
    from unittest.mock import patch
    targets={
        'load_config':(server._app_configuration,'load_config',(),{}),
        'save_config':(server._app_configuration,'save_config',({},),{}),
        'runtime_postgres_repository_or_none':(server._runtime_repository_access,'runtime_postgres_repository_or_none',(),{}),
        'accessory_uid':(server._accessory_policy,'accessory_uid',({},),{}),
        'accessory_material_type':(server._accessory_policy,'accessory_material_type',({},),{}),
        'ensure_pose_collection_image_jobs':(server._pose_collection_jobs,'ensure_pose_collection_image_jobs',({},),{}),
        'public_output_url':(server._service_paths,'public_output_url',(Path('/fixture'),),{}),
        'resolve_service_path':(server._service_paths,'resolve_service_path',('fixture',),{'for_write':False}),
        'preprocess_object_clean_sprites':(server._object_sprite_preprocessor,'preprocess_object_clean_sprites',({},True,False),{}),
    }
    if name not in targets:return False
    from canonical_application_source_contract import verify_actual_sources
    verify_actual_sources()
    owner,method,args,kwargs=targets[name]
    selected=getter()
    result=object()
    if name in {'accessory_uid','accessory_material_type'}:
        with patch.object(owner,method,autospec=True,return_value=result) as receiver:
            test.assertIs(selected(*args),result)
            receiver.assert_called_once_with(*args,**kwargs)
        return True
    with patch.object(type(owner),method,autospec=True,return_value=result) as receiver:
        test.assertIs(selected(*args),result)
        receiver.assert_called_once_with(owner,*args,**kwargs)
        test.assertIs(receiver.call_args.args[0],owner)
    return True


def binding(root,owner):
    tree=ast.parse((Path(root)/'local_inspection_service/accessories/image_composition.py').read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ImageJobs')
    constructor=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    return next(n.value for n in constructor.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Attribute) and isinstance(t.value,ast.Name)
                        and t.value.id=='self' and t.attr==owner for t in n.targets))


@contextmanager
def replace_queue_port(server,name,value):
    target,attribute=queue_target(server,name)
    owned=attribute in vars(target);previous=getattr(target,attribute)
    assign=setattr if isinstance(target,ModuleType) else object.__setattr__
    delete=delattr if isinstance(target,ModuleType) else object.__delattr__
    assign(target,attribute,value)
    try:yield value
    finally:
        if owned:assign(target,attribute,previous)
        else:delete(target,attribute)


# Expressions are contracts for each specific owner, not any Attribute supplier.
EXECUTION_EDGES={
    'files':{name:'execution_files.'+name for name in (
        '_business_files','_image_files','IMAGE_WORKER_LOG_DIR','ROOT','safe_name','resolve_service_path','public_output_url')},
    'evidence':{name:'evidence.'+name for name in ('image_job_prompt','bounded_text')},
    'providers':{name:'providers.'+name for name in (
        'LOCAL_CODEX_IMAGE_PROVIDER','CURSOR_IMAGE2_PROVIDER','CURSOR_IMAGE2_QUEUE_STATUS',
        'CODEX_IMAGE_WORKER_QUEUE_STATUS','MAX_IMAGE_WORKER_INPUTS','cursor_image2_settings',
        'cursor_image2_payload','cursor_auth_headers','extract_cursor_image2_bytes','windows_worker_base_url',
        'windows_worker_headers','windows_worker_image_timeout_seconds','windows_worker_image_response_bytes','masked_url_for_status')},
}
EXECUTION_EDGES['files']['image_job_output_path']='lambda: self.diagnostics.image_job_output_path'
EXECUTION_EDGES['evidence'].update({
    'mutate_candidate_image_job':'lambda: self.queue.mutate_candidate_image_job',
    'update_image_worker_status':'lambda: self.queue.update_image_worker_status',
    '_image_worker_processes':'lambda: self.worker.processes',
    'codex_log_has_generated_image':'lambda: self.diagnostics.codex_log_has_generated_image',
    'classify_image_worker_failure':'lambda: self.diagnostics.classify_image_worker_failure',
})
EXECUTION_EDGES['providers'].update({name:'lambda: self.execution.'+name for name in (
    'run_codex_image_job','run_cursor_image2_job','run_cos_codex_image_job')})
DIAGNOSTIC_EDGES={
    'media':{name:'diagnostic_media.'+name for name in (
        '_business_files','resolve_service_path','safe_name','IMAGE_WORKER_LOG_DIR')},
    'runtime':{'_image_worker_processes':'lambda: self.worker.processes',**{name:'lambda: self.diagnostics.'+name for name in (
        'image_worker_process_alive','codex_process_has_log_open','image_job_has_live_worker')}},
    'policy':'diagnostic_policy',
}
DIAGNOSTIC_EDGES['media']['read_image_worker_log_tail']='lambda: self.diagnostics.read_image_worker_log_tail'


def expression(value):return ast.dump(ast.parse(value,mode='eval').body,include_attributes=False)


def edge_errors(call,contract):
    errors=[]
    actual={kw.arg:kw.value for kw in call.keywords}
    if len(actual)!=len(call.keywords) or set(actual)!=set(contract):errors.append('wrong or duplicate capability groups')
    for group,expected in contract.items():
        node=actual.get(group)
        if node is None:continue
        if isinstance(expected,str):
            if ast.dump(node,include_attributes=False)!=expression(expected):errors.append(group+' binding differs')
            continue
        if not isinstance(node,ast.Call):errors.append(group+' not a capability constructor');continue
        fields={kw.arg:kw.value for kw in node.keywords}
        if node.args or len(fields)!=len(node.keywords) or set(fields)!=set(expected):errors.append(group+' field set differs')
        for name,value in expected.items():
            if name not in fields or ast.dump(fields[name],include_attributes=False)!=expression(value):errors.append(group+'.'+name+' edge differs')
    return errors


def root_errors(root,tree=None):
    import json
    expected=json.loads((Path(root)/'tests/backend_contract/accessory_image_composition_ports.json').read_text())
    if tree is None:
        from canonical_application_source_contract import read_checked_application_source
        tree=ast.parse(read_checked_application_source(Path(root)/'local_inspection_service/server.py', encoding='utf-8'))
    assignments={}
    for node in tree.body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name):assignments.setdefault(target.id,[]).append(node.value)
    errors=[]
    graphs=assignments.get('_image_jobs',[])
    if len(graphs)!=1 or not isinstance(graphs[0],ast.Call):return ['missing or repeated actual image graph']
    call=graphs[0]
    if expression('_ImageJobs')!=ast.dump(call.func,include_attributes=False) or call.args:errors.append('wrong image graph constructor')
    fields={kw.arg:ast.dump(kw.value,include_attributes=False) for kw in call.keywords}
    if len(fields)!=len(call.keywords) or fields!={name:expression(value) for name,value in expected['root_argument_expressions'].items()}:errors.append('external root arguments differ from frozen parent')
    for name,value in expected['aliases'].items():
        nodes=assignments.get(name,[])
        if len(nodes)!=1 or ast.dump(nodes[0],include_attributes=False)!=expression(value):errors.append(name+' ownership alias differs')
    imported=[alias for node in tree.body if isinstance(node,ast.ImportFrom) and node.module=='accessories.image_composition' for alias in node.names]
    if [(alias.name,alias.asname) for alias in imported if alias.asname=='_ImageJobs']!=[('ImageJobs','_ImageJobs')]:errors.append('wrong actual builder import')
    return errors
