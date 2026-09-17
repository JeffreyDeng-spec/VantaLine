"""Training ZIP packaging, streaming hashes and dataset file manifests."""
from collections.abc import Callable, Set
import hashlib
from pathlib import Path
import shutil
import tempfile
from typing import Any
from PIL import Image


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DatasetArchives:
    def __init__(self, safe_name: Callable[[str], str], skip_dirs: Callable[[], Set[str]],
                 jpeg_quality: Callable[[], int], digest: Callable[[Path], str]):
        self.safe_name, self.skip_dirs = safe_name, skip_dirs
        self.jpeg_quality, self.digest = jpeg_quality, digest

    def package_training_dataset(self, dataset_dir: Path, job_id: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
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
        files = []
        for path in sorted(item for item in dataset_dir.rglob("*") if item.is_file()):
            rel = path.relative_to(dataset_dir).as_posix()
            files.append({"path": rel, "size": path.stat().st_size, "sha256": self.digest(path)})
        return files
