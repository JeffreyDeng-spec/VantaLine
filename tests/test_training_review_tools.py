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
         patch.object(worker, 'annotate', side_effect=AssertionError('must not call')):
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
