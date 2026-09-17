"""Display-only derivative; never passed to recognition or matching."""
import io
import hashlib
from PIL import Image
from .runtime.media import MediaWriter

VERSION = 'evidence-preview-v1'


def create(image):
    original_size = list(image.size)
    picture = image.convert('RGBA')
    white = Image.new('RGBA', picture.size, 'white')
    white.alpha_composite(picture)
    picture = white.convert('RGB')
    picture.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    stream = io.BytesIO()
    picture.save(stream, format='JPEG', quality=85, subsampling=0)
    blob = stream.getvalue()
    return blob, dict(version=VERSION, source_size=original_size, preview_size=list(picture.size),
        scale_x=picture.width/original_size[0], scale_y=picture.height/original_size[1],
        bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(), lossy=True, display_only=True)


def save(media: MediaWriter, record, image):
    blob, metadata = create(image)
    path = media.path(record['owner_user_id'], record['standard_id'], record['id']+'-'+VERSION+'.jpg')
    media.write(path, blob)
    record['source_preview_path'] = str(path)
    record['source_preview_sha256'] = metadata['sha256']
    record['diagnostics']['source_preview'] = metadata
