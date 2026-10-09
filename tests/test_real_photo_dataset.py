"""Original pixels, exact accepted versions and group-disjoint dataset publication."""
import io
from PIL import Image
import pytest
from test_real_photo_feedback import state_fixture
from local_inspection_service.training.real_photo_annotation import canonical
from local_inspection_service.training.real_photo_contracts import digest,review_key,dataset_gate
from local_inspection_service.training.real_photo_dataset import build
from local_inspection_service.storage.artifacts.files import BusinessFiles


def test_dataset_only_accepted_originals_full_classes_group_split(tmp_path):
    state=state_fixture()
    for i,s in enumerate(state['samples']):
        raw=io.BytesIO();Image.new('RGB',(80,60),(i,30,50)).save(raw,'PNG')
        path=tmp_path/(str(i)+'.png');path.write_bytes(raw.getvalue())
        _,meta=canonical(raw.getvalue());s.update(source_path=str(path),source_kind='real_photo',image_sha256=digest(raw.getvalue()),geometry=meta)
        s['review'].update(key=review_key(s,state['classes']),job_id='fixture_review')
    selected,splits,unsupported=dataset_gate(state,20)
    job={'owner_user_id':'a','task_id':'task','fingerprint':digest(state),'inputs':{'samples':selected,'classes':state['classes'],'splits':splits,'unsupported_by_real_data':unsupported,'profiles':{}}}
    value=build(job,BusinessFiles(runtime_provider=lambda:None),tmp_path/'dataset')
    assert value['sample_count']==value['real_source_count']==20 and value['synthetic_sample_count']==0
    assert value['unsupported_by_real_data']==['missing'] and len(value['class_names'])==2
    import yaml
    assert yaml.safe_load(open(value['dataset_yaml']))['test']=='images/test'
    for row in value['samples']:
        label=open(row['labels']).read().strip()
        if label:assert all(0<float(v)<=1 for v in label.split()[1:])
    state['samples'][0]['annotation']['version']+=1
    with pytest.raises(ValueError):build(job,BusinessFiles(runtime_provider=lambda:None),tmp_path/'bad')
