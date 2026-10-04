"""Training ZIP packaging, streaming hashes and dataset file manifests."""
from collections.abc import Callable, Set
import hashlib
from pathlib import Path
import shutil
import tempfile
from typing import Any
from PIL import Image
from ..storage.artifacts.runtime import get_runtime
from ..storage.artifacts.files import BusinessFiles

_business_files = BusinessFiles()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with _business_files.local_file(path) as local_path:
        with local_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


class DatasetArchives:
    def __init__(self, safe_name: Callable[[str], str], skip_dirs: Callable[[], Set[str]],
                 jpeg_quality: Callable[[], int], digest: Callable[[Path], str], *, runtime_provider=get_runtime):
        self.safe_name, self.skip_dirs = safe_name, skip_dirs
        self.jpeg_quality, self.digest = jpeg_quality, digest
        self.runtime_provider = runtime_provider

    def _cos_package(self, dataset_dir: Path, *, worker=False):
        runtime = self.runtime_provider()
        if runtime is None:
            return None
        key = runtime.key(dataset_dir)
        if runtime.mode == "hybrid" and not runtime.store.list(key):
            return None
        from ..storage.artifacts.archives import package
        # RunPod accepts native PNG training images. Stream original bytes to
        # avoid an unbounded second image tree or lossy changes during migration.
        return package(runtime.store, key, skip_dirs=self.skip_dirs() if worker else ())

    def package_training_dataset(self, dataset_dir: Path, job_id: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        remote = self._cos_package(dataset_dir)
        if remote is not None:
            return remote
        if not dataset_dir.exists() or not dataset_dir.is_dir():
            raise RuntimeError(f"Training dataset directory is missing: {dataset_dir}")
        temp_dir = tempfile.TemporaryDirectory(prefix=f"vantaline_{self.safe_name(job_id)}_")
        archive_base = Path(temp_dir.name) / "dataset"
        archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=str(dataset_dir)))
        return temp_dir, archive_path

    def build_worker_training_bundle(self, dataset_dir: Path, job_id: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        """Package a *training-only* copy of the dataset for the Windows worker.

    The HK->worker hop runs over a cross-region Tailscale link, so a raw 360MB+
    archive of lossless PNG samples reliably blows past the request timeout.
    We therefore (1) drop UI-only preview/debug folders and (2) transcode the
    PNG training images to high-quality JPEG. YOLO matches labels by file stem,
    so converting the extension is safe and keeps the dataset trainable while
    cutting the payload several-fold.
    """
        remote = self._cos_package(dataset_dir, worker=True)
        if remote is not None:
            return remote
        if not dataset_dir.exists() or not dataset_dir.is_dir():
            raise RuntimeError(f"Training dataset directory is missing: {dataset_dir}")
        temp_dir = tempfile.TemporaryDirectory(prefix=f"vantaline_worker_{self.safe_name(job_id)}_")
        staging_dir = Path(temp_dir.name) / "dataset"
        staging_dir.mkdir(parents=True, exist_ok=True)
        for source in sorted(item for item in dataset_dir.rglob("*") if item.is_file()):
            rel = source.relative_to(dataset_dir)
            if rel.parts and rel.parts[0].lower() in self.skip_dirs():
                continue
            is_training_image = bool(rel.parts) and rel.parts[0].lower() == "images" and source.suffix.lower() in {".png", ".bmp", ".tiff", ".tif"}
            if is_training_image:
                target = (staging_dir / rel).with_suffix(".jpg")
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with Image.open(source) as handle:
                        handle.convert("RGB").save(target, format="JPEG", quality=self.jpeg_quality())
                    continue
                except (OSError, ValueError):
                    target = staging_dir / rel
            else:
                target = staging_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        archive_base = Path(temp_dir.name) / "dataset"
        archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=str(staging_dir)))
        return temp_dir, archive_path

    def dataset_file_manifest(self, dataset_dir: Path) -> list[dict[str, Any]]:
        runtime = self.runtime_provider()
        if runtime is not None:
            key = runtime.key(dataset_dir)
            rows = runtime.store.list(key)
            if rows or runtime.mode != "hybrid":
                return [{"path": Path(row.path).relative_to(key).as_posix(), "size": row.size,
                         "sha256": row.sha256} for row in rows]
        files = []
        for path in sorted(item for item in dataset_dir.rglob("*") if item.is_file()):
            rel = path.relative_to(dataset_dir).as_posix()
            files.append({"path": rel, "size": path.stat().st_size, "sha256": self.digest(path)})
        return files
