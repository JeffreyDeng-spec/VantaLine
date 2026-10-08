"""Durable review rounds and dataset decisions; no image synthesis or model promotion."""
import copy
import time
import uuid
from .real_photo_contracts import approved, dataset_gate, digest, review_key, review_report


def summary(state):
    selected = approved(state)
    counts = {c['class_id']:0 for c in state['classes']}
    for s in selected:
        for o in s['annotation']['objects']:
            counts[o['class_id']] += 1
    return {'candidate_count':len(state['samples']), 'approved_count':len(selected),
            'positive_images':sum(bool(s['annotation']['objects']) for s in selected),
            'negative_images':sum(not s['annotation']['objects'] for s in selected),
            'class_instance_counts':counts, 'source_groups':sorted({s['source_group'] for s in selected if s.get('source_group')}),
            'unsupported_by_real_data':[cid for cid,n in counts.items() if not n]}


def schedule(repo, owner, task):
    def update(state, c):
        if not state['enabled'] or not state.get('initialization') or state.get('pause_reason'):
            return
        current = state.get('round')
        if current:
            jobs = [repo.read_job(c, identifier) for identifier in current['review_jobs']]
            if any(j['status'] in {'failed','interrupted','cancelled','stale'} for j in jobs):
                state['pause_reason']='审核轮次未完整成功；请处理失败后明确重新启动'
                return
            if any(j['status']!='completed' for j in jobs):
                return
            if not current.get('assessment_job'):
                inputs={'classes':state['classes'],'summary':summary(state),'round_id':current['id'],
                        'new_decisions':[j['result'] for j in jobs], 'previous_assessment':state.get('assessment')}
                current['assessment_job']=repo.enqueue(c,state,'assess','assess:'+current['id'],inputs)['id']
            return
        if len(state['samples']) < state.get('review_trigger',20):
            return
        new = [s for s in state['samples'] if s.get('annotation',{}).get('status') in {'completed','failed'}
               and s.get('review',{}).get('key')!=review_key(s,state['classes'])]
        pending = [s for s in state['samples'] if not s.get('annotation')]
        if pending:
            c.execute(f"SELECT raw_json FROM {repo.table('jobs')} WHERE owner_user_id=%s AND task_id=%s AND kind='annotate' AND status IN ('failed','interrupted','stale','cancelled')",(owner,task))
            failed_ids={j['inputs']['sample']['sample_id'] for j in repo.rows(c)}
            if any(s['sample_id'] in failed_ids for s in pending):state['pause_reason']='存在未完整结算的标注；请主动重标并重新启动审核'
            return
        if not new:
            state['pause_reason']='没有新增有效标注可审核；请处理标注失败或补充实拍'
            return
        current={'id':uuid.uuid4().hex,'candidate_count':len(state['samples']), 'review_jobs':[],
                 'created_at':time.time()}
        for i in range(0,len(new),10):
            samples=[{**copy.deepcopy(s),'review_key':review_key(s,state['classes'])} for s in new[i:i+10]]
            job=repo.enqueue(c,state,'review','review:'+current['id']+':'+str(i),
                             {'samples':samples,'classes':state['classes'],'round_id':current['id']})
            current['review_jobs'].append(job['id'])
        state['round']=current
    return repo.mutate(owner,task,update)


def apply_result(repo, state, job, c):
    result=job['result']
    if job['kind']=='annotate':
        snapshot=job['inputs']['sample']
        sample=next(s for s in state['samples'] if s['sample_id']==snapshot['sample_id'])
        if sample['image_sha256']!=snapshot['image_sha256']:
            raise ValueError('source identity changed')
        sample.setdefault('annotation_history',[])
        if sample.get('annotation'):sample['annotation_history'].append(sample['annotation'])
        sample['annotation']={**result,'receipt':{k:v for k,v in result.get('receipt',{}).items() if k!='response'},
                              'version':job['inputs']['version'],'job_id':job['id']}
        return
    if job['kind'] in {'initialize','review','assess'}:
        review_report(job,result)
    if job['kind']=='initialize':
        state['initialization']={**result,'job_id':job['id']}
        state.update(review_trigger=result['review_trigger'],approved_real_target=result['approved_real_target'])
    elif job['kind']=='review':
        current=state.get('round')
        if not current or job['inputs']['round_id']!=current['id']:
            raise ValueError('review round changed')
        for decision in result['decisions']:
            sample=next(s for s in state['samples'] if s['sample_id']==decision['sample_id'])
            if review_key(sample,state['classes'])!=decision['review_key']:
                raise ValueError('annotation changed during review')
            if sample.get('review'):sample.setdefault('review_history',[]).append(sample['review'])
            sample['review']={'key':decision['review_key'],'decision':decision['decision'],
                              'reason':decision['reason'],'job_id':job['id'],'model':job['model'],'created_at':time.time()}
    elif job['kind']=='assess':
        current=state.get('round')
        if not current or job['inputs']['round_id']!=current['id']:
            raise ValueError('dataset assessment changed')
        # Build from the reviewed round's frozen membership, not captures arriving during review.
        round_ids={s['sample_id'] for j in current['review_jobs'] for s in repo.read_job(c,j)['inputs']['samples']}
        previous_ids={s['sample_id'] for s in state['samples'] if s.get('review',{}).get('job_id')
                      and s['sample_id'] not in round_ids}
        frozen={**state,'samples':[s for s in state['samples'] if s['sample_id'] in round_ids|previous_ids]}
        if result['action']=='train':
            selected,splits,unsupported=dataset_gate(frozen,result['approved_real_target'])
            inputs={'samples':copy.deepcopy(selected),'classes':state['classes'],'splits':splits,
                    'unsupported_by_real_data':unsupported,'profiles':state['profiles'],'round_id':current['id']}
            dataset_id=digest(inputs)
            repo.enqueue(c,state,'train','train:'+dataset_id,inputs)
            state['split_assignments']=splits
            state['last_dataset_fingerprint']=dataset_id
        state['assessment']={**result,'job_id':job['id'],'created_at':time.time()}
        state['approved_real_target']=result['approved_real_target']
        state['review_trigger']=current['candidate_count']+result['next_increment']
        if result['action']=='pause':state['pause_reason']=result['reason']
        state['rounds'].append(current)
        state.pop('round',None)
