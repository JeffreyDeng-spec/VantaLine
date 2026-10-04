"""Explicit native image I/O adapters; local calls retain their original arguments."""
import io
from pathlib import Path

from .files import BusinessFiles
from .types import ArtifactUnavailable


class ImageFiles:
    def __init__(self, cv2_provider=None, pil_provider=None, *, files=None):
        self.cv2_provider, self.pil_provider = cv2_provider, pil_provider
        self.files = files if files is not None else BusinessFiles()

    def imread(self, filename, *args, **kwargs):
        cv2 = self.cv2_provider()
        if self.files.runtime(filename) is None:
            return cv2.imread(filename, *args, **kwargs)
        flags = args[0] if args else kwargs.get("flags", 1)
        import numpy as np
        try:
            contents = self.files.read_bytes(filename)
        except FileNotFoundError:
            return None
        if not contents:
            return None
        return cv2.imdecode(np.frombuffer(contents, dtype=np.uint8), flags)

    def imwrite(self, filename, image, *args, **kwargs):
        cv2 = self.cv2_provider()
        if self.files.runtime(filename) is None:
            return cv2.imwrite(filename, image, *args, **kwargs)
        ok, encoded = cv2.imencode(Path(filename).suffix, image, *args, **kwargs)
        if not ok:
            raise ArtifactUnavailable("image encoding failed before publication")
        self.files.write_bytes(filename, encoded.tobytes())
        return True

    def open(self, filename, *args, **kwargs):
        pil = self.pil_provider()
        if not isinstance(filename, (str, Path)) or self.files.runtime(filename) is None:
            return pil.open(filename, *args, **kwargs)
        return pil.open(io.BytesIO(self.files.read_bytes(filename)), *args, **kwargs)

    def save(self, image, filename, *args, **kwargs):
        if not isinstance(filename, (str, Path)) or self.files.runtime(filename) is None:
            return image.save(filename, *args, **kwargs)
        if not args and "format" not in kwargs:
            kwargs["format"] = self.pil_provider().registered_extensions().get(Path(filename).suffix.lower())
        output = io.BytesIO()
        image.save(output, *args, **kwargs)
        self.files.write_bytes(filename, output.getvalue())
