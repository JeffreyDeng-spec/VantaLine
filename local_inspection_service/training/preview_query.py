"""Scoped training plan projection; GET preserves its original sanitization and probes."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

Record = dict[str, Any]


class SerializeAccessories(Protocol):
    def __call__(self, items: list[Record], *, summary: bool) -> list[Record]: ...


class TrainingExecution(Protocol):
    def __call__(self, *, include_worker_probe: bool) -> Record: ...


@dataclass(frozen=True)
class PlanAccess:
    current: Callable[[], Record]
    is_admin: Callable[[Record], bool]
    sanitize: Callable[[], Callable[[Record], Record]]


@dataclass(frozen=True)
class PlanConfiguration:
    load: Callable[[], Record]
    scope: Callable[[], Callable[[Record, Record, str | None], Record]]
    filtered: Callable[[Record, Record, str | None], Record]


@dataclass(frozen=True)
class PlanBackgrounds:
    list: Callable[[Record, str | None], list[Record]]
    selected: Callable[[], Callable[[str | None, Record, str | None], str | None]]
    physical_size: Callable[[], Record]


class TrainingPlanQuery:
    def __init__(self, access: PlanAccess, config: PlanConfiguration, backgrounds: PlanBackgrounds,
                 serialize: Callable[[], SerializeAccessories], execution: TrainingExecution):
        self.access, self.config, self.backgrounds = access, config, backgrounds
        self.serialize, self.execution = serialize, execution

    def training_plan(self, user_id: str | None = None) -> dict[str, Any]:
        user = self.access.current()
        target_user_id = user_id if self.access.is_admin(user) else None
        config = self.config.scope()(self.config.load(), user, target_user_id)
        training = self.config.filtered(config, user, target_user_id)
        return self.access.sanitize()({
            "training": training,
            "accessories": self.serialize()(config.get("accessories", []), summary=True),
            "background_sets": self.backgrounds.list(user, target_user_id),
            "default_background_set_id": self.backgrounds.selected()(training.get("background_set_id"), user, target_user_id),
            "training_execution": self.execution(include_worker_probe=False),
            "render_policy": {
                "sample_count_default": 4000,
                "background": "same-environment background library with per-sample crop/shift/photometric/noise/texture variation; glare ellipse disabled",
                "background_physical_size": self.backgrounds.physical_size(),
                "physical_size_rule": "object foreground uses clean alpha sprite physical_size; document/text uses saved rectified image directly at paper physical_size",
                "rotation": "text_full_random; object_upright_random_rotation; object_lying_random_rotation_with_inverse_source_position",
                "z_order": "randomized_per_sample",
                "label_shape": "visible_polygon_for_occluded_regions",
                "true_rule": "exact_count_match_required",
                "false_rule": "mostly missing_one; 10% of missing_one false bucket becomes extra_one_accessory",
            },
        })
