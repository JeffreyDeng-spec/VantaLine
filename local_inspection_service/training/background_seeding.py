"""Default-background seeding; directory reads retain their existing initialization writes."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from ..storage.artifacts.files import BusinessFiles
_business_files = BusinessFiles()
import shutil
from typing import Any


@dataclass(frozen=True)
class BackgroundSeedPaths:
    default: Callable[[], Path]
    sets: Callable[[], Path]


class BackgroundSeeding:
    def __init__(self, paths: BackgroundSeedPaths, load: Callable[[], Any], write: Callable[[Any], None],
                 minimum: Callable[[str], None], seed: Callable[[], None], clock: Callable[[], float]):
        self.paths, self.load, self.write = paths, load, write
        self.minimum, self.seed, self.clock = minimum, seed, clock

    def seed_default_background_set(self) -> None:
        if not _business_files.exists(self.paths.default()):
            return
        manifest = self.load()
        sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
        default_id = "green_conveyor"
        set_dir = self.paths.sets() / default_id
        set_dir.mkdir(parents=True, exist_ok=True)
        original_target = set_dir / self.paths.default().name
        if not _business_files.exists(original_target):
            _business_files.copy2(self.paths.default(), original_target, local_copy=shutil.copy2)
        self.minimum(default_id)
        sets.setdefault(
            default_id,
            {
                "id": default_id,
                "name": "绿色传送带",
                "description": "同一生产环境的绿色传送带背景集",
                "source": str(self.paths.default()),
                "created_at": int(self.clock()),
                "generation_method": "seeded_from_existing_background",
            },
        )
        manifest["sets"] = sets
        manifest.setdefault("default_set_id", default_id)
        self.write(manifest)

    def background_set_dirs(self) -> list[Path]:
        self.seed()
        dirs = [path for path in _business_files.iterdir(self.paths.sets()) if _business_files.is_dir(path)] if _business_files.exists(self.paths.sets()) else []
        return sorted(dirs, key=lambda path: path.name)
