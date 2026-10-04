"""Private STANDARD COS transport; signed SDK errors never cross this boundary."""
import hashlib
import os
from pathlib import Path

from .types import Artifact, ArtifactIntegrityError, ArtifactUnavailable, checksum


def close_stream(stream):
    if stream is not None:
        try:
            stream.close()
        except Exception:
            # Closing an already consumed HTTP response must not expose signed
            # SDK request details or mask a checksum/capacity failure.
            pass


class CosObjects:
    def __init__(self, client, bucket: str):
        self._client, self.bucket = client, bucket

    @property
    def client(self):
        return self._client() if callable(self._client) else self._client

    def verify(self, artifact: Artifact) -> None:
        stream = None
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=artifact.key)
            stream = response["Body"].get_raw_stream()
            if checksum(stream, limit=artifact.size) != (artifact.sha256, artifact.size):
                raise ArtifactIntegrityError("object checksum mismatch")
        except ArtifactIntegrityError:
            raise
        except Exception:
            raise ArtifactUnavailable("COS verification unavailable") from None
        finally:
            close_stream(stream)

    def put(self, artifact: Artifact, source: Path) -> None:
        try:
            try:
                self.client.head_object(Bucket=self.bucket, Key=artifact.key)
            except Exception as error:
                if str(getattr(error, "get_status_code", lambda: None)()) != "404":
                    raise
                self.client.upload_file(
                    Bucket=self.bucket, Key=artifact.key, LocalFilePath=str(source),
                    PartSize=8, MAXThread=2, EnableMD5=True, StorageClass="STANDARD",
                    Metadata={"x-cos-meta-sha256": artifact.sha256},
                )
        except Exception:
            raise ArtifactUnavailable("COS upload unavailable") from None
        self.verify(artifact)

    def copy_to(self, artifact: Artifact, target) -> None:
        """Verified stream into a caller-owned bounded destination, never a URL."""
        stream = None
        try:
            stream = self.client.get_object(Bucket=self.bucket, Key=artifact.key)["Body"].get_raw_stream()
            sha, size = hashlib.sha256(), 0
            while block := stream.read(1024 * 1024):
                size += len(block)
                if size > artifact.size:
                    raise ArtifactIntegrityError("object exceeds its recorded length")
                target.write(block)
                sha.update(block)
            if (sha.hexdigest(), size) != (artifact.sha256, artifact.size):
                raise ArtifactIntegrityError("object checksum mismatch")
        except ArtifactUnavailable:
            raise
        except Exception:
            raise ArtifactUnavailable("COS stream unavailable") from None
        finally:
            close_stream(stream)

    def download(self, artifact: Artifact, destination: Path) -> None:
        """Only publish to a new caller-owned path; remove partial output on failure."""
        stream, created = None, False
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=artifact.key)
            stream = response["Body"].get_raw_stream()
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(fd, "wb") as out:
                sha, size = hashlib.sha256(), 0
                while block := stream.read(1024 * 1024):
                    size += len(block)
                    if size > artifact.size:
                        raise ArtifactIntegrityError("object exceeds its recorded length")
                    out.write(block)
                    sha.update(block)
                if (sha.hexdigest(), size) != (artifact.sha256, artifact.size):
                    raise ArtifactIntegrityError("object checksum mismatch")
                out.flush()
                os.fsync(out.fileno())
        except BaseException as error:
            if created:
                destination.unlink(missing_ok=True)
            if isinstance(error, (ArtifactIntegrityError, KeyboardInterrupt, SystemExit)):
                raise
            raise ArtifactUnavailable("COS download unavailable") from None
        finally:
            close_stream(stream)
