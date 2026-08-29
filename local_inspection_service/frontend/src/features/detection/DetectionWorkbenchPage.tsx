import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Camera, ChevronRight, FileImage, Maximize2, Play, RefreshCw, Save, Settings, Video, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  analyzeCamera,
  analyzeImage,
  analyzeVideo,
  getAiTaskAutoOptimize,
  getAiTasks,
  getPipeline,
  getPlcWorkstation,
  getServiceStatus,
  getTrainingResources,
  queryKeys,
  updateRules,
  updateTaskRules,
  uploadAiTaskEnvironmentBackground,
  warmupYoloModel
} from "../../api/queries";
import type {
  AiDetectionLibraryTask,
  DetectionItem,
  DetectionResult,
  DetectionRuleItem,
  DetectionVideoFrame,
  PlcWebSerialDiagnosticResult,
  PlcWorkstationResponse,
  ServiceStatusResponse,
  SpecializedModelTask,
  StatusModel
} from "../../api/types";
import { PlcWebSerialClient, type PlcBrowserConnectionState } from "../plc/webSerialClient";
import { nextCaptureTriggerState } from "../plc/captureTriggerState.mjs";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { modelVariantLabel } from "../../utils/format";
import { taskEntriesFromTrainingResources, taskStatusTone, type TaskEntry } from "../../utils/taskNavigation";
import { useAuth } from "../auth/auth-context";

type WorkbenchMode = "inspect" | "ai";
type SourceMode = "image" | "video" | "camera";
type PlcCapturePollState = {
  status: "disabled" | "unarmed" | "armed" | "latched" | "triggered" | "missed" | "read_error";
  value: number | null;
  requestHex: string;
  responseHex: string;
  readAt: number | null;
  triggerAt: number | null;
  message: string;
};

const AI_TASK_MODEL_PREFIX = "ai_detection__task_";
const DETECTION_UPLOAD_MAX_BYTES = 1_500_000;
const DETECTION_UPLOAD_MAX_SIDE = 1920;
const DETECTION_UPLOAD_JPEG_QUALITY = 0.88;
const ENVIRONMENT_UPLOAD_OPTION = "__upload_background__";
const SOURCE_TABS: Array<{ value: SourceMode; label: string; Icon: LucideIcon }> = [
  { value: "image", label: "图片", Icon: FileImage },
  { value: "video", label: "视频", Icon: Video },
  { value: "camera", label: "摄像头", Icon: Camera }
];

function isAiModel(model: StatusModel | Record<string, unknown> | null | undefined) {
  return Boolean(model?.is_ai_detection || model?.variant === "ai_detection" || String(model?.id || "").startsWith(AI_TASK_MODEL_PREFIX));
}

function isWarmableYoloModel(model: StatusModel | null | undefined) {
  if (!model || isAiModel(model)) return false;
  return Boolean(model.id && (model.exists || model.variant === "yolo" || model.variant === "yolo_ocr" || model.uses_ocr));
}

function warmupFailedForModel(failed: unknown, modelId: string) {
  if (!Array.isArray(failed) || !modelId) return false;
  return failed.some((item) => (typeof item === "string" ? item === modelId : String((item as { model_id?: string }).model_id || "") === modelId));
}

function warmupReadyForModel(warmup: ServiceStatusResponse["yolo_warmup"] | undefined, modelId: string) {
  if (!modelId) return false;
  const loaded = warmup?.loaded_model_ids || [];
  const completed = warmup?.completed_model_ids || [];
  return loaded.includes(modelId) || completed.includes(modelId);
}

function environmentBackgroundSetId(
  record:
    | {
        background_set_id?: string;
        environment_background?: Record<string, unknown>;
        background_set?: Record<string, unknown>;
      }
    | null
    | undefined
) {
  const environment = record?.environment_background || {};
  const backgroundSet = record?.background_set || {};
  return String(record?.background_set_id || environment.background_set_id || backgroundSet.id || "");
}

function hasTaskEnvironmentBackground(
  record:
    | {
        background_set_id?: string;
        environment_background?: Record<string, unknown>;
        background_set?: Record<string, unknown>;
      }
    | null
    | undefined
) {
  const setId = environmentBackgroundSetId(record).trim();
  return Boolean(setId && setId !== "green_conveyor");
}

function aiTaskModelId(task: AiDetectionLibraryTask | null | undefined) {
  if (!task?.id) return "";
  return task.model_id || `${AI_TASK_MODEL_PREFIX}${task.id}`;
}

function formatPercent(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return `${Math.round(numeric * 1000) / 10}%`;
}

function formatConfidence(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return numeric.toFixed(3);
}

function formatLocalTimestamp(value: number) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatAiStatus(value: unknown) {
  const status = String(value || "");
  if (status === "ready") return "就绪";
  if (status === "missing_api_key") return "缺少 Key";
  if (status === "disabled") return "未启用";
  if (status === "restricted") return "受限";
  return status || "检查中";
}

function modelOptionLabel(model: StatusModel) {
  return modelVariantLabel(model) || model.label || model.id;
}

function modelOptionMeta(model: StatusModel) {
  if (isAiModel(model)) return "AI 检测";
  if (model.exists) return model.label || model.description || "可用";
  return `${model.label || model.description || ""} 文件缺失`.trim() || "文件缺失";
}

function modelDetectionLabel(model: StatusModel | null | undefined, fallbackAi: boolean) {
  if (model && !isAiModel(model)) {
    const label = modelVariantLabel(model);
    return label && label !== "模型" ? `${label} 检测` : "检测";
  }
  return fallbackAi ? "AI 检测" : "检测";
}

function modelResultLabel(model: StatusModel | null | undefined, fallbackAi: boolean) {
  if (model && !isAiModel(model)) {
    const label = modelVariantLabel(model);
    return label && label !== "模型" ? label : "模型";
  }
  return fallbackAi ? "AI" : "模型";
}

function classLabel(item: { class_id: number; label?: string; name?: string }) {
  return item.label || item.name || `Class ${item.class_id}`;
}

function taskLabel(task: SpecializedModelTask, fallback = "训练任务") {
  const names = (task.accessory_names || []).filter(Boolean);
  return task.label || (names.length ? names.join(" + ") : task.task_id || fallback);
}

function defaultTaskLabel(status: ServiceStatusResponse | undefined) {
  const requiredNames = (status?.rule?.required_classes || [])
    .map((classId) => status?.classes?.find((item) => Number(item.class_id) === Number(classId))?.label)
    .filter(Boolean);
  return requiredNames.length ? requiredNames.join(" + ") : "通用配件合集";
}

function isTaskEntryAi(task: TaskEntry | null | undefined) {
  return Boolean(task && (task.kind === "ai" || task.detectionMethod === "ai" || task.aiTaskId || task.aiModelId));
}

function taskHasAiBaseline(task: TaskEntry | null | undefined) {
  return Boolean(task && (isTaskEntryAi(task) || task.aiBaselineTaskId || task.aiBaselineModelId || task.autoOptimizeTaskId));
}

function sameAccessoryCounts(a: Record<string, number> | undefined, b: Record<string, number> | undefined) {
  const left = a || {};
  const right = b || {};
  const keys = Array.from(new Set([...Object.keys(left), ...Object.keys(right)]));
  return keys.every((key) => Number(left[key] || 1) === Number(right[key] || 1));
}

function aiTaskMatchesEntry(task: AiDetectionLibraryTask, entry: TaskEntry | null | undefined) {
  if (!entry?.accessoryIds.length) return false;
  const taskIds = task.selected_accessory_ids || [];
  if (taskIds.length !== entry.accessoryIds.length) return false;
  const taskSet = new Set(taskIds);
  if (!entry.accessoryIds.every((id) => taskSet.has(id))) return false;
  return sameAccessoryCounts(task.required_accessory_counts, entry.accessoryCounts);
}

function taskInspectPath(task: TaskEntry) {
  return `/tasks/${encodeURIComponent(task.id)}/inspect`;
}

function taskAccessoryText(task: TaskEntry | null | undefined) {
  if (!task) return "-";
  const names = task.accessoryNames.length ? task.accessoryNames : task.accessoryIds;
  return names.length ? names.join("、") : "-";
}

function modelIdCandidatesForTask(task: TaskEntry | null | undefined) {
  if (!task) return new Set<string>();
  const autoOptimizeLink = task.autoOptimizeLink || {};
  return new Set(
    [
      task.sourceId,
      task.aiTaskId || "",
      task.aiModelId || "",
      task.aiBaselineTaskId || "",
      task.aiBaselineModelId || "",
      task.autoOptimizeTaskId || "",
      String(autoOptimizeLink.active_model_id || ""),
      String(autoOptimizeLink.completed_model_id || ""),
      task.modelRunId || "",
      task.trainingTaskId || "",
      task.sampleTaskId || "",
      task.datasetId || ""
    ].filter(Boolean)
  );
}

function statusModelMatchesTask(model: StatusModel, task: TaskEntry | null | undefined) {
  if (!task) return false;
  const record = model as StatusModel & Record<string, unknown>;
  const candidates = modelIdCandidatesForTask(task);
  const modelValues = [
    model.id,
    model.task_id,
    record.run_id,
    record.model_run_id,
    record.training_task_id,
    record.job_id,
    record.source_task_id,
    record.pipeline_task_id
  ]
    .filter(Boolean)
    .map(String);
  if (modelValues.some((value) => candidates.has(value))) return true;
  if (taskHasAiBaseline(task)) return false;
  const modelAccessoryIds = model.selected_accessory_ids || [];
  return Boolean(task.accessoryIds.length && modelAccessoryIds.length && task.accessoryIds.every((id) => modelAccessoryIds.includes(id)));
}

function uniqueModels(models: StatusModel[]) {
  const seen = new Set<string>();
  return models.filter((model) => {
    if (!model.id || seen.has(model.id)) return false;
    seen.add(model.id);
    return true;
  });
}

function optimizedUploadName(name: string) {
  const stem = name.replace(/\.[^.]+$/, "");
  return `${stem || "detection_image"}.jpg`;
}

function imageElementFromFile(file: File) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("图片预处理失败"));
    };
    image.src = url;
  });
}

async function optimizeImageUpload(file: File) {
  if (!file.type.startsWith("image/") || file.size <= DETECTION_UPLOAD_MAX_BYTES) return file;
  const image = await imageElementFromFile(file);
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  if (!width || !height) return file;
  const scale = Math.min(1, DETECTION_UPLOAD_MAX_SIDE / Math.max(width, height));
  const targetWidth = Math.max(1, Math.round(width * scale));
  const targetHeight = Math.max(1, Math.round(height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = targetWidth;
  canvas.height = targetHeight;
  const context = canvas.getContext("2d");
  if (!context) return file;
  context.drawImage(image, 0, 0, targetWidth, targetHeight);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", DETECTION_UPLOAD_JPEG_QUALITY));
  if (!blob || blob.size >= file.size) return file;
  return new File([blob], optimizedUploadName(file.name), { type: "image/jpeg", lastModified: file.lastModified });
}

function uniqueRows<T>(items: T[], keyFor: (item: T) => string) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = keyFor(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function ruleItemKey(item: DetectionRuleItem | string) {
  return typeof item === "string" ? item : String(item.class_id ?? item.label ?? "");
}

function ruleItemLabel(item: DetectionRuleItem | string) {
  return typeof item === "string" ? item : String(item.label ?? item.class_name ?? item.class_id ?? "-");
}

function ruleItemValue(item: DetectionRuleItem | string, key: "found" | "required") {
  if (typeof item === "string") return key === "found" ? "是" : "是";
  const value = item[key];
  if (value === true) return "是";
  if (value === false) return "否";
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

function detectionRows(result: DetectionResult | null, requiredCounts?: Record<string, number>) {
  const rule = result?.rule;
  if (!rule) {
    return (result?.detections || []).map((item) => ({
      key: String(item.accessory_id ?? item.class_id ?? item.label ?? item.class_name ?? Math.random()),
      label: String(item.label ?? item.class_name ?? item.accessory_id ?? item.class_id ?? "-"),
      found: item.present === false ? "否" : String(item.found ?? item.count ?? "是"),
      required: String(item.required ?? (item.accessory_id ? requiredCounts?.[String(item.accessory_id)] : undefined) ?? "-"),
      confidence: formatConfidence(item.confidence ?? item.max_confidence)
    }));
  }

  if (rule.match_policy === "ai_presence") {
    const present = (rule.present || []).map((item) => String(item));
    const missing = (rule.missing || []).map((item) => String(item));
    return uniqueRows([...present, ...missing], String).map((accessoryId) => {
      const detection = (result?.detections || []).find((item) => String(item.accessory_id || "") === accessoryId);
      const isMissing = missing.includes(accessoryId);
      return {
        key: accessoryId,
        label: String(detection?.label || accessoryId),
        found: isMissing ? "否" : "是",
        required: String(requiredCounts?.[accessoryId] ?? "是"),
        confidence: formatConfidence(detection?.confidence)
      };
    });
  }

  const missingKeys = new Set((rule.missing || []).map(ruleItemKey));
  return uniqueRows([...(rule.present || []), ...(rule.missing || [])], ruleItemKey).map((item) => ({
    key: ruleItemKey(item),
    label: ruleItemLabel(item),
    found: typeof item === "string" ? (missingKeys.has(item) ? "否" : "是") : ruleItemValue(item, "found"),
    required: typeof item === "string" ? "是" : ruleItemValue(item, "required"),
    confidence: typeof item === "string" ? "-" : formatConfidence(item.max_confidence)
  }));
}

function videoMissingRows(result: DetectionResult | null, requiredCounts?: Record<string, number>) {
  const frames = result?.frames || [];
  if (!frames.length) return [];
  const missing = uniqueRows(
    frames.flatMap((frame) => frame.missing || []),
    ruleItemKey
  );
  if (!missing.length) return detectionRows(result, requiredCounts);
  return missing.map((item) => ({
    key: ruleItemKey(item),
    label: ruleItemLabel(item),
    found: "否",
    required: typeof item === "string" ? String(requiredCounts?.[item] ?? "是") : ruleItemValue(item, "required"),
    confidence: typeof item === "string" ? "-" : formatConfidence(item.max_confidence)
  }));
}

function detectionRowTone(row: { found: string }) {
  const value = String(row.found || "").trim().toLowerCase();
  return value === "否" || value === "0" || value === "false" || value === "missing" ? "fail" : "pass";
}

function aiMetaText(result: DetectionResult | null) {
  const ai = result?.ai || {};
  if (ai.timed_out) return `AI 超时：${String(ai.error || "超过检测时间")}`;
  if (ai.overloaded) {
    const attempts = Number(ai.attempts || 0);
    const retryText = attempts > 1 ? `，已自动重试 ${attempts} 次` : "";
    return `AI 供应商繁忙${retryText}后仍失败，请稍后重试或切换备用模型/Key`;
  }
  if (ai.error) return `AI 错误：${String(ai.error)}`;
  if (ai.frame_count !== undefined) {
    const pieces = [`${ai.frame_count} 帧`];
    if (ai.first_error) pieces.push(String(ai.first_error));
    if (ai.total_latency_ms !== undefined) pieces.push(`${ai.total_latency_ms} ms`);
    return pieces.join(" / ");
  }
  const pieces: string[] = [];
  if (ai.provider_status) pieces.push(String(ai.provider_status));
  if (ai.latency_ms !== undefined) pieces.push(`${ai.latency_ms} ms`);
  if (ai.fallback_model) pieces.push(`备用 ${String(ai.fallback_model)}`);
  return pieces.join(" / ") || "-";
}

function previewUrl(result: DetectionResult | null) {
  const url = result?.annotated_url || result?.preview_url || result?.frames?.find((frame) => frame.annotated_url)?.annotated_url || "";
  if (!url) return "";
  const token = encodeURIComponent(result?.request_id || String(Date.now()));
  return `${url}${url.includes("?") ? "&" : "?"}t=${token}`;
}

function resultDebugPayload(result: DetectionResult | null) {
  if (!result) return { message: "暂无检测结果。" };
  return {
    request_id: result.request_id,
    passed: result.passed,
    model: result.model,
    ai: result.ai || null,
    plc_sync: result.plc_sync || null,
    rule: result.rule || null,
    detections: result.detections || [],
    annotated_url: result.annotated_url || result.preview_url || "",
    video: Array.isArray(result.frames)
      ? {
          sampled_frames: result.sampled_frames || 0,
          passed_frames: result.passed_frames || 0,
          pass_rate: result.pass_rate || 0,
          frames: result.frames
        }
      : null
  };
}

function plcSyncLabel(result: DetectionResult | null) {
  const sync = result?.plc_sync;
  if (!sync) return "PLC 同步状态未返回";
  if (sync.status === "disabled") return "PLC 同步已关闭（未打开串口）";
  if (sync.status === "acknowledged") return `PLC 已确认${sync.targets?.length ? `：${sync.targets.join(" + ")}` : ""}`;
  if (sync.status === "failed") return `PLC 同步失败：${sync.message || sync.error_code || "未知错误"}`;
  if (sync.status === "sent") return "PLC 已发送，等待确认";
  if (sync.status === "attempting") return "PLC 正在尝试打开串口并写入";
  if (sync.status === "queued") return "PLC 同步排队中";
  return `PLC：${sync.status}`;
}

function plcSyncTone(result: DetectionResult | null) {
  if (result?.plc_sync?.status === "acknowledged") return "ok";
  if (result?.plc_sync?.status === "failed") return "fail";
  return "neutral";
}

function detectionTimeoutMs(kind: SourceMode) {
  return kind === "video" ? 300_000 : 120_000;
}

function detectionTimeoutText(kind: SourceMode, timeoutMs: number) {
  const seconds = Math.round(timeoutMs / 1000);
  return kind === "video" ? `视频分析超过 ${seconds} 秒没有返回，请重试。` : `检测超过 ${seconds} 秒没有返回，请重试。`;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

async function captureVideoFrame(video: HTMLVideoElement | null, prefix: string) {
  if (!video) throw new Error("摄像头画面尚未准备好");
  if (video.paused && video.srcObject) await video.play().catch(() => undefined);
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (!video.videoWidth || !video.videoHeight) throw new Error("摄像头画面尚未准备好");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("无法读取摄像头画面");
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((next) => (next ? resolve(next) : reject(new Error("拍照失败"))), "image/jpeg", 0.92);
  });
  return new File([blob], `${prefix}_${Date.now()}.jpg`, { type: "image/jpeg" });
}

function DetectionMetrics({
  result,
  mode,
  source,
  requiredCounts,
  compact = false
}: {
  result: DetectionResult | null;
  mode: WorkbenchMode;
  source: SourceMode;
  requiredCounts?: Record<string, number>;
  compact?: boolean;
}) {
  const rows = source === "video" ? videoMissingRows(result, requiredCounts) : detectionRows(result, requiredCounts);
  const detectionCount = result?.frames?.length
    ? `${result.passed_frames || 0}/${result.sampled_frames || result.frames.length} 帧`
    : result?.detections?.length ?? "-";
  const passRate = result?.frames?.length ? formatPercent(result.pass_rate) : mode === "ai" ? aiMetaText(result) : "-";
  return (
    <section className={`panel page-panel detection-metrics-panel ${compact ? "compact-detection-metrics" : ""}`}>
      <div className="metric-grid">
        <MetricCard label="结论" value={result ? (result.passed ? "通过" : "不通过") : "-"} tone={result ? (result.passed ? "ok" : "fail") : "neutral"} />
        {compact ? null : <MetricCard label="检测数量" value={detectionCount} detail={source === "video" ? "采样帧" : "检测项"} />}
        <MetricCard label={mode === "ai" ? "AI 响应" : "通过率"} value={passRate} />
      </div>

      {result?.plc_sync ? (
        <div className="settings-subhead" aria-live="polite">
          <div>
            <h4>PLC 同步</h4>
            <p>{plcSyncLabel(result)}</p>
          </div>
          <span className={`pill ${plcSyncTone(result)}`}>{result.plc_sync.status}</span>
        </div>
      ) : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>配件</th>
              <th>检测到</th>
              <th>要求</th>
              <th>置信度</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((row) => (
                <tr className={compact ? `detection-result-row ${detectionRowTone(row)}` : undefined} key={row.key}>
                  <td>{row.label}</td>
                  <td>{row.found}</td>
                  <td>{row.required}</td>
                  <td>{row.confidence}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={4}>暂无检测结果。</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {result?.frames?.length ? (
        <div className="frame-summary-list">
          {result.frames.slice(0, 24).map((frame: DetectionVideoFrame) => (
            <span className={`pill ${frame.passed ? "ok" : "fail"}`} key={`${frame.frame_index}-${frame.timestamp_seconds}`}>
              #{frame.frame_index ?? "-"} · {frame.timestamp_seconds ?? 0}s · {frame.passed ? "通过" : "不通过"} · {frame.detections ?? 0}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function TaskDetectionEntryPage({
  tasks,
  loading,
  error,
  onRetry
}: {
  tasks: TaskEntry[];
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  const visibleTasks = tasks.filter((task) => !["失败", "已暂停"].includes(task.status));

  if (loading) return <LoadingState label="正在加载可检测任务" />;
  if (error) return <ErrorState error={error} action={<button onClick={onRetry}>重试</button>} />;

  return (
    <section className="view active detection-workbench">
      <header className="page-head">
        <div>
          <h2>检测中心</h2>
          <p className="page-desc">先选择一个任务，再进入该任务自己的检测页面。检测页面内只切换当前任务可用的模型。</p>
        </div>
      </header>

      <section className="panel page-panel task-detection-entry-panel">
        <div className="section-title">
          <div>
            <h3>选择检测任务</h3>
            <p>每个任务都有独立的检测中心、样本集和模型集。</p>
          </div>
          <Link className="secondary compact-action" to="/training-library?tab=tasks">
            打开任务库
          </Link>
        </div>

        {visibleTasks.length ? (
          <div className="task-detection-entry-grid">
            {visibleTasks.map((task) => (
              <Link className="task-detection-entry-card" to={taskInspectPath(task)} key={task.id}>
                <span className={`pill ${taskStatusTone(task.status)}`}>{task.status}</span>
                <strong>{task.label}</strong>
                <small>{task.meta}</small>
                <p>配件：{taskAccessoryText(task)}</p>
                <em>
                  进入检测
                  <ChevronRight size={14} aria-hidden="true" />
                </em>
              </Link>
            ))}
          </div>
        ) : (
          <div className="empty-panel compact-empty">
            还没有可检测任务。可以先在任务库或任务流水线里创建任务。
          </div>
        )}
      </section>
    </section>
  );
}

export function DetectionWorkbenchPage({ mode }: { mode: WorkbenchMode }) {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { taskId: routeTaskId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const decodedRouteTaskId = routeTaskId ? decodeURIComponent(routeTaskId) : "";
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const environmentVideoRef = useRef<HTMLVideoElement | null>(null);
  const fullscreenVideoRef = useRef<HTMLVideoElement | null>(null);
  const fullscreenShellRef = useRef<HTMLDivElement | null>(null);
  const requestedWarmupsRef = useRef<Set<string>>(new Set());
  const detectionAudioRef = useRef<AudioContext | null>(null);
  const plcClientRef = useRef(new PlcWebSerialClient());
  const plcBoundModelIdRef = useRef("");
  const busyRef = useRef("");
  const cameraCaptureLockRef = useRef(false);
  const [source, setSource] = useState<SourceMode>("image");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState("__default__");
  const [selectedModelId, setSelectedModelId] = useState("");
  const [pendingModelId, setPendingModelId] = useState("");
  const [selectedAiTaskId, setSelectedAiTaskId] = useState("");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [environmentStream, setEnvironmentStream] = useState<MediaStream | null>(null);
  const [environmentCaptureOpen, setEnvironmentCaptureOpen] = useState(false);
  const [environmentInputMode, setEnvironmentInputMode] = useState<"camera" | "upload">("camera");
  const [environmentUploadFile, setEnvironmentUploadFile] = useState<File | null>(null);
  const [environmentCaptureStatus, setEnvironmentCaptureStatus] = useState("首次检测前需要拍摄一张空白生产环境。");
  const [cameraStatus, setCameraStatus] = useState("支持本机摄像头和已连接的 USB / 外接摄像头。");
  const [plcConnected, setPlcConnected] = useState(false);
  const [plcDiagnosticBusy, setPlcDiagnosticBusy] = useState(false);
  const [plcDiagnostic, setPlcDiagnostic] = useState<PlcWebSerialDiagnosticResult | null>(null);
  const [plcCapturePoll, setPlcCapturePoll] = useState<PlcCapturePollState>({
    status: "disabled",
    value: null,
    requestHex: "",
    responseHex: "",
    readAt: null,
    triggerAt: null,
    message: "PLC 到位拍照未启用。"
  });
  const [plcConnectionStatus, setPlcConnectionStatus] = useState(
    PlcWebSerialClient.supported() ? "PLC 尚未连接。" : "当前浏览器不支持 Web Serial。"
  );
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState<DetectionResult | null>(null);
  const [error, setError] = useState("");
  const [debugOpen, setDebugOpen] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);
  const requestedTaskId = searchParams.get("task_id") || "";
  const canViewDiagnostics = auth.user.role === "admin";
  const shouldLoadTaskEntries = Boolean(decodedRouteTaskId) || !requestedTaskId;

  const statusQuery = useQuery({
    queryKey: queryKeys.serviceStatus(auth.dataUserId),
    queryFn: () => getServiceStatus(auth),
    refetchInterval: 30_000
  });
  const plcWorkstationQuery = useQuery<PlcWorkstationResponse>({
    queryKey: queryKeys.plcWorkstation,
    queryFn: getPlcWorkstation,
    refetchOnWindowFocus: false
  });
  const trainingResourcesQuery = useQuery({
    queryKey: queryKeys.trainingResources(auth.dataUserId),
    queryFn: () => getTrainingResources(auth),
    enabled: shouldLoadTaskEntries,
    refetchInterval: 60_000
  });
  const pipelineQuery = useQuery({
    queryKey: queryKeys.pipeline(auth.dataUserId),
    queryFn: () => getPipeline(auth),
    enabled: shouldLoadTaskEntries,
    refetchInterval: 60_000
  });
  const taskEntries = useMemo(
    () => taskEntriesFromTrainingResources(trainingResourcesQuery.data, pipelineQuery.data),
    [pipelineQuery.data, trainingResourcesQuery.data]
  );
  const routeTask = useMemo(
    () => taskEntries.find((entry) => entry.id === decodedRouteTaskId) || null,
    [decodedRouteTaskId, taskEntries]
  );
  const routeHasAiBaseline = taskHasAiBaseline(routeTask);
  const isAi = isTaskEntryAi(routeTask) || mode === "ai" || searchParams.get("mode") === "ai";
  const shouldLoadAiTasks = routeHasAiBaseline || isAi;
  const aiTasksQuery = useQuery({
    queryKey: queryKeys.aiTasks(auth.dataUserId),
    queryFn: () => getAiTasks(auth),
    enabled: shouldLoadAiTasks
  });
  const globalRuleMutation = useMutation({
    mutationFn: updateRules,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.serviceStatus(auth.dataUserId) });
      notify({ title: "规则已保存", tone: "success" });
      setRulesOpen(false);
    },
    onError: (nextError: Error) => notify({ title: "规则保存失败", description: nextError.message, tone: "error" })
  });
  const taskRuleMutation = useMutation({
    mutationFn: ({ taskId, payload }: { taskId: string; payload: { confidence_threshold: number; required_accessory_counts: Record<string, number> } }) =>
      updateTaskRules(taskId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.serviceStatus(auth.dataUserId) });
      notify({ title: "任务规则已保存", tone: "success" });
      setRulesOpen(false);
    },
    onError: (nextError: Error) => notify({ title: "任务规则保存失败", description: nextError.message, tone: "error" })
  });
  const modelWarmupMutation = useMutation({
    mutationFn: (modelId: string) => warmupYoloModel(modelId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.serviceStatus(auth.dataUserId) });
    },
    onError: (nextError: Error) => notify({ title: "模型预热失败", description: nextError.message, tone: "error" })
  });
  const environmentBackgroundMutation = useMutation({
    mutationFn: ({ taskId, file }: { taskId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      return uploadAiTaskEnvironmentBackground(taskId, form);
    },
    onSuccess: async (nextStatus) => {
      queryClient.setQueryData(queryKeys.aiAutoOptimize(auth.dataUserId, environmentBackgroundTaskId), nextStatus);
      await queryClient.invalidateQueries({ queryKey: queryKeys.aiAutoOptimize(auth.dataUserId, environmentBackgroundTaskId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.aiTasks(auth.dataUserId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.trainingResources(auth.dataUserId) });
      setEnvironmentCaptureOpen(false);
      setEnvironmentCaptureStatus("空场景背景已保存。");
      notify({ title: "空场景背景已保存", description: "后续 sprite 合成训练图会使用这张生产环境背景。", tone: "success" });
    },
    onError: (nextError: Error) => {
      const message = nextError.message || "保存空场景背景失败";
      setEnvironmentCaptureStatus(message);
      notify({ title: "保存空场景背景失败", description: message, tone: "error" });
    }
  });

  const status = statusQuery.data;
  const taskOptions = useMemo(() => {
    const defaults = status?.available_models || [];
    return [
      {
        id: "__default__",
        label: defaultTaskLabel(status),
        meta: "通用检测任务",
        models: defaults,
        accessory_names: [],
        accessory_labels: {},
        required_accessory_counts: {},
        confidence_threshold: status?.rule?.confidence_threshold
      },
      ...(status?.specialized_model_tasks || []).map((task) => ({
        id: task.task_id,
        label: taskLabel(task),
        meta: `${task.models?.length || 0} 个模型`,
        models: task.models || [],
        accessory_names: task.accessory_names || [],
        accessory_labels: task.accessory_labels || task.models?.[0]?.accessory_labels || {},
        required_accessory_counts: task.required_accessory_counts || task.models?.[0]?.required_accessory_counts || {},
        confidence_threshold: task.confidence_threshold ?? task.models?.[0]?.confidence_threshold
      }))
    ];
  }, [status]);
  const currentTask = taskOptions.find((task) => task.id === selectedTaskId) || taskOptions[0];
  const aiTasks = aiTasksQuery.data?.tasks || status?.ai_detection_tasks || [];
  const routeAiTask = routeTask
    ? aiTasks.find((task) =>
        [task.id, task.model_id].filter(Boolean).some((candidate) =>
          [routeTask.sourceId, routeTask.aiTaskId, routeTask.aiModelId, routeTask.aiBaselineTaskId, routeTask.aiBaselineModelId, routeTask.autoOptimizeTaskId]
            .filter(Boolean)
            .includes(String(candidate))
        )
      ) || aiTasks.find((task) => aiTaskMatchesEntry(task, routeTask)) || null
    : null;
  const selectedAiTask = routeAiTask || aiTasks.find((task) => task.id === selectedAiTaskId) || null;
  const environmentBackgroundTaskId =
    selectedAiTask?.id ||
    routeTask?.autoOptimizeTaskId ||
    routeTask?.aiBaselineTaskId ||
    routeTask?.aiTaskId ||
    "";
  const environmentBackgroundQuery = useQuery({
    queryKey: queryKeys.aiAutoOptimize(auth.dataUserId, environmentBackgroundTaskId),
    queryFn: () => getAiTaskAutoOptimize(auth, environmentBackgroundTaskId),
    enabled: Boolean(environmentBackgroundTaskId)
  });
  const routeTaskEnvironmentBackground = routeTask
    ? {
        background_set_id: routeTask.backgroundSetId,
        environment_background: routeTask.environmentBackground
      }
    : null;
  const environmentBackgroundReady =
    hasTaskEnvironmentBackground(environmentBackgroundQuery.data) ||
    hasTaskEnvironmentBackground(selectedAiTask) ||
    hasTaskEnvironmentBackground(routeTaskEnvironmentBackground);
  const environmentBackgroundRequired = Boolean(environmentBackgroundTaskId);
  const selectedAiModelId = aiTaskModelId(selectedAiTask);
  const allStatusModels = useMemo(() => {
    const specializedTaskModels = (status?.specialized_model_tasks || []).flatMap((task) => task.models || []);
    return uniqueModels([...(status?.available_models || []), ...(status?.specialized_models || []), ...specializedTaskModels]);
  }, [status]);
  const routeTaskModelOptions = useMemo(() => {
    if (!routeTask) return [];
    const hasAiBaseline = taskHasAiBaseline(routeTask);
    const related = allStatusModels.filter((model) => statusModelMatchesTask(model, routeTask) && (!hasAiBaseline || !isAiModel(model)));
    if (!hasAiBaseline) return related;
    const aiTaskId = routeAiTask?.id || routeTask.aiBaselineTaskId || routeTask.autoOptimizeTaskId || routeTask.aiTaskId || "";
    const aiModelId = routeAiTask ? aiTaskModelId(routeAiTask) : routeTask.aiBaselineModelId || selectedAiModelId || (aiTaskId ? `${AI_TASK_MODEL_PREFIX}${aiTaskId}` : "");
    const aiBaseline = aiModelId
      ? [{
          id: aiModelId,
          label: "AI / VLM baseline",
          description: "生产初始检测与样本采集",
          exists: true,
          variant: "ai_detection",
          is_ai_detection: true,
          task_id: aiTaskId || routeTask.sourceId,
          task_label: routeTask.label,
          required_accessory_counts: routeTask.accessoryCounts,
          selected_accessory_ids: routeTask.accessoryIds,
          accessory_names: routeTask.accessoryNames
        } as StatusModel]
      : [];
    return uniqueModels([...related, ...aiBaseline]);
  }, [allStatusModels, routeAiTask, routeTask, selectedAiModelId]);
  const legacyAiModelOptions: StatusModel[] = !routeTask && isAi && selectedAiModelId
    ? [{
        id: selectedAiModelId,
        label: "AI / VLM baseline",
        description: "生产初始检测与样本采集",
        exists: true,
        variant: "ai_detection",
        is_ai_detection: true,
        task_id: selectedAiTask?.id,
        task_label: selectedAiTask?.name,
        required_accessory_counts: selectedAiTask?.required_accessory_counts,
        selected_accessory_ids: selectedAiTask?.selected_accessory_ids,
        accessory_names: selectedAiTask?.accessory_names
      }]
    : [];
  const modelOptions = routeTask ? routeTaskModelOptions : isAi ? legacyAiModelOptions : currentTask?.models || [];
  const selectedModel = modelOptions.find((model) => model.id === selectedModelId) || null;
  const activeModelId = selectedModelId || (isAi ? selectedAiModelId : "");
  const activeModelIsAi = selectedModel ? isAiModel(selectedModel) : isAi;
  const activeDetectionLabel = modelDetectionLabel(selectedModel, activeModelIsAi);
  const activeResultLabel = modelResultLabel(selectedModel, activeModelIsAi);
  const warmupStatus = status?.yolo_warmup;
  const loadedModelIds = warmupStatus?.loaded_model_ids || [];
  const completedWarmupIds = warmupStatus?.completed_model_ids || [];
  const pendingModel = pendingModelId ? modelOptions.find((model) => model.id === pendingModelId) || null : null;
  const displayedModelId = pendingModelId || selectedModelId;
  const warmupDisplayModel = pendingModel || selectedModel;
  const warmupDisplayModelId = warmupDisplayModel?.id || "";
  const selectedModelWarmable = isWarmableYoloModel(selectedModel);
  const selectedModelWarmupFailed = selectedModelWarmable && warmupFailedForModel(warmupStatus?.failed_model_ids, selectedModelId);
  const selectedModelReady = !selectedModelWarmable || warmupReadyForModel(warmupStatus, selectedModelId);
  const selectedModelWarming = selectedModelWarmable && !selectedModelReady && !selectedModelWarmupFailed;
  const displayedModelWarmable = isWarmableYoloModel(warmupDisplayModel);
  const displayedModelWarmupFailed = displayedModelWarmable && warmupFailedForModel(warmupStatus?.failed_model_ids, warmupDisplayModelId);
  const displayedModelReady = !displayedModelWarmable || warmupReadyForModel(warmupStatus, warmupDisplayModelId);
  const displayedModelWarming = displayedModelWarmable && !displayedModelReady && !displayedModelWarmupFailed;
  const requiredCounts = routeTask?.accessoryCounts || (isAi ? selectedAiTask?.required_accessory_counts : undefined);
  const resultImage = previewUrl(result);
  const title = routeTask?.label || (isAi ? "AI 检测" : "检测工作台");
  const statusBadge = activeModelIsAi
    ? formatAiStatus(status?.ai_detection && typeof status.ai_detection === "object" ? status.ai_detection.status : "")
    : status?.model_exists
      ? "模型已加载"
      : "模型未就绪";
  const rulesBusy = globalRuleMutation.isPending || taskRuleMutation.isPending;
  const isDefaultTask = !routeTask && !isAi && selectedTaskId === "__default__";
  const defaultRequiredClasses = new Set((status?.rule?.required_classes || []).map(Number));
  const defaultMinCounts = status?.rule?.min_counts || {};
  const taskRequiredCounts = routeTask?.accessoryCounts || currentTask?.required_accessory_counts || selectedModel?.required_accessory_counts || {};
  const taskAccessoryLabels = selectedModel?.accessory_labels || {};
  const taskAccessoryIds = Object.keys(taskRequiredCounts).length
    ? Object.keys(taskRequiredCounts)
    : (routeTask?.accessoryIds || selectedModel?.selected_accessory_ids || []);
  const taskRuleRows = taskAccessoryIds.map((accessoryId, index) => ({
    id: accessoryId,
    label:
      taskAccessoryLabels[accessoryId] ||
      routeTask?.accessoryNames?.[index] ||
      currentTask?.accessory_names?.[index] ||
      selectedModel?.accessory_names?.[index] ||
      accessoryId,
    count: taskRequiredCounts[accessoryId] || 1
  }));
  const ruleThreshold = Number(
    isDefaultTask
      ? status?.rule?.confidence_threshold
      : currentTask?.confidence_threshold ?? selectedModel?.confidence_threshold ?? status?.rule?.confidence_threshold ?? 0.25
  ) || 0.25;
  const warmupLabel = pendingModelId
    ? displayedModelWarmupFailed
      ? "后台预热失败"
      : displayedModelReady
        ? "已预热"
        : "后台预热中"
    : selectedModelWarmupFailed
      ? "预热失败"
      : selectedModelReady
        ? "已预热"
        : "预热中";
  const warmupTone = (pendingModelId ? displayedModelWarmupFailed : selectedModelWarmupFailed)
    ? "failed"
    : (pendingModelId ? displayedModelReady : selectedModelReady)
      ? "ready"
      : "warming";
  const environmentSourceValue = environmentInputMode === "upload" ? ENVIRONMENT_UPLOAD_OPTION : selectedDeviceId;
  const environmentBackgroundCanSave = environmentInputMode === "upload" ? Boolean(environmentUploadFile) : Boolean(environmentStream);

  function modelMatchesRequest(model: StatusModel, value: string) {
    if (!value) return false;
    const record = model as StatusModel & Record<string, unknown>;
    return [
      model.id,
      model.task_id,
      record.run_id,
      record.model_run_id,
      record.training_task_id,
      record.job_id
    ]
      .filter(Boolean)
      .some((candidate) => String(candidate) === value);
  }

  function requestedTaskSelection(value: string) {
    if (!value) return null;
    for (const task of taskOptions) {
      const matchingModel = (task.models || []).find((model) => modelMatchesRequest(model, value));
      if (task.id === value || matchingModel) return { task, model: matchingModel || null };
    }
    return null;
  }

  function modelIsReady(model: StatusModel | null | undefined) {
    if (!model || !isWarmableYoloModel(model)) return true;
    return warmupReadyForModel(warmupStatus, model.id);
  }

  function requestModelWarmup(modelId: string) {
    if (!modelId || requestedWarmupsRef.current.has(modelId)) return;
    requestedWarmupsRef.current.add(modelId);
    modelWarmupMutation.mutate(modelId);
  }

  function handleModelSelection(nextModelId: string) {
    const nextModel = modelOptions.find((model) => model.id === nextModelId) || null;
    if (!nextModel) {
      setPendingModelId("");
      setSelectedModelId(nextModelId);
      return;
    }
    if (isWarmableYoloModel(nextModel) && !modelIsReady(nextModel)) {
      setPendingModelId(nextModel.id);
      requestModelWarmup(nextModel.id);
      statusQuery.refetch();
      notify({
        title: "模型后台预热中",
        description: selectedModel ? `预热完成前继续使用 ${modelOptionLabel(selectedModel)} 检测。` : "预热完成后会自动切换。",
        tone: "info"
      });
      return;
    }
    setPendingModelId("");
    setSelectedModelId(nextModel.id);
  }

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  useEffect(() => {
    if (!plcConnected || !activeModelId || busy) return;
    if (plcBoundModelIdRef.current === activeModelId) return;
    void plcClientRef.current.rebindModel(activeModelId, (message) => {
      plcBoundModelIdRef.current = "";
      setPlcConnected(false);
      setPlcConnectionStatus(message);
    }).then(() => {
      plcBoundModelIdRef.current = activeModelId;
      setPlcConnectionStatus("PLC 已连接，可连续检测。");
    }).catch(() => undefined);
  }, [activeModelId, busy, plcConnected]);

  useEffect(() => {
    const handleVisibility = () => {
      if (!plcClientRef.current.state()) return;
      if (document.visibilityState !== "visible") {
        setPlcConnectionStatus("页面在后台，PLC 保持连接；已暂停新的写入。");
        return;
      }
      void plcClientRef.current.resume((message) => {
        plcBoundModelIdRef.current = "";
        setPlcConnected(false);
        setPlcConnectionStatus(message);
      }).then((state) => {
        if (!state) return;
        setPlcConnected(true);
        setPlcConnectionStatus("PLC 已恢复就绪，可连续检测。");
      }).catch(() => undefined);
    };
    const handleUnload = () => { void plcClientRef.current.disconnect(false); };
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("beforeunload", handleUnload);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("beforeunload", handleUnload);
      void plcClientRef.current.disconnect(true);
    };
  }, []);

  useEffect(() => {
    const workstation = plcWorkstationQuery.data;
    const plan = workstation?.capture_read_plan;
    const captureEnabled = Boolean(workstation?.config?.enabled && workstation.config.capture_trigger_enabled);
    if (!plcConnected || !captureEnabled || !plan) {
      setPlcCapturePoll((current) => ({
        ...current,
        status: "disabled",
        message: captureEnabled ? "连接 PLC 后开始读取到位信号。" : "PLC 到位拍照未启用。"
      }));
      return;
    }

    let cancelled = false;
    let timer = 0;
    let armed = false;
    setPlcCapturePoll({
      status: "unarmed",
      value: null,
      requestHex: plan.frame_hex,
      responseHex: "",
      readAt: null,
      triggerAt: null,
      message: `等待 ${plan.target} 先出现非 ${plan.trigger_value} 值后武装。`
    });

    const schedule = () => {
      if (!cancelled) timer = window.setTimeout(() => { void poll(); }, plan.poll_interval_ms);
    };
    const poll = async () => {
      if (cancelled) return;
      if (document.visibilityState !== "visible" || plcDiagnosticBusy) {
        schedule();
        return;
      }
      try {
        const read = await plcClientRef.current.readCaptureInput(plan, (message) => {
          plcBoundModelIdRef.current = "";
          setPlcConnected(false);
          setPlcConnectionStatus(message);
        });
        if (!read || cancelled) {
          schedule();
          return;
        }
        const common = {
          value: read.value,
          requestHex: read.request_hex,
          responseHex: read.response_hex,
          readAt: read.read_at
        };
        const edge = nextCaptureTriggerState(armed, read.value, plan.trigger_value);
        armed = edge.armed;
        if (edge.action === "armed") {
          setPlcCapturePoll((current) => ({
            ...current,
            ...common,
            status: "armed",
            message: `已武装；等待 ${plan.target} 变为 ${plan.trigger_value}。`
          }));
        } else if (edge.action === "latched") {
          setPlcCapturePoll((current) => ({
            ...current,
            ...common,
            status: current.status === "triggered" || current.status === "missed" ? "latched" : "unarmed",
            message: `当前值持续为 ${plan.trigger_value}；不会重复拍照，等待复位。`
          }));
        } else {
          const triggerAt = Date.now();
          const video = videoRef.current;
          const cameraReady = source === "camera" && Boolean(stream) && Boolean(activeModelId)
            && Boolean(video && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth > 0 && video.videoHeight > 0)
            && Boolean(stream?.getVideoTracks().some((track) => track.readyState === "live" && track.enabled))
            && !busyRef.current && !plcDiagnosticBusy;
          if (!cameraReady) {
            setPlcCapturePoll((current) => ({
              ...current,
              ...common,
              triggerAt,
              status: "missed",
              message: "检测到到位沿，但摄像头、模型或检测任务未就绪；本次不补拍。"
            }));
          } else {
            const requiredPlcState = plcClientRef.current.state();
            if (!requiredPlcState) {
              setPlcCapturePoll((current) => ({
                ...current,
                ...common,
                triggerAt,
                status: "missed",
                message: "检测到到位沿，但 PLC 租约已经失效；本次不补拍。"
              }));
              schedule();
              return;
            }
            setPlcCapturePoll((current) => ({
              ...current,
              ...common,
              triggerAt,
              status: "triggered",
              message: `检测到 ${plan.target}=${plan.trigger_value}，正在拍照检测。`
            }));
            const completed = await runCamera(video, {
              requiredPlcState,
              cameraRequestId: `plc_trigger_${crypto.randomUUID()}`
            });
            if (!completed) {
              setPlcCapturePoll((current) => ({
                ...current,
                status: "missed",
                message: "到位沿已消费，但拍照或 PLC 专用检测未完成；本次不补拍。"
              }));
            }
          }
        }
        schedule();
      } catch (nextError) {
        if (cancelled) return;
        setPlcCapturePoll((current) => ({
          ...current,
          status: "read_error",
          message: nextError instanceof Error ? nextError.message : String(nextError)
        }));
      }
    };
    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [
    activeModelId,
    plcConnected,
    plcDiagnosticBusy,
    plcWorkstationQuery.data?.capture_read_plan?.config_generation,
    plcWorkstationQuery.data?.capture_read_plan?.frame_hex,
    plcWorkstationQuery.data?.capture_read_plan?.trigger_value,
    plcWorkstationQuery.data?.config?.capture_trigger_enabled,
    plcWorkstationQuery.data?.config?.enabled,
    source,
    stream
  ]);

  useEffect(() => {
    if (routeTask && !isAi) {
      const fallback = modelOptions.find((model) => model.exists || isAiModel(model));
      if (!selectedModelId || !modelOptions.some((model) => model.id === selectedModelId && (model.exists || isAiModel(model)))) {
        setSelectedModelId(fallback?.id || "");
      }
      return;
    }
    if (routeTask) return;
    if (!taskOptions.length) return;
    const requestedSelection = !isAi ? requestedTaskSelection(requestedTaskId) : null;
    if (requestedSelection) {
      if (selectedTaskId !== requestedSelection.task.id) {
        setSelectedTaskId(requestedSelection.task.id);
        setSelectedModelId(requestedSelection.model?.id || "");
        return;
      }
      if (requestedSelection.model?.id && selectedModelId !== requestedSelection.model.id) {
        setSelectedModelId(requestedSelection.model.id);
        return;
      }
      return;
    }
    if (!taskOptions.some((task) => task.id === selectedTaskId)) {
      setSelectedTaskId("__default__");
      return;
    }
    const options = (taskOptions.find((task) => task.id === selectedTaskId) || taskOptions[0]).models || [];
    if (!options.some((model) => model.id === selectedModelId && (model.exists || isAiModel(model)))) {
      const fallback = selectedTaskId === "__default__"
        ? options.find((model) => model.id === status?.active_model_id && (model.exists || isAiModel(model))) || options.find((model) => model.exists || isAiModel(model))
        : options.find((model) => model.exists || isAiModel(model));
      setSelectedModelId(fallback?.id || "");
    }
  }, [isAi, modelOptions, requestedTaskId, routeTask, selectedModelId, selectedTaskId, status?.active_model_id, taskOptions]);

  useEffect(() => {
    if (routeTask && isAi) {
      if (selectedAiTask && selectedAiTaskId !== selectedAiTask.id) {
        setSelectedAiTaskId(selectedAiTask.id);
        return;
      }
      const fallback = modelOptions.find((model) => model.exists || isAiModel(model));
      if (!selectedModelId || !modelOptions.some((model) => model.id === selectedModelId && (model.exists || isAiModel(model)))) {
        setSelectedModelId(fallback?.id || selectedAiModelId || "");
      }
      return;
    }
    if (!isAi || !aiTasks.length) return;
    const requestedAiTask = requestedTaskId
      ? aiTasks.find((task) => [task.id, task.model_id].filter(Boolean).some((candidate) => String(candidate) === requestedTaskId))
      : null;
    if (requestedAiTask && selectedAiTaskId !== requestedAiTask.id) {
      setSelectedAiTaskId(requestedAiTask.id);
      return;
    }
    if (!aiTasks.some((task) => task.id === selectedAiTaskId)) {
      setSelectedAiTaskId(aiTasks[0]?.id || "");
      return;
    }
    if (selectedAiModelId && selectedModelId !== selectedAiModelId) {
      setSelectedModelId(selectedAiModelId);
    }
  }, [aiTasks, isAi, modelOptions, requestedTaskId, routeTask, selectedAiModelId, selectedAiTask, selectedAiTaskId, selectedModelId]);

  useEffect(() => {
    return () => {
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [stream]);

  useEffect(() => {
    return () => {
      environmentStream?.getTracks().forEach((track) => track.stop());
    };
  }, [environmentStream]);

  useEffect(() => {
    if (!fullscreenOpen || !fullscreenVideoRef.current || !stream) return;
    fullscreenVideoRef.current.srcObject = stream;
    fullscreenVideoRef.current.play().catch(() => undefined);
  }, [fullscreenOpen, stream]);

  useEffect(() => {
    if (!fullscreenOpen) return;
    window.requestAnimationFrame(() => fullscreenShellRef.current?.focus());
  }, [fullscreenOpen]);

  useEffect(() => {
    if (!selectedModelWarmable || selectedModelReady || selectedModelWarmupFailed || !selectedModelId) return;
    requestModelWarmup(selectedModelId);
  }, [selectedModelId, selectedModelReady, selectedModelWarmable, selectedModelWarmupFailed]);

  useEffect(() => {
    if (!selectedModelWarming && !displayedModelWarming) return;
    statusQuery.refetch();
    const timer = window.setInterval(() => {
      statusQuery.refetch();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [displayedModelWarming, selectedModelWarming, statusQuery.refetch]);

  useEffect(() => {
    if (!pendingModelId) return;
    let cancelled = false;
    let timer: number | undefined;

    async function pollPendingWarmup() {
      try {
        const nextStatus = await getServiceStatus(auth);
        queryClient.setQueryData(queryKeys.serviceStatus(auth.dataUserId), nextStatus);
        if (cancelled) return;
        if (warmupFailedForModel(nextStatus.yolo_warmup?.failed_model_ids, pendingModelId)) {
          setPendingModelId("");
          notify({ title: "模型预热失败", description: "已继续保持当前检测模型。", tone: "error" });
          return;
        }
        if (warmupReadyForModel(nextStatus.yolo_warmup, pendingModelId)) {
          const nextModel = modelOptions.find((model) => model.id === pendingModelId) || null;
          if (nextModel) {
            setSelectedModelId(nextModel.id);
            setPendingModelId("");
            notify({ title: "模型已预热", description: `已切换到 ${modelOptionLabel(nextModel)}。`, tone: "success" });
            return;
          }
        }
      } catch {
        // Keep the current AI model active and retry status polling.
      }
      if (!cancelled) timer = window.setTimeout(pollPendingWarmup, 1500);
    }

    pollPendingWarmup();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [auth, modelOptions, notify, pendingModelId, queryClient]);

  useEffect(() => {
    if (!pendingModelId) return;
    const nextModel = modelOptions.find((model) => model.id === pendingModelId) || null;
    if (!nextModel) {
      setPendingModelId("");
      return;
    }
    if (displayedModelWarmupFailed) {
      setPendingModelId("");
      notify({ title: "模型预热失败", description: "已继续保持当前检测模型。", tone: "error" });
      return;
    }
    if (modelIsReady(nextModel)) {
      setSelectedModelId(nextModel.id);
      setPendingModelId("");
      notify({ title: "模型已预热", description: `已切换到 ${modelOptionLabel(nextModel)}。`, tone: "success" });
    }
  }, [completedWarmupIds, displayedModelWarmupFailed, loadedModelIds, modelOptions, pendingModelId]);

  useEffect(() => {
    if (!fullscreenOpen) return;
    function handleFullscreenKeydown(event: KeyboardEvent) {
      const isEnter = event.key === "Enter" || event.code === "Enter" || event.keyCode === 13;
      if (!isEnter || busy) return;
      event.preventDefault();
      event.stopPropagation();
      runCamera(fullscreenVideoRef.current);
    }
    document.addEventListener("keydown", handleFullscreenKeydown, true);
    return () => document.removeEventListener("keydown", handleFullscreenKeydown, true);
  }, [busy, fullscreenOpen, stream, activeModelId, activeModelIsAi, selectedAiTaskId]);

  function detectionAudioContext() {
    if (typeof window === "undefined") return null;
    if (!detectionAudioRef.current) {
      const AudioContextCtor = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioContextCtor) return null;
      detectionAudioRef.current = new AudioContextCtor();
    }
    const context = detectionAudioRef.current;
    if (context.state === "suspended") {
      context.resume().catch(() => undefined);
    }
    return context;
  }

  function playDetectionBeep(context: AudioContext, frequency: number, start: number, duration: number, type: OscillatorType, gainValue: number) {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, start);
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(gainValue, start + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(start);
    oscillator.stop(start + duration + 0.02);
  }

  function playDetectionSound(passed: boolean) {
    const context = detectionAudioContext();
    if (!context) return;
    const now = context.currentTime + 0.025;
    if (passed) {
      playDetectionBeep(context, 659.25, now, 0.09, "sine", 0.08);
      playDetectionBeep(context, 987.77, now + 0.085, 0.16, "sine", 0.07);
      return;
    }
    playDetectionBeep(context, 392.0, now, 0.08, "square", 0.055);
    playDetectionBeep(context, 261.63, now + 0.095, 0.08, "square", 0.055);
    playDetectionBeep(context, 196.0, now + 0.19, 0.1, "square", 0.05);
  }

  async function refreshCameras() {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setDevices([]);
      setCameraStatus("当前浏览器不支持摄像头枚举。");
      return [];
    }
    const next = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === "videoinput");
    setDevices(next);
    if (!selectedDeviceId && next[0]?.deviceId) setSelectedDeviceId(next[0].deviceId);
    setCameraStatus(next.length ? `检测到 ${next.length} 个摄像头。` : "未检测到摄像头。");
    return next;
  }

  async function startCamera(deviceId = selectedDeviceId) {
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraStatus("当前浏览器不支持摄像头预览。");
      return;
    }
    setBusy("camera");
    setError("");
    try {
      stream?.getTracks().forEach((track) => track.stop());
      const nextStream = await navigator.mediaDevices.getUserMedia({
        video: deviceId ? { deviceId: { exact: deviceId } } : true,
        audio: false
      });
      setStream(nextStream);
      if (videoRef.current) {
        videoRef.current.srcObject = nextStream;
        await videoRef.current.play();
      }
      const track = nextStream.getVideoTracks()[0];
      const settings = track?.getSettings?.() || {};
      if (settings.deviceId) setSelectedDeviceId(settings.deviceId);
      await refreshCameras();
      setCameraStatus(`摄像头已连接：${track?.label || "当前摄像头"}`);
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : String(nextError);
      setCameraStatus(`摄像头不可用：${message}`);
      setError(message);
      notify({ title: "摄像头不可用", description: message, tone: "error" });
    } finally {
      setBusy("");
    }
  }

  function stopEnvironmentCamera() {
    environmentStream?.getTracks().forEach((track) => track.stop());
    setEnvironmentStream(null);
    if (environmentVideoRef.current) environmentVideoRef.current.srcObject = null;
  }

  async function startEnvironmentCamera(deviceId = selectedDeviceId) {
    if (!navigator.mediaDevices?.getUserMedia) {
      setEnvironmentCaptureStatus("当前浏览器不支持摄像头预览。");
      return;
    }
    setEnvironmentInputMode("camera");
    setEnvironmentUploadFile(null);
    setEnvironmentCaptureStatus("正在打开摄像头。");
    try {
      environmentStream?.getTracks().forEach((track) => track.stop());
      const nextStream = await navigator.mediaDevices.getUserMedia({
        video: deviceId ? { deviceId: { exact: deviceId } } : true,
        audio: false
      });
      setEnvironmentStream(nextStream);
      if (environmentVideoRef.current) {
        environmentVideoRef.current.srcObject = nextStream;
        await environmentVideoRef.current.play();
      }
      const track = nextStream.getVideoTracks()[0];
      const settings = track?.getSettings?.() || {};
      if (settings.deviceId) setSelectedDeviceId(settings.deviceId);
      await refreshCameras();
      setEnvironmentCaptureStatus(`摄像头已连接：${track?.label || "当前摄像头"}。请确认流水线为空，再拍摄背景。`);
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : String(nextError);
      setEnvironmentCaptureStatus(`摄像头不可用：${message}`);
      notify({ title: "摄像头不可用", description: message, tone: "error" });
    }
  }

  async function openEnvironmentCapture() {
    setSource("camera");
    setFullscreenOpen(false);
    setEnvironmentCaptureOpen(true);
    setEnvironmentInputMode("camera");
    setEnvironmentUploadFile(null);
    setEnvironmentCaptureStatus("首次检测前需要拍摄空白生产环境。");
    await refreshCameras();
    await startEnvironmentCamera();
  }

  async function ensureEnvironmentBackground() {
    if (!environmentBackgroundRequired || environmentBackgroundReady) return true;
    if (environmentBackgroundQuery.isLoading) {
      notify({ title: "正在检查空场景背景", tone: "info" });
      return false;
    }
    await openEnvironmentCapture();
    return false;
  }

  function closeEnvironmentCapture() {
    setEnvironmentCaptureOpen(false);
    setEnvironmentInputMode("camera");
    setEnvironmentUploadFile(null);
    stopEnvironmentCamera();
  }

  function handleEnvironmentSourceChange(value: string) {
    if (value === ENVIRONMENT_UPLOAD_OPTION) {
      setEnvironmentInputMode("upload");
      stopEnvironmentCamera();
      setEnvironmentCaptureStatus("请选择一张空白生产环境照片。");
      return;
    }
    setEnvironmentInputMode("camera");
    setEnvironmentUploadFile(null);
    setSelectedDeviceId(value);
    void startEnvironmentCamera(value);
  }

  function handleEnvironmentUploadChange(file: File | null | undefined) {
    if (!file) {
      setEnvironmentUploadFile(null);
      setEnvironmentCaptureStatus("请选择一张空白生产环境照片。");
      return;
    }
    setEnvironmentUploadFile(file);
    setEnvironmentCaptureStatus(`已选择：${file.name}`);
  }

  async function saveEnvironmentBackground() {
    if (!environmentBackgroundTaskId) {
      notify({ title: "当前任务没有可绑定的 AI 任务", tone: "error" });
      return;
    }
    try {
      const file =
        environmentInputMode === "upload"
          ? environmentUploadFile
          : await captureVideoFrame(environmentVideoRef.current, "environment_background");
      if (!file) {
        setEnvironmentCaptureStatus("请先选择一张空白生产环境照片。");
        return;
      }
      await environmentBackgroundMutation.mutateAsync({ taskId: environmentBackgroundTaskId, file });
      stopEnvironmentCamera();
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : String(nextError);
      setEnvironmentCaptureStatus(message);
      notify({ title: "拍摄空场景失败", description: message, tone: "error" });
    }
  }

  async function runAnalysis(
    kind: SourceMode,
    file: File,
    options?: { requiredPlcState?: PlcBrowserConnectionState; cameraRequestId?: string }
  ) {
    if (!(await ensureEnvironmentBackground())) return false;
    if (!activeModelId) {
      notify({ title: "当前任务暂无可用模型", tone: "error" });
      return false;
    }
    detectionAudioContext();
    busyRef.current = kind;
    setBusy(kind);
    setError("");
    const controller = new AbortController();
    const timeoutMs = detectionTimeoutMs(kind);
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const form = new FormData();
      const uploadFile = kind === "video" || activeModelIsAi ? file : await optimizeImageUpload(file);
      form.append("file", uploadFile);
      form.append("model_id", activeModelId);
      const currentPlcState = kind === "camera" ? plcClientRef.current.state() : null;
      const requiredPlcState = options?.requiredPlcState;
      if (requiredPlcState && (
        !currentPlcState
        || currentPlcState.sessionId !== requiredPlcState.sessionId
        || currentPlcState.leaseEpoch !== requiredPlcState.leaseEpoch
        || currentPlcState.configGeneration !== requiredPlcState.configGeneration
      )) {
        throw new Error("PLC 自动触发连接或配置已失效，禁止降级为普通图片检测");
      }
      const plcState = requiredPlcState || currentPlcState;
      if (plcState) {
        form.append("plc_session_id", plcState.sessionId);
        form.append("camera_request_id", options?.cameraRequestId || `camera_${crypto.randomUUID()}`);
      }
      let next = kind === "video"
        ? await analyzeVideo(form, { signal: controller.signal })
        : plcState
          ? await analyzeCamera(form, { signal: controller.signal })
          : await analyzeImage(form, { signal: controller.signal });
      if (requiredPlcState && !next.plc_sync) {
        throw new Error("PLC 自动触发检测未返回工作站指令计划");
      }
      if (plcState && next.plc_sync?.status === "planned") {
        next = {
          ...next,
          plc_sync: await plcClientRef.current.execute(next.plc_sync, (message) => {
            setPlcConnected(false);
            setPlcConnectionStatus(message);
          })
        };
        await plcWorkstationQuery.refetch();
      }
      setResult(next);
      setSource(kind);
      playDetectionSound(Boolean(next.passed));
      notify({ title: kind === "video" ? "视频分析完成" : `${activeDetectionLabel}完成`, tone: "success" });
      return true;
    } catch (nextError) {
      const message = isAbortError(nextError) ? detectionTimeoutText(kind, timeoutMs) : nextError instanceof Error ? nextError.message : String(nextError);
      setError(message);
      playDetectionSound(false);
      notify({ title: "检测失败", description: message, tone: "error" });
      return false;
    } finally {
      window.clearTimeout(timeout);
      busyRef.current = "";
      setBusy("");
    }
  }

  async function runCamera(
    videoElement: HTMLVideoElement | null = videoRef.current,
    options?: { requiredPlcState?: PlcBrowserConnectionState; cameraRequestId?: string }
  ) {
    if (cameraCaptureLockRef.current || busyRef.current) {
      if (!options?.requiredPlcState) notify({ title: "已有检测正在执行", tone: "info" });
      return false;
    }
    if (plcDiagnosticBusy) {
      notify({ title: "PLC 通讯诊断正在执行", description: "请等待诊断结束后再拍照检测", tone: "info" });
      return false;
    }
    cameraCaptureLockRef.current = true;
    busyRef.current = "camera";
    setBusy("camera");
    try {
      if (!(await ensureEnvironmentBackground())) return false;
      if (!stream) {
        if (options?.requiredPlcState) return false;
        await startCamera();
      }
      const file = await captureVideoFrame(videoElement, activeModelIsAi ? "ai_camera_capture" : "camera_capture");
      return await runAnalysis("camera", file, options);
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : String(nextError);
      setError(message);
      notify({ title: "摄像头检测失败", description: message, tone: "error" });
      return false;
    } finally {
      cameraCaptureLockRef.current = false;
      if (busyRef.current === "camera") busyRef.current = "";
      setBusy("");
    }
  }

  async function connectPlc() {
    if (!activeModelId) {
      notify({ title: "请先选择检测模型", tone: "error" });
      return;
    }
    const workstation = plcWorkstationQuery.data;
    if (!workstation?.paired || !workstation.station) return notify({ title: "请让管理员先在 PLC 设置中绑定本机工作站", tone: "error" });
    if (!workstation.config?.enabled) return notify({ title: "管理员尚未允许这台工作站启用 PLC 联动", tone: "error" });
    try {
      await plcClientRef.current.connect(workstation.station.id, activeModelId, (message) => {
        setPlcConnected(false);
        setPlcConnectionStatus(message);
      });
      plcBoundModelIdRef.current = activeModelId;
      setPlcConnected(true);
      setPlcConnectionStatus(`已连接 ${workstation.station.name}；可连续检测；配置 generation ${workstation.config_generation}。`);
      await plcWorkstationQuery.refetch();
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : String(nextError);
      setPlcConnected(false);
      setPlcConnectionStatus(`PLC 连接失败：${message}`);
      notify({ title: "PLC 连接失败", description: message, tone: "error" });
    }
  }

  async function disconnectPlc(message = "PLC 已断开。") {
    await plcClientRef.current.disconnect(true);
    plcBoundModelIdRef.current = "";
    setPlcConnected(false);
    setPlcConnectionStatus(message);
    await plcWorkstationQuery.refetch();
  }

  async function runPlcDiagnostic() {
    if (!plcConnected) return notify({ title: "请先连接本机 PLC", tone: "error" });
    if (!window.confirm("该测试会把 D206 临时写成 6，并立即读取 D206。请确认 D206 当前可以安全覆盖。")) return;
    setPlcDiagnosticBusy(true);
    setPlcDiagnostic(null);
    try {
      const diagnostic = await plcClientRef.current.diagnoseD206((message) => {
        setPlcConnected(false);
        setPlcConnectionStatus(message);
      });
      setPlcDiagnostic(diagnostic);
      notify({
        title: diagnostic.status === "success" ? "PLC 通讯成功" : "PLC 通讯诊断未通过",
        description: diagnostic.conclusion,
        tone: diagnostic.status === "success" ? "success" : "error"
      });
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : String(nextError);
      setPlcDiagnostic({
        status: "failed",
        conclusion: message,
        write_frame_hex: "",
        write_response_hex: "",
        read_frame_hex: "",
        read_response_hex: "",
        read_value: null
      });
      notify({ title: "PLC 通讯诊断失败", description: message, tone: "error" });
    } finally {
      setPlcDiagnosticBusy(false);
    }
  }

  async function openFullscreenCamera() {
    setSource("camera");
    setFullscreenOpen(true);
    await refreshCameras();
    await startCamera();
  }

  function handleRulesSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const confidence_threshold = Number(data.get("confidence_threshold") || ruleThreshold);
    if (isDefaultTask) {
      globalRuleMutation.mutate({
        confidence_threshold,
        required_classes: (status?.classes || [])
          .filter((item) => data.get(`required_${item.class_id}`) === "on")
          .map((item) => item.class_id),
        min_counts: Object.fromEntries(
          (status?.classes || []).map((item) => [
            String(item.class_id),
            Math.max(1, Number(data.get(`count_${item.class_id}`) || defaultMinCounts[String(item.class_id)] || 1))
          ])
        )
      });
      return;
    }
    const required_accessory_counts = Object.fromEntries(
      taskRuleRows
        .filter((item) => data.get(`required_${item.id}`) === "on")
        .map((item) => [
          item.id,
          Math.max(1, Number(data.get(`count_${item.id}`) || item.count || 1))
        ])
    );
    if (!Object.keys(required_accessory_counts).length) {
      notify({ title: "至少保留一个必检配件", tone: "error" });
      return;
    }
    const taskRuleId = routeTask ? selectedModel?.task_id || routeTask.sourceId : selectedTaskId;
    taskRuleMutation.mutate({
      taskId: taskRuleId,
      payload: { confidence_threshold, required_accessory_counts }
    });
  }

  if (!decodedRouteTaskId && !requestedTaskId) {
    return (
      <TaskDetectionEntryPage
        tasks={taskEntries}
        loading={trainingResourcesQuery.isLoading || pipelineQuery.isLoading}
        error={trainingResourcesQuery.error || pipelineQuery.error}
        onRetry={() => {
          trainingResourcesQuery.refetch();
          pipelineQuery.refetch();
        }}
      />
    );
  }

  if (decodedRouteTaskId && (trainingResourcesQuery.isLoading || pipelineQuery.isLoading)) {
    return <LoadingState label="正在加载任务检测中心" />;
  }
  if (decodedRouteTaskId && (trainingResourcesQuery.isError || pipelineQuery.isError)) {
    return (
      <ErrorState
        error={trainingResourcesQuery.error || pipelineQuery.error}
        action={<button onClick={() => {
          trainingResourcesQuery.refetch();
          pipelineQuery.refetch();
        }}>重试</button>}
      />
    );
  }
  if (decodedRouteTaskId && !routeTask) return <Navigate to="/inspect" replace />;

  if (statusQuery.isLoading || (shouldLoadAiTasks && aiTasksQuery.isLoading)) return <LoadingState label="正在加载检测工作台" />;
  if (statusQuery.isError) return <ErrorState error={statusQuery.error} action={<button onClick={() => statusQuery.refetch()}>重试</button>} />;
  if (shouldLoadAiTasks && aiTasksQuery.isError) return <ErrorState error={aiTasksQuery.error} action={<button onClick={() => aiTasksQuery.refetch()}>重试</button>} />;

  return (
    <section className="view active detection-workbench">
      <header className="page-head">
        <div>
          <h2>{routeTask?.label || "检测中心"}</h2>
          <p className="page-desc">
            当前页面已绑定任务，只能切换这个任务下的可用模型；上传图片、视频或使用摄像头输出通过 / 不通过。
          </p>
        </div>
        <div className="page-head-actions detection-head-actions">
          <strong className={`pill ${statusBadge.includes("就绪") || statusBadge.includes("加载") ? "ok" : "neutral"}`}>{statusBadge}</strong>
          <button className="secondary compact-action" type="button" disabled={Boolean(busy)} onClick={openFullscreenCamera}>
            <Maximize2 size={16} aria-hidden="true" />
            全屏检测
          </button>
          {!activeModelIsAi ? (
            <button className="secondary compact-action" type="button" onClick={() => setRulesOpen(true)}>
              <Settings size={16} aria-hidden="true" />
              设置规则
            </button>
          ) : null}
          <span className={`result-badge ${result ? (result.passed ? "pass" : "fail") : "waiting"}`}>
            {result ? (result.passed ? "通过" : "不通过") : "等待输入"}
          </span>
        </div>
      </header>

      <section className="panel page-panel detection-toolbar task-bound-toolbar">
        <div className="selected-task-card compact-selected-task-card">
          <strong>{routeTask?.label || selectedAiTask?.name || currentTask?.label || "当前任务"}</strong>
          <span>{routeTask ? routeTask.meta : isAi ? "AI 检测任务" : currentTask?.meta}</span>
          <span>配件：{routeTask ? taskAccessoryText(routeTask) : selectedAiTask?.accessory_names?.join("、") || currentTask?.accessory_names?.join("、") || "-"}</span>
        </div>
        <label className="toolbar-field task-bound-model-field">
          <span className="toolbar-field-label">当前模型</span>
          <select value={displayedModelId} onChange={(event) => handleModelSelection(event.currentTarget.value)}>
            {modelOptions.length ? (
              modelOptions.map((model) => (
                <option value={model.id} key={model.id} disabled={!model.exists && !isAiModel(model)}>
                  {modelOptionLabel(model)} · {modelOptionMeta(model)}
                </option>
              ))
            ) : (
              <option value="">暂无可用模型</option>
            )}
          </select>
          {displayedModelWarmable ? (
            <span className={`model-warmup-status ${warmupTone}`} aria-live="polite">
              <span aria-hidden="true" />
              {warmupLabel}
            </span>
          ) : null}
          {pendingModel ? (
            <span className="record-meta">
              {modelOptionLabel(pendingModel)} 后台预热中，当前生效：{selectedModel ? modelOptionLabel(selectedModel) : "AI 检测"}
            </span>
          ) : null}
        </label>
      </section>

      <div className="inspect-grid">
        <section className="panel page-panel input-panel">
          <div className="section-title">
            <h3>输入源</h3>
          </div>
          <div className="tabbar" role="tablist" aria-label={`${title}输入源`}>
            {SOURCE_TABS.map(({ value, label, Icon }) => (
              <button
                className={`mode-tab ${source === value ? "active" : ""}`}
                type="button"
                role="tab"
                aria-selected={source === value}
                onClick={() => setSource(value)}
                key={value}
              >
                <Icon size={15} aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>

          {source === "image" ? (
            <div className="tabpane active">
              <label className="dropzone">
                <input type="file" accept="image/*" onChange={(event) => setImageFile(event.currentTarget.files?.[0] || null)} />
                <span className="dropzone-file-action">选择图片</span>
                <strong>上传 {activeDetectionLabel}图片</strong>
                <span className="dropzone-file-name">{imageFile?.name || "支持 PNG / JPG / JPEG"}</span>
              </label>
              <button className="primary icon-label" type="button" disabled={!imageFile || Boolean(busy)} onClick={() => imageFile && runAnalysis("image", imageFile)}>
                <Play size={16} aria-hidden="true" />
                开始 {activeDetectionLabel}
              </button>
            </div>
          ) : null}

          {source === "video" ? (
            <div className="tabpane active">
              <label className="dropzone">
                <input type="file" accept="video/*" onChange={(event) => setVideoFile(event.currentTarget.files?.[0] || null)} />
                <span className="dropzone-file-action">选择视频</span>
                <strong>上传 {activeDetectionLabel}视频</strong>
                <span className="dropzone-file-name">{videoFile?.name || "抽帧检测并应用同一套通过规则"}</span>
              </label>
              <button className="primary icon-label" type="button" disabled={!videoFile || Boolean(busy)} onClick={() => videoFile && runAnalysis("video", videoFile)}>
                <Play size={16} aria-hidden="true" />
                分析视频
              </button>
            </div>
          ) : null}

          {source === "camera" ? (
            <div className="tabpane active">
              <label className="toolbar-field">
                摄像头
                <select value={selectedDeviceId} onChange={(event) => {
                  setSelectedDeviceId(event.currentTarget.value);
                  if (event.currentTarget.value) startCamera(event.currentTarget.value);
                }}>
                  {devices.length ? (
                    devices.map((device, index) => (
                      <option value={device.deviceId} key={device.deviceId || index}>
                        {device.label || `摄像头 ${index + 1}`}
                      </option>
                    ))
                  ) : (
                    <option value="">未检测到摄像头</option>
                  )}
                </select>
              </label>
              <div className="camera-preview">
                <video ref={videoRef} autoPlay playsInline muted />
                {!stream ? <div className="camera-empty">选择摄像头后显示实时画面</div> : null}
              </div>
              <div className="camera-actions">
                <button className="secondary compact-action" type="button" disabled={busy === "camera"} onClick={async () => {
                  await refreshCameras();
                  await startCamera();
                }}>
                  <RefreshCw size={15} aria-hidden="true" />
                  检测摄像头
                </button>
                <button className="primary compact-action" type="button" disabled={Boolean(busy) || plcDiagnosticBusy} onClick={() => runCamera()}>
                  <Camera size={15} aria-hidden="true" />
                  拍照 {activeDetectionLabel}
                </button>
                {plcConnected ? (
                  <button className="secondary compact-action" type="button" onClick={() => void disconnectPlc()}>
                    断开 PLC
                  </button>
                ) : (
                  <button
                    className="secondary compact-action"
                    type="button"
                    disabled={Boolean(busy) || !PlcWebSerialClient.supported() || !plcWorkstationQuery.data?.paired}
                    onClick={() => void connectPlc()}
                  >
                    连接本机 PLC
                  </button>
                )}
              </div>
              <p className={`hint-line ${error ? "danger-text" : ""}`}>{error || cameraStatus}</p>
              <p className={`hint-line ${plcConnected ? "success-text" : ""}`}>
                {plcWorkstationQuery.data?.station ? `工作站：${plcWorkstationQuery.data.station.name}。` : "本机尚未绑定工作站。"} {plcConnectionStatus}
              </p>
              <section className="plc-communication-diagnostic" aria-label="PLC 到位拍照状态">
                <div className="section-title compact">
                  <h3>PLC 到位拍照</h3>
                  <span className={`pill ${plcCapturePoll.status === "armed" ? "ok" : plcCapturePoll.status === "read_error" || plcCapturePoll.status === "missed" ? "danger" : "neutral"}`}>
                    {{
                      disabled: "未启用",
                      unarmed: "未武装",
                      armed: "已武装",
                      latched: "已锁定",
                      triggered: "已触发",
                      missed: "已错过",
                      read_error: "读取故障"
                    }[plcCapturePoll.status]}
                  </span>
                </div>
                <div className="plc-diagnostic-labels" aria-live="polite">
                  <label>PLC 型号<output>三菱 FX3GA-40MR</output></label>
                  <label>输入寄存器<output>{plcWorkstationQuery.data?.config?.capture_input_register || "—"}</output></label>
                  <label>当前读取值<output>{plcCapturePoll.value ?? "—"}</output></label>
                  <label>状态说明<output>{plcCapturePoll.message}</output></label>
                  <label>最近读取时间<output>{plcCapturePoll.readAt ? formatLocalTimestamp(plcCapturePoll.readAt) : "—"}</output></label>
                  <label>最近触发时间<output>{plcCapturePoll.triggerAt ? formatLocalTimestamp(plcCapturePoll.triggerAt) : "—"}</output></label>
                  <label>最近读取指令<code>{plcCapturePoll.requestHex || "—"}</code></label>
                  <label>最近原始返回<code>{plcCapturePoll.responseHex || "—"}</code></label>
                </div>
              </section>
              <p className="hint-line">仅本页摄像头拍照检测会写 PLC；图片上传和视频分析永远不会写串口。页面隐藏、刷新、拔线或租约失效会立即停止新写入。</p>
              {canViewDiagnostics ? (
                <section className="plc-communication-diagnostic" aria-label="PLC 通讯诊断">
                  <div className="section-title title-with-action">
                    <div>
                      <h3>PLC 通讯诊断</h3>
                      <p className="hint-line">手动写入 D206=6，再读取 D206；不会控制任何 Y 点。</p>
                    </div>
                    <button
                      className="secondary compact-action"
                      type="button"
                      disabled={!plcConnected || plcDiagnosticBusy || Boolean(busy)}
                      onClick={() => void runPlcDiagnostic()}
                    >
                      {plcDiagnosticBusy ? "诊断中…" : "写入 6 并读取 D206"}
                    </button>
                  </div>
                  <div className="plc-diagnostic-labels" aria-live="polite">
                    <label>
                      通讯结论
                      <output className={plcDiagnostic?.status === "success" ? "success-text" : plcDiagnostic ? "danger-text" : ""}>
                        {plcDiagnostic?.conclusion || "尚未执行"}
                      </output>
                    </label>
                    <label>
                      D206 读取值
                      <output>{plcDiagnostic?.read_value ?? "—"}</output>
                    </label>
                    <label>
                      写入指令（D206=6）
                      <code>{plcDiagnostic?.write_frame_hex || "—"}</code>
                    </label>
                    <label>
                      写入返回（应为 06 ACK）
                      <code>{plcDiagnostic?.write_response_hex || "—"}</code>
                    </label>
                    <label>
                      读取指令（D206）
                      <code>{plcDiagnostic?.read_frame_hex || "—"}</code>
                    </label>
                    <label>
                      PLC 读取原始返回
                      <code>{plcDiagnostic?.read_response_hex || "—"}</code>
                    </label>
                  </div>
                </section>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="panel page-panel result-panel">
          <div className="section-title title-with-action">
            <h3>{activeResultLabel} 结果预览</h3>
            {canViewDiagnostics ? (
              <button className="secondary compact-action" type="button" onClick={() => setDebugOpen(true)}>
                开发诊断
              </button>
            ) : null}
          </div>
          <div className={`progress-panel ${busy ? "active" : ""}`} aria-live="polite">
            <div className="progress-copy">
              <strong>{busy === "video" ? "正在分析视频" : busy ? "正在检测" : "准备检测"}</strong>
              <span>{busy ? "处理中" : "0%"}</span>
            </div>
            <progress className="native-progress" value={busy ? 72 : 0} max={100} />
            <p>{busy ? "文件已提交，等待服务返回检测结果；超时会提示重试。" : "上传图片或视频后开始检测。"}</p>
          </div>
          <div className="preview-frame">
            {resultImage ? <img src={resultImage} alt={`${activeDetectionLabel}结果`} /> : <div className="empty-state">检测标注图会显示在这里</div>}
          </div>
          {error && source !== "camera" ? <p className="hint-line danger-text">{error}</p> : null}
        </section>
      </div>

      <DetectionMetrics result={result} mode={activeModelIsAi ? "ai" : "inspect"} source={source} requiredCounts={requiredCounts} />

      {environmentCaptureOpen ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-panel wide task-rule-modal" role="dialog" aria-modal="true" aria-label="拍摄空场景背景">
            <header className="modal-head">
              <div>
                <h3>拍摄空场景背景</h3>
                <span>{routeTask?.label || selectedAiTask?.name || "当前检测任务"}</span>
              </div>
              <button className="icon-only" type="button" aria-label="关闭" onClick={closeEnvironmentCapture}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="modal-body settings-form">
              <p className="hint-line">请保持流水线为空，不要放配件。保存后，后续训练集会把 sprite 叠加到这张真实生产环境背景上。</p>
              <label className="toolbar-field">
                背景来源
                <select value={environmentSourceValue} onChange={(event) => handleEnvironmentSourceChange(event.currentTarget.value)}>
                  <option value="">自动选择摄像头</option>
                  <option value={ENVIRONMENT_UPLOAD_OPTION}>上传照片</option>
                  {devices.length ? (
                    devices.map((device, index) => (
                      <option value={device.deviceId} key={device.deviceId || index}>
                        {device.label || `摄像头 ${index + 1}`}
                      </option>
                    ))
                  ) : (
                    <option value="">未检测到摄像头</option>
                  )}
                </select>
              </label>
              {environmentInputMode === "upload" ? (
                <label className="dropzone compact-dropzone">
                  <input type="file" accept="image/*" onChange={(event) => handleEnvironmentUploadChange(event.currentTarget.files?.[0])} />
                  <span className="dropzone-file-action">选择照片</span>
                  <strong>上传空白生产环境照片</strong>
                  <span className="dropzone-file-name">{environmentUploadFile?.name || "支持 PNG / JPG / JPEG"}</span>
                </label>
              ) : (
                <div className="camera-preview">
                  <video ref={environmentVideoRef} autoPlay playsInline muted />
                  {!environmentStream ? <div className="camera-empty">正在打开摄像头</div> : null}
                </div>
              )}
              <p className={`hint-line ${environmentCaptureStatus.includes("失败") || environmentCaptureStatus.includes("不可用") ? "danger-text" : ""}`}>{environmentCaptureStatus}</p>
            </div>
            <footer className="modal-footer">
              <button className="secondary compact-action" type="button" onClick={closeEnvironmentCapture}>
                稍后
              </button>
              {environmentInputMode === "camera" ? (
                <button className="secondary compact-action" type="button" disabled={environmentBackgroundMutation.isPending} onClick={() => startEnvironmentCamera()}>
                  <RefreshCw size={15} aria-hidden="true" />
                  重新连接
                </button>
              ) : null}
              <button className="primary compact-action" type="button" disabled={!environmentBackgroundCanSave || environmentBackgroundMutation.isPending} onClick={saveEnvironmentBackground}>
                <Camera size={15} aria-hidden="true" />
                {environmentBackgroundMutation.isPending ? "保存中" : environmentInputMode === "upload" ? "保存上传背景" : "拍摄并保存背景"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {rulesOpen && !activeModelIsAi ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-panel wide task-rule-modal" role="dialog" aria-modal="true" aria-label="设置检测通过规则">
            <header className="modal-head">
              <div>
                <h3>设置规则</h3>
                <span>{currentTask?.label || "当前检测任务"}</span>
              </div>
              <button className="icon-only" type="button" aria-label="关闭" onClick={() => setRulesOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <form className="modal-body settings-form" key={selectedTaskId} onSubmit={handleRulesSubmit}>
              <label className="field range-field">
                置信度阈值
                <input
                  name="confidence_threshold"
                  type="range"
                  min="0.05"
                  max="0.95"
                  step="0.05"
                  defaultValue={ruleThreshold}
                  onInput={(event) => {
                    const output = event.currentTarget.closest(".range-field")?.querySelector("output");
                    if (output) output.textContent = Number(event.currentTarget.value).toFixed(2);
                  }}
                />
                <output>{ruleThreshold.toFixed(2)}</output>
              </label>
              {isDefaultTask ? (
                status?.classes?.length ? (
                  <div className="rule-grid task-rule-grid">
                    {status.classes.map((item) => (
                      <label className="check-row" key={item.class_id}>
                        <input
                          name={`required_${item.class_id}`}
                          type="checkbox"
                          defaultChecked={defaultRequiredClasses.has(item.class_id)}
                        />
                        <span>{classLabel(item)}</span>
                        <input
                          name={`count_${item.class_id}`}
                          type="number"
                          min="1"
                          max="99"
                          defaultValue={defaultMinCounts[String(item.class_id)] || 1}
                        />
                      </label>
                    ))}
                  </div>
                ) : (
                  <div className="empty-panel">当前模型未返回类别。</div>
                )
              ) : taskRuleRows.length ? (
                <div className="rule-grid task-rule-grid">
                  {taskRuleRows.map((item) => (
                    <label className="check-row" key={item.id}>
                      <input name={`required_${item.id}`} type="checkbox" defaultChecked={item.count > 0} />
                      <span>{item.label}</span>
                      <input name={`count_${item.id}`} type="number" min="1" max="99" defaultValue={item.count || 1} />
                    </label>
                  ))}
                </div>
              ) : (
                <div className="empty-panel">当前任务没有可配置的配件规则。</div>
              )}
              <div className="button-row">
                <button className="primary compact-action" type="submit" disabled={rulesBusy || (!isDefaultTask && !taskRuleRows.length)}>
                  <Save size={16} aria-hidden="true" />
                  保存规则
                </button>
                <button className="secondary compact-action" type="button" onClick={() => setRulesOpen(false)}>
                  取消
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {fullscreenOpen ? (
        <div
          className="inspection-fullscreen"
          role="dialog"
          aria-modal="true"
          aria-label="全屏检测"
          ref={fullscreenShellRef}
          tabIndex={-1}
        >
          <header className="inspection-fullscreen-head">
            <div>
              <strong>{selectedAiTask?.name || currentTask?.label || "当前检测任务"}</strong>
              <span>{`${activeDetectionLabel} · 摄像头输入`}</span>
            </div>
            <div className="inspection-fullscreen-actions">
              <span className={`result-badge ${result ? (result.passed ? "pass" : "fail") : "waiting"}`}>
                {result ? (result.passed ? "通过" : "不通过") : "等待拍照"}
              </span>
              <button className="secondary compact-action" type="button" disabled={Boolean(busy) || plcDiagnosticBusy} onClick={() => runCamera(fullscreenVideoRef.current)}>
                <Camera size={15} aria-hidden="true" />
                拍照 {activeDetectionLabel}
              </button>
              <button className="icon-only" type="button" aria-label="退出全屏" onClick={() => setFullscreenOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </div>
          </header>
          <main className="inspection-fullscreen-stage">
            <aside className="inspection-fullscreen-result">
              <div className="preview-frame compact">
                {resultImage ? <img src={resultImage} alt="检测结果" /> : <div className="empty-state">按 Enter 或点击拍照检测</div>}
              </div>
            </aside>
            <aside className={`inspection-fullscreen-sidebar ${result ? (result.passed ? "result-pass" : "result-fail") : "result-waiting"}`}>
              <section className="inspection-fullscreen-video">
                <video ref={fullscreenVideoRef} autoPlay playsInline muted />
                {!stream ? <div className="camera-empty">正在打开摄像头</div> : null}
              </section>
              <DetectionMetrics result={result} mode={activeModelIsAi ? "ai" : "inspect"} source="camera" requiredCounts={requiredCounts} compact />
              <p className={`hint-line ${error ? "danger-text" : ""}`}>{error || cameraStatus || "按 Enter 拍照。"}</p>
            </aside>
          </main>
        </div>
      ) : null}

      {debugOpen && canViewDiagnostics ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-panel wide" role="dialog" aria-modal="true" aria-label="检测开发诊断">
            <header className="modal-head">
              <div>
                <h3>开发诊断</h3>
                <span>{result?.request_id || "暂无检测结果"}</span>
              </div>
              <button className="icon-only" type="button" aria-label="关闭" onClick={() => setDebugOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="modal-body">
              <pre className="json-panel">{JSON.stringify(resultDebugPayload(result), null, 2)}</pre>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
