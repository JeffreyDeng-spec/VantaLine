"""Business progress text and private customer-note provenance; no runtime I/O."""
import re
import hashlib

# These are platform progress templates, not a global replacement in customer
# notes. Keep the stored evidence and administrator projection unchanged.
PLATFORM_NOTES = {
    "Imported from RunPod YOLO training worker.": "已导入训练成果。",
    "RunPod 训练产物已上传，等待平台导入模型。": "训练产物已上传，等待导入。",
    "样本已生成，正在准备 RunPod YOLO worker 训练数据包。": "样本已生成，正在准备训练数据。",
    "训练任务已提交到 RunPod YOLO worker，等待远端处理。": "训练任务已提交，等待处理。",
    "RunPod YOLO worker 训练完成，模型已导入训练库。": "训练完成，成果已导入训练库。",
    "已生成 RunPod 训练数据包，等待远端 worker 拉取。": "训练数据已准备，等待处理。",
    "已生成 RunPod 训练产物上传地址，等待远端 worker 上传。": "正在等待训练产物上传。",
    "Windows Worker 已退役；请使用 RunPod 训练链路。": "旧训练服务已停用，请联系管理员。",
    "已选择样本集，正在启动 YOLO 训练。": "已选择样本集，正在启动视觉模型训练。",
    "样本已生成，正在启动 YOLO 训练。": "样本已生成，正在启动视觉模型训练。",
    "系统正在通过 Windows 本地 CodexImageWorker 生成默认多角度图片。": "正在生成默认多角度图片。",
    "Windows 本地 CodexImageWorker 生成任务已完成。": "多角度图片生成任务已完成。",
    "系统正在通过 Cursor Image2 API 生成默认图片。": "正在生成默认图片。",
    "Cursor Image2 API 生成任务已完成。": "图片生成任务已完成。",
    "Prepared one-vs-rest public-reference YOLO dataset.": "训练数据集已准备。",
    "YOLO training completed.": "视觉模型训练完成。",
    "YOLO training failed.": "视觉模型训练未完成。",
    "历史 Windows-worker 训练记录仅保留只读展示；生产训练执行已切换为 RunPod。": "历史训练记录仅保留只读展示。",
}


def _is_customer_note(value, record):
    marker = record.get("_customer_note_sha256")
    return isinstance(value, str) and isinstance(marker, str) and marker == hashlib.sha256(value.encode()).hexdigest()


def public_note(value, record, context=""):
    if _is_customer_note(value, record):
        return value
    platform = (
        any(key in record for key in ("job_id", "action", "run_id", "provider", "generation_method", "variant", "model_variant"))
        or ("status" in record and ("mode" in record or "progress" in record or context in {"tasks", "task", "jobs", "items", "training", "training_states"}))
        or context in {"models", "model", "datasets", "dataset"}
    )
    if not platform:
        return value
    if not isinstance(value, str):
        return value
    if value in PLATFORM_NOTES:
        return PLATFORM_NOTES[value]
    epoch = re.fullmatch(r"YOLO 训练(已启动|中)：Epoch (\d+)/(\d+)。", value)
    if epoch:
        return f"视觉模型训练{epoch[1]}：轮次 {epoch[2]}/{epoch[3]}。"
    if re.fullmatch(r"RunPod YOLO worker 状态：.*。", value, re.S):
        return "训练任务正在处理。"
    if re.fullmatch(r"上传到 Windows Worker 失败（第 \d+ 次），正在重试：.*", value, re.S):
        return "训练数据上传未完成，正在重试。"
    if record.get("status") == "failed" and value.startswith(("任务失败：", "背景生成失败：")):
        return "任务未完成，请检查业务状态或联系管理员。"
    return value


def customer_note_fields(value):
    """Mark only customer notes that collide with a platform progress template."""
    return {"_customer_note_sha256": hashlib.sha256(value.encode()).hexdigest()} if isinstance(value, str) and public_note(value, {"status": "failed", "job_id": "note-origin"}) != value else {}


def preserved_note_fields(record):
    return {"_customer_note_sha256": record["_customer_note_sha256"]} if _is_customer_note(record.get("note"), record) else {}
