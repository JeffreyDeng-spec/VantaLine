"""Server-side execution adapter; Agent cannot invoke this or bypass admission."""
import time
import threading
from dataclasses import dataclass
from typing import Callable
from .real_photo_api import accounts
from .real_photo_dataset import build
from .real_photo_contracts import dataset_gate


@dataclass(frozen=True)
class DispatchPorts:
    repository: Callable
    files: Callable
    output: Callable
    submit: Callable
    training: Callable
    configuration: Callable | None = None
    metadata: Callable | None = None


class Dispatcher:
    def __init__(self,ports):self.ports=ports;self.live=None

    def operation(self,fn):
        raw=self.ports.repository()
        if raw is None:raise RuntimeError('PostgreSQL required')
        from ..storage.real_photo_feedback import RealPhotoRepository
        try:return fn(RealPhotoRepository(raw))
        finally:raw.connection.close()

    def tick(self):
        if self.live:
            job,token,training_id=self.live
            if not self.operation(lambda r:r.pulse(job['id'],token)):
                self.live=None;return
            task=self.ports.training(training_id)
            if not task or task.get('status') not in {'completed','failed','cancelled'}:return
            def finish(repo):
                def apply(state,current,c):
                    candidate=next(x for x in state['candidate_models'] if x['job_id']==training_id)
                    candidate.update(status=task['status'],metrics=task.get('real_photo_test_metrics'),completed_at=time.time())
                    if task['status']!='completed':state['pause_reason']='训练未完整成功；请核查现有任务，不自动重放同一数据快照'
                return repo.finish(job['id'],token,{'training_id':training_id,'status':task['status']},apply)
            self.operation(finish);self.live=None;return
        if not accounts():return
        if self.reconcile():return
        # Serial claim also prevents a second server process dispatching a training snapshot.
        claimed=self.operation(lambda r:r.claim(accounts(),{'train'},'yolo','real-photo-dispatch-v1'))
        if not claimed:return
        job,token=claimed
        stopped=threading.Event()
        def heartbeat():
            while not stopped.wait(5):
                try:
                    if not self.operation(lambda r:r.pulse(job['id'],token)):return
                except Exception:return
        thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
        try:
            # Re-check every frozen acceptance/version and source split immediately before publication.
            state={'samples':job['inputs']['samples'],'classes':job['inputs']['classes'],
                   'split_assignments':job['inputs']['splits']}
            dataset_gate(state,20)
            if self.ports.configuration:
                job['inputs']['training_configuration']=self.ports.configuration()
            if self.ports.metadata:job['inputs']['training_metadata']=self.ports.metadata(job)
            dataset=build(job,self.ports.files(),self.ports.output(job['owner_user_id']))
            if not self.operation(lambda r:r.pulse(job['id'],token)):raise ValueError('dataset dispatch cancelled')
            training_id=dataset['training_job_id']
            # Reserve before enqueue. A crash here requires explicit reconciliation; never resubmit.
            def reservation(repo):
                def reserve(state,c):
                    current=repo.read_job(c,job['id'])
                    from .real_photo_contracts import digest
                    if current['status']!='running' or current['epoch']!=state['epoch'] or not state['enabled'] or current['token_hash']!=digest(token.encode()) or time.time()>current['deadline']:
                        raise ValueError('training reservation revoked')
                    state['datasets'].append(dataset)
                    state['candidate_models'].append({'job_id':training_id,'dataset_id':dataset['id'],'status':'dispatching',
                        'model_id':'trained_'+training_id+'__yolo','unsupported_by_real_data':dataset['unsupported_by_real_data'],
                        'real_source_count':dataset['real_source_count'],'positive_image_count':dataset['positive_image_count'],
                        'negative_image_count':dataset['negative_image_count'],'split_image_counts':dataset['split_image_counts'],
                        'limitation':'source-group split; unsupported/test-empty categories are not evaluable'})
                    current['deadline']=time.time()+7*24*3600
                    current['training_id']=training_id
                    current['training_configuration']=dataset.get('training_configuration')
                    current['training_metadata']=dataset.get('training_metadata')
                    repo.save_job(c,current)
                return repo.mutate(job['owner_user_id'],job['task_id'],reserve)
            self.operation(reservation)
            if not self.operation(lambda r:r.pulse(job['id'],token)):raise ValueError('training submission revoked')
            self.ports.submit(job,dataset)
            self.live=(job,token,training_id)
        except Exception as exc:
            try:self.operation(lambda r:r.finish(job['id'],token,{'error_type':type(exc).__name__},lambda *a:None,success=False))
            except Exception:pass
        finally:stopped.set();thread.join(timeout=6)

    def reconcile(self):
        """Observe an existing deterministic task after restart; never submit it again."""
        busy=False
        for state in self.operation(lambda r:r.states(accounts())):
            for candidate in state.get('candidate_models',[]):
                if candidate['status'] not in {'dispatching','running'}:continue
                task=self.ports.training(candidate['job_id'])
                if task and task.get('status') in {'queued','running'}:
                    busy=True;continue
                if task and task.get('status') in {'completed','failed','cancelled'}:
                    def update(current,c):
                        item=next(x for x in current['candidate_models'] if x['job_id']==candidate['job_id'])
                        item.update(status=task['status'],metrics=task.get('real_photo_test_metrics'),completed_at=time.time())
                        current['pause_reason']='训练调度曾中断；现有任务已结算，请核查后明确恢复审核。原数据快照不会重提交'
                    self.operation(lambda r:r.mutate(state['owner_user_id'],state['task_id'],update))
                elif not task:
                    def missing(current,c):current['pause_reason']='训练提交结果不确定；请核查既有训练任务，不自动重提交'
                    self.operation(lambda r:r.mutate(state['owner_user_id'],state['task_id'],missing))
        return busy
