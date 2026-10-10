"""Cost service ownership with explicit read capabilities; construction performs no IO."""
from collections.abc import Callable
from typing import Any
from .cost_repository import CostRepository, CostStoreDependencies
from .costs import CostLedger


class CostServices:
    def __init__(self, storage: CostStoreDependencies, timestamp: Callable[[Any], int]):
        self.repository = CostRepository(storage)
        self.ledger = CostLedger(self.repository, timestamp)
