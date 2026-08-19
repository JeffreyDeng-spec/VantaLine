import type { AiDetectionLibraryTask, PipelineResponse, PipelineTask, TrainingResourcesResponse } from "../api/types";

export type TaskEntryKind = "ai" | "pipeline";

export interface TaskEntry {
  id: string;
  sourceId: string;
  kind: TaskEntryKind;
  label: string;
  meta: string;
  status: string;
  path: string;
  detailPath: string;
  accessoryNames: string[];
  accessoryIds: string[];
  accessoryCounts: Record<string, number>;
  stage?: string;
  progress?: number;
  detectionMethod?: string;
  taskKind?: string;
  materialCode?: string;
  materialName?: string;
  referenceVersionLabel?: string;
  optimizationRoute?: string;
  autoAdvance?: boolean;
  expectedProductionCount?: number;
  autoOptimizeInitialization?: Record<string, unknown>;
  autoOptimizeTaskId?: string;
  aiBaselineTaskId?: string;
  aiBaselineModelId?: string;
  autoOptimizeLink?: Record<string, unknown>;
  backgroundSetId?: string;
  environmentBackground?: Record<string, unknown>;
  sampleTaskId?: string;
  trainingTaskId?: string;
  datasetId?: string;
  datasetStatus?: string;
  datasetExists?: boolean;
  aiTaskId?: string;
  aiModelId?: string;
  modelRunId?: string;
  modelLabel?: string;
  modelStatus?: string;
  modelExists?: boolean;
  lastError?: string;
  currentEpoch?: number;
  totalEpochs?: number;
  createdAt: number;
  updatedAt: number;
  canDelete: boolean;
}

export const PINNED_TASK_IDS_KEY = "vantaline.sidebar.pinnedTasks.v1";
export const ARCHIVED_TASK_IDS_KEY = "vantaline.sidebar.archivedTasks.v1";
export const LEGACY_TASK_PREFERENCES_OWNER_KEY = "vantaline.sidebar.preferences.legacyOwner.v1";
export const TASK_STORAGE_EVENT = "vantaline:task-storage-change";

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function timeOf(value: unknown) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) ? numeric : 0;
}

function taskId(kind: TaskEntryKind, sourceId: string) {
  return `${kind}:${sourceId}`;
}

function aiTaskLabel(task: AiDetectionLibraryTask) {
  return task.name || task.accessory_names?.join(" + ") || task.selected_accessory_ids?.join(" + ") || task.id || "AI 检测任务";
}

function pipelineTaskLabel(task: PipelineTask) {
  const names = unique([...(task.accessory_names || []), ...((task.accessories || []).map((item) => item.name || item.id))]);
  return task.name || (names.length ? names.join(" + ") : task.id || "检测任务");
}

function pipelineTaskPath(task: PipelineTask) {
  return `/tasks/${encodeURIComponent(taskId("pipeline", task.id))}/inspect`;
}

function pipelineTaskStatus(task: PipelineTask) {
  if (task.task_kind === "incoming_material_text") {
    return task.status === "ready" ? "可检验" : "待配置标准";
  }
  const method = String(task.detection_method || "").toLowerCase();
  if ((method === "ai" || task.ai_task_id || task.ai_model_id || task.task_kind === "ai_detection") && task.stage === "library") {
    return "可用";
  }
  if (task.stage === "library" && task.status === "completed") return "已上线";
  if (task.status === "running") return "运行中";
  if (task.status === "failed") return "失败";
  if (task.pause_requested || task.status === "stopped") return "已暂停";
  if (task.stage === "draft") return "定义中";
  if (task.stage === "samples") return "生成样本";
  if (task.stage === "training") return "训练中";
  return task.status || task.stage || "任务";
}

export function taskEntriesFromTrainingResources(
  resources: TrainingResourcesResponse | undefined,
  pipeline?: PipelineResponse | undefined
): TaskEntry[] {
  const pipelineEntries: TaskEntry[] = (pipeline?.items || [])
    .filter((task) => task?.id)
    .map((task) => {
      const accessoryCount = task.accessory_ids?.length || task.accessories?.length || task.accessory_names?.length || 0;
      const updatedAt = timeOf(task.updated_at || task.created_at);
      const countIds = Object.keys(task.accessory_counts || {});
      const accessoryIds = unique([...(task.accessory_ids || []), ...((task.accessories || []).map((item) => item.id)), ...countIds]);
      const nameById = new Map((task.accessories || []).map((item) => [item.id, item.name || item.id]));
      const accessoryNames = accessoryIds.map((id, index) => task.accessory_names?.[index] || nameById.get(id) || id);
      return {
        id: taskId("pipeline", task.id),
        sourceId: task.id,
        kind: "pipeline",
        label: pipelineTaskLabel(task),
        meta: task.task_kind === "incoming_material_text"
          ? `包材文字检验 · ${task.reference_version_label ? `标准 ${task.reference_version_label}` : "待配置标准"}`
          : `${accessoryCount} 类配件 · ${task.detection_method === "ai" ? "AI 检测" : task.optimization_route || "检测任务"}`,
        status: pipelineTaskStatus(task),
        path: pipelineTaskPath(task),
        detailPath: `/tasks/${encodeURIComponent(taskId("pipeline", task.id))}`,
        accessoryNames,
        accessoryIds,
        accessoryCounts: task.accessory_counts || {},
        stage: task.stage,
        progress: task.progress,
        detectionMethod: task.detection_method,
        taskKind: task.task_kind,
        materialCode: task.material_code,
        materialName: task.material_name,
        referenceVersionLabel: task.reference_version_label,
        optimizationRoute: task.optimization_route,
        autoAdvance: task.auto_advance,
        expectedProductionCount: Number(task.expected_production_count || task.params?.expected_production_count || 0),
        autoOptimizeInitialization: task.auto_optimize_initialization,
        autoOptimizeTaskId: task.auto_optimize_task_id,
        aiBaselineTaskId: task.ai_baseline_task_id,
        aiBaselineModelId: task.ai_baseline_model_id,
        autoOptimizeLink: task.auto_optimize_link,
        backgroundSetId: String(task.background_set_id || task.environment_background?.background_set_id || task.params?.background_set_id || ""),
        environmentBackground: task.environment_background,
        sampleTaskId: task.samples_task_id,
        trainingTaskId: task.training_task_id,
        datasetId: task.dataset_id,
        datasetStatus: task.dataset_status,
        datasetExists: task.dataset_exists,
        aiTaskId: task.ai_task_id,
        aiModelId: task.ai_model_id,
        modelRunId: task.model_run_id,
        modelLabel: task.model_label,
        modelStatus: task.model_status,
        modelExists: task.model_exists,
        lastError: task.last_error,
        currentEpoch: task.current_epoch,
        totalEpochs: task.total_epochs,
        createdAt: timeOf(task.created_at),
        updatedAt,
        canDelete: true
      };
    });

  if (pipelineEntries.length) {
    return pipelineEntries.sort((a, b) => b.createdAt - a.createdAt);
  }

  const aiEntries: TaskEntry[] = (resources?.ai_detection_tasks || [])
    .filter((task) => task?.id)
    .map((task) => {
      const sourceId = String(task.id);
      const accessoryCount = task.accessory_count || task.selected_accessory_ids?.length || task.accessory_names?.length || 0;
      const updatedAt = timeOf(task.updated_at || task.created_at);
      return {
        id: taskId("ai", sourceId),
        sourceId,
        kind: "ai",
        label: aiTaskLabel(task),
        meta: `AI 检测 · ${accessoryCount} 类配件`,
        status: "AI",
        path: `/tasks/${encodeURIComponent(taskId("ai", sourceId))}/inspect`,
        detailPath: `/tasks/${encodeURIComponent(taskId("ai", sourceId))}`,
        accessoryNames: task.accessory_names || task.selected_accessory_ids || [],
        accessoryIds: task.selected_accessory_ids || [],
        accessoryCounts: task.required_accessory_counts || {},
        stage: "ai_detection",
        detectionMethod: "ai",
        aiTaskId: sourceId,
        aiModelId: task.model_id,
        backgroundSetId: String(task.background_set_id || task.environment_background?.background_set_id || ""),
        environmentBackground: task.environment_background,
        progress: undefined,
        createdAt: timeOf(task.created_at),
        updatedAt,
        canDelete: true
      };
    });
  return aiEntries.sort((a, b) => b.createdAt - a.createdAt);
}

export function readStoredTaskIds(key: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function writeStoredTaskIds(key: string, ids: string[]) {
  if (typeof window === "undefined") return;
  const nextIds = unique(ids);
  window.localStorage.setItem(key, JSON.stringify(nextIds));
  window.dispatchEvent(new CustomEvent(TASK_STORAGE_EVENT, { detail: { key, ids: nextIds } }));
}

export function taskPreferenceStorageKey(key: string, userId: string) {
  return `${key}.user.${encodeURIComponent(userId)}`;
}

export function readStoredTaskIdsForUser(key: string, userId: string) {
  if (!userId) return [];
  return readStoredTaskIds(taskPreferenceStorageKey(key, userId));
}

export function writeStoredTaskIdsForUser(key: string, userId: string, ids: string[]) {
  if (!userId) return;
  writeStoredTaskIds(taskPreferenceStorageKey(key, userId), ids);
}

/**
 * Bind the pre-account localStorage keys to at most one authenticated user.
 * The owner marker is written before values are returned so another account
 * can never inherit the same anonymous browser state.
 */
export function claimLegacyTaskPreferences(userId: string) {
  if (typeof window === "undefined" || !userId) return { pinnedTaskIds: [], archivedTaskIds: [], claimed: false };
  const owner = window.localStorage.getItem(LEGACY_TASK_PREFERENCES_OWNER_KEY);
  if (owner && owner !== userId) return { pinnedTaskIds: [], archivedTaskIds: [], claimed: false };
  if (!owner) window.localStorage.setItem(LEGACY_TASK_PREFERENCES_OWNER_KEY, userId);
  return {
    pinnedTaskIds: readStoredTaskIds(PINNED_TASK_IDS_KEY),
    archivedTaskIds: readStoredTaskIds(ARCHIVED_TASK_IDS_KEY),
    claimed: true
  };
}

export function clearClaimedLegacyTaskPreferences(userId: string) {
  if (typeof window === "undefined" || !userId) return;
  if (window.localStorage.getItem(LEGACY_TASK_PREFERENCES_OWNER_KEY) !== userId) return;
  window.localStorage.removeItem(PINNED_TASK_IDS_KEY);
  window.localStorage.removeItem(ARCHIVED_TASK_IDS_KEY);
}

export function taskStatusTone(status: string) {
  const normalized = status.toLowerCase();
  if (["completed", "ready", "done", "success", "ai"].includes(normalized)) return "ok";
  if (status === "可用" || status === "已上线") return "ok";
  if (["failed", "error"].includes(normalized)) return "fail";
  if (["训练中", "排队训练", "运行中", "生成样本"].includes(status)) return "warn";
  if (["pending", "running", "training", "generating", "review"].some((item) => normalized.includes(item))) return "warn";
  return "neutral";
}
