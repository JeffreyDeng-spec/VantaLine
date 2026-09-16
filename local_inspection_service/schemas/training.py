"""Training request shapes; defaults and coercion match the existing API."""
from pydantic import BaseModel


class AutoOptimizeSettingsRequest(BaseModel):
    enabled: bool | None = None
    samples_per_real_image: int | None = None
    min_trainable_samples: int | None = None
    min_positive_samples: int | None = None
    min_negative_samples: int | None = None
    negative_samples_per_real_image: int | None = None
    training_epochs: int | None = None
    training_image_size: int | None = None
    max_label_jobs_per_cycle: int | None = None
    mask_compare_min_score: float | None = None
    shadow_min_samples: int | None = None
    shadow_min_agreement: float | None = None
    auto_promote: bool | None = None


class AutoOptimizeSampleApproveRequest(BaseModel):
    mode: str | None = "sprite"


class TrainingPreviewRequest(BaseModel):
    selected_accessory_ids: list[str]
    sample_count: int = 4000
    train_mode: str = "yolo_ocr"
    preview_count: int = 5
    preview_pose_family_policy: str = "auto"
    background_set_id: str | None = None
    force_refresh: bool = True


class TrainingStartRequest(BaseModel):
    selected_accessory_ids: list[str]
    sample_count: int = 4000
    train_mode: str = "yolo_ocr"
    approved_preview_id: str | None = None
    dataset_id: str | None = None
    epochs: int = 80
    image_size: int = 640
    background_set_id: str | None = None
    pipeline_task_id: str | None = None
    pipeline_task_name: str | None = None


class TrainingTaskUpdateRequest(BaseModel):
    label: str | None = None
    note: str | None = None


class TrainingResourceUpdateRequest(BaseModel):
    display_name: str | None = None
    note: str | None = None
