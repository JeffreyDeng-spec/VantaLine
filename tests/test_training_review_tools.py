"""No model calls: sandbox mount separation and bounded crop tools."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from local_inspection_service.codex_compare.worker import sandbox_command,MODULE as LABEL,SKILL as LABEL_SKILL
from local_inspection_service.training_review.worker import MODULE,SKILL,prepare


def test_review_mounts_do_not_inherit_label_tools(tmp_path):
    runtime=tmp_path/'codex';runtime.write_text('fixture')
    with patch('shutil.which',return_value='/usr/bin/bwrap'):
        baseline=sandbox_command(tmp_path,tmp_path,runtime,'token','model')
        review=sandbox_command(tmp_path,tmp_path,runtime,'token','gpt-6-astra',tools_module=MODULE,skill_directory=SKILL)
    assert str(LABEL/'cli.py') in baseline and str(LABEL_SKILL) in baseline
    assert str(MODULE/'cli.py') in review and str(SKILL) in review
    assert str(LABEL/'cli.py') not in review and str(LABEL_SKILL) not in review
    assert '--ro-bind' in review and '--clearenv' in review and 'web_search="disabled"' in review


def test_more_than_ten_originals_block_before_read_or_model(tmp_path):
    files=SimpleNamespace(read_bytes=lambda *a,**k:pytest.fail('must not read'))
    with pytest.raises(ValueError):prepare({'kind':'review','inputs':{'samples':[{}]*11}},tmp_path,files)


def test_crop_cannot_write_input_or_escape_sandbox():
    from local_inspection_service.training_review.image_tools import crop
    with pytest.raises(ValueError):crop('/input/original.png','/input/replaced.png',[0,0,10,10])
    with pytest.raises(ValueError):crop('/secret/actual.png','/work/crop.png',[0,0,10,10])


@pytest.mark.parametrize('legacy',[False,True])
def test_crop_pixels_and_transform_support_legacy_system_pillow(tmp_path,legacy):
    import PIL
    from PIL import Image
    from local_inspection_service.training_review.image_tools import crop
    source=tmp_path/'original.png';target=tmp_path/'crop.png'
    Image.new('RGB',(40,30),'red').save(source)
    api=SimpleNamespace(open=Image.open,LANCZOS=Image.Resampling.LANCZOS) if legacy else Image
    # Exercise API selection without deleting globals used internally by current Pillow.
    def mapped(path):return Path('/input/original.png' if path==source else '/work/crop.png')
    with patch.object(PIL,'Image',api),patch.object(Path,'resolve',mapped):
        evidence=crop(str(source),str(target),[3,4,13,14],2)
    with Image.open(target) as result:
        assert result.size==(20,20) and result.getpixel((10,10))==(255,0,0)
    import json
    assert json.loads(Path(str(target)+'.transform.json').read_text())==evidence
    assert evidence['crop_pixels']==[3,4,13,14] and evidence['resampler']=='LANCZOS'


def test_annotation_preparation_failure_is_persisted_without_paid_call():
    import time
    from local_inspection_service.training_review import worker
    job = {'id':'job', 'kind':'annotate', 'attempt_id':'attempt', 'started_at':time.time(),
           'inputs': {'sample': {'source_path':'fixture', 'image_sha256':'digest'}, 'classes':[]}}
    finished = []
    repo = SimpleNamespace(finish=lambda *a, **kw: finished.append((a, kw)))
    with patch.object(worker, 'with_repo', lambda fn: fn(repo)), \
         patch.object(worker, 'BusinessFiles', lambda: SimpleNamespace(read_bytes=lambda *a, **kw: b'fixture')), \
         patch.object(worker, 'digest', lambda raw: 'digest'), \
         patch.object(worker, 'settings', side_effect=ValueError('sensitive exception text')), \
         patch.object(worker, 'annotate_cached', side_effect=AssertionError('must not call')):
        worker.run(job, 'token', {'secret_file':'private'})
    assert len(finished) == 1
    args, kwargs = finished[0]
    result = args[2]
    assert result['status'] == 'failed' and result['error_code'] == 'model_settings_failed'
    assert result['receipt']['external_call_started'] is False
    assert 'sensitive' not in str(result) and 'success' not in kwargs
    state = {}; current = {'result':result}
    with patch.object(worker, 'apply_result') as apply:
        args[3](state, current, 'cursor')
        apply.assert_called_once_with(repo, state, current, 'cursor')


def test_completed_cli_without_report_cannot_pass_and_keeps_usage():
    import time
    from local_inspection_service.training_review import worker
    receipt=[];finished=[]
    repo=SimpleNamespace(receipt=lambda *a:receipt.append(a),finish=lambda *a,**kw:finished.append((a,kw)))
    meta={'session_id':'fixture','usage':{'input_tokens':123},
          'diagnostics':{'exit_code':0,'turn_completed':True,'turn_failed':False,'report_accepted':False}}
    job={'id':'job','kind':'initialize','attempt_id':'attempt','started_at':time.time()}
    with patch.object(worker,'with_repo',lambda fn:fn(repo)), \
         patch.object(worker,'review',side_effect=worker.ReviewFailure('report_missing',meta)):
        worker.run(job,'token',{})
    assert len(finished)==1 and len(receipt)==1
    args,kw=finished[0]
    assert kw['success'] is False and args[2]['error_code']=='report_missing'
    assert args[2]['usage']=={'input_tokens':123} and args[2]['diagnostics']['report_accepted'] is False
    assert args[3]({}, {}, None) is None  # failed report cannot mutate acceptance state


def test_broker_rejects_overlong_reason_with_safe_code_and_retains_contract(tmp_path):
    import json,threading,tempfile
    from local_inspection_service.training_review import worker,cli
    auth=tmp_path/'auth.json';auth.write_text('{}')
    accepted=[];diagnostics={};receipts=[]
    repo=SimpleNamespace(pulse=lambda *a:True,receipt=lambda *a:receipts.append(a))
    job={'kind':'initialize','id':'job','attempt_id':'attempt'}
    # Unix socket names have a short kernel limit (also on macOS).
    with tempfile.TemporaryDirectory(prefix='rp-',dir='/tmp') as socket_dir, \
         patch.object(worker,'with_repo',lambda fn:fn(repo)), \
         patch.dict('os.environ',{'VANTALINE_TASK_SOCKET':socket_dir+'/report.sock'}):
        path=Path(socket_dir)/'report.sock'
        server=worker.broker(job,'fixture-token',path,accepted,auth,diagnostics)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            conn=cli.Connection('localhost')
            payload={'review_trigger':20,'approved_real_target':20,'reason':'x'*1001}
            conn.request('POST','/',json.dumps(payload),{'Authorization':'Bearer fixture-token'})
            response=conn.getresponse();body=json.loads(response.read());conn.close()
            assert response.status==422 and body['error_code']=='reason_invalid'
            assert not accepted and not receipts and diagnostics=={'report_refusals':{'reason_invalid':1}}
            assert 'x'*10 not in json.dumps(body)+json.dumps(diagnostics)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)


def test_report_refusal_is_distinct_from_missing_or_abnormal_cli_exit():
    from local_inspection_service.training_review.worker import completion_failure
    assert completion_failure(0,True,False,[],'session',{})=='report_missing'
    assert completion_failure(0,True,False,[],'session',{'reason_invalid':1})=='report_rejected'
    assert completion_failure(1,True,False,[{}],'session',{})=='cli_exit_failed'
    assert completion_failure(0,True,True,[{}],'session',{})=='cli_turn_failed'
    assert completion_failure(0,False,False,[{}],'session',{})=='cli_turn_incomplete'
    assert completion_failure(0,True,False,[{}],None,{})=='cli_session_missing'
    assert completion_failure(0,True,False,[{}],'session',{}) is None
