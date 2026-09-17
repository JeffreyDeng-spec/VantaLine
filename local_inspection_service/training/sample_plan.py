"""Deterministic sample allocation with explicit pose and sampling policies."""
from collections.abc import Callable
import math
from typing import Any
import numpy as np


def split_counts(total: int) -> dict[str, int]:
    total = max(1, int(total))
    if total < 3:
        return {"train": total, "val": 0, "test": 0}
    val = max(1, int(round(total * 0.1)))
    test = max(1, int(round(total * 0.1)))
    train = max(1, total - val - test)
    while train + val + test > total:
        if train >= val and train >= test and train > 1:
            train -= 1
        elif val >= test and val > 1:
            val -= 1
        else:
            test -= 1
    while train + val + test < total:
        train += 1
    return {"train": train, "val": val, "test": test}


def missing_count_for_false_sample(accessory_count: int, rng: np.random.Generator) -> int:
    accessory_count = max(1, int(accessory_count))
    if accessory_count == 1 or rng.random() < 0.95:
        return 1
    candidates = list(range(2, accessory_count + 1))
    weights = np.array([0.5 ** (value - 2) for value in candidates], dtype=np.float64)
    weights = weights / weights.sum()
    return int(rng.choice(candidates, p=weights))


class SamplePlanner:
    def __init__(self, split: Callable[[int], dict[str, int]],
                 missing: Callable[[int, np.random.Generator], int],
                 poses: Callable[[list[dict[str, Any]], int, str], list[str | None]]):
        self.split, self.missing, self.poses = split, missing, poses

    def build_training_sample_plan(self,
        selected: list[dict[str, Any]],
        sample_count: int,
        seed: int,
        pose_policy: str,
    ) -> list[dict[str, Any]]:
        rng = np.random.default_rng(seed)
        selected_ids = [str(item["id"]) for item in selected]
        counts = self.split(sample_count)
        plan: list[dict[str, Any]] = []
        pose_sequence = self.poses(selected, sample_count, pose_policy)
        true_target = sample_count // 2
        true_counts = {split: count // 2 for split, count in counts.items()}
        remaining_true = true_target - sum(true_counts.values())
        for split in sorted(counts, key=lambda key: counts[key], reverse=True):
            if remaining_true <= 0:
                break
            capacity = counts[split] - true_counts[split]
            add = min(capacity, remaining_true)
            true_counts[split] += add
            remaining_true -= add
        sample_index = 0
        for split, count in counts.items():
            true_count = true_counts[split]
            false_count = count - true_count
            split_items: list[dict[str, Any]] = []
            for _ in range(true_count):
                split_items.append({"is_true": True, "missing_ids": [], "extra_ids": []})
            false_items: list[dict[str, Any]] = []
            for _ in range(false_count):
                missing_count = self.missing(len(selected_ids), rng)
                missing_ids = [str(item) for item in rng.choice(selected_ids, size=missing_count, replace=False).tolist()]
                false_items.append({"is_true": False, "missing_ids": missing_ids, "extra_ids": []})
            split_items.extend(false_items)
            rng.shuffle(split_items)
            for item in split_items:
                present_ids = [item_id for item_id in selected_ids if item_id not in set(item["missing_ids"])]
                present_ids.extend(item.get("extra_ids") or [])
                plan.append(
                    {
                        "index": sample_index,
                        "split": split,
                        "is_true": bool(item["is_true"]),
                        "required_accessory_ids": selected_ids,
                        "present_accessory_ids": present_ids,
                        "missing_accessory_ids": item["missing_ids"],
                        "extra_accessory_ids": item.get("extra_ids") or [],
                        "missing_count": len(item["missing_ids"]),
                        "extra_count": len(item.get("extra_ids") or []),
                        "false_reason": (
                            "extra_one_accessory"
                            if item.get("extra_ids")
                            else ("missing_accessory" if item.get("missing_ids") else None)
                        ),
                        "pose_family_policy": pose_sequence[sample_index] if sample_index < len(pose_sequence) else None,
                    }
                )
                sample_index += 1
        missing_one_indexes = [
            idx
            for idx, item in enumerate(plan)
            if not item.get("is_true") and len(item.get("missing_accessory_ids") or []) == 1 and not item.get("extra_accessory_ids")
        ]
        extra_target = int(math.floor(len(missing_one_indexes) * 0.10 + 0.5))
        if extra_target > 0:
            for idx in rng.choice(missing_one_indexes, size=extra_target, replace=False).tolist():
                missing_id = str(plan[idx]["missing_accessory_ids"][0])
                present_ids = list(plan[idx]["required_accessory_ids"])
                present_ids.append(missing_id)
                plan[idx]["present_accessory_ids"] = present_ids
                plan[idx]["missing_accessory_ids"] = []
                plan[idx]["extra_accessory_ids"] = [missing_id]
                plan[idx]["missing_count"] = 0
                plan[idx]["extra_count"] = 1
                plan[idx]["false_reason"] = "extra_one_accessory"
        return plan
