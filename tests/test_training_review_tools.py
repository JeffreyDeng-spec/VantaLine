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
