import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent, PointerEvent, ReactNode } from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors
} from "@dnd-kit/core";
import type { CollisionDetection, DragEndEvent, DragStartEvent } from "@dnd-kit/core";
import {
  Archive,
  Bot,
  Boxes,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Eye,
  GripVertical,
  Library,
  Loader2,
  Minus,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Send,
  SlidersHorizontal,
  Trash2,
  X
} from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addPipelineAccessory,
  advancePipelineTask,
  createAccessory,
  createPipelineTask,
  deletePipelineTask,
  getAccessories,
  getAgentRecommendation,
  getPipeline,
  getTrainingDatasetDetail,
  getTrainingResources,
  queryKeys,
  removePipelineAccessory,
  sendPipelineAgentChat,
  sendPipelineAgentFeedback,
  updatePipelineTask
} from "../../api/queries";
import type {
  AccessorySummary,
  PipelineCandidate,
  PipelineDetectionMethod,
  PipelineStage,
  PipelineTask,
  PipelineTaskAccessory,
  PipelineTaskPayload,
  TrainingDataset,
  TrainingSample
} from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { recordAuditText, statusLabel, toneForStatus } from "../../utils/format";
import { useAuth } from "../auth/auth-context";

type PipelineMethod = "yolo_ocr" | "yolo" | "ai" | "locate";
type LaneStage = "draft" | "samples" | "training";
type DropKind = "lane" | "task" | "library" | "remove-accessory";
type DragKind = "accessory" | "task";
type AgentMcpDecision = "pending" | "continue_existing_assets" | "continue_training" | "replan_requested" | "cancelled";
type AgentMcpStageKey = "agent_pose_planning" | "pose_image_generation" | "sample_generation" | "model_training";

interface AgentPosePlan {
  accessory_id: string;
  accessory_name: string;
  object_kind: "cube" | "bottle" | "thin_object" | "generic_object";
  plan_source: "react_preview_rules";
  image_contract: "one_accessory_per_image";
  poses: Array<{
    pose_id: string;
    label: string;
    stable_contact: string;
    gravity_basis: string;
    conveyor_view: string;
    request: {
      subject_count: 1;
      target_paper: false;
      grid_layout: false;
      background: "conveyor";
    };
  }>;
}

interface AgentMcpStage {
  key: AgentMcpStageKey;
  label: string;
  status: "pending" | "completed" | "running" | "needs_user_action" | "skipped" | "failed";
  detail: string;
}

interface AgentMcpPreview {
  plans: AgentPosePlan[];
  stages: AgentMcpStage[];
  toolContracts: Array<{ tool: string; status: string; detail: string }>;
  pauseReason: string;
  suggestedActions: string[];
  activeStage?: string;
}

interface PipelineProgressBar {
  label: string;
  value: number;
  max: number;
  text: string;
  tone?: string;
  indeterminate?: boolean;
}

interface PipelineOperationOutput {
  key: string;
  label: string;
  status: string;
  detail: string;
  images: Array<{ url: string; label: string }>;
  rows: Array<{ label: string; value: string; tone?: string }>;
  progressBars?: PipelineProgressBar[];
}

interface PipelineSampleOutputState {
  requested: boolean;
  loading: boolean;
  error: unknown;
}

interface AgentConversationEntry {
  key: string;
  role: "agent" | "user" | "system";
  label: string;
  message: string;
  action?: string;
  reason?: string;
  targetStage?: string;
  source?: string;
  needsUser?: boolean;
  agentError?: string;
  images?: Array<{ url: string; label: string }>;
  createdAt?: number;
}

const AGENT_ACTION_LABELS: Record<string, string> = {
  advance: "推进阶段",
  set_params: "调整参数",
  goto_stage: "回退修改",
  retry: "重试生成",
  replan: "重新规划",
  pause_and_ask: "请求确认",
  continue_existing_assets: "沿用素材",
  continue_training: "进入训练",
  cancel: "取消任务",
  reply: "回复"
};

function agentActionLabel(action?: string): string {
  if (!action) return "";
  return AGENT_ACTION_LABELS[action] || action;
}

interface ActiveDrag {
  type: DragKind;
  id: string;
  label: string;
}

interface ParamsTarget {
  taskId: string;
  stageKey: "samples" | "training";
  advanceAfter: boolean;
}

const PIPELINE_METHODS: Array<{ value: PipelineMethod; label: string; usesTraining: boolean }> = [
  { value: "yolo_ocr", label: "YOLO + OCR", usesTraining: true },
  { value: "yolo", label: "YOLO", usesTraining: true },
  { value: "ai", label: "AI 检测", usesTraining: false },
  { value: "locate", label: "Locate Anything", usesTraining: false }
];

const PIPELINE_LANES: Array<{ stage: LaneStage; step: string; title: string; hint: string }> = [
  {
    stage: "draft",
    step: "2",
    title: "任务创建",
    hint: "先新建任务，再把第 1 栏配件拖入任务卡片。"
  },
  {
    stage: "samples",
    step: "3",
    title: "生成样本",
    hint: "把任务卡片拖入这里开始生成样本，完成后再拖入训练。"
  },
  {
    stage: "training",
    step: "4",
    title: "模型训练",
    hint: "训练完成后拖入模型库，即可在工作台切换使用。"
  }
];

const NEXT_STAGE: Record<string, PipelineStage> = {
  draft: "samples",
  samples: "training",
  training: "library"
};

const ACCESSORY_PENDING_STATUSES = new Set([
  "queued",
  "running",
  "pending",
  "candidate_review",
  "building",
  "generating",
  "failed",
  "error"
]);

function appendPipelineFormValue(form: FormData, key: string, value: string | number | boolean | undefined) {
  if (value === undefined || value === "") return;
  form.append(key, String(value));
}

function normalizePipelineMethod(value: PipelineDetectionMethod | undefined): PipelineMethod {
  const method = String(value || "").trim().toLowerCase();
  if (["ai_detection", "ai_inspect", "gemini", "ai"].includes(method)) return "ai";
  if (["locate_anything", "locateanything", "open_vocab", "locate"].includes(method)) return "locate";
  return method === "yolo" ? "yolo" : "yolo_ocr";
}

function methodMeta(value: PipelineDetectionMethod | undefined) {
  const method = normalizePipelineMethod(value);
  return PIPELINE_METHODS.find((item) => item.value === method) || PIPELINE_METHODS[0];
}

function pipelineTaskMethod(task: PipelineTask | null | undefined) {
  const params = task?.params || {};
  return normalizePipelineMethod(
    task?.detection_method || String(params.train_mode || params.route || "")
  );
}

function pipelineTaskUsesTraining(task: PipelineTask | null | undefined) {
  if (task?.uses_training_flow !== undefined) return task.uses_training_flow !== false;
  return methodMeta(pipelineTaskMethod(task)).usesTraining;
}

function stageLabel(stage: PipelineStage | undefined) {
  if (stage === "draft") return "任务创建";
  if (stage === "samples") return "生成样本";
  if (stage === "training") return "模型训练";
  if (stage === "library") return "模型库";
  return stage || "任务创建";
}

function pipelineStatusLabel(value: string | undefined) {
  if (value === "ready") return "待开始";
  if (value === "running") return "执行中";
  if (value === "pending") return "待参考图";
  if (value === "completed") return "已完成";
  if (value === "failed") return "失败";
  if (value === "stopped") return "已停止";
  return statusLabel(value);
}

function materialLabel(value: string | undefined) {
  return value === "text" ? "文字类" : value === "object" ? "物品类" : "配件";
}

function accessoryReady(item: AccessorySummary | PipelineCandidate) {
  const status = String(item.status || "active").trim().toLowerCase();
  return !ACCESSORY_PENDING_STATUSES.has(status);
}

function taskAccessoryCount(task: PipelineTask, accessoryId: string) {
  const raw = Number(task.accessory_counts?.[accessoryId] || 1);
  return Math.max(1, Math.min(99, Number.isFinite(raw) ? raw : 1));
}

function taskAccessoryRows(task: PipelineTask, inFlowAccessories: AccessorySummary[], libraryAccessories: AccessorySummary[]) {
  if (Array.isArray(task.accessories) && task.accessories.length) return task.accessories;
  const allAccessories = [...inFlowAccessories, ...libraryAccessories];
  return (task.accessory_ids || []).map((itemId) => {
    const accessory = allAccessories.find((item) => String(item.id) === String(itemId));
    return {
      id: itemId,
      name: accessory?.name || itemId,
      material_type: accessory?.material_type || "",
      count: taskAccessoryCount(task, itemId)
    };
  });
}

function agentSlug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "accessory";
}

function inferAgentObjectKind(item: PipelineTaskAccessory): AgentPosePlan["object_kind"] {
  const text = `${item.name || ""} ${item.id || ""}`.toLowerCase();
  if (/bottle|vial|jar|flask|瓶|罐/.test(text)) return "bottle";
  if (/cube|block|dice|方块|立方|积木/.test(text)) return "cube";
  if (item.material_type === "text" || /thin|card|label|sheet|manual|tag|片|纸|标签|说明书|卡/.test(text)) return "thin_object";
  return "generic_object";
}

function poseRequest() {
  return {
    subject_count: 1 as const,
    target_paper: false as const,
    grid_layout: false as const,
    background: "conveyor" as const
  };
}

function inferAgentPosePlan(item: PipelineTaskAccessory): AgentPosePlan {
  const objectKind = inferAgentObjectKind(item);
  const baseId = agentSlug(item.id || item.name || "accessory");
  const poseSets: Record<AgentPosePlan["object_kind"], AgentPosePlan["poses"]> = {
    cube: [
      {
        pose_id: `${baseId}_face_a_down`,
        label: "face_a_down",
        stable_contact: "one square face flat on conveyor",
        gravity_basis: "cube rests stably on any face",
        conveyor_view: "top face visible with slight side edge",
        request: poseRequest()
      },
      {
        pose_id: `${baseId}_face_b_down`,
        label: "face_b_down",
        stable_contact: "adjacent square face flat on conveyor",
        gravity_basis: "rotated cube exposes a different face",
        conveyor_view: "alternate face visible",
        request: poseRequest()
      },
      {
        pose_id: `${baseId}_face_c_down`,
        label: "face_c_down",
        stable_contact: "third square face flat on conveyor",
        gravity_basis: "third axis face can contact conveyor",
        conveyor_view: "third face visible",
        request: poseRequest()
      }
    ],
    bottle: [
      {
        pose_id: `${baseId}_upright`,
        label: "upright_base_down",
        stable_contact: "base on conveyor",
        gravity_basis: "flat base can stand vertically",
        conveyor_view: "cap/top footprint visible",
        request: poseRequest()
      },
      {
        pose_id: `${baseId}_horizontal_side`,
        label: "horizontal_side_down",
        stable_contact: "curved side contacts conveyor",
        gravity_basis: "bottle can lie on side after falling",
        conveyor_view: "long body silhouette visible",
        request: poseRequest()
      }
    ],
    thin_object: [
      {
        pose_id: `${baseId}_face_up`,
        label: "face_up",
        stable_contact: "back face on conveyor",
        gravity_basis: "thin object settles flat",
        conveyor_view: "front face visible",
        request: poseRequest()
      },
      {
        pose_id: `${baseId}_face_down`,
        label: "face_down",
        stable_contact: "front face on conveyor",
        gravity_basis: "thin object may flip but remains flat",
        conveyor_view: "back face visible",
        request: poseRequest()
      }
    ],
    generic_object: [
      {
        pose_id: `${baseId}_primary_rest`,
        label: "primary_resting_pose",
        stable_contact: "largest stable surface on conveyor",
        gravity_basis: "object settles on broadest support area",
        conveyor_view: "primary silhouette visible",
        request: poseRequest()
      },
      {
        pose_id: `${baseId}_side_rest`,
        label: "side_resting_pose",
        stable_contact: "secondary side surface on conveyor",
        gravity_basis: "secondary plausible rest pose",
        conveyor_view: "side silhouette visible",
        request: poseRequest()
      }
    ]
  };
  return {
    accessory_id: item.id,
    accessory_name: item.name || item.id,
    object_kind: objectKind,
    plan_source: "react_preview_rules",
    image_contract: "one_accessory_per_image",
    poses: poseSets[objectKind]
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asRecords(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item))) : [];
}

function shortId(value: unknown) {
  const text = String(value || "").trim();
  return text.length > 18 ? `${text.slice(0, 8)}...${text.slice(-6)}` : text;
}

function samplePublicUrl(sample: TrainingSample) {
  if (sample.annotated_url) return sample.annotated_url;
  if (sample.url) return sample.url;
  const image = String(sample.image || "");
  const marker = "/data/outputs/";
  if (image.includes(marker)) return `/outputs/${image.split(marker).pop()}`;
  return "";
}

function sampleDisplayName(sample: TrainingSample) {
  const raw = String(sample.image || sample.url || "sample");
  return raw.split(/[\\/]/).pop() || "sample";
}

function findPipelineDataset(datasets: TrainingDataset[], task: PipelineTask | null) {
  if (!task) return null;
  const ids = new Set([task.dataset_id, task.samples_task_id].map((item) => String(item || "")).filter(Boolean));
  return datasets.find((dataset) => ids.has(String(dataset.id || ""))) || null;
}

function callStatusSummary(calls: Array<Record<string, unknown>>) {
  const completed = calls.filter((call) => call.status === "completed").length;
  const failed = calls.filter((call) => call.status === "failed").length;
  const running = calls.filter((call) => call.status === "running").length;
  const pending = Math.max(0, calls.length - completed - failed - running);
  return { completed, failed, running, pending };
}

function stageByKey(agentMcp: Record<string, unknown>, key: AgentMcpStageKey) {
  return asRecords(agentMcp.stages).find((stage) => stage.key === key);
}

function PipelineThumb({ url, label, eager = false }: { url: string; label: string; eager?: boolean }) {
  const [failed, setFailed] = useState(false);
  return (
    <figure className={failed ? "pipeline-thumb-failed" : undefined}>
      {failed ? (
        <div className="pipeline-thumb-error" role="img" aria-label={`${label} 加载失败`}>
          <span>图片加载失败</span>
          <a href={url} target="_blank" rel="noreferrer">
            打开链接
          </a>
        </div>
      ) : (
        <a href={url} target="_blank" rel="noreferrer" className="pipeline-thumb-link" title={`${label} · 点击查看原图`}>
          <img src={url} alt={label} loading={eager ? "eager" : "lazy"} decoding="async" onError={() => setFailed(true)} />
        </a>
      )}
      <figcaption>{label}</figcaption>
    </figure>
  );
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 MB";
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  if (mb >= 10) return `${Math.round(mb)} MB`;
  return `${mb.toFixed(1)} MB`;
}

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}m${rest.toString().padStart(2, "0")}s`;
}

function transferProgressBar(
  label: string,
  status: string | undefined,
  startedAt: number | undefined,
  completedAt: number | undefined,
  doneBytes: number | undefined,
  totalBytes: number | undefined,
  nowSeconds: number
): PipelineProgressBar | null {
  const normalized = String(status || "").toLowerCase();
  if (!normalized) return null;
  const total = Number(totalBytes || 0);
  const done = Math.min(Number(doneBytes || 0), total || Number(doneBytes || 0));
  const started = Number(startedAt || 0);
  const completed = Number(completedAt || 0);
  const elapsed = started ? (completed && completed >= started ? completed - started : Math.max(0, nowSeconds - started)) : 0;
  const tone = normalized === "failed" ? "failed" : normalized === "completed" ? "completed" : "running";
  if (normalized === "completed") {
    return {
      label,
      value: total || 1,
      max: total || 1,
      tone,
      text: `${total ? formatBytes(total) : "完成"} · 用时 ${formatDuration(elapsed)}`
    };
  }
  if (normalized === "failed") {
    return { label, value: done, max: total || done || 1, tone, text: `传输失败 · 已传 ${formatBytes(done)}` };
  }
  const pct = total > 0 ? Math.min(99, Math.round((done / total) * 100)) : 0;
  const sizeText = total > 0 ? `${formatBytes(done)} / ${formatBytes(total)} (${pct}%)` : formatBytes(done);
  return {
    label,
    value: done,
    max: total || done || 1,
    tone,
    indeterminate: total <= 0,
    text: `${sizeText} · 已用 ${formatDuration(elapsed)}`
  };
}

function buildTransferProgressBars(task: PipelineTask): PipelineProgressBar[] {
  const now = Math.floor(Date.now() / 1000);
  const bars: PipelineProgressBar[] = [];
  const upload = transferProgressBar(
    "素材上传 HK → Worker",
    task.worker_upload_status,
    task.worker_upload_started_at,
    task.worker_upload_completed_at,
    task.worker_upload_sent_bytes,
    task.worker_upload_total_bytes,
    now
  );
  if (upload) bars.push(upload);
  const totalEpochs = Number(task.total_epochs || 0);
  if (totalEpochs > 0 && (task.worker_upload_status === "completed" || Number(task.current_epoch || 0) > 0)) {
    const currentEpoch = Math.min(Number(task.current_epoch || 0), totalEpochs);
    const epochDone = task.status === "completed";
    bars.push({
      label: "模型训练 Epoch",
      value: epochDone ? totalEpochs : currentEpoch,
      max: totalEpochs,
      tone: task.status === "failed" ? "failed" : epochDone ? "completed" : "running",
      text: `${epochDone ? totalEpochs : currentEpoch}/${totalEpochs} epochs`
    });
  }
  const download = transferProgressBar(
    "模型回传 Worker → HK",
    task.worker_download_status,
    task.worker_download_started_at,
    task.worker_download_completed_at,
    task.worker_download_received_bytes,
    task.worker_download_total_bytes,
    now
  );
  if (download) bars.push(download);
  return bars;
}

function buildPipelineOperationOutputs(
  task: PipelineTask,
  sampleDataset: TrainingDataset | null,
  sampleState: PipelineSampleOutputState
): PipelineOperationOutput[] {
  const agentMcp = asRecord(task.agent_mcp);
  const toolCalls = asRecords(agentMcp.tool_calls);
  const posePlan = asRecord(agentMcp.pose_plan);
  const poseCalls = toolCalls.filter((call) => call.tool === "generate_accessory_pose_image");
  const sampleCalls = toolCalls.filter((call) => call.tool === "generate_training_samples");
  const trainingCalls = toolCalls.filter((call) => call.tool === "start_model_training");
  const poseSummary = callStatusSummary(poseCalls);
  const sampleSummary = callStatusSummary(sampleCalls);
  const trainingSummary = callStatusSummary(trainingCalls);
  const poseStage = stageByKey(agentMcp, "pose_image_generation");
  const sampleStage = stageByKey(agentMcp, "sample_generation");
  const trainingStage = stageByKey(agentMcp, "model_training");
  const sampleImages = (sampleDataset?.samples || [])
    .map((sample) => ({ url: samplePublicUrl(sample), label: sampleDisplayName(sample) }))
    .filter((item) => item.url)
    .slice(0, 12);
  const sampleLoadError = sampleState.error instanceof Error ? sampleState.error.message : sampleState.error ? String(sampleState.error) : "";
  const backgroundPlate = asRecord(agentMcp.background_plate);
  const plateUrl = String(backgroundPlate.plate_url || "");
  const poseImages = [
    ...(plateUrl ? [{ url: plateUrl, label: "背景底图 / Background Plate" }] : []),
    ...poseCalls
      .map((call) => ({
        url: String(call.output_url || ""),
        label: [call.accessory_id, call.pose_id].map(shortId).filter(Boolean).join(" / ") || shortId(call.call_id) || "pose"
      }))
      .filter((item) => item.url)
      .slice(0, 12)
  ];

  return [
    {
      key: "pose_image_generation",
      label: "Image Generation",
      status: String(poseStage?.status || (poseCalls.length ? "logged" : "pending")),
      detail: String(
        poseStage?.detail ||
          (poseCalls.length
            ? `${poseSummary.completed}/${poseCalls.length} generated, ${poseSummary.running} running, ${poseSummary.failed} failed`
            : `${Number(posePlan.pose_count || 0)} planned pose images`)
      ),
      images: poseImages,
      rows: poseCalls.slice(0, 8).map((call) => ({
        label: [call.accessory_id, call.pose_id].map(shortId).filter(Boolean).join(" / ") || shortId(call.call_id) || "pose call",
        value: String(call.error || call.status || "-"),
        tone: String(call.status || "")
      }))
    },
    {
      key: "sample_generation",
      label: "Sample Generation",
      status: String(sampleStage?.status || task.status || "pending"),
      detail: String(
        sampleStage?.detail ||
          (sampleDataset
            ? `${sampleDataset.sample_count || sampleDataset.samples?.length || 0} samples in ${sampleDataset.display_name || sampleDataset.id}`
            : task.samples_task_id
              ? `Sample job ${task.samples_task_id}`
              : "Waiting for generated pose images and sample parameters")
      ),
      images: sampleImages,
      rows: [
        sampleState.loading ? { label: "Thumbnails", value: "Loading generated sample images", tone: "running" } : null,
        sampleLoadError ? { label: "Thumbnails", value: sampleLoadError, tone: "failed" } : null,
        sampleState.requested && !sampleState.loading && !sampleLoadError && sampleDataset && !sampleImages.length
          ? { label: "Thumbnails", value: "No generated sample thumbnails returned", tone: "pending" }
          : null,
        task.samples_task_id ? { label: "Job", value: String(task.samples_task_id), tone: sampleSummary.failed ? "failed" : sampleSummary.running ? "running" : "completed" } : null,
        task.dataset_id ? { label: "Dataset", value: String(task.dataset_id) } : null,
        sampleDataset?.sample_count ? { label: "Samples", value: String(sampleDataset.sample_count) } : null,
        sampleCalls[0]?.error ? { label: "Error", value: String(sampleCalls[0].error), tone: "failed" } : null
      ].filter((item): item is { label: string; value: string; tone?: string } => Boolean(item))
    },
    {
      key: "model_training",
      label: "Model Training",
      status: String(trainingStage?.status || (task.training_task_id ? task.status || "running" : "pending")),
      detail: String(trainingStage?.detail || (task.training_task_id ? `Training job ${task.training_task_id}` : "Waiting for sample approval")),
      images: [],
      progressBars: buildTransferProgressBars(task),
      rows: [
        task.training_task_id ? { label: "Job", value: String(task.training_task_id), tone: trainingSummary.failed ? "failed" : trainingSummary.running ? "running" : "completed" } : null,
        task.current_epoch !== undefined || task.total_epochs ? { label: "Epoch", value: `${task.current_epoch || 0}/${task.total_epochs || "?"}` } : null,
        task.ai_model_id ? { label: "Model", value: String(task.ai_model_id) } : null
      ].filter((item): item is { label: string; value: string; tone?: string } => Boolean(item))
    }
  ];
}

function buildAgentConversation(task: PipelineTask): AgentConversationEntry[] {
  const agentMcp = asRecord(task.agent_mcp);
  const conversation = asRecords(agentMcp.conversation);
  if (conversation.length) {
    const poseImages = asRecords(agentMcp.tool_calls)
      .filter((call) => call.tool === "generate_accessory_pose_image" && call.output_url)
      .map((call) => ({
        url: String(call.output_url || ""),
        label: [call.accessory_id, call.pose_id].map(shortId).filter(Boolean).join(" / ") || "pose"
      }))
      .slice(0, 6);
    const imageActions = new Set(["replan", "retry", "continue_existing_assets", "advance"]);
    let lastImageAgentIndex = -1;
    conversation.forEach((entry, index) => {
      if (entry.role === "agent" && imageActions.has(String(entry.action || ""))) lastImageAgentIndex = index;
    });
    return conversation.map((entry, index) => {
      const role = entry.role === "user" ? "user" : entry.role === "system" ? "system" : "agent";
      const source = String(entry.source || "");
      const label =
        role === "user" ? "你" : role === "system" ? "系统" : source === "rules" ? "Agent · 规则兜底" : "Agent";
      return {
        key: `conv:${entry.id || index}`,
        role,
        label,
        message: String(entry.message || ""),
        action: String(entry.action || "") || undefined,
        reason: String(entry.reason || "") || undefined,
        targetStage: String(entry.target_stage || "") || undefined,
        source: source || undefined,
        needsUser: Boolean(entry.needs_user),
        agentError: String(entry.agent_error || "") || undefined,
        images: role === "agent" && index === lastImageAgentIndex && poseImages.length ? poseImages : undefined,
        createdAt: Number(entry.created_at || 0) || undefined
      };
    });
  }
  const entries: AgentConversationEntry[] = [];
  asRecords(agentMcp.stages).forEach((stage, index) => {
    const detail = String(stage.detail || stage.status || "").trim();
    if (!detail) return;
    entries.push({
      key: `stage:${stage.key || index}`,
      role: "agent",
      label: String(stage.label || stage.key || "Agent"),
      message: detail,
      createdAt: Number(stage.updated_at || agentMcp.updated_at || 0) || undefined
    });
  });
  const pause = asRecord(agentMcp.pause);
  if (pause.reason) {
    entries.push({
      key: "pause",
      role: "system",
      label: "Needs action",
      message: String(pause.reason),
      createdAt: Number(pause.created_at || agentMcp.updated_at || 0) || undefined
    });
  }
  asRecords(agentMcp.feedback).forEach((item, index) => {
    entries.push({
      key: `feedback:${index}`,
      role: "user",
      label: String(item.decision || item.action || "User request"),
      message: String(item.message || item.decision || item.action || ""),
      createdAt: Number(item.created_at || 0) || undefined
    });
  });
  if (task.agent_reason) {
    entries.unshift({
      key: "recommendation",
      role: "agent",
      label: task.agent_source === "agent" ? "Agent recommendation" : "Rule recommendation",
      message: task.agent_reason
    });
  }
  return entries.filter((entry) => entry.message.trim()).slice(-10);
}

function persistedAgentPosePlans(agentMcp: Record<string, unknown>): AgentPosePlan[] {
  const posePlan = asRecord(agentMcp.pose_plan);
  return asRecords(posePlan.accessories).map((plan) => ({
    accessory_id: String(plan.accessory_id || ""),
    accessory_name: String(plan.accessory_name || plan.accessory_id || "accessory"),
    object_kind: ["cube", "bottle", "thin_object", "generic_object"].includes(String(plan.object_kind))
      ? (String(plan.object_kind) as AgentPosePlan["object_kind"])
      : "generic_object",
    plan_source: "react_preview_rules",
    image_contract: String(plan.image_contract || "one_accessory_per_image") as "one_accessory_per_image",
    poses: asRecords(plan.poses).map((pose) => {
      const request = asRecord(pose.request);
      return {
        pose_id: String(pose.pose_id || ""),
        label: String(pose.label || pose.pose_id || "pose"),
        stable_contact: String(pose.stable_contact || ""),
        gravity_basis: String(pose.gravity_basis || ""),
        conveyor_view: String(pose.conveyor_view || ""),
        request: {
          subject_count: 1,
          target_paper: request.target_paper === true ? false : false,
          grid_layout: request.grid_layout === true ? false : false,
          background: "conveyor"
        }
      };
    })
  }));
}

function persistedAgentStages(agentMcp: Record<string, unknown>): AgentMcpStage[] {
  return asRecords(agentMcp.stages).map((stage) => ({
    key: String(stage.key || "agent_pose_planning") as AgentMcpStageKey,
    label: String(stage.label || stage.key || "Agent/MCP"),
    status: String(stage.status || "pending") as AgentMcpStage["status"],
    detail: String(stage.detail || `${stage.progress ?? 0}%`)
  }));
}

function persistedToolContracts(agentMcp: Record<string, unknown>): AgentMcpPreview["toolContracts"] {
  const calls = asRecords(agentMcp.tool_calls);
  const grouped = new Map<string, Array<Record<string, unknown>>>();
  calls.forEach((call) => {
    const tool = String(call.tool || "tool");
    grouped.set(tool, [...(grouped.get(tool) || []), call]);
  });
  return Array.from(grouped.entries()).map(([tool, toolCalls]) => {
    const statuses = Array.from(new Set(toolCalls.map((call) => String(call.status || "pending"))));
    const firstError = String(toolCalls.find((call) => call.error)?.error || "");
    return {
      tool,
      status: statuses.join(", "),
      detail: firstError || `${toolCalls.length} call${toolCalls.length === 1 ? "" : "s"} logged`
    };
  });
}

function buildAgentMcpPreview(task: PipelineTask, rows: PipelineTaskAccessory[]): AgentMcpPreview | null {
  if (!pipelineTaskUsesTraining(task)) return null;
  const agentMcp = asRecord(task.agent_mcp);
  const persistedPlans = persistedAgentPosePlans(agentMcp);
  const plans = persistedPlans.length ? persistedPlans : rows.map(inferAgentPosePlan);
  const poseCount = plans.reduce((total, plan) => total + plan.poses.length, 0);
  const persistedStages = persistedAgentStages(agentMcp);
  const pause = asRecord(agentMcp.pause);
  const sampleRunning = task.stage === "samples" && task.status === "running";
  const sampleDone = task.stage === "training" || task.stage === "library" || (task.stage === "samples" && task.status === "completed");
  const trainRunning = task.stage === "training" && task.status === "running";
  const trainDone = task.stage === "library" || (task.stage === "training" && task.status === "completed");
  return {
    plans,
    stages: persistedStages.length ? persistedStages : [
      {
        key: "agent_pose_planning",
        label: "Agent 姿态规划",
        status: rows.length ? "completed" : "pending",
        detail: rows.length ? `${rows.length} 个配件 / ${poseCount} 个姿态` : "等待配件"
      },
      {
        key: "pose_image_generation",
        label: "MCP 姿态图",
        status: "pending",
        detail: "等待后端生成持久规划"
      },
      {
        key: "sample_generation",
        label: "样本生成",
        status: sampleDone ? "completed" : sampleRunning ? "running" : "pending",
        detail: sampleDone ? "样本任务完成" : sampleRunning ? "生成中" : "等待姿态图或用户决策"
      },
      {
        key: "model_training",
        label: "模型训练",
        status: trainDone ? "completed" : trainRunning ? "running" : "pending",
        detail: trainDone ? "模型可入库" : trainRunning ? "训练中" : "等待样本质量门"
      }
    ],
    toolContracts: persistedToolContracts(agentMcp).length ? persistedToolContracts(agentMcp) : [
      {
        tool: "generate_accessory_pose_image",
        status: "pending",
        detail: "请求为单配件单姿态图；不使用 target paper 或 9 宫格。"
      },
      {
        tool: "generate_training_samples",
        status: sampleDone ? "completed" : sampleRunning ? "running" : "pending",
        detail: "等姿态图就绪或用户确认沿用现有素材后进入。"
      },
      {
        tool: "start_model_training",
        status: trainDone ? "completed" : trainRunning ? "running" : "pending",
        detail: "样本质量门通过后启动 YOLO / YOLO+OCR。"
      }
    ],
    pauseReason: String(pause.reason || ""),
    suggestedActions: Array.isArray(pause.suggested_actions) ? pause.suggested_actions.map(String) : [],
    activeStage: String(agentMcp.active_stage || "")
  };
}

function assignedAccessoryIds(tasks: PipelineTask[]) {
  const result = new Set<string>();
  tasks.forEach((task) => {
    if (task.stage === "library") return;
    (task.accessory_ids || []).forEach((itemId) => result.add(String(itemId)));
  });
  return result;
}

function canDragTask(task: PipelineTask) {
  if (task.stage === "draft") return task.status !== "running";
  if (task.stage === "samples" || task.stage === "training") return task.status === "completed";
  return false;
}

function numberParam(value: unknown, fallback: number) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function paramsSummary(task: PipelineTask) {
  const method = pipelineTaskMethod(task);
  if (!methodMeta(method).usesTraining) {
    return method === "ai" ? "AI 检测工作台" : "Locate Anything 工作台";
  }
  const params = task.params || {};
  const parts = [];
  if (params.sample_count) parts.push(`${params.sample_count} 样本`);
  if (params.epochs) parts.push(`${params.epochs} epoch`);
  if (params.image_size) parts.push(`${params.image_size}px`);
  if (params.train_mode) parts.push(params.train_mode === "yolo_ocr" ? "YOLO+OCR" : "YOLO");
  return parts.length ? parts.join(" · ") : "待推荐参数";
}

function advanceLabel(task: PipelineTask) {
  if (task.advancing) return "推进中…";
  const method = pipelineTaskMethod(task);
  const usesTraining = pipelineTaskUsesTraining(task);
  if (task.stage === "draft") {
    if (!usesTraining) return method === "ai" ? "创建 AI 任务" : "启用定位任务";
    return "生成样本";
  }
  if (task.stage === "samples") return "开始训练";
  return "入库使用";
}

function canAdvanceTask(task: PipelineTask) {
  if (task.advancing) return false;
  if (task.stage === "draft") return task.status !== "running";
  return task.status === "completed";
}

function progressWidth(value: unknown) {
  const progress = Number(value);
  if (!Number.isFinite(progress)) return 0;
  return Math.max(2, Math.min(100, progress));
}

const CARD_DRAG_BLOCK_SELECTOR = [
  "button",
  "a",
  "input",
  "select",
  "textarea",
  "label",
  "summary",
  "[role='button']",
  "[role='menu']",
  "[role='menuitem']",
  "[data-no-card-drag='true']"
].join(",");

function stopCardDragFromInteractive(event: PointerEvent<HTMLElement>) {
  const target = event.target instanceof HTMLElement ? event.target : null;
  const blocker = target?.closest(CARD_DRAG_BLOCK_SELECTOR);
  if (blocker && blocker !== event.currentTarget) {
    event.stopPropagation();
  }
}

function MethodPill({ method, ready }: { method: PipelineMethod; ready?: boolean }) {
  const meta = methodMeta(method);
  return <span className={`pipeline-type-pill ${ready ? "ready" : ""}`}>{ready ? "AI 就绪" : meta.label}</span>;
}

function DroppableZone({
  id,
  kind,
  stage,
  disabled,
  className,
  children
}: {
  id: string;
  kind: DropKind;
  stage?: PipelineStage;
  disabled?: boolean;
  className: string;
  children: ReactNode;
}) {
  const { isOver, setNodeRef } = useDroppable({
    id,
    disabled,
    data: { type: kind, stage }
  });
  return (
    <div ref={setNodeRef} className={`${className} ${isOver ? "drop-target" : ""}`}>
      {children}
    </div>
  );
}

function AccessoryCard({
  item,
  onRemove
}: {
  item: AccessorySummary;
  onRemove: (accessoryId: string) => void;
}) {
  const ready = accessoryReady(item);
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `accessory:${item.id}`,
    disabled: !ready,
    data: { type: "accessory", id: item.id, label: item.name || item.id }
  });
  const dragProps = ready ? { ...attributes, ...listeners } : {};
  return (
    <article
      ref={setNodeRef}
      className={`pipeline-card pipeline-accessory-card ${ready ? "ready" : "pending"} ${isDragging ? "dragging" : ""}`}
      style={{ opacity: isDragging ? 0.45 : undefined }}
      onPointerDownCapture={ready ? stopCardDragFromInteractive : undefined}
      {...dragProps}
    >
      <div className="pipeline-card-head">
        <strong>{item.name || item.id}</strong>
        <span className={`pipeline-state-dot ${ready ? "ready" : "pending"}`} title={ready ? "可使用" : "等待中"} />
      </div>
      <p className="pipeline-card-meta">
        {(item.source_file_count ?? item.source_files?.length ?? 0)} 份素材 · {ready ? "已上传" : "等待中"}
      </p>
      <p className="pipeline-card-meta">{recordAuditText(item, { includeUpdated: true })}</p>
      <div className="pipeline-card-actions">
        {ready ? (
          <span className="pipeline-drag-hint">
            <GripVertical size={14} aria-hidden="true" />
            拖动卡片
          </span>
        ) : null}
        <button className="secondary compact-action danger" type="button" onClick={() => onRemove(item.id)}>
          <Trash2 size={14} aria-hidden="true" />
          移出
        </button>
      </div>
    </article>
  );
}

function CandidateCard({ candidate }: { candidate: PipelineCandidate }) {
  const failed = candidate.status === "failed";
  const ready = candidate.status === "ready";
  const running = candidate.status === "running";
  const dotClass = failed ? "failed" : ready ? "ready" : "pending";
  const showProgress = candidate.progress !== undefined && (ready || failed || running || Number(candidate.progress) > 0);
  return (
    <article className={`pipeline-card pipeline-accessory-card ${ready ? "ready candidate-ready" : "pending"} ${failed ? "failed" : ""}`}>
      <div className="pipeline-card-head">
        <strong>{candidate.name || "新配件"}</strong>
        <span className={`pipeline-state-dot ${dotClass}`} title={candidate.status_text || "待确认"} />
      </div>
      <p className="pipeline-card-meta">{candidate.status_text || pipelineStatusLabel(candidate.status)}</p>
      <p className="pipeline-card-meta">{recordAuditText(candidate, { includeUpdated: true })}</p>
      {showProgress ? (
        <div className="pipeline-progress" aria-label="候选配件进度">
          <div className="pipeline-progress-bar" style={{ width: `${progressWidth(candidate.progress)}%` }} />
        </div>
      ) : null}
    </article>
  );
}

function AgentMcpPanel({
  preview,
  compact = false,
  busy = false,
  onDecision
}: {
  preview: AgentMcpPreview | null;
  compact?: boolean;
  busy?: boolean;
  onDecision?: (decision: AgentMcpDecision) => void;
}) {
  if (!preview) return null;
  const thinkingStageKeys = new Set(
    preview.stages
      .filter((stage) => stage.status === "running" || (preview.activeStage === stage.key && !preview.pauseReason && !["completed", "skipped", "needs_user_action", "failed"].includes(stage.status)))
      .map((stage) => stage.key)
  );
  const controlsDisabled = busy || thinkingStageKeys.size > 0;
  return (
    <section className={`pipeline-agent-mcp ${compact ? "compact" : ""}`}>
      <div className="pipeline-agent-mcp-head">
        <span>
          <Bot size={14} aria-hidden="true" />
          Agent/MCP
        </span>
        <strong>{preview.plans.reduce((total, plan) => total + plan.poses.length, 0)} pose images</strong>
      </div>
      <div className="pipeline-agent-stage-grid">
        {preview.stages.map((stage) => {
          const thinking = thinkingStageKeys.has(stage.key);
          return (
            <div className={`pipeline-agent-stage status-${stage.status} ${thinking ? "thinking" : ""}`} key={stage.key}>
              <strong>{stage.label}</strong>
              {thinking ? (
                <span className="pipeline-agent-thinking">
                  <Loader2 className="spin" size={12} aria-hidden="true" />
                  thinking
                </span>
              ) : null}
              <span>{stage.detail}</span>
            </div>
          );
        })}
      </div>
      {preview.pauseReason ? (
        <div className="pipeline-agent-pause">
          <CircleAlert size={15} aria-hidden="true" />
          <span>{preview.pauseReason}</span>
        </div>
      ) : null}
      {!compact ? (
        <>
          <div className="pipeline-tool-contracts">
            {preview.toolContracts.map((tool) => (
              <div className="pipeline-tool-contract" key={tool.tool}>
                <code>{tool.tool}</code>
                <span>{tool.status}</span>
                <p>{tool.detail}</p>
              </div>
            ))}
          </div>
          <div className="pipeline-pose-plan-list">
            {preview.plans.map((plan) => (
              <div className="pipeline-pose-plan" key={plan.accessory_id}>
                <strong>
                  {plan.accessory_name} · {plan.object_kind}
                </strong>
                <span>{plan.image_contract}</span>
                {plan.poses.map((pose) => (
                  <p key={pose.pose_id}>
                    <code>{pose.pose_id}</code> {pose.label} · {pose.stable_contact} · {pose.gravity_basis}
                  </p>
                ))}
              </div>
            ))}
          </div>
        </>
      ) : null}
      {onDecision ? (
        <div className="pipeline-agent-actions">
          {preview.activeStage === "model_training" ? (
            <button className="secondary compact-action" type="button" disabled={controlsDisabled} onClick={() => onDecision("continue_training")}>
              {busy ? <Loader2 className="spin" size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
              继续训练
            </button>
          ) : null}
          <button className="secondary compact-action" type="button" disabled={controlsDisabled} onClick={() => onDecision("replan_requested")}>
            <RotateCcw size={14} aria-hidden="true" />
            重规划
          </button>
          <button className="secondary compact-action danger" type="button" disabled={busy} onClick={() => onDecision("cancelled")}>
            <X size={14} aria-hidden="true" />
            取消
          </button>
        </div>
      ) : null}
    </section>
  );
}

function PipelineTaskCard({
  task,
  inFlowAccessories,
  libraryAccessories,
  onAdvance,
  onDelete,
  onDetail,
  onParams,
  onToggleAuto,
  onAgentDecision,
  busyKey
}: {
  task: PipelineTask;
  inFlowAccessories: AccessorySummary[];
  libraryAccessories: AccessorySummary[];
  onAdvance: (task: PipelineTask) => void;
  onDelete: (task: PipelineTask) => void;
  onDetail: (task: PipelineTask) => void;
  onParams: (task: PipelineTask) => void;
  onToggleAuto: (task: PipelineTask, checked: boolean) => void;
  onAgentDecision: (task: PipelineTask, decision: AgentMcpDecision) => void;
  busyKey: string;
}) {
  const method = pipelineTaskMethod(task);
  const rows = taskAccessoryRows(task, inFlowAccessories, libraryAccessories);
  const agentPreview = buildAgentMcpPreview(task, rows);
  const accessorySummary = rows.map((item) => `${item.name || item.id}x${taskAccessoryCount(task, item.id)}`).join("、");
  const draggable = canDragTask(task);
  const { attributes, listeners, setNodeRef: setDragRef, isDragging } = useDraggable({
    id: `task:${task.id}`,
    disabled: !draggable,
    data: { type: "task", id: task.id, label: task.name || task.id }
  });
  const dragProps = draggable ? { ...attributes, ...listeners } : {};
  const { isOver, setNodeRef: setDropRef } = useDroppable({
    id: `task-drop:${task.id}`,
    disabled: task.stage !== "draft",
    data: { type: "task", taskId: task.id }
  });
  const setRefs = useCallback(
    (node: HTMLElement | null) => {
      setDragRef(node);
      setDropRef(node);
    },
    [setDragRef, setDropRef]
  );
  const epochInfo = task.stage === "training" && task.total_epochs ? ` · Epoch ${task.current_epoch || 0}/${task.total_epochs}` : "";
  const showProgress = task.stage === "samples" || task.stage === "training" || Boolean(task.advancing);
  const aiReady = method === "ai" && Boolean((task.accessory_ids || []).length);

  return (
    <article
      ref={setRefs}
      className={`pipeline-card pipeline-task-card status-${task.status || "ready"} ${isDragging ? "dragging" : ""} ${isOver ? "drop-target" : ""}`}
      style={{ opacity: isDragging ? 0.45 : undefined }}
      onPointerDownCapture={draggable ? stopCardDragFromInteractive : undefined}
      {...dragProps}
    >
      <div className="pipeline-card-head">
        <strong>{task.name || "流水线任务"}</strong>
        <div className="pipeline-card-badges">
          <MethodPill method={method} ready={aiReady} />
          {task.status === "needs_user_action" ? (
            <span className="pill warn pipeline-needs-user" title={agentPreview?.pauseReason || task.last_error || ""}>
              <CircleAlert size={12} aria-hidden="true" />
              需要你确认
            </span>
          ) : (
            <span className={`pill ${toneForStatus(task.status)}`}>{pipelineStatusLabel(task.status)}</span>
          )}
        </div>
      </div>
      <p className="pipeline-card-meta">
        {methodMeta(method).label} · {accessorySummary || task.accessory_names?.join("、") || "未选择配件"}
        {epochInfo}
      </p>
      <p className="pipeline-card-meta">{recordAuditText(task, { includeUpdated: true })}</p>
      {showProgress ? (
        <div className="pipeline-progress" aria-label="任务进度">
          <div className="pipeline-progress-bar" style={{ width: `${progressWidth(task.progress)}%` }} />
        </div>
      ) : null}
      {task.advancing && task.job_note ? <p className="pipeline-card-meta">{task.job_note}</p> : null}
      {task.last_error ? <p className="pipeline-card-error">{task.last_error}</p> : null}
      <AgentMcpPanel preview={agentPreview} compact busy={busyKey === `agent:${task.id}`} onDecision={(decision) => onAgentDecision(task, decision)} />
      {pipelineTaskUsesTraining(task) ? (
        <button className="pipeline-params-chip" type="button" title={task.agent_reason || ""} onClick={() => onParams(task)}>
          <SlidersHorizontal size={13} aria-hidden="true" />
          {paramsSummary(task)}
        </button>
      ) : (
        <span className="pipeline-params-chip disabled">{paramsSummary(task)}</span>
      )}
      <div className="pipeline-card-actions">
        <button className="secondary compact-action" type="button" onClick={() => onDetail(task)}>
          <Eye size={14} aria-hidden="true" />
          详情
        </button>
        {canAdvanceTask(task) ? (
          <button className="secondary compact-action" type="button" onClick={() => onAdvance(task)}>
            <ChevronRight size={14} aria-hidden="true" />
            {advanceLabel(task)}
          </button>
        ) : task.advancing ? (
          <button className="secondary compact-action" type="button" disabled>
            <Loader2 size={14} aria-hidden="true" className="spin" />
            推进中…
          </button>
        ) : null}
        <label className="pipeline-auto-mini" title="阶段完成后自动进入下一步">
          <input
            type="checkbox"
            checked={Boolean(task.auto_advance)}
            onChange={(event) => onToggleAuto(task, event.currentTarget.checked)}
          />
          自动
        </label>
        {draggable ? (
          <span className="pipeline-drag-hint">
            <GripVertical size={14} aria-hidden="true" />
            拖动卡片
          </span>
        ) : null}
        <button className="secondary compact-action danger" type="button" onClick={() => onDelete(task)}>
          <Trash2 size={14} aria-hidden="true" />
          删除
        </button>
      </div>
    </article>
  );
}

function CreateTaskModal({
  onClose,
  onCreate
}: {
  onClose: () => void;
  onCreate: (payload: PipelineTaskPayload) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [method, setMethod] = useState<PipelineMethod>("yolo_ocr");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      await onCreate({ name: name.trim(), detection_method: method });
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal-panel pipeline-task-modal" role="dialog" aria-modal="true" aria-label="新建训练任务" onSubmit={submit}>
        <header className="modal-head">
          <div>
            <h3>新建训练任务</h3>
            <span>创建后可拖入配件并调整数量。</span>
          </div>
          <button className="icon-only" type="button" aria-label="关闭" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="modal-body pipeline-modal-body">
          <label className="field">
            检测方法
            <select value={method} onChange={(event) => setMethod(event.currentTarget.value as PipelineMethod)}>
              {PIPELINE_METHODS.map((item) => (
                <option value={item.value} key={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            任务名称
            <input value={name} placeholder="例如：说明书齐套训练" onChange={(event) => setName(event.currentTarget.value)} />
          </label>
          <div className="pipeline-task-detail-entry">
            <span>详情</span>
            <strong>任务卡片会显示已选配件、执行进度和训练参数。</strong>
          </div>
        </div>
        <footer className="modal-footer">
          <button className="secondary compact-action" type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary compact-action" type="submit" disabled={busy}>
            <Plus size={16} aria-hidden="true" />
            创建任务
          </button>
        </footer>
      </form>
    </div>
  );
}

function TaskDetailModal({
  task,
  inFlowAccessories,
  libraryAccessories,
  sampleDataset,
  sampleDatasetError,
  sampleDatasetLoading,
  sampleDatasetRequested,
  onClose,
  onCountChange,
  onAgentDecision,
  onAgentRequest,
  busyKey
}: {
  task: PipelineTask;
  inFlowAccessories: AccessorySummary[];
  libraryAccessories: AccessorySummary[];
  sampleDataset: TrainingDataset | null;
  sampleDatasetError: unknown;
  sampleDatasetLoading: boolean;
  sampleDatasetRequested: boolean;
  onClose: () => void;
  onCountChange: (task: PipelineTask, accessoryId: string, delta: number) => void;
  onAgentDecision: (task: PipelineTask, decision: AgentMcpDecision) => void;
  onAgentRequest: (task: PipelineTask, message: string) => Promise<void>;
  busyKey: string;
}) {
  const rows = taskAccessoryRows(task, inFlowAccessories, libraryAccessories);
  const canEditCounts = task.stage === "draft";
  const method = pipelineTaskMethod(task);
  const agentPreview = buildAgentMcpPreview(task, rows);
  const operationOutputs = buildPipelineOperationOutputs(task, sampleDataset, {
    requested: sampleDatasetRequested,
    loading: sampleDatasetLoading,
    error: sampleDatasetError
  });
  const conversation = buildAgentConversation(task);
  const [agentRequest, setAgentRequest] = useState("");
  const agentBusy = busyKey === `agent:${task.id}`;

  async function submitAgentRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = agentRequest.trim();
    if (!message) return;
    await onAgentRequest(task, message);
    setAgentRequest("");
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel pipeline-task-detail-modal" role="dialog" aria-modal="true" aria-label="任务详情">
        <header className="modal-head">
          <div>
            <h3>{task.name || "任务详情"}</h3>
            <span>{recordAuditText(task, { includeUpdated: true })}</span>
          </div>
          <button className="icon-only" type="button" aria-label="关闭" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="modal-body pipeline-modal-body">
          <div className="pipeline-task-detail-meta">
            <span>{methodMeta(method).label}</span>
            <strong className={method === "ai" && rows.length ? "ready" : ""}>{method === "ai" && rows.length ? "AI 就绪" : pipelineStatusLabel(task.status)}</strong>
            <span>{stageLabel(task.stage)}</span>
          </div>
          <AgentMcpPanel preview={agentPreview} busy={agentBusy} onDecision={(decision) => onAgentDecision(task, decision)} />
          <section className="pipeline-output-panel">
            <div className="section-title">
              <h3>阶段输出</h3>
            </div>
            <div className="pipeline-output-list">
              {operationOutputs.map((output) => (
                <article className={`pipeline-output-card status-${output.status} output-${output.key}`} key={output.key}>
                  <header>
                    <strong>{output.label}</strong>
                    <span>{pipelineStatusLabel(output.status)}</span>
                  </header>
                  <p>{output.detail}</p>
                  {output.images.length ? (
                    <div className={`pipeline-output-images count-${Math.min(output.images.length, 4)}`}>
                      {output.images.map((image) => (
                        <PipelineThumb key={`${output.key}:${image.url}`} url={image.url} label={image.label} eager />
                      ))}
                    </div>
                  ) : null}
                  {output.progressBars && output.progressBars.length ? (
                    <div className="pipeline-output-progress">
                      {output.progressBars.map((bar) => (
                        <div className={`pipeline-progress-item tone-${bar.tone || "running"}`} key={`${output.key}:${bar.label}`}>
                          <div className="pipeline-progress-head">
                            <span>{bar.label}</span>
                            <strong>{bar.text}</strong>
                          </div>
                          <div className={`pipeline-progress-track${bar.indeterminate ? " indeterminate" : ""}`}>
                            <div
                              className="pipeline-progress-fill"
                              style={{ width: bar.indeterminate ? undefined : `${Math.min(100, Math.max(0, Math.round((bar.value / (bar.max || 1)) * 100)))}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {output.rows.length ? (
                    <div className="pipeline-output-rows">
                      {output.rows.map((row) => (
                        <div className={`pipeline-output-row ${row.tone ? `tone-${row.tone}` : ""}`} key={`${output.key}:${row.label}`}>
                          <span>{row.label}</span>
                          <strong>{row.value}</strong>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
          {pipelineTaskUsesTraining(task) ? (
          <section className="pipeline-agent-chat-panel">
            <div className="section-title">
              <h3>Agent 对话</h3>
              {agentBusy ? (
                <span className="pipeline-agent-thinking">
                  <Loader2 className="spin" size={13} aria-hidden="true" />
                  Agent 处理中
                </span>
              ) : null}
            </div>
            <div className="pipeline-agent-thread">
              {conversation.length ? (
                conversation.map((entry) => (
                  <div
                    className={`pipeline-agent-message role-${entry.role}${entry.needsUser ? " needs-user" : ""}`}
                    key={entry.key}
                  >
                    <span className="pipeline-agent-message-head">
                      {entry.label}
                      {entry.action ? <em className="pipeline-agent-action">{agentActionLabel(entry.action)}</em> : null}
                      {entry.targetStage ? <em className="pipeline-agent-action">→ {stageLabel(entry.targetStage)}</em> : null}
                    </span>
                    <p>{entry.message}</p>
                    {entry.reason && entry.reason !== entry.message ? (
                      <small className="pipeline-agent-reason">理由：{entry.reason}</small>
                    ) : null}
                    {entry.agentError ? (
                      <small className="pipeline-agent-reason tone-failed">Agent 调用失败，已回退规则：{entry.agentError}</small>
                    ) : null}
                    {entry.images && entry.images.length ? (
                      <div className="pipeline-agent-message-images">
                        {entry.images.map((image) => (
                          <PipelineThumb key={`${entry.key}:${image.url}`} url={image.url} label={image.label} />
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))
              ) : (
                <div className="lane-empty">和 Agent 说说你的需求，它会自动前往对应阶段处理并继续推进。</div>
              )}
            </div>
            <form className="pipeline-agent-request" onSubmit={submitAgentRequest}>
              <label>
                和 Agent 对话
                <textarea
                  value={agentRequest}
                  onChange={(event) => setAgentRequest(event.currentTarget.value)}
                  placeholder="例如：每个配件只保留俯视角；或：样本太少，多生成一些再训练。"
                />
              </label>
              <button className="secondary compact-action" type="submit" disabled={agentBusy || !agentRequest.trim()}>
                {agentBusy ? <Loader2 className="spin" size={14} aria-hidden="true" /> : <Send size={14} aria-hidden="true" />}
                发送
              </button>
            </form>
          </section>
          ) : null}
          <div className="pipeline-task-accessory-list">
            {rows.length ? (
              rows.map((item) => {
                const count = taskAccessoryCount(task, item.id);
                return (
                  <div className="pipeline-task-accessory-row" key={item.id}>
                    <div>
                      <strong>{item.name || item.id}</strong>
                      <span>{materialLabel(item.material_type)}</span>
                    </div>
                    <div className="pipeline-quantity-control">
                      <button
                        type="button"
                        disabled={!canEditCounts || count <= 1}
                        aria-label="减少数量"
                        onClick={() => onCountChange(task, item.id, -1)}
                      >
                        <Minus size={14} aria-hidden="true" />
                      </button>
                      <strong>{count}</strong>
                      <button
                        type="button"
                        disabled={!canEditCounts || count >= 99}
                        aria-label="增加数量"
                        onClick={() => onCountChange(task, item.id, 1)}
                      >
                        <Plus size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="lane-empty">还没有选择配件。把左侧配件拖入这个任务后，可在这里调整数量。</div>
            )}
          </div>
        </div>
        <footer className="modal-footer">
          <button className="primary compact-action" type="button" onClick={onClose}>
            完成
          </button>
        </footer>
      </section>
    </div>
  );
}

function ParamsModal({
  target,
  task,
  onClose,
  onSaved
}: {
  target: ParamsTarget;
  task: PipelineTask;
  onClose: () => void;
  onSaved: (advanced: boolean) => Promise<void>;
}) {
  const { notify } = useToast();
  const [sampleCount, setSampleCount] = useState("400");
  const [epochs, setEpochs] = useState("40");
  const [imageSize, setImageSize] = useState("640");
  const [trainMode, setTrainMode] = useState<PipelineMethod>("yolo_ocr");
  const [reason, setReason] = useState("正在获取推荐参数...");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const params = task.params || {};
    setSampleCount(String(numberParam(params.sample_count, 400)));
    setEpochs(String(numberParam(params.epochs, 40)));
    setImageSize(String(numberParam(params.image_size, 640)));
    setTrainMode(normalizePipelineMethod(String(params.train_mode || pipelineTaskMethod(task))));
    setReason(task.agent_reason ? `${task.agent_source === "agent" ? "Agent 推荐" : "规则推荐"}：${task.agent_reason}` : "可直接接受或修改后保存。");

    const needsRecommendation = target.stageKey === "samples" ? !params.sample_count : !params.epochs;
    // Prefer params the backend pre-generated when the previous step finished, so
    // the next step is ready without an extra round-trip.
    const pregen =
      needsRecommendation && task.recommended_params?.stage === target.stageKey && task.recommended_params?.params
        ? task.recommended_params
        : null;
    if (pregen) {
      const merged = { ...(pregen.params || {}), ...params };
      setSampleCount(String(numberParam(merged.sample_count, 400)));
      setEpochs(String(numberParam(merged.epochs, 40)));
      setImageSize(String(numberParam(merged.image_size, 640)));
      setTrainMode(normalizePipelineMethod(String(merged.train_mode || pipelineTaskMethod(task))));
      const sourceLabel = pregen.source === "agent" ? "Agent 推荐" : "规则推荐";
      setReason(pregen.reason ? `${sourceLabel}（已预生成）：${pregen.reason}` : `${sourceLabel}（已预生成）：可直接接受或修改后保存。`);
      return () => {
        cancelled = true;
      };
    }
    if (needsRecommendation) {
      setLoading(true);
      setReason("正在获取推荐参数...");
      getAgentRecommendation({
        stage: target.stageKey,
        accessory_ids: task.accessory_ids || [],
        sample_count: params.sample_count ? Number(params.sample_count) : null
      })
        .then((result) => {
          if (cancelled) return;
          const merged = { ...(result.params || {}), ...params };
          setSampleCount(String(numberParam(merged.sample_count, 400)));
          setEpochs(String(numberParam(merged.epochs, 40)));
          setImageSize(String(numberParam(merged.image_size, 640)));
          setTrainMode(normalizePipelineMethod(String(merged.train_mode || pipelineTaskMethod(task))));
          const sourceLabel = result.source === "agent" ? "Agent 推荐" : "规则推荐";
          setReason(result.reason ? `${sourceLabel}：${result.reason}` : `${sourceLabel}：可直接接受或修改后保存。`);
        })
        .catch((error) => {
          if (!cancelled) setReason(`推荐失败，使用默认值：${error instanceof Error ? error.message : String(error)}`);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [target.stageKey, task]);

  function payloadForStage() {
    if (target.stageKey === "samples") {
      return {
        sample_count: Math.max(50, Math.min(20000, Number(sampleCount) || 400)),
        train_mode: trainMode
      };
    }
    return {
      epochs: Math.max(1, Math.min(500, Number(epochs) || 40)),
      image_size: Math.max(320, Math.min(1280, Number(imageSize) || 640)),
      train_mode: trainMode
    };
  }

  async function save(advance: boolean) {
    setBusy(true);
    try {
      await updatePipelineTask(target.taskId, { params: payloadForStage() });
      if (advance || target.advanceAfter) {
        await advancePipelineTask(target.taskId);
        notify({ title: "参数已确认，任务开始执行", tone: "success" });
      } else {
        notify({ title: "参数已保存", tone: "success" });
      }
      await onSaved(advance || target.advanceAfter);
      onClose();
    } catch (error) {
      notify({ title: "保存参数失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel pipeline-params-modal" role="dialog" aria-modal="true" aria-label="推荐参数">
        <header className="modal-head">
          <div>
            <h3>{target.stageKey === "samples" ? `生成样本参数 · ${task.name || task.id}` : `训练参数 · ${task.name || task.id}`}</h3>
            <span>{loading ? "正在计算建议值" : "确认后可继续推进任务"}</span>
          </div>
          <button className="icon-only" type="button" aria-label="关闭" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="modal-body pipeline-modal-body">
          <div className="pipeline-agent-reason">{reason}</div>
          <div className="pipeline-params-grid">
            {target.stageKey === "samples" ? (
              <label className="field">
                样本数量
                <input min="50" max="20000" step="50" type="number" value={sampleCount} onChange={(event) => setSampleCount(event.currentTarget.value)} />
              </label>
            ) : null}
            {target.stageKey === "training" ? (
              <>
                <label className="field">
                  Epoch
                  <input min="1" max="500" step="1" type="number" value={epochs} onChange={(event) => setEpochs(event.currentTarget.value)} />
                </label>
                <label className="field">
                  分辨率
                  <select value={imageSize} onChange={(event) => setImageSize(event.currentTarget.value)}>
                    <option value="480">480px</option>
                    <option value="640">640px</option>
                    <option value="960">960px</option>
                    <option value="1280">1280px</option>
                  </select>
                </label>
              </>
            ) : null}
            <label className="field">
              训练方式
              <select value={trainMode} onChange={(event) => setTrainMode(event.currentTarget.value as PipelineMethod)}>
                <option value="yolo">YOLO</option>
                <option value="yolo_ocr">YOLO + OCR</option>
              </select>
            </label>
          </div>
        </div>
        <footer className="modal-footer">
          <button className="secondary compact-action" type="button" disabled={busy} onClick={() => save(false)}>
            <Save size={16} aria-hidden="true" />
            保存参数
          </button>
          <button className="primary compact-action" type="button" disabled={busy} onClick={() => save(true)}>
            <ChevronRight size={16} aria-hidden="true" />
            接受并继续
          </button>
        </footer>
      </section>
    </div>
  );
}

function AddAccessoryModal({
  items,
  loading,
  error,
  creating,
  currentIds,
  onClose,
  onAdd,
  onCreate,
  onRetry
}: {
  items: AccessorySummary[];
  loading: boolean;
  error: unknown;
  creating: boolean;
  currentIds: Set<string>;
  onClose: () => void;
  onAdd: (accessoryId: string) => void;
  onCreate: (form: FormData) => Promise<void>;
  onRetry: () => void;
}) {
  const { notify } = useToast();
  const [draft, setDraft] = useState({
    name: "",
    material_type: "object",
    material_alpha_policy: "",
    paper_preset: "A4",
    paper_width_mm: "",
    paper_height_mm: "",
    object_length_mm: "",
    object_width_mm: "",
    object_height_mm: "",
    size_reference: "a4"
  });
  const [draftFiles, setDraftFiles] = useState<File[]>([]);

  function setDraftField(key: keyof typeof draft, value: string) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = draft.name.trim();
    if (!name) {
      notify({ title: "请输入配件名称", tone: "error" });
      return;
    }
    if (!draftFiles.length) {
      notify({ title: "请先添加至少一张照片或一段视频", tone: "error" });
      return;
    }
    if (draft.material_type === "object" && !draft.material_alpha_policy) {
      notify({ title: "请先选择物品透明或不透明", tone: "error" });
      return;
    }
    const form = new FormData();
    appendPipelineFormValue(form, "name", name);
    appendPipelineFormValue(form, "material_type", draft.material_type);
    appendPipelineFormValue(form, "training_role", draft.material_type === "text" ? "detect_then_ocr" : "detect_shape");
    appendPipelineFormValue(form, "pipeline_context", "pipeline");
    if (draft.material_type === "text") {
      appendPipelineFormValue(form, "paper_preset", draft.paper_preset);
      appendPipelineFormValue(form, "paper_width_mm", draft.paper_width_mm);
      appendPipelineFormValue(form, "paper_height_mm", draft.paper_height_mm);
    } else {
      appendPipelineFormValue(form, "material_alpha_policy", draft.material_alpha_policy);
      appendPipelineFormValue(form, "size_reference", draft.size_reference);
    }
    draftFiles.forEach((file) => form.append("files", file, file.name));
    await onCreate(form);
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel pipeline-add-accessory-modal" role="dialog" aria-modal="true" aria-label="添加配件">
        <header className="modal-head">
          <div>
            <h3>添加配件</h3>
            <span>可新建配件，或从配件库加入当前流水线。</span>
          </div>
          <button className="icon-only" type="button" aria-label="关闭" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="modal-body pipeline-modal-body">
          <form className="pipeline-inline-create" onSubmit={submit}>
            <div className="section-title title-with-action">
              <h3>新建配件</h3>
              <span className="hint-line">创建后会自动加入当前流水线</span>
            </div>
            <div className="form-grid pipeline-create-fields">
              <label>
                名称
                <input
                  value={draft.name}
                  onChange={(event) => setDraftField("name", event.currentTarget.value)}
                  placeholder="例如：钢笔盒"
                />
              </label>
              <label>
                类型
                <select
                  value={draft.material_type}
                  onChange={(event) => setDraftField("material_type", event.currentTarget.value)}
                >
                  <option value="object">物品类</option>
                  <option value="text">文字类</option>
                </select>
              </label>
              {draft.material_type === "object" ? (
                <>
                  <label>
                    透明策略
                    <select
                      value={draft.material_alpha_policy}
                      onChange={(event) => setDraftField("material_alpha_policy", event.currentTarget.value)}
                      required
                    >
                      <option value="">请选择</option>
                      <option value="opaque">不透明</option>
                      <option value="transparent">透明/玻璃</option>
                    </select>
                  </label>
                  <label>
                    尺寸参照物
                    <select
                      value={draft.size_reference}
                      onChange={(event) => setDraftField("size_reference", event.currentTarget.value)}
                    >
                      <option value="a4">A4 纸 (297×210mm)</option>
                      <option value="a5">A5 纸 (210×148mm)</option>
                      <option value="b5">B5 纸 (250×176mm)</option>
                      <option value="ruler">直尺/卷尺（读刻度）</option>
                    </select>
                    <span className="hint-line">请在素材里包含一张「配件 + 该参照物」同框照片，Agent 会据此推断真实尺寸，无需手填。</span>
                  </label>
                </>
              ) : (
                <>
                  <label>
                    纸张
                    <select value={draft.paper_preset} onChange={(event) => setDraftField("paper_preset", event.currentTarget.value)}>
                      <option value="A4">A4</option>
                      <option value="A5">A5</option>
                      <option value="A6">A6</option>
                      <option value="custom">自定义</option>
                    </select>
                  </label>
                  <label>
                    纸张 mm
                    <div className="pipeline-size-row two">
                      <input
                        aria-label="纸张宽度"
                        inputMode="decimal"
                        placeholder="宽"
                        value={draft.paper_width_mm}
                        onChange={(event) => setDraftField("paper_width_mm", event.currentTarget.value)}
                      />
                      <input
                        aria-label="纸张高度"
                        inputMode="decimal"
                        placeholder="高"
                        value={draft.paper_height_mm}
                        onChange={(event) => setDraftField("paper_height_mm", event.currentTarget.value)}
                      />
                    </div>
                  </label>
                </>
              )}
            </div>
            <label className="pipeline-create-file-field">
              素材
              <input
                type="file"
                multiple
                accept="image/*,video/*"
                onChange={(event) => setDraftFiles(Array.from(event.currentTarget.files || []))}
                required
              />
            </label>
            <div className="button-row">
              <button className="primary compact-action" type="submit" disabled={creating}>
                {creating ? <Loader2 className="spin" size={15} aria-hidden="true" /> : <Save size={15} aria-hidden="true" />}
                创建并加入流水线
              </button>
              <span className="hint-line">{draftFiles.length ? `${draftFiles.length} 个文件已选择` : "支持图片或视频素材"}</span>
            </div>
          </form>
          <div className="section-title pipeline-library-title">
            <h3>从配件库加入</h3>
          </div>
          {loading ? <LoadingState label="正在加载配件库" /> : null}
          {error ? <ErrorState error={error} action={<button onClick={onRetry}>重试</button>} /> : null}
          {!loading && !error ? (
            <div className="pipeline-library-accessory-list">
              {items.length ? (
                items.map((item) => {
                  const inFlow = currentIds.has(item.id);
                  return (
                    <div className="pipeline-library-accessory-row" key={item.id}>
                      <div>
                        <strong>{item.name || item.id}</strong>
                        <span>
                          {materialLabel(item.material_type)} · {pipelineStatusLabel(item.status)} · {recordAuditText(item)}
                        </span>
                      </div>
                      <button className="secondary compact-action" type="button" disabled={inFlow} onClick={() => onAdd(item.id)}>
                        <Plus size={15} aria-hidden="true" />
                        {inFlow ? "已加入" : "加入"}
                      </button>
                    </div>
                  );
                })
              ) : (
                <div className="lane-empty">配件库暂无可用配件。</div>
              )}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

export function TrainingPipelinePage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [createOpen, setCreateOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [detailTaskId, setDetailTaskId] = useState("");
  const [paramsTarget, setParamsTarget] = useState<ParamsTarget | null>(null);
  const [activeDrag, setActiveDrag] = useState<ActiveDrag | null>(null);
  const [busy, setBusy] = useState("");

  const pipelineQuery = useQuery({
    queryKey: queryKeys.pipeline(auth.dataUserId),
    queryFn: () => getPipeline(auth),
    refetchInterval: 6000
  });
  const resourcesQuery = useQuery({
    queryKey: queryKeys.trainingResources(auth.dataUserId),
    queryFn: () => getTrainingResources(auth),
    refetchInterval: 20_000
  });
  const accessoriesQuery = useQuery({
    queryKey: queryKeys.accessories(auth.dataUserId),
    queryFn: () => getAccessories(auth),
    enabled: addOpen
  });

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor));
  const pipeline = pipelineQuery.data;
  const tasks = pipeline?.items || [];
  const inFlowAccessories = pipeline?.accessories || [];
  const libraryAccessories = accessoriesQuery.data?.items || [];
  const assignedIds = useMemo(() => assignedAccessoryIds(tasks), [tasks]);
  const visibleAccessories = inFlowAccessories.filter((item) => !assignedIds.has(String(item.id)));
  const currentFlowIds = useMemo(() => new Set(inFlowAccessories.map((item) => item.id)), [inFlowAccessories]);
  const detailTask = tasks.find((task) => task.id === detailTaskId) || null;
  const detailDatasetSummary = findPipelineDataset(resourcesQuery.data?.datasets || [], detailTask);
  const detailDatasetId = String(detailTask?.dataset_id || detailTask?.samples_task_id || detailDatasetSummary?.id || "");
  const detailDatasetQuery = useQuery({
    queryKey: queryKeys.trainingDatasetDetail(detailDatasetId),
    queryFn: () => getTrainingDatasetDetail(detailDatasetId),
    enabled: Boolean(detailTask && detailDatasetId)
  });
  const detailDataset = detailDatasetQuery.data?.dataset || detailDatasetSummary || null;
  const paramsTask = paramsTarget ? tasks.find((task) => task.id === paramsTarget.taskId) || null : null;
  const activeTasks = tasks.filter((task) => task.stage !== "library").length;
  const archivedTasks = tasks.filter((task) => task.stage === "library").length;
  const runningTasks = tasks.filter((task) => task.status === "running").length;
  const datasets = resourcesQuery.data?.datasets?.length || 0;
  const models = resourcesQuery.data?.models?.length || 0;
  const collisionDetection = useCallback<CollisionDetection>((args) => {
    const collisions = pointerWithin(args);
    const taskCollisions = collisions.filter((collision) => String(collision.id).startsWith("task-drop:"));
    return taskCollisions.length ? taskCollisions : collisions;
  }, []);

  async function refreshPipeline() {
    await queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(auth.dataUserId) });
  }

  async function refreshAdjacent() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(auth.dataUserId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.trainingResources(auth.dataUserId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.aiTasks(auth.dataUserId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.locateAccessories(auth.dataUserId) })
    ]);
  }

  async function createTask(payload: PipelineTaskPayload) {
    try {
      await createPipelineTask(payload);
      notify({ title: "任务已创建", description: "拖入配件后即可确认参数。", tone: "success" });
      await refreshPipeline();
    } catch (error) {
      notify({ title: "创建任务失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
      throw error;
    }
  }

  async function addExistingAccessory(accessoryId: string) {
    setBusy(`add:${accessoryId}`);
    try {
      await addPipelineAccessory(accessoryId);
      notify({ title: "配件已加入当前流水线", tone: "success" });
      await refreshPipeline();
    } catch (error) {
      notify({ title: "加入失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function createAccessoryInFlow(form: FormData) {
    setBusy("create-accessory");
    try {
      await createAccessory(form);
      notify({ title: "配件已创建并加入当前流水线", description: "可直接拖入任务。", tone: "success" });
      setAddOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(auth.dataUserId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.accessories(auth.dataUserId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainingResources(auth.dataUserId) })
      ]);
    } catch (error) {
      notify({ title: "创建配件失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function removeAccessoryFromFlow(accessoryId: string) {
    setBusy(`remove:${accessoryId}`);
    try {
      await removePipelineAccessory(accessoryId);
      notify({ title: "已从当前流水线移出", description: "配件库记录仍保留。", tone: "success" });
      await refreshPipeline();
    } catch (error) {
      notify({ title: "移出失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function addAccessoryToTask(task: PipelineTask, accessoryId: string) {
    if (!task.id || task.stage !== "draft") return;
    if ((task.accessory_ids || []).includes(accessoryId)) return;
    setBusy(`task-acc:${task.id}`);
    try {
      await updatePipelineTask(task.id, { accessory_ids: [...(task.accessory_ids || []), accessoryId] });
      notify({ title: "配件已加入任务", tone: "success" });
      await refreshPipeline();
    } catch (error) {
      notify({ title: "加入配件失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  function openParams(task: PipelineTask, advanceAfter = false) {
    const stageKey = task.stage === "samples" ? "training" : "samples";
    setParamsTarget({ taskId: task.id, stageKey, advanceAfter });
  }

  async function runAdvance(task: PipelineTask) {
    if (task.stage === "draft" && !(task.accessory_ids || []).length) {
      notify({ title: "先拖入至少一个配件", tone: "error" });
      return;
    }
    const usesTraining = pipelineTaskUsesTraining(task);
    const stageKey = task.stage === "samples" ? "training" : "samples";
    const missing = stageKey === "samples" ? !task.params?.sample_count : !task.params?.epochs;
    if (usesTraining && missing && task.stage !== "training") {
      openParams(task, true);
      return;
    }
    setBusy(`advance:${task.id}`);
    try {
      const advanced = await advancePipelineTask(task.id);
      const method = pipelineTaskMethod(task);
      notify({
        title: advanced.advancing
          ? "已开始推进"
          : advanced.status === "pending"
            ? "参考图生成中"
            : !usesTraining && task.stage === "draft"
              ? method === "ai"
                ? "AI 检测任务已创建"
                : "Locate Anything 任务已启用"
              : task.stage === "training"
                ? "模型已入库"
                : "已进入下一阶段",
        description: advanced.advancing
          ? advanced.job_note || "正在后台推进，进度会实时更新。"
          : advanced.status === "pending"
            ? advanced.job_note || advanced.last_error || "生成完成后可再次生成样本。"
            : undefined,
        tone: "success"
      });
      await refreshAdjacent();
    } catch (error) {
      notify({ title: "推进失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function removeTask(task: PipelineTask) {
    if (!window.confirm(`删除流水线任务 ${task.name || task.id}？`)) return;
    setBusy(`delete:${task.id}`);
    try {
      await deletePipelineTask(task.id);
      notify({ title: "流水线任务已删除", tone: "success" });
      await refreshPipeline();
    } catch (error) {
      notify({ title: "删除失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function toggleAuto(task: PipelineTask, checked: boolean) {
    try {
      await updatePipelineTask(task.id, { auto_advance: checked });
      notify({ title: checked ? "已开启自动推进" : "已关闭自动推进", tone: "success" });
      await refreshPipeline();
    } catch (error) {
      notify({ title: "设置失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
      await refreshPipeline();
    }
  }

  async function changeAccessoryCount(task: PipelineTask, accessoryId: string, delta: number) {
    const counts = { ...(task.accessory_counts || {}) };
    counts[accessoryId] = Math.max(1, Math.min(99, taskAccessoryCount(task, accessoryId) + delta));
    try {
      await updatePipelineTask(task.id, { accessory_counts: counts });
      notify({ title: "配件数量已更新", tone: "success" });
      await refreshPipeline();
    } catch (error) {
      notify({ title: "调整数量失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    }
  }

  async function setAgentDecision(task: PipelineTask, decision: AgentMcpDecision) {
    const titles: Record<AgentMcpDecision, string> = {
      pending: "Agent/MCP 等待决策",
      continue_existing_assets: "已记录：沿用现有素材",
      continue_training: "已记录：继续训练",
      replan_requested: "已记录：请求重规划",
      cancelled: "已记录：取消本次预览"
    };
    const action = decision === "replan_requested" ? "replan" : decision === "cancelled" ? "cancel" : decision === "continue_training" ? "continue_training" : "resume";
    setBusy(`agent:${task.id}`);
    try {
      await sendPipelineAgentFeedback(task.id, { action, decision });
      notify({ title: titles[decision], tone: decision === "cancelled" ? "error" : "success" });
      await refreshAdjacent();
    } catch (error) {
      notify({ title: "Agent/MCP 决策失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function sendAgentRequest(task: PipelineTask, message: string) {
    setBusy(`agent:${task.id}`);
    try {
      await sendPipelineAgentChat(task.id, message);
      notify({ title: "已发送给 Agent", description: "Agent 正在按你的需求处理并推进流程。", tone: "success" });
      await refreshAdjacent();
    } catch (error) {
      notify({ title: "发送失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
      throw error;
    } finally {
      setBusy("");
    }
  }

  function handleDragStart(event: DragStartEvent) {
    const data = event.active.data.current as ActiveDrag | undefined;
    if (data?.type && data.id) setActiveDrag(data);
  }

  async function handleDragEnd(event: DragEndEvent) {
    setActiveDrag(null);
    const active = event.active.data.current as { type?: DragKind; id?: string } | undefined;
    const over = event.over?.data.current as { type?: DropKind; stage?: PipelineStage; taskId?: string } | undefined;
    if (!active?.type || !active.id || !over?.type) return;
    if (active.type === "accessory") {
      if (over.type === "task" && over.taskId) {
        const task = tasks.find((item) => item.id === over.taskId);
        if (task) await addAccessoryToTask(task, active.id);
        return;
      }
      if (over.type === "remove-accessory") {
        await removeAccessoryFromFlow(active.id);
        return;
      }
      notify({
        title: over.type === "lane" && over.stage === "draft" ? "先新建任务，再拖到任务卡片" : "配件需要先组成任务",
        tone: "error"
      });
      return;
    }

    const task = tasks.find((item) => item.id === active.id);
    if (!task) return;
    const targetStage = over.type === "library" ? "library" : over.stage;
    if (!targetStage) return;
    if (NEXT_STAGE[String(task.stage || "draft")] !== targetStage) {
      notify({ title: "只能拖入下一个阶段", tone: "error" });
      return;
    }
    await runAdvance(task);
  }

  if (pipelineQuery.isLoading) return <LoadingState label="正在加载训练流水线" />;
  if (pipelineQuery.isError) {
    return <ErrorState error={pipelineQuery.error} action={<button onClick={() => pipelineQuery.refetch()}>重试</button>} />;
  }

  return (
    <section className="view active pipeline-view">
      <header className="page-head">
        <div>
          <h2>训练流水线</h2>
          <p className="page-desc">从配件建档到模型投产的看板视图。完成的卡片可拖入下一阶段。</p>
        </div>
        <div className="page-head-actions">
          <span className={`pill ${pipeline?.agent?.configured ? "ok" : "neutral"}`}>
            {pipeline?.agent?.configured ? "Agent 推荐" : "规则推荐"}
          </span>
          <button className="secondary compact-action" type="button" onClick={() => pipelineQuery.refetch()}>
            <RefreshCw size={16} aria-hidden="true" />
            刷新
          </button>
        </div>
      </header>

      <section className="metric-grid four">
        <MetricCard label="当前配件" value={inFlowAccessories.length} detail="流水线内" />
        <MetricCard label="执行任务" value={activeTasks} detail={runningTasks ? `${runningTasks} 个运行中` : "等待推进"} />
        <MetricCard label="样本库" value={datasets} detail="当前数据范围" />
        <MetricCard label="模型库" value={models + archivedTasks} detail={archivedTasks ? `${archivedTasks} 个流水线入库` : "训练产物"} />
      </section>

      <DndContext sensors={sensors} collisionDetection={collisionDetection} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="pipeline-board">
          <section className="pipeline-lane" data-lane="accessories">
            <header className="lane-head">
              <div className="lane-title">
                <span className="lane-step">1</span>
                <h3>配件管理</h3>
              </div>
            </header>
            <p className="lane-hint">仅显示当前流水线使用的配件和待确认候选。拖到移出区可退回配件库。</p>
            <div className="lane-body">
              {(pipeline?.pending_candidates || []).map((candidate) => (
                <CandidateCard candidate={candidate} key={candidate.id} />
              ))}
              {visibleAccessories.map((item) => (
                <AccessoryCard item={item} key={item.id} onRemove={removeAccessoryFromFlow} />
              ))}
              {!(pipeline?.pending_candidates || []).length && !visibleAccessories.length ? (
                <div className="lane-empty">
                  {assignedIds.size ? "当前配件都已分配到任务。" : "当前流水线还没有配件。"}
                </div>
              ) : null}
            </div>
            <DroppableZone id="pipeline-remove-accessory" kind="remove-accessory" className="pipeline-remove-zone">
              <Library size={16} aria-hidden="true" />
              <span>拖到这里移出当前流</span>
            </DroppableZone>
            <button className="pipeline-add-button" type="button" onClick={() => setAddOpen(true)}>
              <Plus size={16} aria-hidden="true" />
              添加配件
            </button>
          </section>

          {PIPELINE_LANES.map((lane) => {
            const laneTasks = tasks.filter((task) => task.stage === lane.stage);
            return (
              <section className="pipeline-lane" data-lane={lane.stage} key={lane.stage}>
                <header className="lane-head">
                  <div className="lane-title">
                    <span className="lane-step">{lane.step}</span>
                    <h3>{lane.title}</h3>
                  </div>
                  {lane.stage === "draft" ? (
                    <button className="secondary compact-action" type="button" onClick={() => setCreateOpen(true)}>
                      <Plus size={15} aria-hidden="true" />
                      新建任务
                    </button>
                  ) : null}
                </header>
                <p className="lane-hint">{lane.hint}</p>
                <DroppableZone id={`lane:${lane.stage}`} kind="lane" stage={lane.stage} className="lane-body">
                  {laneTasks.length ? (
                    laneTasks.map((task) => (
                      <PipelineTaskCard
                        inFlowAccessories={inFlowAccessories}
                        libraryAccessories={libraryAccessories}
                        key={task.id}
                        onAdvance={runAdvance}
                        onDelete={removeTask}
                        onDetail={(nextTask) => setDetailTaskId(nextTask.id)}
                        onParams={(nextTask) => openParams(nextTask)}
                        onToggleAuto={toggleAuto}
                        onAgentDecision={setAgentDecision}
                        busyKey={busy}
                        task={task}
                      />
                    ))
                  ) : (
                    <div className="lane-empty">
                      {lane.stage === "draft"
                        ? "新建任务或拖入配件开始。"
                        : lane.stage === "samples"
                          ? "把待开始的任务拖到这里生成样本。"
                          : "样本完成后拖到这里开始训练。"}
                    </div>
                  )}
                </DroppableZone>
                {lane.stage === "training" ? (
                  <DroppableZone id="pipeline-library-zone" kind="library" stage="library" className="pipeline-library-zone">
                    <Archive size={18} aria-hidden="true" />
                    <strong>模型库</strong>
                    <span>拖入训练完成的任务即投入使用</span>
                  </DroppableZone>
                ) : null}
              </section>
            );
          })}
        </div>
        <DragOverlay>
          {activeDrag ? (
            <div className="pipeline-drag-overlay">
              {activeDrag.type === "accessory" ? <Boxes size={16} aria-hidden="true" /> : <CheckCircle2 size={16} aria-hidden="true" />}
              <span>{activeDrag.label}</span>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      {createOpen ? <CreateTaskModal onClose={() => setCreateOpen(false)} onCreate={createTask} /> : null}
      {addOpen ? (
        <AddAccessoryModal
          creating={busy === "create-accessory"}
          currentIds={currentFlowIds}
          error={accessoriesQuery.error}
          items={accessoriesQuery.data?.items || []}
          loading={accessoriesQuery.isLoading}
          onAdd={addExistingAccessory}
          onClose={() => setAddOpen(false)}
          onCreate={createAccessoryInFlow}
          onRetry={() => accessoriesQuery.refetch()}
        />
      ) : null}
      {detailTask ? (
        <TaskDetailModal
          inFlowAccessories={inFlowAccessories}
          libraryAccessories={libraryAccessories}
          sampleDataset={detailDataset}
          sampleDatasetError={detailDatasetQuery.error}
          sampleDatasetLoading={detailDatasetQuery.isFetching}
          sampleDatasetRequested={Boolean(detailDatasetId)}
          onClose={() => setDetailTaskId("")}
          onCountChange={changeAccessoryCount}
          onAgentDecision={setAgentDecision}
          onAgentRequest={sendAgentRequest}
          busyKey={busy}
          task={detailTask}
        />
      ) : null}
      {paramsTarget && paramsTask ? (
        <ParamsModal
          onClose={() => setParamsTarget(null)}
          onSaved={async () => refreshAdjacent()}
          target={paramsTarget}
          task={paramsTask}
        />
      ) : null}
      {busy ? <span className="pipeline-busy-sentinel" aria-live="polite">{busy}</span> : null}
    </section>
  );
}
