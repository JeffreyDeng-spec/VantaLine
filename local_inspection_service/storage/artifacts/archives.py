"""Index-driven ZIP creation with one scratch lease and bounded output writes."""
from pathlib import Path, PurePosixPath
import zipfile

from .disk import DiskCapacityError
from .types import Artifact, checksum_file


class BoundedOutput:
    def __init__(self, stream, budget, limit):
        self.stream, self.budget, self.limit = stream, budget, limit
        self.high_water = 0

    def write(self, data):
        end = self.stream.tell() + len(data)
        growth = max(0, end - self.high_water)
        if end > self.limit or self.budget.free_bytes() - growth < self.budget.reserve_bytes:
            raise DiskCapacityError("archive workspace capacity unavailable")
        written = self.stream.write(data)
        self.high_water = max(self.high_water, self.stream.tell())
        return written

    def tell(self):
        return self.stream.tell()

    def seek(self, *args):
        return self.stream.seek(*args)

    def flush(self):
        return self.stream.flush()


class LeasedArchive:
    """TemporaryDirectory-compatible cleanup retains a cross-process reservation."""
    def __init__(self, context, directory):
        self.context, self.name = context, str(directory)
        self.closed = False

    def cleanup(self):
        if not self.closed:
            self.closed = True
            self.context.__exit__(None, None, None)

    def __enter__(self):
        return self.name

    def __exit__(self, *args):
        self.cleanup()

    def publish(self, store, path, source, *, expected_generation):
        if self.closed or Path(source).resolve().parent != Path(self.name).resolve():
            raise ValueError("archive is not owned by this live workspace")
        # This completed ZIP is owned by the held work reservation. Upload it
        # directly, avoiding a second full copy in the 2 GiB upload partition.
        sha, size = checksum_file(source)
        row = Artifact(path, expected_generation + 1, sha, size)
        store.objects.put(row, source)
        if checksum_file(source) != (sha, size):
            raise ValueError("archive changed during publication")
        return store.locations.publish(row, expected_generation=expected_generation)


def package(store, prefix: str, *, skip_dirs=()):
    rows = store.list(prefix)
    if not rows:
        raise FileNotFoundError("training dataset is not indexed")
    rows = [(row, PurePosixPath(row.path).relative_to(prefix).as_posix()) for row in rows]
    rows = [(row, name) for row, name in rows if name.split("/", 1)[0].lower() not in skip_dirs]
    if not rows:
        raise FileNotFoundError("training dataset has no included files")
    # DEFLATE worst-case expansion plus UTF-8 filenames/ZIP64 headers. Writes
    # additionally enforce this reservation; unexpected expansion fails closed.
    allowance = sum(row.size + row.size // 100 + 1024 + len(name.encode()) * 2 for row, name in rows) + 1024*1024
    context = store.budget.workspace("work", allowance)
    directory = context.__enter__()
    handle = LeasedArchive(context, directory)
    archive = directory / "dataset.zip"
    try:
        with archive.open("xb") as raw:
            output = BoundedOutput(raw, store.budget, allowance)
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as target:
                for row, name in rows:
                    with target.open(name, "w", force_zip64=True) as entry:
                        store.objects.copy_to(row, entry)
            output.flush()
        return handle, archive
    except BaseException:
        handle.cleanup()
        raise
