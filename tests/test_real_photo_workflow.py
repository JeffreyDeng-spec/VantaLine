"""Review orchestration tests with deterministic reports, not visual accuracy claims."""
import copy
import time
from local_inspection_service.training.real_photo_cache import cache_key
import pytest
from test_real_photo_feedback import database,classes,state_fixture
from local_inspection_service.training.real_photo_workflow import schedule,apply_result
from local_inspection_service.training.real_photo_contracts import review_key


def finish(repo,kind,result):
    if kind=='annotate':
        repo.mutate('a','task',lambda state,c:state.update(reference_cache={'key':cache_key(state),'status':'ready','expires_at':time.time()+3600,'response_id':'resp_fixture','references':[]}))
    job,token=repo.claim({'a'},{kind},'gpt-6-astra','fixture')
    return repo.finish(job['id'],token,result(job),lambda s,j,c:apply_result(repo,s,j,c))


def ready(database,approved_target=20):
    repo=database();repo.enable('a','task',classes(),{})
    finish(repo,'initialize',lambda j:{'review_trigger':20,'approved_real_target':approved_target,'reason':'first real cohort'})
    state=state_fixture()
    for sample in state['samples']:
        sample=copy.deepcopy(sample);sample.pop('review')
        repo.capture('a','task',sample)
    return repo


def test_complete_round_missing_class_train_and_frozen_new_arrival(database):
    repo=ready(database);schedule(repo,'a','task')
    current=repo.get('a','task')['round'];assert len(current['review_jobs'])==2
    extra=copy.deepcopy(state_fixture()['samples'][0]);extra.update(sample_id='next',image_sha256='new');extra.pop('review')
    repo.capture('a','task',extra)
    for _ in range(2):
        finish(repo,'review',lambda j:{'decisions':[{'sample_id':s['sample_id'],'review_key':s['review_key'],
            'decision':'accept_positive' if s['annotation']['objects'] else 'accept_negative','reason':'fixture correct'} for s in j['inputs']['samples']]})
    schedule(repo,'a','task')
    finish(repo,'assess',lambda j:{'action':'train','approved_real_target':20,'next_increment':1,'reason':'missing class metrics unavailable, enough real positives','gaps':[]})
    train=next(j for j in repo.jobs('a','task') if j['kind']=='train')
    assert len(train['inputs']['samples'])==20 and train['inputs']['unsupported_by_real_data']==['missing']
    assert repo.get('a','task')['review_trigger']==21
    schedule(repo,'a','task');assert repo.get('a','task')['round']['candidate_count']==21


def test_failed_chunk_blocks_round_admission_and_never_replayed(database):
    repo=ready(database);schedule(repo,'a','task')
    job,token=repo.claim({'a'},{'review'},'model','cli')
    repo.finish(job['id'],token,{'error_type':'fixture'},lambda *a:None,success=False)
    schedule(repo,'a','task')
    assert repo.get('a','task')['pause_reason']
    assert not any(j['kind']=='train' for j in repo.jobs('a','task'))


def test_pause_archives_round_and_revokes_late_review_before_source_edit(database):
    repo=ready(database);schedule(repo,'a','task')
    before=repo.get('a','task');current=copy.deepcopy(before['round'])
    job,token=repo.claim({'a'},{'review'},'model','fixture')
    repo.enable('a','task',classes(),{},False)
    state=repo.get('a','task')
    assert not state['enabled'] and 'round' not in state
    archived=state['rounds'][-1]
    assert archived['id']==current['id'] and archived['sample_ids']==current['sample_ids']
    assert archived['status']=='cancelled' and archived['cancelled_at']
    assert state['initialization']==before['initialization']
    assert state['samples']==before['samples']
    assert {j['status'] for j in repo.jobs('a','task') if j['kind']=='review'}=={'cancelled','cancel_requested'}
    with pytest.raises(ValueError):repo.finish(job['id'],token,{},lambda *a:None)
    repo.enable('a','task',classes(),{},False)
    assert len(repo.get('a','task')['rounds'])==1
    assert repo.claim({'a'},{'review'},'model','fixture') is None


def test_failed_initialization_diagnostics_survive_without_requeue(database):
    repo=database();repo.enable('a','task',classes(),{})
    job,token=repo.claim({'a'},{'initialize'},'gpt-6-astra','fixture')
    diagnostics={'exit_code':0,'turn_completed':True,'report_accepted':False,
                 'report_refusals':{'reason_invalid':1},'prompt_sha256':'fixture'}
    repo.receipt(job['id'],job['attempt_id'],{'diagnostics':diagnostics,'usage':{'input_tokens':123}})
    repo.finish(job['id'],token,{'error_code':'report_rejected'},lambda *a:None,success=False)
    schedule(repo,'a','task')
    saved=repo.jobs('a','task')
    assert len(saved)==1 and saved[0]['status']=='failed'
    assert saved[0]['attempt_receipt']['diagnostics']==diagnostics
    assert saved[0]['attempt_receipt']['usage']=={'input_tokens':123}
    assert repo.get('a','task')['pause_reason'] and not repo.claim({'a'},{'initialize'},'model','fixture')


@pytest.mark.parametrize('future_failed',[False,True])
def test_pending_cohort_freezes_before_late_unannotated_or_failed_arrival(database,future_failed):
    repo=database();repo.enable('a','task',classes(),{})
    finish(repo,'initialize',lambda j:{'review_trigger':20,'approved_real_target':20,'reason':'bounded first cohort'})
    template=state_fixture()['samples']
    for i,row in enumerate(template):
        sample=copy.deepcopy(row);sample.pop('review')
        if i==19:sample.pop('annotation')
        repo.capture('a','task',sample)
    schedule(repo,'a','task')
    current=repo.get('a','task')['round']
    assert current['candidate_count']==20 and len(current['sample_ids'])==20 and not current['review_jobs']
    extra=copy.deepcopy(template[0]);extra.update(sample_id='late',image_sha256='late')
    extra.pop('review');extra.pop('annotation');repo.capture('a','task',extra)
    finish(repo,'annotate',lambda j:{'status':'completed','objects':template[19]['annotation']['objects'],'receipt':{}})
    if future_failed:
        repo.mutate('a','task',lambda state,c:state.update(reference_cache={'key':cache_key(state),'status':'ready','expires_at':time.time()+3600,'response_id':'resp_fixture','references':[]}))
        job,token=repo.claim({'a'},{'annotate'},'model','fixture')
        repo.finish(job['id'],token,{'error_type':'future fixture'},lambda *a:None,success=False)
    schedule(repo,'a','task')
    state=repo.get('a','task');current=state['round']
    assert current['candidate_count']==20 and not state.get('pause_reason')
    jobs=[repo.read_job(repo.repository._cursor(),jid) for jid in current['review_jobs']]
    assert {s['sample_id'] for j in jobs for s in j['inputs']['samples']}=={str(i) for i in range(20)}
    # The late annotation predates ready reviews; FIFO must not starve screening.
    claimed=repo.claim({'a'},{'annotate','review'},'model','fixture')
    assert claimed[0]['kind']=='review'


def test_failed_cohort_annotation_archives_scope_and_allows_explicit_recovery(database):
    repo=database();repo.enable('a','task',classes(),{})
    finish(repo,'initialize',lambda j:{'review_trigger':20,'approved_real_target':20,'reason':'bounded cohort'})
    for i,row in enumerate(state_fixture()['samples']):
        sample=copy.deepcopy(row);sample.pop('review')
        if i==19:sample.pop('annotation')
        repo.capture('a','task',sample)
    schedule(repo,'a','task')
    repo.mutate('a','task',lambda state,c:state.update(reference_cache={'key':cache_key(state),'status':'ready','expires_at':time.time()+3600,'response_id':'resp_fixture','references':[]}))
    job,token=repo.claim({'a'},{'annotate'},'model','fixture')
    repo.finish(job['id'],token,{'error_type':'uncertain fixture'},lambda *a:None,success=False)
    schedule(repo,'a','task');state=repo.get('a','task')
    assert state['pause_reason'] and 'round' not in state
    assert state['rounds'][-1]['status']=='annotation_incomplete'
    assert len(state['rounds'][-1]['sample_ids'])==20
    assert not any(j['kind'] in {'review','train'} for j in repo.jobs('a','task'))


def test_failed_assessment_blocks_future_paid_annotation(database):
    repo=ready(database);schedule(repo,'a','task')
    for _ in range(2):
        finish(repo,'review',lambda j:{'decisions':[{'sample_id':s['sample_id'],'review_key':s['review_key'],
            'decision':'accept_positive','reason':'fixture correct'} for s in j['inputs']['samples']]})
    extra=copy.deepcopy(state_fixture()['samples'][0]);extra.update(sample_id='late',image_sha256='late')
    extra.pop('review');extra.pop('annotation');repo.capture('a','task',extra)
    schedule(repo,'a','task')
    job,token=repo.claim({'a'},{'annotate','assess'},'model','fixture')
    assert job['kind']=='assess'
    repo.finish(job['id'],token,{'error_type':'failed fixture'},lambda *a:None,success=False)
    schedule(repo,'a','task')
    assert repo.get('a','task')['pause_reason'] and repo.claim({'a'},{'annotate'},'model','fixture') is None


def test_explicit_annotation_version_rechecks_without_new_photo_or_duplicate_wakeup(database):
    repo=ready(database);schedule(repo,'a','task')
    for _ in range(2):
        finish(repo,'review',lambda j:{'decisions':[{'sample_id':s['sample_id'],'review_key':s['review_key'],
            'decision':'accept_positive','reason':'fixture correct'} for s in j['inputs']['samples']]})
    schedule(repo,'a','task')
    finish(repo,'assess',lambda j:{'action':'collect','approved_real_target':20,'next_increment':5,
                                 'reason':'additional scene variation','gaps':['more capture scenes']})
    assert repo.get('a','task')['review_trigger']==25
    def relabel(state,c):
        sample=state['samples'][0];sample.setdefault('annotation_history',[]).append(sample.pop('annotation'))
        repo.enqueue(c,state,'annotate','explicit-fixture',{'sample':sample,'classes':state['classes'],'profiles':{},'version':2,'explicit':True})
    repo.mutate('a','task',relabel)
    finish(repo,'annotate',lambda j:{'status':'completed','objects':[{'class_id':'a','bbox':[0,0,10,10]}],'receipt':{}})
    schedule(repo,'a','task');current=repo.get('a','task')['round']
    assert current['sample_ids']==['0'] and current['candidate_count']==20
    finish(repo,'review',lambda j:{'decisions':[{'sample_id':'0','review_key':j['inputs']['samples'][0]['review_key'],
        'decision':'accept_positive','reason':'new version checked'}]})
    schedule(repo,'a','task')
    finish(repo,'assess',lambda j:{'action':'collect','approved_real_target':20,'next_increment':5,
                                 'reason':'additional scene variation','gaps':['more capture scenes']})
    before=len(repo.jobs('a','task'));schedule(repo,'a','task');schedule(repo,'a','task')
    state=repo.get('a','task')
    assert len(state['samples'])==20 and state['review_trigger']==25 and not state['recheck_sample_ids']
    assert 'round' not in state and len(repo.jobs('a','task'))==before


def test_assessment_receives_initial_and_current_thresholds_before_lowering(database):
    repo=ready(database,approved_target=30);schedule(repo,'a','task')
    for _ in range(2):
        finish(repo,'review',lambda j:{'decisions':[{'sample_id':s['sample_id'],'review_key':s['review_key'],
            'decision':'accept_positive','reason':'fixture correct'} for s in j['inputs']['samples']]})
    schedule(repo,'a','task')
    assess=next(j for j in repo.jobs('a','task') if j['kind']=='assess')
    assert assess['inputs']['initialization']['approved_real_target']==30
    assert assess['inputs']['approved_real_target']==30 and assess['inputs']['review_trigger']==20
    finish(repo,'assess',lambda j:{'action':'train','approved_real_target':20,'next_increment':10,
        'reason':'lower target after completed quality screening','gaps':[]})
    state=repo.get('a','task')
    assert state['approved_real_target']==20 and state['initialization']['approved_real_target']==30
    assert len([j for j in repo.jobs('a','task') if j['kind']=='train'])==1
