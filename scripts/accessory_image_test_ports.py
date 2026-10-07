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
    return targets.get(name,(server,name))


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
