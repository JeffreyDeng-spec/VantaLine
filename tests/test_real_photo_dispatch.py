"""Real PostgreSQL dispatch fencing and restart monitoring, without executing YOLO."""
import copy
import io
from PIL import Image
from test_real_photo_feedback import database, classes, state_fixture
from local_inspection_service.training.real_photo_contracts import dataset_gate, digest, review_key
from local_inspection_service.training.real_photo_annotation import canonical
from local_inspection_service.training.real_photo_dispatch import Dispatcher, DispatchPorts
from local_inspection_service.storage.artifacts.files import BusinessFiles


def test_single_training_submission_and_restart_reconciliation(database,tmp_path,monkeypatch):
    monkeypatch.setenv('VANTALINE_REAL_PHOTO_ACCOUNTS','a')
    repo=database();repo.enable('a','task',classes(),{})
    def seed(state,c):
        state['initialization']={'reason':'fixture'}
        state.update(state_fixture(),enabled=True,datasets=[],candidate_models=[])
        for i,s in enumerate(state['samples']):
            out=io.BytesIO();Image.new('RGB',(80,60),(i,20,50)).save(out,'PNG')
            raw=out.getvalue();path=tmp_path/(str(i)+'.png');path.write_bytes(raw)
            _,meta=canonical(raw);s.update(source_path=str(path),source_kind='real_photo',geometry=meta,image_sha256=digest(raw))
            s['review'].update(key=review_key(s,state['classes']),job_id='fixture')
        selected,splits,unsupported=dataset_gate(state,20)
        repo.enqueue(c,state,'train','fixture_train',{'samples':selected,'classes':state['classes'],'splits':splits,'unsupported_by_real_data':unsupported,'profiles':{}})
    repo.mutate('a','task',seed)
    tasks={};calls=[]
    def submit(job,dataset):
        calls.append(dataset['training_job_id']);tasks[calls[-1]]={'status':'running'}
    ports=DispatchPorts(repository=lambda:database().repository,files=lambda:BusinessFiles(runtime_provider=lambda:None),output=lambda owner:tmp_path/'datasets',submit=submit,training=lambda identifier:tasks.get(identifier))
    first=Dispatcher(ports);first.tick()
    assert len(calls)==1
    restarted=Dispatcher(ports);restarted.tick();assert len(calls)==1
    tasks[calls[0]]={'status':'completed','real_photo_test_metrics':{'missing':{'status':'unavailable','metrics':None}}}
    restarted.tick();assert len(calls)==1
    state=repo.get('a','task')
    assert state['enabled'] and state['candidate_models'][0]['status']=='completed'
    assert state['candidate_models'][0]['metrics']['missing']['metrics'] is None
    assert 'promotion' not in state


def test_changed_class_definition_revokes_active_initialization(database):
    repo=database();repo.enable('a','task',classes(),{})
    job,token=repo.claim({'a'},{'initialize'},'gpt-6-astra','fixture')
    changed=copy.deepcopy(classes());changed[0]['definition']='new definition'
    repo.enable('a','task',changed,{})
    assert not repo.pulse(job['id'],token)
    assert next(j for j in repo.jobs('a','task') if j['id']==job['id'])['status']=='cancel_requested'
