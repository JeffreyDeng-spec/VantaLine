import io
import json
import subprocess
import sys
from pathlib import Path
import pytest
from PIL import Image
from local_inspection_service.codex_compare.contracts import box, item, summary, validate_report, normalize_image
from local_inspection_service.codex_compare.media import MediaStore
from local_inspection_service.codex_compare.worker import artifact, sandbox_command


def png(text_color='white'):
    image = Image.new('RGB', (100, 80), text_color)
    output = io.BytesIO(); image.save(output, 'PNG'); return output.getvalue()


@pytest.mark.parametrize('bounds', [[0,0,0,1], [-.1,0,1,1], [0,0,1.1,1], [True,0,1,1], [0,0,float('nan'),1], [1,2,3]])
def test_bad_coordinates(bounds):
    with pytest.raises(ValueError): box(bounds)


def test_report_never_invents_pass():
    value = {'items': {}, 'summary': None}
    with pytest.raises(ValueError): validate_report(value)
    value['items']['a'] = item({'id':'a','status':'uncertain','explanation':'unclear','reference_text':'ABC','actual_text':'','reference_box':None,'actual_box':None})
    value['summary'] = summary({'decision':'MATCH','message':'same','checked_scope':'all','unchecked_scope':''})
    with pytest.raises(ValueError): validate_report(value)
    value['summary']['decision'] = 'REVIEW_REQUIRED'; validate_report(value)


def test_media_transform_and_owner(tmp_path):
    import base64
    media = MediaStore(tmp_path)
    source = media.image('a', png('red'))
    task = {'inputs': {'actual':source}}
    # Altered white upload must not be accepted as source pixels. The server
    # reconstructs the crop from immutable red input and records the transform.
    result = artifact(media, 'a', task, {'data':base64.b64encode(png()).decode(),'source':'actual','box':[0,0,.5,.5]})
    with Image.open(io.BytesIO(media.read('a',result['image']))) as im:
        assert im.getpixel((1,1)) == (255,0,0)
    assert result['source_pixels'] == [0,0,50,40]
    with pytest.raises(FileNotFoundError): media.read('b',result['image'])
    with pytest.raises(ValueError): media.path('a','../../etc/passwd')
    with pytest.raises(Exception): normalize_image(b'not an image')


def test_sandbox_has_no_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr('shutil.which',lambda _: None)
    with pytest.raises(RuntimeError): sandbox_command(tmp_path,tmp_path,tmp_path/'codex','secret','model')


def test_cli_help():
    cli = Path(__file__).parents[2]/'local_inspection_service/codex_compare/cli.py'
    # Resolve from repository root, regardless of pytest working directory.
    cli = Path(__file__).resolve().parents[2]/'local_inspection_service/codex_compare/cli.py'
    value = subprocess.run([sys.executable,str(cli),'--help'], capture_output=True,text=True)
    assert value.returncode == 0 and 'report' in value.stdout
