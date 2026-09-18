"""Default-background seeding; directory reads retain their existing initialization writes."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
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
        if not self.paths.default().exists():
            return
        manifest = self.load()
        sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
        default_id = "green_conveyor"
        set_dir = self.paths.sets() / default_id
        set_dir.mkdir(parents=True, exist_ok=True)
        original_target = set_dir / self.paths.default().name
        if not original_target.exists():
            shutil.copy2(self.paths.default(), original_target)
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
        dirs = [path for path in self.paths.sets().iterdir() if path.is_dir()] if self.paths.sets().exists() else []
        return sorted(dirs, key=lambda path: path.name)
