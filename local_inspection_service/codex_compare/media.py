"""Content-addressed private images. File names are never supplied by an agent."""
import os
import re
from pathlib import Path
from .contracts import digest, normalize_image


class MediaStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, owner, sha):
        if not re.fullmatch('[a-f0-9]{64}', sha):
            raise ValueError('Invalid image identity')
        path = self.root / digest(owner.encode()) / sha
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('Invalid media path')
        return path

    def put(self, owner, data):
        sha = digest(data)
        path = self.path(owner, sha)
        # The provisioned root group is limited to web/worker accounts.
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.mkdir(mode=0o770)
        except FileExistsError:
            pass
        else:
            path.parent.chmod(0o2770)
        import tempfile
        fd, temporary = tempfile.mkstemp(prefix='.image-', dir=path.parent)
        try:
            os.fchmod(fd, 0o660)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if digest(path.read_bytes()) != sha:
                    raise ValueError('Corrupt stored evidence')
        finally:
            os.unlink(temporary)
        return sha

    def image(self, owner, data):
        normalized, preview, size = normalize_image(data)
        return {'original': self.put(owner, data), 'image': self.put(owner, normalized),
                'preview': self.put(owner, preview), 'size': size}

    def read(self, owner, sha):
        data = self.path(owner, sha).read_bytes()
        if digest(data) != sha:
            raise ValueError('Evidence hash mismatch')
        return data
