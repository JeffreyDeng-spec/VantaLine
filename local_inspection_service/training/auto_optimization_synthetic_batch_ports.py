"""Narrow configuration, sprite and rendering capabilities for one synthetic batch."""
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
Record = dict[str, Any]

class CanonicalSizes(Protocol):
    def __call__(self, state: Record, extra_sprites: list[Record] | None = None) -> dict[str, dict[str, int]]: ...

class RenderSample(Protocol):
    def __call__(self, *, sprites: list[Record], class_index: dict[str, int],
                 accessories_by_id: dict[str, Record], output_path: Path,
                 label_path: Path, annotated_path: Path, split: str,
                 rng: np.random.Generator,
                 canonical_sizes: dict[str, dict[str, int]] | None = None,
                 background_set_id: str | None = None) -> Record | None: ...

@dataclass(frozen=True)
class SyntheticBatchConfiguration:
    safe_background_set_id: Callable[[], Callable[[str], str]]
    default_auto_optimize_settings: Callable[[], Callable[[], Record]]
    auto_optimize_positive_derivatives_per_real_image: Callable[[], Callable[[Record], int]]
    AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY: Callable[[], str]
    _request_user: Callable[[], ContextVar[Record | None]]
    LEGACY_OWNER_ID: Callable[[], str]
    scope_config_for_user: Callable[[], Callable[[Record, Record], Record]]
    load_config: Callable[[], Callable[[], Record]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]

@dataclass(frozen=True)
class SyntheticBatchSprites:
    auto_optimize_backfill_missing_sprites_for_sample: Callable[[], Callable[[str, Record, Record], int]]
    auto_optimize_sprite_records_for_sample: Callable[[], Callable[[Record], list[Record]]]
    auto_optimize_canonical_sprite_sizes: Callable[[], CanonicalSizes]

@dataclass(frozen=True)
class SyntheticBatchPublication:
    safe_record_id: Callable[[], Callable[[str], str]]
    output_write_dir_for_owner: Callable[[], Callable[[str, str], Path]]
    auto_optimize_render_synthetic_sample: Callable[[], RenderSample]
