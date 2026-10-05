"""Application-owned directory setup and one-time local path migration."""
from collections.abc import Callable
from pathlib import Path
import threading
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..storage.artifacts.files import BusinessFiles
Record = dict[str, Any]

class ServiceDirectories:
    def __init__(self, paths: Callable[[], tuple[Path, ...]], config_path: Callable[[], Path],
                 defaults: Callable[[], Record], files: Callable[[], "BusinessFiles"],
                 save_config: Callable[[], Callable[[Record], None]],
                 migrate: Callable[[], Callable[[], None]]):
        self.paths, self.config_path, self.defaults = paths, config_path, defaults
        self.files, self.save_config, self.migrate = files, save_config, migrate

    def ensure(self) -> None:
        for path in self.paths():
            path.mkdir(parents=True, exist_ok=True)
        if not self.files().exists(self.config_path()):
            self.save_config()(self.defaults())
        self.migrate()()


class LocalPathMigration:
    def __init__(self, config_path: Callable[[], Path], roots: Callable[[], tuple[Path, ...]],
                 files: Callable[[], "BusinessFiles"], migrate_file: Callable[[], Callable[[Path], bool]]):
        self.config_path, self.roots = config_path, roots
        self.files, self.migrate_file = files, migrate_file
        self.lock = threading.RLock()
        self.done = False

    def run(self) -> None:
        if self.done:
            return
        with self.lock:
            if self.done:
                return
            candidates: set[Path] = {self.config_path()}
            for root in self.roots():
                if self.files().exists(root):
                    candidates.update(path for path in self.files().glob(root, "*.json", recursive=True) if self.files().is_file(path))
            for path in sorted(candidates):
                self.migrate_file()(path)
            self.done = True
