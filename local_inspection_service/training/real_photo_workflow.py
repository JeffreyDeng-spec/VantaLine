"""Durable review rounds and dataset decisions; no image synthesis or model promotion."""
import copy
import time
import uuid
from .real_photo_contracts import approved, dataset_gate, digest, review_key, review_report, source_confirmed
from .real_photo_cache import schedule_cache, cache_key


def summary(state):
    selected = approved(state)
    counts = {c['class_id']:0 for c in state['classes']}
    for s in selected:
        for o in s['annotation']['objects']:
            counts[o['class_id']] += 1
    return {'candidate_count':len(state['samples']), 'approved_count':len(selected),
            'unconfirmed_source_count':sum(not source_confirmed(s) for s in state['samples']),
            'positive_images':sum(bool(s['annotation']['objects']) for s in selected),
            'negative_images':sum(not s['annotation']['objects'] for s in selected),
            'class_instance_counts':counts, 'source_groups':sorted({s['source_group'] for s in selected if s.get('source_group')}),
            'unsupported_by_real_data':[cid for cid,n in counts.items() if not n]}


def schedule(repo, owner, task):
    def update(state, c):
        schedule_cache(repo,state,c)
        if not state['enabled'] or not state.get('initialization') or state.get('pause_reason'):
            return
        current = state.get('round')
        if not current:
            trigger=state.get('review_trigger',20)
            rechecks=set(state.get('recheck_sample_ids',[]))
            if len(state['samples']) < trigger and not rechecks:return
            # Freeze at the cumulative trigger, before labels settle. Later arrivals
            # cannot enlarge this cohort or keep it waiting indefinitely.
            fresh=len(state['samples']) >= trigger
            cutoff=trigger if fresh else state.get('reviewed_candidate_count',max(
                (r['candidate_count'] for r in state.get('rounds',[]) if r.get('assessment_job')),default=0))
            scope={s['sample_id'] for s in state['samples'][:trigger]} if fresh else set()
            new=[s for s in state['samples'] if s['sample_id'] in scope|rechecks
                 and s.get('review',{}).get('key')!=review_key(s,state['classes'])]
            if not new:
                state['pause_reason']='没有新增有效标注可审核；请处理标注失败或补充实拍'
                return
            current={'id':uuid.uuid4().hex,'candidate_count':cutoff,'review_jobs':[],
                     'sample_ids':[s['sample_id'] for s in new],'created_at':time.time()}
            state['round']=current
        if not current['review_jobs']:
            if not current.get('sample_ids'):
                state['pause_reason']='本轮冻结范围缺失；请核查并明确重新启动'
                return
            membership=set(current['sample_ids'])
            new=[s for s in state['samples'] if s['sample_id'] in membership]
            if len(new)!=len(membership):raise ValueError('frozen review original missing')
            pending=[s for s in new if s.get('annotation',{}).get('status') not in {'completed','failed'}]
            if pending:
                c.execute(f"SELECT raw_json FROM {repo.table('jobs')} WHERE owner_user_id=%s AND task_id=%s AND kind='annotate' AND status IN ('failed','interrupted','stale','cancelled')",(owner,task))
                failed_versions={(j['inputs']['sample']['sample_id'], int(j['inputs'].get('version',1))) for j in repo.rows(c)}
                if any((s['sample_id'],int(s.get('annotation_version',1))) in failed_versions for s in pending):
                    state['pause_reason']='存在未完整结算的标注；请主动重标并重新启动审核'
                    current['status']='annotation_incomplete'
                    state['rounds'].append(current);state.pop('round')
                return
            for i in range(0,len(new),10):
                samples=[{**copy.deepcopy(s),'review_key':review_key(s,state['classes'])} for s in new[i:i+10]]
                job=repo.enqueue(c,state,'review','review:'+current['id']+':'+str(i),
                                 {'samples':samples,'classes':state['classes'],'round_id':current['id']})
                current['review_jobs'].append(job['id'])
            return
        jobs = [repo.read_job(c, identifier) for identifier in current['review_jobs']]
        if current.get('assessment_job'):jobs.append(repo.read_job(c,current['assessment_job']))
        if any(j['status'] in {'failed','interrupted','cancelled','stale'} for j in jobs):
            state['pause_reason']='审核或汇总未完整成功；请处理失败后明确重新启动'
            return
        if any(j['status']!='completed' for j in jobs):return
        if not current.get('assessment_job'):
            inputs={'classes':state['classes'],'summary':summary(state),'round_id':current['id'],
                    'new_decisions':[j['result'] for j in jobs], 'previous_assessment':state.get('assessment'),
                    'initialization':copy.deepcopy(state['initialization']),
                    'approved_real_target':state['approved_real_target'],
                    'review_trigger':state['review_trigger']}
            current['assessment_job']=repo.enqueue(c,state,'assess','assess:'+current['id'],inputs)['id']
    return repo.mutate(owner,task,update)


def apply_result(repo, state, job, c):
    result=job['result']
    if job['kind']=='reference_cache':
        pointer=state.get('reference_cache') or {}
        if pointer.get('job_id')!=job['id'] or job['inputs']['cache_key']!=cache_key(state):
            raise ValueError('reference cache version changed')
        if result.get('status')=='completed':
            pointer.update(status='ready',response_id=result['response_id'],expires_at=result['expires_at'],
                           references=result['references'])
        else:
            pointer['status']='failed'
            state['pause_reason']='豆包参考图缓存未成功；请核查调用证据后明确重新启动，不自动重放'
        return
    if job['kind']=='annotate':
        snapshot=job['inputs']['sample']
        sample=next(s for s in state['samples'] if s['sample_id']==snapshot['sample_id'])
        if sample['image_sha256']!=snapshot['image_sha256']:
            raise ValueError('source identity changed')
        sample.setdefault('annotation_history',[])
        if sample.get('annotation'):sample['annotation_history'].append(sample['annotation'])
        sample['annotation']={**result,'receipt':{k:v for k,v in result.get('receipt',{}).items() if k!='response'},
                              'version':job['inputs']['version'],'job_id':job['id']}
        if result.get('status')=='failed' and (result.get('receipt',{}).get('failure_stage')=='transport'
                                             or result.get('receipt',{}).get('http_status',200)!=200):
            state['pause_reason']='豆包连接或服务请求失败；已暂停后续调用，请处理后明确恢复并主动重标失败图片'
        if job['inputs'].get('explicit') and sample.get('review'):
            rechecks=state.setdefault('recheck_sample_ids',[])
            if sample['sample_id'] not in rechecks:rechecks.append(sample['sample_id'])
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
        state['reviewed_candidate_count']=current['candidate_count']
        state['recheck_sample_ids']=[identifier for identifier in state.get('recheck_sample_ids',[]) if identifier not in round_ids]
        state['review_trigger']=current['candidate_count']+result['next_increment']
        if result['action']=='pause':state['pause_reason']=result['reason']
        state['rounds'].append(current)
        state.pop('round',None)
