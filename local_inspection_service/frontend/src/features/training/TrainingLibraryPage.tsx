import { useEffect, useMemo, useState } from "react";
import { Archive, Eye, Pin, Play, RefreshCw, RotateCcw, Save, Trash2, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteAiTask,
  deletePipelineTask,
  deleteTrainingDataset,
  deleteTrainingDatasetSample,
  deleteTrainingModel,
  getPipeline,
  getTrainingDatasetDetail,
  getTrainingResources,
  queryKeys,
  updateTrainingDataset,
  updateTrainingModel,
  updateTrainingTask
} from "../../api/queries";
import type {
  AiDetectionLibraryTask,
  AiTasksResponse,
  PipelineResponse,
  TrainingDataset,
  TrainingModel,
  TrainingResourcesResponse,
  TrainingSample,
  TrainingTask
} from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { LibrarySearchBox } from "../../components/LibrarySearchBox";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { hasPermission } from "../../app/permissions";
import { modelVariantLabel, recordAuditText, statusLabel } from "../../utils/format";
import { candidateMatches, type SearchCandidate } from "../../utils/search";
import { taskEntriesFromTrainingResources, taskStatusTone } from "../../utils/taskNavigation";
import { useAuth } from "../auth/auth-context";
import { useTaskNavigationPreferences } from "../tasks/useTaskNavigationPreferences";

type LibraryTab = "tasks" | "datasets" | "models";
type ModelFilter = "all" | "trained" | "yolo_ocr" | "yolo" | "ai_detection" | "other";
type SortMode = "time_desc" | "time_asc" | "name_asc" | "name_desc";
type ResourceDetailTarget = { kind: "dataset" | "modelRun" | "aiTask"; id: string };

const SORT_OPTIONS: Array<{ value: SortMode; label: string }> = [
  { value: "time_desc", label: "时间（最新优先）" },
  { value: "time_asc", label: "时间（最早优先）" },
  { value: "name_asc", label: "名称（A→Z）" },
  { value: "name_desc", label: "名称（Z→A）" }
];

function sortByMode<T>(items: T[], mode: SortMode, nameOf: (item: T) => string, timeOf: (item: T) => number): T[] {
  const copy = [...items];
  copy.sort((a, b) => {
    if (mode === "name_asc" || mode === "name_desc") {
      const cmp = nameOf(a).localeCompare(nameOf(b), "zh-Hans-CN", { numeric: true, sensitivity: "base" });
      return mode === "name_asc" ? cmp : -cmp;
    }
    const cmp = timeOf(a) - timeOf(b);
    return mode === "time_asc" ? cmp : -cmp;
  });
  return copy;
}

interface ModelGroup {
  id: string;
  task: TrainingTask | null;
  models: TrainingModel[];
}

const MODEL_FILTER_OPTIONS: Array<{ value: ModelFilter; label: string; meta: string }> = [
  { value: "all", label: "全部类型", meta: "模型与任务" },
  { value: "trained", label: "训练模型", meta: "所有训练产物" },
  { value: "yolo_ocr", label: "YOLO + OCR", meta: "说明书分类" },
  { value: "yolo", label: "YOLO", meta: "目标检测" },
  { value: "ai_detection", label: "AI 检测任务", meta: "无训练模型" },
  { value: "other", label: "其他类型", meta: "历史模型" }
];

function modelRunGroups(models: TrainingModel[], tasks: TrainingTask[]): ModelGroup[] {
  const trainTasks = tasks.filter((task) => task.action === "train_model" || (task.models || []).length);
  const taskById = new Map(trainTasks.map((task) => [String(task.job_id || task.task_id || ""), task]));
  const groups = new Map<string, ModelGroup>();

  for (const task of trainTasks) {
    const id = String(task.job_id || task.task_id || "");
    if (id) groups.set(id, { id, task, models: [] });
  }

  for (const model of models) {
    const id = String(model.run_id || model.task_id || model.id || "");
    if (!id) continue;
    const group = groups.get(id) || { id, task: taskById.get(String(model.task_id || "")) || null, models: [] };
    group.models.push(model);
    groups.set(id, group);
  }

  return Array.from(groups.values())
    .filter((group) => group.models.length)
    .sort((a, b) => {
      const aTime = Math.max(Number(a.task?.created_at || 0), ...a.models.map((item) => Number(item.created_at || 0)));
      const bTime = Math.max(Number(b.task?.created_at || 0), ...b.models.map((item) => Number(item.created_at || 0)));
      return bTime - aTime;
    });
}

function modelRunLabel(group: ModelGroup) {
  const names = [
    ...(group.task?.accessory_names || []),
    ...group.models.flatMap((model) => model.accessory_names || [])
  ].filter(Boolean);
  if (names.length) return Array.from(new Set(names)).join(" + ");
  return group.task?.label || group.models[0]?.label || group.id || "训练模型";
}

function modelRunAccessoryText(group: ModelGroup) {
  const names = Array.from(new Set(group.models.flatMap((model) => model.accessory_names || []).filter(Boolean)));
  const ids = Array.from(new Set(group.models.flatMap((model) => model.selected_accessory_ids || []).filter(Boolean)));
  return names.length ? names.join("、") : ids.length ? ids.join(", ") : "配件信息缺失";
}

function modelGroupTime(group: ModelGroup): number {
  return Math.max(Number(group.task?.created_at || 0), 0, ...group.models.map((item) => Number(item.created_at || 0)));
}

function modelGroupAuditRecord(group: ModelGroup | null | undefined) {
  if (!group) return null;
  return [group.task, ...group.models]
    .filter(Boolean)
    .sort((a, b) => Number(b?.created_at || 0) - Number(a?.created_at || 0))[0];
}

function modelLibraryTypeForGroup(group: ModelGroup): ModelFilter {
  const variants = new Set(group.models.map((model) => String(model.variant || "").toLowerCase()).filter(Boolean));
  if (variants.has("yolo_ocr")) return "yolo_ocr";
  if (variants.has("yolo")) return "yolo";
  return "other";
}

function aiDetectionLibraryTasks(resources: TrainingResourcesResponse | undefined) {
  return (resources?.ai_detection_tasks || [])
    .filter((task) => task?.id)
    .sort((a, b) => Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0));
}

function aiTaskAccessoryText(task: AiDetectionLibraryTask) {
  const labels = task.accessory_labels || {};
  const counts = task.required_accessory_counts || {};
  const ids = task.selected_accessory_ids || Object.keys(counts);
  const names = ids.map((itemId, index) => {
    const label = labels[itemId] || (task.accessory_names || [])[index] || itemId;
    const count = Math.max(1, Number(counts[itemId] || 1));
    return `${label}${count > 1 ? `x${count}` : ""}`;
  });
  return names.length ? names.join("、") : "配件信息缺失";
}

function presentFilterOptions(modelGroups: ModelGroup[], aiTasks: AiDetectionLibraryTask[]) {
  const present = new Set<ModelFilter>(["all"]);
  if (modelGroups.length) present.add("trained");
  modelGroups.forEach((group) => present.add(modelLibraryTypeForGroup(group)));
  if (aiTasks.length) present.add("ai_detection");
  return MODEL_FILTER_OPTIONS.filter((item) => present.has(item.value));
}

function trainingTaskById(resources: TrainingResourcesResponse | undefined, taskId: string) {
  return (resources?.training_tasks || resources?.tasks || []).find(
    (item) => item.job_id === taskId || item.task_id === taskId
  );
}

function trainingModelRunById(resources: TrainingResourcesResponse | undefined, runId: string) {
  return modelRunGroups(resources?.models || [], resources?.training_tasks || resources?.tasks || []).find(
    (group) => group.id === runId
  );
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

function TrainingResourceModal({
  detail,
  resources,
  canDeleteAiTasks,
  onClose,
  onChanged
}: {
  detail: ResourceDetailTarget;
  resources: TrainingResourcesResponse | undefined;
  canDeleteAiTasks: boolean;
  onClose: () => void;
  onChanged: () => Promise<unknown>;
}) {
  const { notify } = useToast();
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const datasetQuery = useQuery({
    queryKey: queryKeys.trainingDatasetDetail(detail.id),
    queryFn: () => getTrainingDatasetDetail(detail.id),
    enabled: detail.kind === "dataset"
  });

  const dataset =
    detail.kind === "dataset"
      ? datasetQuery.data?.dataset || (resources?.datasets || []).find((item) => item.id === detail.id) || null
      : null;
  const modelGroup = detail.kind === "modelRun" ? trainingModelRunById(resources, detail.id) || null : null;
  const aiTask =
    detail.kind === "aiTask" ? aiDetectionLibraryTasks(resources).find((item) => item.id === detail.id) || null : null;
  const task = modelGroup?.task || trainingTaskById(resources, detail.id) || null;
  const models = modelGroup?.models || task?.models || (resources?.models || []).filter((model) => model.task_id === detail.id);

  useEffect(() => {
    if (dataset) {
      setTitle(dataset.display_name || dataset.id);
      setNote(dataset.note || "");
    } else if (modelGroup || task) {
      setTitle((modelGroup && modelRunLabel(modelGroup)) || task?.label || models[0]?.label || detail.id);
      setNote(task?.note || models[0]?.note || "");
    } else if (aiTask) {
      setTitle(aiTask.name || "AI 检测任务");
      setNote("");
    }
  }, [aiTask, dataset, detail.id, modelGroup, models, task]);

  async function saveResource() {
    setBusy("save");
    try {
      if (dataset) {
        await updateTrainingDataset(dataset.id, { display_name: title, note });
      } else if (modelGroup || task) {
        const id = modelGroup?.id || task?.job_id || detail.id;
        if (task?.job_id) {
          await updateTrainingTask(task.job_id, { label: title, note }).catch(() => undefined);
        }
        await updateTrainingModel(id, { display_name: title, note });
      }
      notify({ title: "资源信息已保存", tone: "success" });
      await onChanged();
      await datasetQuery.refetch();
    } catch (error) {
      notify({ title: "保存失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function removeDataset(target: TrainingDataset) {
    if (!window.confirm(`删除样本库 ${target.display_name || target.id}？`)) return;
    setBusy("delete");
    try {
      await deleteTrainingDataset(target.id);
      notify({ title: "样本库已删除", tone: "success" });
      await onChanged();
      onClose();
    } catch (error) {
      notify({ title: "删除样本库失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function removeModelRun(runId: string) {
    if (!window.confirm(`删除模型组 ${runId}？`)) return;
    setBusy("delete");
    try {
      await deleteTrainingModel(runId);
      notify({ title: "模型组已删除", tone: "success" });
      await onChanged();
      onClose();
    } catch (error) {
      notify({ title: "删除模型组失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function removeSample(sample: TrainingSample) {
    if (!dataset) return;
    const name = sampleDisplayName(sample);
    if (!window.confirm(`删除样本 ${name}？`)) return;
    setBusy(`sample:${name}`);
    try {
      await deleteTrainingDatasetSample(dataset.id, name);
      notify({ title: "样本已删除", tone: "success" });
      await onChanged();
      await datasetQuery.refetch();
    } catch (error) {
      notify({ title: "删除样本失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function removeAiTask(taskId: string) {
    if (!window.confirm(`删除 AI 检测任务 ${taskId}？`)) return;
    setBusy("delete");
    try {
      await deleteAiTask(taskId);
      notify({ title: "AI 检测任务已删除", tone: "success" });
      await onChanged();
      onClose();
    } catch (error) {
      notify({ title: "删除 AI 任务失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  const modalTitle = dataset?.display_name || (modelGroup ? modelRunLabel(modelGroup) : task?.label) || aiTask?.name || "资源详情";
  const currentEpoch = Number(task?.current_epoch || 0);
  const totalEpochs = Number(task?.total_epochs || task?.epochs || 0);

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel wide" role="dialog" aria-modal="true" aria-label="训练库详情">
        <header className="modal-head">
          <div>
            <h3>{modalTitle}</h3>
            <span>{detail.id}</span>
          </div>
          <button className="icon-only" type="button" aria-label="关闭" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className="modal-body">
          {detail.kind === "dataset" && datasetQuery.isLoading ? <LoadingState label="正在加载样本详情" /> : null}
          {detail.kind === "dataset" && datasetQuery.isError ? (
            <ErrorState error={datasetQuery.error} action={<button onClick={() => datasetQuery.refetch()}>重试</button>} />
          ) : null}

          {dataset ? (
            <>
              <section className="detail-grid">
                <div>
                  <label>样本</label>
                  <strong>{dataset.samples?.length || dataset.sample_count || 0}</strong>
                </div>
                <div>
                  <label>背景集</label>
                  <strong>{dataset.background_set_id || "-"}</strong>
                </div>
                <div>
                  <label>进度</label>
                  <strong>{dataset.missing_files ? "文件缺失" : "可用"}</strong>
                </div>
                <div>
                  <label>创建记录</label>
                  <strong>{recordAuditText(dataset)}</strong>
                </div>
              </section>
              <section className="resource-edit-row">
                <input value={title} onChange={(event) => setTitle(event.currentTarget.value)} />
                <input value={note} placeholder="备注" onChange={(event) => setNote(event.currentTarget.value)} />
                <button className="secondary compact-action" type="button" disabled={busy === "save"} onClick={saveResource}>
                  <Save size={16} aria-hidden="true" />
                  保存
                </button>
              </section>
              {dataset.missing_files ? <div className="empty-panel compact-empty">样本文件缺失或已被删除。</div> : null}
              <section className="training-resource-thumb-grid">
                {(dataset.samples || []).length ? (
                  (dataset.samples || []).map((sample) => {
                    const url = samplePublicUrl(sample);
                    const name = sampleDisplayName(sample);
                    return (
                      <figure className="gallery-card" key={`${name}-${sample.split || ""}`}>
                        {url ? <img src={url} alt={name} loading="lazy" /> : <div className="asset-empty">无预览</div>}
                        <figcaption>
                          <strong>{name}</strong>
                          <span>
                            {sample.is_true ? "True" : "False"} · {sample.split || "-"} · 缺 {sample.missing_count || 0}
                          </span>
                          <span>{recordAuditText(sample, { owner: false })}</span>
                        </figcaption>
                        <button
                          className="secondary compact-action danger"
                          type="button"
                          disabled={busy === `sample:${name}`}
                          onClick={() => removeSample(sample)}
                        >
                          <Trash2 size={15} aria-hidden="true" />
                          删除样本
                        </button>
                      </figure>
                    );
                  })
                ) : (
                  <div className="empty-panel">暂无样本缩略图</div>
                )}
              </section>
            </>
          ) : null}

          {detail.kind === "modelRun" && (modelGroup || task) ? (
            <>
              <section className="detail-grid">
                <div>
                  <label>进度</label>
                  <strong>{task?.status ? statusLabel(task.status) : "历史模型"}</strong>
                </div>
                <div>
                  <label>样本</label>
                  <strong>{task?.completed_samples || task?.sample_count || 0}/{task?.sample_count || 0}</strong>
                </div>
                <div>
                  <label>Epoch</label>
                  <strong>{totalEpochs ? `${currentEpoch}/${totalEpochs}` : "-"}</strong>
                </div>
                <div>
                  <label>模型</label>
                  <strong>{models.length}</strong>
                </div>
              </section>
              <section className="resource-edit-row">
                <input value={title} onChange={(event) => setTitle(event.currentTarget.value)} />
                <input value={note} placeholder="备注" onChange={(event) => setNote(event.currentTarget.value)} />
                <button className="secondary compact-action" type="button" disabled={busy === "save"} onClick={saveResource}>
                  <Save size={16} aria-hidden="true" />
                  保存
                </button>
              </section>
              <section className="resource-detail-list">
                <p><strong>Run ID</strong><span>{modelGroup?.id || detail.id}</span></p>
                <p><strong>Task ID</strong><span>{task?.job_id || models[0]?.task_id || "-"}</span></p>
                <p><strong>配件</strong><span>{modelGroup ? modelRunAccessoryText(modelGroup) : "-"}</span></p>
                <p><strong>Manifest</strong><span>{task?.manifest_path || "-"}</span></p>
                <p><strong>训练日志</strong><span>{task?.training_log_path || "-"}</span></p>
                {models.map((model) => (
                  <p key={model.id}>
                    <strong>{modelVariantLabel(model)}{model.exists ? "" : "（文件缺失）"}</strong>
                    <span>{model.path || ""}</span>
                  </p>
                ))}
              </section>
            </>
          ) : null}

          {aiTask ? (
            <section className="resource-detail-list">
              <p><strong>任务类型</strong><span>AI 检测</span></p>
              <p><strong>配件数量</strong><span>{aiTask.accessory_count || aiTask.selected_accessory_ids?.length || 0}</span></p>
              <p><strong>来源</strong><span>{aiTask.source || "ai_detection_workbench"}</span></p>
              <p><strong>创建记录</strong><span>{recordAuditText(aiTask, { includeUpdated: true })}</span></p>
              <p><strong>Model ID</strong><span>{aiTask.model_id || `ai_detection__task_${aiTask.id}`}</span></p>
              <p><strong>配件</strong><span>{aiTaskAccessoryText(aiTask)}</span></p>
              {(aiTask.missing_accessory_ids || []).length ? (
                <p><strong>缺失配件</strong><span>{aiTask.missing_accessory_ids?.join(", ")}</span></p>
              ) : null}
            </section>
          ) : null}
        </div>

        <footer className="modal-footer">
          {dataset ? (
            <button className="secondary danger compact-action" type="button" disabled={busy === "delete"} onClick={() => removeDataset(dataset)}>
              <Trash2 size={16} aria-hidden="true" />
              删除样本库
            </button>
          ) : null}
          {detail.kind === "modelRun" && (modelGroup || task) ? (
            <button className="secondary danger compact-action" type="button" disabled={busy === "delete"} onClick={() => removeModelRun(modelGroup?.id || detail.id)}>
              <Trash2 size={16} aria-hidden="true" />
              删除模型组
            </button>
          ) : null}
          {aiTask && canDeleteAiTasks ? (
            <button className="secondary danger compact-action" type="button" disabled={busy === "delete"} onClick={() => removeAiTask(aiTask.id)}>
              <Trash2 size={16} aria-hidden="true" />
              删除 AI 任务
            </button>
          ) : null}
        </footer>
      </section>
    </div>
  );
}

export function TrainingLibraryPage() {
  const auth = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<LibraryTab>(() => {
    const requested = searchParams.get("tab");
    return requested === "datasets" || requested === "models" || requested === "tasks" ? requested : "tasks";
  });
  const [filter, setFilter] = useState<ModelFilter>("all");
  const [sortMode, setSortMode] = useState<SortMode>("time_desc");
  const [taskSearch, setTaskSearch] = useState("");
  const [datasetSearch, setDatasetSearch] = useState("");
  const [modelSearch, setModelSearch] = useState("");
  const [detail, setDetail] = useState<ResourceDetailTarget | null>(null);
  const [busy, setBusy] = useState("");
  const { pinnedTaskIds, archivedTaskIds, persistTaskPreferences } = useTaskNavigationPreferences(auth.user.id, (error) => {
    notify({ title: "保存任务偏好失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
  });
  const resourcesQuery = useQuery({
    queryKey: queryKeys.trainingResources(auth.dataUserId),
    queryFn: () => getTrainingResources(auth)
  });
  const pipelineQuery = useQuery({
    queryKey: queryKeys.pipeline(auth.dataUserId),
    queryFn: () => getPipeline(auth)
  });

  const resources = resourcesQuery.data;
  const datasets = resources?.datasets || [];
  const models = resources?.models || [];
  const tasks = resources?.training_tasks || resources?.tasks || [];
  const modelGroups = useMemo(() => modelRunGroups(models, tasks), [models, tasks]);
  const aiTasks = useMemo(() => aiDetectionLibraryTasks(resources), [resources]);
  const taskEntries = useMemo(() => taskEntriesFromTrainingResources(resources, pipelineQuery.data), [pipelineQuery.data, resources]);
  const filterOptions = useMemo(() => presentFilterOptions(modelGroups, aiTasks), [modelGroups, aiTasks]);
  const canDeleteAiTasks = hasPermission(auth.user, "ai_detection");
  const taskSearchCandidates = useMemo<SearchCandidate[]>(
    () =>
      taskEntries.map((entry) => ({
        id: entry.id,
        label: entry.label,
        keywords: [
          entry.sourceId,
          entry.meta,
          entry.status,
          entry.detectionMethod || "",
          entry.optimizationRoute || "",
          ...(entry.accessoryNames || []),
          ...(entry.accessoryIds || [])
        ]
      })),
    [taskEntries]
  );
  const datasetSearchCandidates = useMemo<SearchCandidate[]>(
    () =>
      datasets.map((dataset) => ({
        id: dataset.id,
        label: dataset.display_name || dataset.id,
        keywords: [
          dataset.id,
          dataset.note || "",
          dataset.background_set_id || "",
          ...(dataset.selected_accessory_ids || [])
        ]
      })),
    [datasets]
  );
  const modelSearchCandidates = useMemo<SearchCandidate[]>(
    () => [
      ...modelGroups.map((group) => ({
        id: `model:${group.id}`,
        label: modelRunLabel(group),
        keywords: [
          group.id,
          modelRunAccessoryText(group),
          group.task?.status || "",
          ...(group.models || []).map((model) => modelVariantLabel(model))
        ]
      })),
      ...aiTasks.map((task) => ({
        id: `ai:${task.id}`,
        label: task.name || "AI 检测任务",
        keywords: [task.id, task.model_id || "", aiTaskAccessoryText(task), ...(task.accessory_names || [])]
      }))
    ],
    [aiTasks, modelGroups]
  );

  useEffect(() => {
    const requested = searchParams.get("tab");
    if ((requested === "datasets" || requested === "models" || requested === "tasks") && requested !== tab) {
      setTab(requested);
    }
  }, [searchParams, tab]);

  useEffect(() => {
    if (!filterOptions.some((item) => item.value === filter)) setFilter("all");
  }, [filter, filterOptions]);

  function selectTab(nextTab: LibraryTab) {
    setTab(nextTab);
    setSearchParams({ tab: nextTab });
  }

  function pinTask(taskId: string) {
    persistTaskPreferences((current) => ({
      pinnedTaskIds: [...current.pinnedTaskIds.filter((id) => id !== taskId), taskId],
      archivedTaskIds: current.archivedTaskIds.filter((id) => id !== taskId)
    }));
  }

  function unpinTask(taskId: string) {
    persistTaskPreferences((current) => ({
      pinnedTaskIds: current.pinnedTaskIds.filter((id) => id !== taskId),
      archivedTaskIds: current.archivedTaskIds
    }));
  }

  function archiveTask(taskId: string) {
    persistTaskPreferences((current) => ({
      pinnedTaskIds: current.pinnedTaskIds.filter((id) => id !== taskId),
      archivedTaskIds: current.archivedTaskIds.includes(taskId)
        ? current.archivedTaskIds
        : [...current.archivedTaskIds, taskId]
    }));
  }

  function restoreTask(taskId: string) {
    persistTaskPreferences((current) => ({
      pinnedTaskIds: current.pinnedTaskIds,
      archivedTaskIds: current.archivedTaskIds.filter((id) => id !== taskId)
    }));
  }

  async function refreshResources() {
    await Promise.all([resourcesQuery.refetch(), pipelineQuery.refetch()]);
  }

  function removePipelineTaskFromCache(taskId: string) {
    queryClient.setQueryData<PipelineResponse>(queryKeys.pipeline(auth.dataUserId), (current) =>
      current ? { ...current, items: (current.items || []).filter((task) => task.id !== taskId) } : current
    );
  }

  function removeAiTaskFromCache(taskId: string) {
    queryClient.setQueryData<TrainingResourcesResponse>(queryKeys.trainingResources(auth.dataUserId), (current) =>
      current ? { ...current, ai_detection_tasks: (current.ai_detection_tasks || []).filter((task) => task.id !== taskId) } : current
    );
    queryClient.setQueryData<AiTasksResponse>(queryKeys.aiTasks(auth.dataUserId), (current) =>
      current
        ? {
            ...current,
            selected_task_id: current.selected_task_id === taskId ? undefined : current.selected_task_id,
            task: current.task?.id === taskId ? undefined : current.task,
            tasks: (current.tasks || []).filter((task) => task.id !== taskId)
          }
        : current
    );
  }

  async function quickDeleteDataset(dataset: TrainingDataset) {
    if (!window.confirm(`删除样本库 ${dataset.display_name || dataset.id}？`)) return;
    setBusy(`dataset:${dataset.id}`);
    try {
      await deleteTrainingDataset(dataset.id);
      notify({ title: "样本库已删除", tone: "success" });
      await refreshResources();
    } catch (error) {
      notify({ title: "删除样本库失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function quickDeleteModel(runId: string) {
    if (!window.confirm(`删除模型组 ${runId}？`)) return;
    setBusy(`model:${runId}`);
    try {
      await deleteTrainingModel(runId);
      notify({ title: "模型组已删除", tone: "success" });
      await refreshResources();
    } catch (error) {
      notify({ title: "删除模型组失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function quickDeleteAiTask(taskId: string) {
    if (!window.confirm(`删除 AI 检测任务 ${taskId}？`)) return;
    setBusy(`ai:${taskId}`);
    const previousResources = queryClient.getQueryData<TrainingResourcesResponse>(queryKeys.trainingResources(auth.dataUserId));
    const previousAiTasks = queryClient.getQueryData<AiTasksResponse>(queryKeys.aiTasks(auth.dataUserId));
    const previousPinned = pinnedTaskIds;
    const previousArchived = archivedTaskIds;
    const storedId = `ai:${taskId}`;
    persistTaskPreferences((current) => ({
      pinnedTaskIds: current.pinnedTaskIds.filter((id) => id !== storedId),
      archivedTaskIds: current.archivedTaskIds.filter((id) => id !== storedId)
    }));
    removeAiTaskFromCache(taskId);
    try {
      await deleteAiTask(taskId);
      notify({ title: "AI 检测任务已删除", tone: "success" });
      await refreshResources();
    } catch (error) {
      queryClient.setQueryData(queryKeys.trainingResources(auth.dataUserId), previousResources);
      queryClient.setQueryData(queryKeys.aiTasks(auth.dataUserId), previousAiTasks);
      persistTaskPreferences((current) => ({
        pinnedTaskIds: previousPinned.includes(storedId)
          ? [...current.pinnedTaskIds.filter((id) => id !== storedId), storedId]
          : current.pinnedTaskIds.filter((id) => id !== storedId),
        archivedTaskIds: previousArchived.includes(storedId)
          ? [...current.archivedTaskIds.filter((id) => id !== storedId), storedId]
          : current.archivedTaskIds.filter((id) => id !== storedId)
      }));
      notify({ title: "删除 AI 任务失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function quickDeletePipelineTask(taskId: string) {
    if (!window.confirm(`删除任务 ${taskId}？`)) return;
    setBusy(`pipeline:${taskId}`);
    const previousPipeline = queryClient.getQueryData<PipelineResponse>(queryKeys.pipeline(auth.dataUserId));
    const previousPinned = pinnedTaskIds;
    const previousArchived = archivedTaskIds;
    const storedId = `pipeline:${taskId}`;
    persistTaskPreferences((current) => ({
      pinnedTaskIds: current.pinnedTaskIds.filter((id) => id !== storedId),
      archivedTaskIds: current.archivedTaskIds.filter((id) => id !== storedId)
    }));
    removePipelineTaskFromCache(taskId);
    try {
      await deletePipelineTask(taskId);
      notify({ title: "任务已删除", tone: "success" });
      await Promise.all([refreshResources(), pipelineQuery.refetch()]);
    } catch (error) {
      queryClient.setQueryData(queryKeys.pipeline(auth.dataUserId), previousPipeline);
      persistTaskPreferences((current) => ({
        pinnedTaskIds: previousPinned.includes(storedId)
          ? [...current.pinnedTaskIds.filter((id) => id !== storedId), storedId]
          : current.pinnedTaskIds.filter((id) => id !== storedId),
        archivedTaskIds: previousArchived.includes(storedId)
          ? [...current.archivedTaskIds.filter((id) => id !== storedId), storedId]
          : current.archivedTaskIds.filter((id) => id !== storedId)
      }));
      notify({ title: "删除任务失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  if (resourcesQuery.isLoading || pipelineQuery.isLoading) return <LoadingState label="正在加载训练库" />;
  if (resourcesQuery.isError) return <ErrorState error={resourcesQuery.error} action={<button onClick={() => resourcesQuery.refetch()}>重试</button>} />;
  if (pipelineQuery.isError) return <ErrorState error={pipelineQuery.error} action={<button onClick={() => pipelineQuery.refetch()}>重试</button>} />;

  const sortedTaskEntries = sortByMode(
    taskEntries.filter((entry) =>
      candidateMatches(
        {
          id: entry.id,
          label: entry.label,
          keywords: [
            entry.sourceId,
            entry.meta,
            entry.status,
            entry.detectionMethod || "",
            entry.optimizationRoute || "",
            ...(entry.accessoryNames || []),
            ...(entry.accessoryIds || [])
          ]
        },
        taskSearch
      )
    ),
    sortMode,
    (item) => item.label,
    (item) => item.createdAt
  );
  const sortedDatasets = sortByMode(
    datasets.filter((dataset) =>
      candidateMatches(
        {
          id: dataset.id,
          label: dataset.display_name || dataset.id,
          keywords: [dataset.note || "", dataset.background_set_id || "", ...(dataset.selected_accessory_ids || [])]
        },
        datasetSearch
      )
    ),
    sortMode,
    (item) => String(item.display_name || item.id || ""),
    (item) => Number(item.created_at || item.updated_at || 0)
  );
  const visibleModelGroups = sortByMode(
    modelGroups.filter((group) => {
      const typeOk = filter === "all" || filter === "trained" || modelLibraryTypeForGroup(group) === filter;
      return (
        typeOk &&
        candidateMatches(
          {
            id: group.id,
            label: modelRunLabel(group),
            keywords: [
              modelRunAccessoryText(group),
              group.task?.status || "",
              ...(group.models || []).map((model) => modelVariantLabel(model))
            ]
          },
          modelSearch
        )
      );
    }),
    sortMode,
    (group) => modelRunLabel(group),
    (group) => modelGroupTime(group)
  );
  const visibleAiTasks =
    filter === "all" || filter === "ai_detection"
      ? sortByMode(
          aiTasks.filter((task) =>
            candidateMatches(
              {
                id: task.id,
                label: task.name || "AI 检测任务",
                keywords: [task.model_id || "", aiTaskAccessoryText(task), ...(task.accessory_names || [])]
              },
              modelSearch
            )
          ),
          sortMode,
          (item) => String(item.name || item.id || ""),
          (item) => Number(item.updated_at || item.created_at || 0)
        )
      : [];

  const sortControl = (
    <label className="toolbar-field">
      排序
      <select value={sortMode} onChange={(event) => setSortMode(event.currentTarget.value as SortMode)}>
        {SORT_OPTIONS.map((option) => (
          <option value={option.value} key={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <section className="view active">
      <header className="page-head">
        <div>
          <h2>训练与资产</h2>
          <p className="page-desc">集中管理任务库、样本与数据集、训练模型和 AI 检测任务资源。</p>
        </div>
        <button className="secondary compact-action" type="button" onClick={() => resourcesQuery.refetch()}>
          <RefreshCw size={16} aria-hidden="true" />
          刷新资源
        </button>
      </header>

      <section className="metric-grid">
        <MetricCard label="任务库" value={taskEntries.length} detail="全部检测任务" />
        <MetricCard label="样本库" value={datasets.length} detail="已归档数据集" />
        <MetricCard label="模型组" value={modelGroups.length} detail={`${models.length} 个模型变体`} />
        <MetricCard label="AI 任务" value={aiTasks.length} detail="AI 检测模型入口" />
      </section>

      <div className="tabbar training-library-tabs" role="tablist" aria-label="训练库">
        <button
          className={`mode-tab ${tab === "tasks" ? "active" : ""}`}
          type="button"
          role="tab"
          aria-selected={tab === "tasks"}
          onClick={() => selectTab("tasks")}
        >
          任务库
        </button>
        <button
          className={`mode-tab ${tab === "datasets" ? "active" : ""}`}
          type="button"
          role="tab"
          aria-selected={tab === "datasets"}
          onClick={() => selectTab("datasets")}
        >
          样本与数据集
        </button>
        <button
          className={`mode-tab ${tab === "models" ? "active" : ""}`}
          type="button"
          role="tab"
          aria-selected={tab === "models"}
          onClick={() => selectTab("models")}
        >
          模型库
        </button>
      </div>

      {tab === "tasks" ? (
        <section className="panel page-panel training-library-pane">
          <div className="section-title model-library-head">
            <h3>任务库</h3>
            <span className="pill neutral">{taskEntries.length}</span>
            <LibrarySearchBox
              value={taskSearch}
              onChange={setTaskSearch}
              candidates={taskSearchCandidates}
              placeholder="搜索任务名称或配件"
            />
            {sortControl}
          </div>
          <div className="resource-list">
            {sortedTaskEntries.length ? (
              sortedTaskEntries.map((entry) => {
                const isPinned = pinnedTaskIds.includes(entry.id);
                const isArchived = archivedTaskIds.includes(entry.id);
                return (
                  <article className={`resource-card task-library-card ${isArchived ? "archived" : ""}`} key={entry.id}>
                    <div>
                      <Link className="task-library-title" to={entry.detailPath}>{entry.label}</Link>
                      <span className="record-meta">{entry.kind === "ai" ? "AI 检测任务" : "配件组合任务"}</span>
                      <span>{entry.meta}</span>
                      <span>Sidebar：{isPinned ? "已 Pin" : "未 Pin"} · {isArchived ? "已存档" : "可用"}</span>
                    </div>
                    <div className="resource-status-column">
                      <span className={`pill ${taskStatusTone(entry.status)}`}>{entry.status}</span>
                    </div>
                    <div className="card-action-row vertical task-library-actions">
                      <Link className="secondary compact-action" to={entry.path}>
                        <Play size={15} aria-hidden="true" />
                        开始检测
                      </Link>
                      <Link className="secondary compact-action" to={entry.detailPath}>
                        <Eye size={15} aria-hidden="true" />
                        详情
                      </Link>
                      {isArchived ? (
                        <button className="secondary compact-action" type="button" onClick={() => restoreTask(entry.id)}>
                          <RotateCcw size={15} aria-hidden="true" />
                          恢复
                        </button>
                      ) : isPinned ? (
                        <button className="secondary compact-action" type="button" onClick={() => unpinTask(entry.id)}>
                          <Pin size={15} aria-hidden="true" />
                          取消 Pin
                        </button>
                      ) : (
                        <button className="secondary compact-action" type="button" onClick={() => pinTask(entry.id)}>
                          <Pin size={15} aria-hidden="true" />
                          Pin 到侧栏
                        </button>
                      )}
                      {!isArchived ? (
                        <button className="secondary compact-action" type="button" onClick={() => archiveTask(entry.id)}>
                          <Archive size={15} aria-hidden="true" />
                          存档
                        </button>
                      ) : null}
                      {entry.canDelete ? (
                        <button
                          className="secondary compact-action danger"
                          type="button"
                          disabled={busy === `${entry.kind}:${entry.sourceId}` || (entry.kind === "ai" && !canDeleteAiTasks)}
                          onClick={() => entry.kind === "pipeline" ? quickDeletePipelineTask(entry.sourceId) : quickDeleteAiTask(entry.sourceId)}
                        >
                          <Trash2 size={15} aria-hidden="true" />
                          删除
                        </button>
                      ) : null}
                    </div>
                  </article>
                );
              })
            ) : (
              <div className="empty-panel">暂无检测任务。AI 任务或训练模型生成后会出现在这里。</div>
            )}
          </div>
        </section>
      ) : tab === "datasets" ? (
        <section className="panel page-panel training-library-pane">
          <div className="section-title model-library-head">
            <h3>样本与数据集</h3>
            <span className="pill neutral">{datasets.length}</span>
            <LibrarySearchBox
              value={datasetSearch}
              onChange={setDatasetSearch}
              candidates={datasetSearchCandidates}
              placeholder="搜索样本集名称或配件"
            />
            {sortControl}
          </div>
          <div className="resource-list">
            {sortedDatasets.length ? (
              sortedDatasets.map((dataset) => (
                <article className="resource-card" key={dataset.id}>
                  <div>
                    <strong>{dataset.display_name || dataset.id}</strong>
                    <span className="record-meta">{recordAuditText(dataset)}</span>
                    <span>
                      {dataset.sample_count || 0} 个样本 · {dataset.missing_files ? "文件缺失" : "已归档"}
                      {dataset.selected_accessory_ids?.length ? ` · ${dataset.selected_accessory_ids.join(", ")}` : ""}
                    </span>
                    {dataset.background_set_id ? <span>背景集：{dataset.background_set_id}</span> : null}
                    {dataset.note ? <span>{dataset.note}</span> : null}
                  </div>
                  <div className="resource-status-column">
                    <span className={`pill ${dataset.missing_files ? "fail" : "ok"}`}>
                      {dataset.missing_files ? "缺失" : "可用"}
                    </span>
                  </div>
                  <div className="card-action-row vertical">
                    <button className="secondary compact-action" type="button" onClick={() => setDetail({ kind: "dataset", id: dataset.id })}>
                      <Eye size={15} aria-hidden="true" />
                      详情
                    </button>
                    <button
                      className="secondary compact-action danger"
                      type="button"
                      disabled={busy === `dataset:${dataset.id}`}
                      onClick={() => quickDeleteDataset(dataset)}
                    >
                      <Trash2 size={15} aria-hidden="true" />
                      删除
                    </button>
                  </div>
                </article>
              ))
            ) : (
              <div className="empty-panel">暂无样本库</div>
            )}
          </div>
        </section>
      ) : (
        <section className="panel page-panel training-library-pane">
          <div className="section-title model-library-head">
            <h3>模型库</h3>
            <LibrarySearchBox
              value={modelSearch}
              onChange={setModelSearch}
              candidates={modelSearchCandidates}
              placeholder="搜索模型名称或配件"
            />
            <label className="toolbar-field">
              任务类型
              <select value={filter} onChange={(event) => setFilter(event.currentTarget.value as ModelFilter)}>
                {filterOptions.map((option) => (
                  <option value={option.value} key={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            {sortControl}
          </div>
          <div className="resource-list">
            {visibleModelGroups.length || visibleAiTasks.length ? (
              <>
                {visibleModelGroups.map((group) => {
                  const task = group.task || {};
                  const taskModels = group.models;
                  const dataset = task.dataset;
                  const missingCount = taskModels.filter((item) => !item.exists).length;
                  return (
                    <article className="resource-card" key={group.id}>
                      <div>
                        <strong>{modelRunLabel(group)}</strong>
                        <span className="record-meta">{recordAuditText(modelGroupAuditRecord(group))}</span>
                        <span>
                          {task.status ? statusLabel(task.status) : "历史模型"} · {task.sample_count || 0} 个样本
                        </span>
                        <span>配件：{modelRunAccessoryText(group)}</span>
                        <span>
                          样本库：{dataset ? "已归档" : "未生成"} · 模型：
                          {taskModels.length
                            ? taskModels.map((item) => `${modelVariantLabel(item)}${item.exists ? "" : "（文件缺失）"}`).join(" / ")
                            : "无"}
                          {missingCount ? ` · 缺失 ${missingCount}` : ""}
                        </span>
                        {task.note ? <span>{task.note}</span> : null}
                      </div>
                      <div className="resource-status-column">
                        <span className={`pill ${missingCount ? "warn" : "ok"}`}>{missingCount ? "部分缺失" : "可用"}</span>
                      </div>
                      <div className="card-action-row vertical">
                        <button className="secondary compact-action" type="button" onClick={() => setDetail({ kind: "modelRun", id: group.id })}>
                          <Eye size={15} aria-hidden="true" />
                          详情
                        </button>
                        <button
                          className="secondary compact-action danger"
                          type="button"
                          disabled={busy === `model:${group.id}`}
                          onClick={() => quickDeleteModel(group.id)}
                        >
                          <Trash2 size={15} aria-hidden="true" />
                          删除
                        </button>
                      </div>
                    </article>
                  );
                })}
                {visibleAiTasks.map((task) => (
                  <article className="resource-card ai-library-card" key={task.id}>
                    <div>
                      <strong>{task.name || "AI 检测任务"}</strong>
                      <span className="record-meta">{recordAuditText(task, { includeUpdated: true })}</span>
                      <span>AI 检测任务 · {task.accessory_count || task.selected_accessory_ids?.length || 0} 类配件</span>
                      <span>配件：{aiTaskAccessoryText(task)}</span>
                      <span>模型 ID：{task.model_id || `ai_detection__task_${task.id}`}</span>
                    </div>
                    <div className="resource-status-column">
                      <span className="pill neutral">AI</span>
                    </div>
                    <div className="card-action-row vertical">
                      <button className="secondary compact-action" type="button" onClick={() => setDetail({ kind: "aiTask", id: task.id })}>
                        <Eye size={15} aria-hidden="true" />
                        详情
                      </button>
                      {canDeleteAiTasks ? (
                        <button
                          className="secondary compact-action danger"
                          type="button"
                          disabled={busy === `ai:${task.id}`}
                          onClick={() => quickDeleteAiTask(task.id)}
                        >
                          <Trash2 size={15} aria-hidden="true" />
                          删除
                        </button>
                      ) : null}
                    </div>
                  </article>
                ))}
              </>
            ) : (
              <div className="empty-panel">当前类型暂无模型资源</div>
            )}
          </div>
        </section>
      )}

      {detail ? (
        <TrainingResourceModal
          detail={detail}
          resources={resources}
          canDeleteAiTasks={canDeleteAiTasks}
          onClose={() => setDetail(null)}
          onChanged={refreshResources}
        />
      ) : null}
    </section>
  );
}
