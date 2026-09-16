"""Image-coordinate contract regression; no network or production data."""
import copy
import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image
from local_inspection_service.label_inspection import model


def main():
    issue = dict(description="fixture", onStandard=True, onCamera=True,
                 bboxStandard=dict(x=.2, y=.3, w=.1, h=.2),
                 bboxCamera=dict(x=.1, y=.2, w=.3, h=.4))
    raw = dict(hasDiff=True, similarity=88, coordinateSpace=model.COORDINATE_SPACE,
               issues=[issue])
    snapshot = copy.deepcopy(raw)
    result = model.result(raw, None, (1200, 800))
    assert result['issues'][0]['reference_box'] == [.2, .3, .1, .2]
    assert result['issues'][0]['actual_box'] == [.1, .2, .3, .4]
    assert result['coordinate_space'] == model.COORDINATE_SPACE
    assert raw == snapshot
    cropped = model.result(raw, [120, 80, 600, 400], (1200, 800))
    assert cropped['issues'][0]['actual_box'] == [.15, .2, .15, .2]
    assert cropped['issues'][0]['reference_box'] == [.2, .3, .1, .2]
    # Missing/old coordinate declarations must not reactivate ambiguous history.
    for space in (None, 'label_relative', ''):
        old = {**raw, 'coordinateSpace': space}
        row = model.result(old, None, (1200, 800))['issues'][0]
        assert row['reference_box'] is None and row['actual_box'] is None
    # Malformed geometry only disables that side, not all other issue boxes.
    for box in (None, [], {}, dict(x=True,y=.2,w=.3,h=.4),
                dict(x=-.1,y=.2,w=.3,h=.4), dict(x=.8,y=.2,w=.3,h=.4),
                dict(x=.1,y=.2,w=0,h=.4), dict(x=float('nan'),y=.2,w=.3,h=.4)):
        bad = {**raw, 'issues': [{**issue, 'bboxCamera': box}, issue]}
        rows = model.result(bad, None, (1200,800))['issues']
        assert rows[0]['actual_box'] is None and rows[0]['reference_box']
        assert rows[1]['actual_box'] and rows[1]['reference_box']
    invisible = {**raw, 'issues': [{**issue, 'onCamera': False}]}
    row = model.result(invisible, None, (1200,800))['issues'][0]
    assert row['actual_box'] is None and row['reference_box']
    # The input and displayed evidence share EXIF-transposed orientation.
    image = Image.new('RGB', (120,80)); exif = image.getexif(); exif[274] = 6
    data=io.BytesIO(); image.save(data, 'JPEG', exif=exif)
    oriented, transform = model.decode(data.getvalue())
    assert oriented.size == (80,120) and transform['orientation'] == 6
    for name in ('original','cropped'):
        prompt=model.PROMPTS[name]
        assert model.COORDINATE_SPACE in prompt and '整张输入图片' in prompt
        assert '相对于标签的比例' not in prompt
    print('label image-coordinate contracts PASS')

if __name__ == '__main__':
    main()
