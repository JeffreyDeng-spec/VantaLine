"""Compose one artifact owner and its file/image views without allocating storage."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from .files import BusinessFiles
from .images import ImageFiles
from .runtime import ArtifactRuntimeProvider, RuntimeBuilder


@dataclass(frozen=True)
class ArtifactComposition:
    runtime: ArtifactRuntimeProvider
    files: BusinessFiles
    images: ImageFiles


def create_artifact_composition(
    environment: Callable[[], Mapping[str, str]],
    cv2_provider: Callable[[], Any],
    pil_provider: Callable[[], Any],
    *, builder: RuntimeBuilder | None = None,
) -> ArtifactComposition:
    if environment is None or cv2_provider is None or pil_provider is None:
        raise TypeError("environment and image providers are required")
    runtime = ArtifactRuntimeProvider(environment, builder=builder)
    files = BusinessFiles(runtime_provider=runtime.get)
    return ArtifactComposition(runtime, files, ImageFiles(cv2_provider, pil_provider, files=files))
