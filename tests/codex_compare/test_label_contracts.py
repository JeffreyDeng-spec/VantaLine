import copy
import json
import subprocess
import sys
from pathlib import Path
import pytest
from local_inspection_service.codex_compare.label_contracts import DIMENSIONS, apply, region
from local_inspection_service.codex_compare.contracts import validate_report


def card():
    task = dict(report_version='label-v2', elements={}, checks={}, issues={}, artifacts={}, decodes={})
    apply(task, 'element', {'id':'E1','name':'outline','category':'outline','description':'single label',
                           'reference':{'box':[0,0,1,1]}, 'actual':{'box':[0,0,1,1]}})
    plan = [{'id':'G'+d,'dimension':d,'element_ids':[], 'expected':'Inspect '+d} for d in DIMENSIONS]
    plan += [{'id':'E'+d,'dimension':d,'element_ids':['E1'],'expected':'Inspect outline '+d} for d in ('shape','layout','completeness')]
    apply(task,'checklist',{'checks':plan})
    for c in list(task['checks'].values()):
        apply(task,'check',{**c,'status':'not_applicable' if c['dimension']=='codes' else 'match','observed':'No code' if c['dimension']=='codes' else 'Same','explanation':'Both original images inspected'})
    task['summary'] = dict(decision='MATCH',message='same',checked_scope='all planned scope',unchecked_scope='')
    return task


def test_additive_plan_preserves_results_and_pending():
    task=card();validate_report(task)
    original=copy.deepcopy(task['checks'])
    apply(task,'checklist',{'checks':[{'id':'new','dimension':'print','expected':'Recheck small region','element_ids':['E1']}]})
    assert all(task['checks'][k]==v for k,v in original.items())
    apply(task,'checklist',{'checks':[{'id':'Gshape','dimension':'shape','expected':'Inspect shape','element_ids':[]}]})
    assert task['checks']['Gshape']['status']=='match'
    assert task['checks']['new']['status']=='pending'
    with pytest.raises(ValueError,match='Unfinished'):validate_report(task)
    with pytest.raises(ValueError,match='immutable'):
        apply(task,'check',{**task['checks']['new'],'dimension':'text'})


def test_coverage_and_uncertainty_cannot_pass():
    task=card();del task['checks']['Gcolor']
    with pytest.raises(ValueError,match='ten'):validate_report(task)
    task=card();del task['checks']['Eshape']
    with pytest.raises(ValueError,match='element dimensions'):validate_report(task)
    task=card();task['checks']['Gcolor'].update(status='uncertain',observed='glare',explanation='cannot distinguish ink from reflection')
    with pytest.raises(ValueError):validate_report(task)
    task['summary'].update(decision='REVIEW_REQUIRED',unchecked_scope='color under glare')
    validate_report(task)


def test_issue_revision_and_missing_side():
    task=card();task['checks']['Eshape']['status']='difference';task['summary']['decision']='DIFFERENCES'
    with pytest.raises(ValueError,match='issue'):validate_report(task)
    issue={'id':'I1','check_id':'Eshape','title':'notch missing','explanation':'actual location unavailable','reference':{'polygon':[[0,0],[.4,0],[.2,.3]]},'actual':None}
    apply(task,'issue',issue);validate_report(task)
    with pytest.raises(ValueError):apply(task,'issue',{**issue,'resolved':True})
    task['checks']['Eshape']['status']='match';apply(task,'issue',{**issue,'resolved':True})
    task['summary']['decision']='MATCH';validate_report(task)


@pytest.mark.parametrize('value',[{'polygon':[[0,0],[2,0],[1,1]]},{'polygon':[[0,0],[.2,.2],[.3,.3]]},{'box':[0,0,1,1],'html':'<script/>'},{'polygon':[[0,0],[True,0],[0,1]]}])
def test_invalid_regions(value):
    with pytest.raises(ValueError):region(value)


def test_code_match_needs_equal_local_payloads():
    task=card();entry={**task['checks']['Gcodes'],'status':'match'}
    with pytest.raises(ValueError,match='decoding'):apply(task,'check',entry)
    task['decodes']={'r':{'source':'reference','values':['ABC']},'a':{'source':'actual','values':['XYZ']}}
    with pytest.raises(ValueError,match='differ'):apply(task,'check',{**entry,'decode_ids':['r','a']})
    task['decodes']['a']['values']=['ABC'];apply(task,'check',{**entry,'decode_ids':['r','a']})


def test_geometry_mapping_and_skill_contract():
    from argparse import Namespace
    from local_inspection_service.codex_compare.image_tools import local_image
    assert local_image(Namespace(action='map',box='[0,0,.5,1]'.replace('.5','0.5'),crop='[0.1,0.2,0.4,0.6]'))['box']==[.1,.2,.2,.6]
    base=Path(__file__).resolve().parents[2]/'local_inspection_service/codex_compare'
    for group in ('card','element','checklist','check','issue','image'):
        result=subprocess.run([sys.executable,str(base/'cli.py'),group,'--help'],capture_output=True)
        assert result.returncode==0
    assert '$vantaline-label-inspection' in (base/'label_prompt.md').read_text()
    assert (base/'skills/vantaline-label-inspection/references/cli.md').is_file()


def test_required_element_dimension_cannot_be_skipped():
    task=card()
    with pytest.raises(ValueError,match='inapplicable'):
        apply(task,'check',{**task['checks']['Eshape'],'status':'not_applicable'})


def test_local_decode_uses_source_pixels(tmp_path):
    import io
    from PIL import Image
    from local_inspection_service.codex_compare.media import MediaStore
    from local_inspection_service.codex_compare.worker import decode
    cv2=pytest.importorskip('cv2')
    qr=cv2.QRCodeEncoder_create().encode('VantaLine-test-payload')
    buffer=io.BytesIO()
    Image.fromarray(cv2.copyMakeBorder(qr,4,4,4,4,cv2.BORDER_CONSTANT,value=255)).resize((400,400),Image.Resampling.NEAREST).save(buffer,'PNG')
    media=MediaStore(tmp_path);task={'inputs':{'reference':media.image('a',buffer.getvalue())}}
    result=decode(media,'a',task,{'source':'reference','box':[0,0,1,1]})
    assert result['values']==['VantaLine-test-payload']
    with pytest.raises(ValueError):decode(media,'a',task,{'source':'reference','box':[0,0,1,1],'values':['fake']})


def test_selected_label_boundary():
    task=card();task['inputs']={'reference_region':[.2,.2,.4,.4]}
    with pytest.raises(ValueError,match='outside selected'):
        apply(task,'element',task['elements']['E1'])
    apply(task,'element',{**task['elements']['E1'],'id':'annotation','category':'engineering'})


def test_quality_metrics_separate_uncertainty_and_sample_provenance():
    from scripts.evaluate_label_cards import evaluate
    def case(kind,status):return {'kind':kind,'expected':{'color':'difference'},'report':{'checks':[{'dimension':'color','status':status}]}}
    result=evaluate([case('real_photo','uncertain'),case('source_mutation','match'),case('synthetic','difference')])
    assert result['real_photo']['dimensions']['color']['uncertain']==1
    assert result['real_photo']['dimensions']['color']['false_negative']==0
    assert result['source_mutation']['dimensions']['color']['false_negative']==1
    assert result['synthetic']['dimensions']['color']['true_positive']==1
