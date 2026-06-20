const STATUS_LABELS: Record<string, string> = {
  running: "运行中",
  idle: "空闲",
  pending: "等待中",
  queued: "排队中",
  queued_for_codex_image_worker: "排队中",
  failed: "失败",
  stopped: "已停止",
  completed: "已完成",
  active: "启用",
  sample_generation_requested: "样本生成已请求",
  reference_uploaded: "素材已上传",
  normalized_text_ready: "文字规范化完成",
  needs_crop: "等待裁剪图",
  image_tool_plan_ready: "生成计划就绪",
  preview_ready: "预览已生成",
  requested: "训练已请求"
};

export function statusLabel(value: string | undefined) {
  return value ? STATUS_LABELS[value] || value : "-";
}

export function formatRecordTime(value: unknown) {
  const raw = Number(value || 0);
  if (!Number.isFinite(raw) || raw <= 0) return "时间缺失";
  const millis = raw > 100_000_000_000 ? raw : raw * 1000;
  const date = new Date(millis);
  if (Number.isNaN(date.getTime())) return "时间缺失";
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function recordAuditText(
  record: { created_at?: number; updated_at?: number; owner_username?: string; owner_user_id?: string } | null | undefined,
  options: { owner?: boolean; includeUpdated?: boolean } = {}
) {
  const owner = options.owner === false ? "" : record?.owner_username || record?.owner_user_id || "";
  const created = formatRecordTime(record?.created_at);
  const updated =
    options.includeUpdated && record?.updated_at && record.updated_at !== record.created_at
      ? ` / 更新 ${formatRecordTime(record.updated_at)}`
      : "";
  return [owner ? `归属 ${owner}` : "", `创建 ${created}${updated}`].filter(Boolean).join(" · ");
}

export function modelVariantLabel(model: { variant?: string; uses_ocr?: boolean } | null | undefined) {
  const variant = String(model?.variant || "").toLowerCase();
  if (variant === "yolo_ocr" || model?.uses_ocr) return "YOLO + OCR";
  if (variant === "yolo") return "YOLO";
  if (variant === "ai_detection") return "AI 检测";
  if (variant === "label_sheet_local") return "标签匹配";
  return variant || "模型";
}

export function toneForStatus(value: string | undefined) {
  if (value === "running" || value === "completed" || value === "connected" || value === "ready") return "ok";
  if (value === "failed" || value === "unreachable" || value === "unsupported_provider" || value === "invalid_base_url") {
    return "fail";
  }
  if (value === "queued" || value === "pending" || value === "untested" || value === "missing_api_key") return "warn";
  return "neutral";
}
