"""One-operation training lookup snapshots; create and consume on the same thread."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

Record = dict[str, Any]
TaskFinder = Callable[[Path], Record | None]


class TrainingRepository(Protocol):
    def fetch_all(self, table: str) -> list[Record]: ...


@dataclass(frozen=True)
class LookupCache:
    get: Callable[[str], tuple[bool, Any]]
    put: Callable[[str, Any], None]


@dataclass(frozen=True)
class LookupRows:
    decode: Callable[[list[Record]], list[Record]]
    identifier: Callable[[Path], str]
    matches: Callable[[Record, str, Record], bool]


class TrainingTaskLookup:
    def __init__(self, repository: Callable[[], TrainingRepository | None],
                 file_loader: Callable[[], TaskFinder], cache: LookupCache, rows: LookupRows):
        self.repository, self.file_loader = repository, file_loader
        self.cache, self.rows = cache, rows

    def training_task_finder(self) -> Callable[[Path], dict[str, Any] | None]:
        """Return a callable mirroring load_training_task() but with the Postgres
        table fetched once (lazily, on first lookup), so callers looping over many
        run dirs or tasks avoid a full-table scan per item."""
        repository = self.repository()
        if repository is None:
            return self.file_loader()
        pairs: list[tuple[dict[str, Any], dict[str, Any]]] | None = None

        def finder(path: Path) -> dict[str, Any] | None:
            nonlocal pairs
            if pairs is None:
                cached, cached_pairs = self.cache.get("training_task_pairs")
                if cached:
                    pairs = cached_pairs
                else:
                    pairs = []
                    for row in repository.fetch_all("training_tasks"):
                        raw_tasks = self.rows.decode([row])
                        task = raw_tasks[0] if raw_tasks else {}
                        if task:
                            pairs.append((task, row))
                    self.cache.put("training_task_pairs", pairs)
            requested = self.rows.identifier(path)
            for task, row in pairs:
                if self.rows.matches(task, requested, row):
                    return task
            return None

        return finder
