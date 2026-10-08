"""Review orchestration tests with deterministic reports, not visual accuracy claims."""
import copy
from test_real_photo_feedback import database,classes,state_fixture
from local_inspection_service.training.real_photo_workflow import schedule,apply_result
from local_inspection_service.training.real_photo_contracts import review_key


def finish(repo,kind,result):
    job,token=repo.claim({'a'},{kind},'gpt-6-astra','fixture')
    return repo.finish(job['id'],token,result(job),lambda s,j,c:apply_result(repo,s,j,c))


def ready(database):
    repo=database();repo.enable('a','task',classes(),{})
    finish(repo,'initialize',lambda j:{'review_trigger':20,'approved_real_target':20,'reason':'first real cohort'})
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
