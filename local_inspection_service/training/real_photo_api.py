"""Opt-in real-photo API and capture adapter with explicit composition ports."""
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Any
from fastapi import HTTPException, Response
from pydantic import BaseModel, StrictBool
from .real_photo_annotation import canonical
from .real_photo_contracts import MODEL, STRATEGY, digest, approved, review_key, objects, source_confirmed
from .real_photo_provenance import source_group, original_sha, pixel_sha
from ..storage.real_photo_feedback import RealPhotoRepository


def accounts():
    return {s.strip() for s in os.getenv('VANTALINE_REAL_PHOTO_ACCOUNTS', '').split(',') if s.strip()}


@dataclass(frozen=True)
class FeedbackPorts:
    repository: Callable[[], Any]
    user: Callable[[], dict]
    tasks: Callable[[], list]
    authorize: Callable[..., Any]
    config: Callable[[dict], dict]
    references: Callable[[dict], list]
    read: Callable[[str], bytes]
    profiles: Callable[[], Any]
    legacy_state: Callable[[str], dict]
    freeze: Callable[[dict, bytes, str], str] | None = None
    legacy_disable: Callable[[str], None] | None = None
    model_task: Callable[[str, dict], str] | None = None


class EnableRequest(BaseModel):
    enabled: bool


class GroupRequest(BaseModel):
    source_group: str
    source_group_confirmed: StrictBool | None = None


class HistoryImportRequest(BaseModel):
    source_group: str
    source_sha256: str
    width: int
    height: int
    source_orientation: int
    coordinate_system: str


class FeedbackService:
    def __init__(self, ports):
        self.ports = ports

    @contextmanager
    def repo(self):
        raw = self.ports.repository()
        if raw is None:
            raise HTTPException(503, '实拍回流需要PostgreSQL')
        try:
            yield RealPhotoRepository(raw)
        finally:
            raw.connection.close()

    def task(self, identifier, write=False):
        user = self.ports.user()
        task = next((t for t in self.ports.tasks() if t.get('id') == identifier), None)
        if task is None:
            raise HTTPException(404, '任务不存在')
        self.ports.authorize(task, user, write=write)
        owner = str(task.get('owner_user_id') or '')
        if not owner or owner != user['id']:
            raise HTTPException(403, '仅任务所属账户可操作实拍回流')
        return user, task

    def class_metadata(self, task, user):
        config = self.ports.config(user)
        ids = task.get('selected_accessory_ids') or task.get('accessory_ids') or []
        items = {i['id']:i for i in config.get('accessories', []) if i.get('id')}
        result = []
        for cid in ids:
            item = items.get(cid)
            if not item:raise HTTPException(409, '任务配件定义缺失')
            paths = self.ports.references(item)
            if not paths:raise HTTPException(409, '任务配件参考图缺失')
            result.append({'class_id':cid, 'name':str(item.get('name') or cid),
                           'definition':str(item.get('ai_profile') or item.get('description') or item.get('name') or cid)[:8000],
                           'reference_path':str(paths[0])})
        if not result or len(result)>50:raise HTTPException(409, '需要1至50个有效任务类别')
        return result

    def classes(self, task, user):
        result=self.class_metadata(task,user)
        for item in result:
            _,meta=canonical(self.ports.read(item['reference_path']))
            item['reference_sha256']=meta['source_sha256']
        return result

    def sync_definitions(self,repo,state,task,user):
        if not state or not state['enabled']:return state
        try:
            current=self.class_metadata(task,user)
            previous=[{k:v for k,v in item.items() if k!='reference_sha256'} for item in state['classes']]
            if current!=previous:
                # Full image hashes are read only on a definition/reference identity change.
                return repo.enable(user['id'],state['task_id'],self.classes(task,user),state['profiles'],True,state.get('business_context'))
        except (HTTPException,ValueError,OSError):
            repo.enable(user['id'],state['task_id'],state['classes'],state['profiles'],False)
            repo.mutate(user['id'],state['task_id'],lambda s,c:s.update(pause_reason='当前任务类别或参考图不完整；修复后重新启用实拍回流'))
            return repo.get(user['id'],state['task_id'])
        return state

    def enable(self, identifier, request):
        user, task = self.task(identifier, True)
        if user['id'] not in accounts():
            raise HTTPException(403, '实拍回流尚未为此账户启用')
        if not request.enabled:
            with self.repo() as repo:
                state = repo.get(user['id'], identifier)
                if state:
                    repo.enable(user['id'], identifier, state['classes'], state['profiles'], False)
            return self.status(identifier)
        classes = self.classes(task, user)
        profiles = self.ports.profiles().snapshot()
        reference = profiles.get('bbox_annotation')
        settings = self.ports.profiles().resolve('bbox_annotation', reference)
        if request.enabled and (not settings.get('configured') or settings.get('model') != MODEL or settings.get('provider') != 'doubao'):
            raise HTTPException(409, '请先绑定固定版本的实拍回流定位模型')
        if self.ports.legacy_disable:self.ports.legacy_disable(identifier)
        legacy=self.ports.legacy_state(identifier)
        context={'task_name':str(task.get('name') or task.get('label') or identifier)[:200],
                 'required_counts':task.get('required_accessory_counts') or {},
                 'historical_material_count':len(legacy.get('samples',[])),
                 'historical_material_policy':'preserved drafts; geometry and source groups require explicit confirmation'}
        with self.repo() as repo:
            repo.enable(user['id'], identifier, classes, {'bbox_annotation':reference}, request.enabled,context)
        return self.status(identifier)

    def status(self, identifier):
        user, task = self.task(identifier)
        if user['id'] not in accounts():
            return {'available':False,'strategy':STRATEGY}
        with self.repo() as repo:
            state = repo.get(user['id'], identifier)
            state = self.sync_definitions(repo,state,task,user)
            jobs = repo.jobs(user['id'], identifier) if state else []
            stats = repo.statistics(user['id'], identifier) if state else {}
        if state is None:
            return {'available':True,'selected':False,'enabled':False,'strategy':STRATEGY,'samples':[],'jobs':[]}
        samples = []
        for s in state['samples'][-80:]:
            annotation=s.get('annotation')
            if annotation:
                annotation={**annotation,'receipt':{k:v for k,v in annotation.get('receipt',{}).items() if k!='response'}}
            samples.append({k:s.get(k) for k in ('sample_id','image_sha256','source_group','source_group_version','source_kind','review','created_at','geometry')}|{'annotation':annotation,'source_group_confirmed':source_confirmed(s)})
        public_jobs = [{k:j.get(k) for k in ('id','kind','status','created_at','elapsed_seconds','model','runner_version','usage','result')}
                       for j in jobs]
        for j in public_jobs:
            if j['kind']=='reference_cache' and isinstance(j.get('result'),dict):
                j['result']={k:v for k,v in j['result'].items() if k not in {'response_id','references'}}
            if j['kind']=='mask' and isinstance(j.get('result'),dict):
                j['result']={k:v for k,v in j['result'].items() if k!='path'}
            if (j.get('result') or {}).get('receipt'):
                j['result']={k:v for k,v in j['result'].items() if k!='receipt'}
        accepted=approved(state)
        counts={'approved_count':len(accepted),'positive_count':sum(bool(s['annotation']['objects']) for s in accepted),
                'unconfirmed_source_count':sum(not source_confirmed(s) for s in state['samples']),
                'negative_count':sum(not s['annotation']['objects'] for s in accepted),
                'pending_annotation_count':sum(not s.get('annotation') for s in state['samples']),
                'excluded_count':sum(s.get('review',{}).get('decision') in {'exclude','uncertain'} for s in state['samples']),
                'failed_annotation_count':sum(s.get('annotation',{}).get('status')=='failed' for s in state['samples']),
                'pending_review_count':sum(s.get('annotation',{}).get('status')=='completed' and s.get('review',{}).get('key')!=review_key(s,state['classes']) for s in state['samples'])}
        return {'available':True,'selected':True,'strategy':STRATEGY,'enabled':state['enabled'],
                'candidate_count':len(state['samples']), 'samples':samples,'jobs':public_jobs,**counts,
                **{k:state.get(k) for k in ('initialization','review_trigger','approved_real_target','assessment','pause_reason','candidate_models')},
                'review_running':bool(state.get('round')),
                'call_statistics':stats,
                'reference_cache':{k:v for k,v in (state.get('reference_cache') or {}).items() if k in {'status','expires_at','generation'}},
                'datasets':[{k:d.get(k) for k in ('id','created_at','sample_count','real_source_count','unsupported_by_real_data','snapshot_fingerprint')} for d in state['datasets']]}

    def relabel(self, identifier, sample_id):
        user,_=self.task(identifier,True)
        def update(state,c):
            if not state['enabled'] or state.get('round'):raise HTTPException(409,'请启用回流且等待当前审核结束')
            sample=next((s for s in state['samples'] if s['sample_id']==sample_id),None)
            if sample is None:raise HTTPException(404,'样本不存在')
            c.execute(f"SELECT raw_json FROM {repo.table('jobs')} WHERE owner_user_id=%s AND task_id=%s AND status IN ('queued','running')",(user['id'],identifier))
            if any(j['kind']=='annotate' and j['inputs']['sample']['sample_id']==sample_id for j in repo.rows(c)):
                raise HTTPException(409,'此图标注尚未结束')
            version=max([int(a.get('version',0)) for a in sample.get('annotation_history',[])]+[int(sample.get('annotation',{}).get('version',0)),int(sample.get('annotation_version',0))])+1
            sample['annotation_version']=version
            if sample.get('annotation'):sample.setdefault('annotation_history',[]).append(sample.pop('annotation'))
            repo.enqueue(c,state,'annotate',f'annotation:{sample_id}:{version}',
                         {'sample':sample,'classes':state['classes'],'profiles':state['profiles'],'version':version,'explicit':True})
        with self.repo() as repo:repo.mutate(user['id'],identifier,update)
        return self.status(identifier)

    def restart(self, identifier):
        user,_=self.task(identifier,True)
        def update(state,c):
            if not state['enabled']:raise HTTPException(409,'请先启用回流')
            c.execute(f"SELECT raw_json FROM {repo.table('jobs')} WHERE owner_user_id=%s AND task_id=%s AND status IN ('running','cancel_requested')",(user['id'],identifier))
            if repo.rows(c):raise HTTPException(409,'请先等待所有当前任务结算')
            c.execute(f"SELECT raw_json FROM {repo.table('jobs')} WHERE owner_user_id=%s AND task_id=%s AND kind IN ('initialize','review','assess') AND status='queued'",(user['id'],identifier))
            for job in repo.rows(c):
                job['status']='cancelled';repo.save_job(c,job)
            state.pop('round',None);state.pop('pause_reason',None)
            # A new paid cache attempt requires this explicit user action.
            if (state.get('reference_cache') or {}).get('status') in {'failed','interrupted'}:
                state['reference_cache']['status']='retry_authorized'
            if not state.get('initialization'):
                repo.enqueue(c,state,'initialize','initialize:'+state['epoch']+':explicit:'+uuid.uuid4().hex,
                             {'classes':state['classes'],'history_count':len(state['samples']),'business_context':state.get('business_context',{})})
            else:state['review_trigger']=len(state['samples'])
        with self.repo() as repo:repo.mutate(user['id'],identifier,update)
        return self.status(identifier)

    def capture(self, record, result, request_id, image_path):
        if not accounts():return False
        try:return self._capture(record,result,request_id,image_path)
        except Exception as exc:
            print('real-photo capture unavailable: '+type(exc).__name__,flush=True)
            return True

    def _capture(self, record, result, request_id, image_path):
        if not accounts():
            return False
        user = self.ports.user()
        if not user or user.get('id') not in accounts() or not record:
            return False
        model = result.get('model') or {}
        task_id = model.get('task_id') or model.get('feedback_task_id')
        with self.repo() as repo:
            if self.ports.model_task and not repo.get(user['id'],str(task_id or '')):
                task_id=self.ports.model_task(str(model.get('id') or model.get('model_id') or ''),user)
            if not task_id:
                # Only candidate IDs belonging to this owner may map a YOLO result.
                for task in self.ports.tasks():
                    state = repo.get(user['id'], task['id'])
                    if state and any(c.get('model_id') == (model.get('id') or model.get('model_id')) for c in state['candidate_models']):
                        task_id = task['id']; break
            if not task_id:
                return False
            state = repo.get(user['id'], task_id)
            if state is None:
                return False
            # Once explicitly selected, do not fall back into legacy synthetic feedback, even paused.
            if not state['enabled']:
                return True
            _,task=self.task(task_id)
            state=self.sync_definitions(repo,state,task,user)
            if not state['enabled']:return True
            source = record.get('source_image') or {}
            if not (source_group.get() or record.get('source_group') or source.get('source_group')):
                return True  # no ordinary/camera/video ingestion evidence; never harvest pretraining renders.
            path = source.get('path')
            if not path:
                return True
            try:
                data = self.ports.read(str(path)); _, meta = canonical(data)
            except (ValueError, OSError):
                return True
            if original_sha.get() and meta['source_sha256']!=original_sha.get():return True
            group = record.get('source_group') or source.get('source_group') or source_group.get()
            if not group:
                for key in ('source_video_id','camera_session_id','upload_batch_id'):
                    value = record.get(key) or source.get(key)
                    if value:
                        group = key+':'+str(value); break
            if self.ports.freeze:
                path=self.ports.freeze(user,data,meta['source_sha256'])
            sample = {'sample_id':'real_'+uuid.uuid4().hex,'source_path':str(path),
                      'source_kind':'real_photo','image_sha256':meta['source_sha256'],'geometry':meta,
                      'source_group':group,'created_at':time.time(),'record_id':record.get('record_id'),
                      'request_id':request_id, 'lineage_hashes':[]}
            repo.capture(user['id'], task_id, sample)
        return True

    def capture_local(self,result,request_id,image_path,pixels,encode_pixels):
        if not accounts():return
        try:return self._capture_local(result,request_id,image_path,pixels,encode_pixels)
        except Exception as exc:print('real-photo local capture unavailable: '+type(exc).__name__,flush=True)

    def _capture_local(self,result,request_id,image_path,pixels,encode_pixels):
        if not source_group.get():return
        if pixel_sha.get() and digest(pixels.tobytes())!=pixel_sha.get():return
        user=self.ports.user()
        if user.get('id') not in accounts():return
        model=result.get('model') or {}
        if image_path and model.get('task_id'):return  # existing AI publication already admitted this original.
        with self.repo() as repo:
            states=repo.states({user['id']})
            matched=any(state['task_id']==model.get('task_id') or any(c.get('model_id')==model.get('id') for c in state['candidate_models']) for state in states)
            if not matched and self.ports.model_task:
                linked=self.ports.model_task(str(model.get('id') or ''),user)
                matched=any(state['task_id']==linked for state in states)
        if not matched:return
        if not image_path:
            if not self.ports.freeze:return
            raw=encode_pixels(pixels)
            image_path=self.ports.freeze(user,raw,digest(raw))
        self.capture({'source_image':{'path':str(image_path)}},result,request_id,image_path)

    def group(self, identifier, sample_id, request):
        user, _ = self.task(identifier, True)
        if not request.source_group.strip() or len(request.source_group)>200:
            raise HTTPException(422, '需要有效拍摄分组')
        group = request.source_group.strip()
        confirmed = source_confirmed({'source_group':group}) if request.source_group_confirmed is None else request.source_group_confirmed
        if confirmed and not source_confirmed({'source_group':group}):
            raise HTTPException(422,'请核实实际拍摄分组，不能确认待核实的占位分组')
        def update(state, c):
            sample = next((s for s in state['samples'] if s['sample_id']==sample_id), None)
            if sample is None: raise HTTPException(404,'样本不存在')
            if sample.get('source_group') in state.get('split_assignments', {}):
                raise HTTPException(409,'已冻结数据集的来源组不能修改')
            if state.get('round'):
                if state['enabled']:
                    raise HTTPException(409,'审核轮次进行中，请先关闭回流再调整分组')
                # Older releases left a revoked round behind when pausing.
                # Explicit source editing can archive it without enabling paid work.
                repo.cancel_round(state)
            if sample.get('source_group') == group and source_confirmed(sample) == confirmed:
                return
            sample.setdefault('source_group_history',[]).append({
                'source_group':sample.get('source_group'), 'confirmed':source_confirmed(sample),
                'version':sample.get('source_group_version',0),
                'modified_by':sample.get('source_group_modified_by'),'modified_at':sample.get('source_group_modified_at')})
            sample.update(source_group=group, source_group_confirmed=confirmed,
                          source_group_version=sample.get('source_group_version',0)+1,
                          source_group_modified_by=user['id'], source_group_modified_at=time.time())
            if sample.get('review'):
                rechecks=state.setdefault('recheck_sample_ids',[])
                if sample_id not in rechecks:rechecks.append(sample_id)
        with self.repo() as repo:repo.mutate(user['id'],identifier,update)
        return self.status(identifier)

    def image(self, identifier, sample_id):
        user, _ = self.task(identifier)
        with self.repo() as repo:state=repo.get(user['id'],identifier)
        sample=next((s for s in (state or {}).get('samples',[]) if s['sample_id']==sample_id),None)
        if sample is None:raise HTTPException(404,'样本不存在')
        data=self.ports.read(sample['source_path'])
        if digest(data)!=sample['image_sha256']:raise HTTPException(409,'原图已改变')
        clean,_=canonical(data)
        return Response(clean,media_type='image/png',headers={'Cache-Control':'private, no-store'})

    def historical(self,identifier,sample_id=None):
        user,_=self.task(identifier)
        state=self.ports.legacy_state(identifier)
        if state.get('owner_user_id') not in (None,'',user['id']):raise HTTPException(403,'历史样本账户不匹配')
        samples=state.get('samples',[])
        if sample_id is None:
            return [{'sample_id':s['sample_id'],'label_status':s.get('label_status'),
                     'mapping_status':'requires_explicit_original_geometry_confirmation',
                     'has_mask':bool((s.get('label_artifacts') or {}).get('color_mask_path') or (s.get('label_artifacts') or {}).get('color_mask_url'))}
                    for s in samples if s.get('sample_id')]
        sample=next((s for s in samples if s.get('sample_id')==sample_id),None)
        if sample is None:raise HTTPException(404,'历史样本不存在')
        data=self.ports.read(sample['source_image']['path']);clean,meta=canonical(data)
        labels=sample.get('bbox_labels') or sample.get('labels') or []
        boxes=[{'class_id':l['accessory_id'],'bbox':l['bbox_xyxy']} for l in labels]
        return sample,data,clean,meta,boxes

    def request_mask(self,identifier,sample_id):
        user,_=self.task(identifier,True)
        reference=self.ports.profiles().snapshot().get('image')
        if not self.ports.profiles().resolve('image',reference).get('configured'):
            raise HTTPException(409,'按需 mask 的图片模型尚未配置')
        def update(state,c):
            if not state['enabled']:raise HTTPException(409,'请先启用实拍回流')
            sample=next((s for s in state['samples'] if s['sample_id']==sample_id),None)
            if sample is None:raise HTTPException(404,'样本不存在')
            c.execute(f"SELECT raw_json FROM {repo.table('jobs')} WHERE owner_user_id=%s AND task_id=%s AND kind='mask' AND status IN ('queued','running')",(user['id'],identifier))
            if any(j['inputs']['sample']['sample_id']==sample_id for j in repo.rows(c)):raise HTTPException(409,'此图已有按需 mask 任务')
            repo.enqueue(c,state,'mask','mask:'+uuid.uuid4().hex,
                         {'sample':sample,'classes':state['classes'],'image_profile':reference})
        with self.repo() as repo:repo.mutate(user['id'],identifier,update)
        return self.status(identifier)

    def versions(self,identifier,sample_id):
        user,_=self.task(identifier)
        with self.repo() as repo:state=repo.get(user['id'],identifier)
        sample=next((s for s in (state or {}).get('samples',[]) if s['sample_id']==sample_id),None)
        if sample is None:raise HTTPException(404,'样本不存在')
        return {'annotations':sample.get('annotation_history',[])+([sample['annotation']] if sample.get('annotation') else []),
                'reviews':sample.get('review_history',[])+([sample['review']] if sample.get('review') else []),
                'source_groups':sample.get('source_group_history',[])+[{'source_group':sample.get('source_group'),
                    'confirmed':source_confirmed(sample),'version':sample.get('source_group_version',0),
                    'modified_by':sample.get('source_group_modified_by'),'modified_at':sample.get('source_group_modified_at')}],
                'masks':[{k:m.get(k) for k in ('job_id','model_profile','annotation_version','geometry','mapping_status','mask_sha256')} for m in sample.get('masks',[])]}

    def mask_image(self,identifier,sample_id,mask_id):
        user,_=self.task(identifier)
        with self.repo() as repo:state=repo.get(user['id'],identifier)
        sample=next((s for s in (state or {}).get('samples',[]) if s['sample_id']==sample_id),None)
        mask=next((m for m in (sample or {}).get('masks',[]) if m['job_id']==mask_id),None)
        if mask is None:raise HTTPException(404,'Mask 附件不存在')
        data=self.ports.read(mask['path'])
        if digest(data)!=mask['mask_sha256']:raise HTTPException(409,'Mask 附件内容已改变')
        return Response(data,media_type='image/png',headers={'Cache-Control':'private, no-store'})

    def import_historical(self,identifier,sample_id,request):
        user,_=self.task(identifier,True)
        sample,data,_,meta,boxes=self.historical(identifier,sample_id)
        if request.coordinate_system!='original_first_frame_pixel_xyxy' or request.source_sha256!=meta['source_sha256'] or (request.width,request.height,request.source_orientation)!=(meta['width'],meta['height'],meta['source_orientation']):
            raise HTTPException(409,'必须明确核实历史框的原图身份及坐标映射，不能静默重解释')
        if not request.source_group.strip() or len(request.source_group)>200:raise HTTPException(422,'请补充历史拍摄分组')
        with self.repo() as repo:
            state=repo.get(user['id'],identifier)
            if not state or not state['enabled']:raise HTTPException(409,'请先启用实拍回流')
            if any(s['image_sha256']==meta['source_sha256'] for s in state['samples']):raise HTTPException(409,'原图已进入实拍池，请查看其现有版本')
            try:valid=objects(boxes,{c['class_id'] for c in state['classes']},meta['width'],meta['height'])
            except ValueError:raise HTTPException(409,'历史框不符合当前类别或原图坐标，需要主动重标')
            if not valid:raise HTTPException(409,'历史样本没有可复用的完整框')
            path=self.ports.freeze(user,data,meta['source_sha256']) if self.ports.freeze else sample['source_image']['path']
            repo.capture(user['id'],identifier,{'sample_id':'real_'+uuid.uuid4().hex,'source_path':str(path),
                'source_kind':'real_photo','image_sha256':meta['source_sha256'],'geometry':meta,
                'source_group':request.source_group.strip(),'created_at':time.time(),'legacy_sample_id':sample_id,
                'annotation':{'status':'completed','version':1,'objects':valid,'source':'historical_draft',
                              'mapping_confirmation':request.model_dump(),'confirmed_by':user['id']},'lineage_hashes':[]})
        return self.status(identifier)


def compose(app, service):
    @app.get('/api/ai/tasks/{task_id}/real-photo')
    def status(task_id:str):return service.status(task_id)
    @app.patch('/api/ai/tasks/{task_id}/real-photo')
    def enable(task_id:str,request:EnableRequest):return service.enable(task_id,request)
    @app.patch('/api/ai/tasks/{task_id}/real-photo/samples/{sample_id}/group')
    def group(task_id:str,sample_id:str,request:GroupRequest):return service.group(task_id,sample_id,request)
    @app.get('/api/ai/tasks/{task_id}/real-photo/samples/{sample_id}/image')
    def image(task_id:str,sample_id:str):return service.image(task_id,sample_id)
    @app.post('/api/ai/tasks/{task_id}/real-photo/samples/{sample_id}/relabel')
    def relabel(task_id:str,sample_id:str):return service.relabel(task_id,sample_id)
    @app.post('/api/ai/tasks/{task_id}/real-photo/restart')
    def restart(task_id:str):return service.restart(task_id)
    @app.get('/api/ai/tasks/{task_id}/real-photo/history')
    def history(task_id:str):return service.historical(task_id)
    @app.post('/api/ai/tasks/{task_id}/real-photo/history/{sample_id}/import')
    def import_history(task_id:str,sample_id:str,request:HistoryImportRequest):return service.import_historical(task_id,sample_id,request)
    @app.get('/api/ai/tasks/{task_id}/real-photo/history/{sample_id}/image')
    def historical_image(task_id:str,sample_id:str):
        _,_,clean,_,_=service.historical(task_id,sample_id)
        return Response(clean,media_type='image/png',headers={'Cache-Control':'private, no-store'})
    @app.get('/api/ai/tasks/{task_id}/real-photo/history/{sample_id}/geometry')
    def historical_geometry(task_id:str,sample_id:str):
        _,_,_,meta,boxes=service.historical(task_id,sample_id)
        return {'geometry':meta,'objects':boxes,'mapping_status':'requires_explicit_original_geometry_confirmation'}
    @app.post('/api/ai/tasks/{task_id}/real-photo/samples/{sample_id}/mask')
    def mask(task_id:str,sample_id:str):return service.request_mask(task_id,sample_id)
    @app.get('/api/ai/tasks/{task_id}/real-photo/samples/{sample_id}/versions')
    def versions(task_id:str,sample_id:str):return service.versions(task_id,sample_id)
    @app.get('/api/ai/tasks/{task_id}/real-photo/samples/{sample_id}/masks/{mask_id}/image')
    def mask_image(task_id:str,sample_id:str,mask_id:str):return service.mask_image(task_id,sample_id,mask_id)
    return service


def associated_task(model_id,user,models,pipelines):
    spec=next((m for m in models if m.get('id')==model_id and m.get('owner_user_id')==user['id']),None)
    if not spec:return ''
    pid=str(spec.get('pipeline_task_id') or '')
    task=next((p for p in pipelines if p.get('id')==pid and p.get('owner_user_id')==user['id']),None)
    if task:return str(task.get('ai_task_id') or (pid[len('pipe_ai_'):] if pid.startswith('pipe_ai_') else ''))
    return pid[len('pipe_ai_'):] if pid.startswith('pipe_ai_') else ''
