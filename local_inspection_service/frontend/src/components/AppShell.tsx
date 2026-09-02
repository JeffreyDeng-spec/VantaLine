import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Archive, ChevronDown, ChevronRight, Database, LogOut, Minus, MoreHorizontal, Pin, Play, Plus, ShieldCheck, Trash2, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  dataAnalysisNavItem,
  detectionCenterNavItem,
  textCompareBetaNavItem,
  navItems,
  overviewNavItem,
  systemNavItems,
  trainingAssetNavItems
} from "../app/navigation";
import { hasPermission } from "../app/permissions";
import {
  createPipelineTask,
  deleteAiTask,
  deletePipelineTask,
  getAccessories,
  getPipeline,
  getTrainingResources,
  getUsers,
  queryKeys
} from "../api/queries";
import type { AccessorySummary, AiTasksResponse, PipelineResponse, PipelineTaskPayload, TrainingResourcesResponse } from "../api/types";
import { useAuth } from "../features/auth/auth-context";
import { Dashboard } from "../features/dashboard/Dashboard";
import { DetectionWorkbenchPage } from "../features/detection/DetectionWorkbenchPage";
import { PlaceholderPage } from "../features/placeholder/PlaceholderPage";
import { TrainingPipelinePage } from "../features/pipeline/TrainingPipelinePage";
import { AccessoriesPage } from "../features/accessories/AccessoriesPage";
import { DataAnalysisPage } from "../features/data-analysis/DataAnalysisPage";
import { RulesPage } from "../features/rules/RulesPage";
import { TaskDetailRoute, TaskInspectionRoute } from "../features/incoming-text/IncomingTextRoutes";
import { useTaskNavigationPreferences } from "../features/tasks/useTaskNavigationPreferences";
import { TrainingLibraryPage } from "../features/training/TrainingLibraryPage";
import { UsersPage } from "../features/users/UsersPage";
import { TextCompareBetaPage } from "../features/text-compare/TextCompareBetaPage";
import {
  taskEntriesFromTrainingResources,
  taskStatusTone,
  type TaskEntry
} from "../utils/taskNavigation";

function PermissionRoute({ permission, children }: { permission?: string; children: React.ReactNode }) {
  const auth = useAuth();
  if (!hasPermission(auth.user, permission)) {
    return (
      <section className="view active">
        <div className="empty-panel">
          <ShieldCheck size={22} aria-hidden="true" />
          <strong>没有权限访问此页面</strong>
        </div>
      </section>
    );
  }
  return <>{children}</>;
}

function AnyPermissionRoute({ permissions, children }: { permissions: string[]; children: React.ReactNode }) {
  const auth = useAuth();
  if (!permissions.some((permission) => hasPermission(auth.user, permission))) {
    return <section className="view active"><div className="empty-panel"><ShieldCheck size={22} /><strong>没有权限访问此页面</strong></div></section>;
  }
  return <>{children}</>;
}

function taskNavActive(path: string, location: ReturnType<typeof useLocation>) {
  const [pathname, search = ""] = path.split("?");
  if (pathname === "/inspect" && /^\/tasks\/[^/]+\/inspect$/.test(location.pathname)) return true;
  if (location.pathname !== pathname) return false;
  if (!search) return true;
  const expected = new URLSearchParams(search);
  const current = new URLSearchParams(location.search);
  return Array.from(expected.entries()).every(([key, value]) => current.get(key) === value);
}

function SidebarLink({ item, indent = false }: { item: (typeof navItems)[number]; indent?: boolean }) {
  const location = useLocation();
  const Icon = item.icon;
  return (
    <Link className={`nav-item ${indent ? "nav-item-child" : ""} ${taskNavActive(item.path, location) ? "active" : ""}`} to={item.path}>
      <Icon size={18} aria-hidden="true" />
      <span>{item.label}</span>
    </Link>
  );
}

const USER_AVATAR_COLORS = ["#2563eb", "#7c3aed", "#059669", "#dc2626", "#ea580c", "#0891b2", "#4f46e5", "#be123c"];

function userAvatarColor(username: string) {
  const seed = username || "user";
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) % USER_AVATAR_COLORS.length;
  }
  return USER_AVATAR_COLORS[Math.abs(hash) % USER_AVATAR_COLORS.length];
}

function userAvatarInitial(username: string) {
  return (Array.from(username.trim())[0] || "U").toUpperCase();
}

function taskNameKey(value = "") {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function SidebarCreateTaskModal({
  accessories,
  existingTasks,
  busy,
  onClose,
  onCreate
}: {
  accessories: AccessorySummary[];
  existingTasks: TaskEntry[];
  busy: boolean;
  onClose: () => void;
  onCreate: (payload: PipelineTaskPayload) => Promise<unknown>;
}) {
  const [name, setName] = useState("");
  const [formError, setFormError] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [expectedProductionCount, setExpectedProductionCount] = useState("");

  function addAccessory(accessoryId: string) {
    setSelectedIds((current) => current.includes(accessoryId) ? current : [...current, accessoryId]);
    setCounts((current) => ({ ...current, [accessoryId]: current[accessoryId] || 1 }));
  }

  function removeAccessory(accessoryId: string) {
    setSelectedIds((current) => current.filter((id) => id !== accessoryId));
  }

  function setAccessoryCount(accessoryId: string, nextValue: number) {
    setCounts((current) => ({ ...current, [accessoryId]: Math.max(1, Math.min(99, Math.round(nextValue || 1))) }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selectedAccessories = accessories.filter((item) => selectedIds.includes(item.id));
    const fallbackName = selectedAccessories.map((item) => item.name || item.id).join(" + ");
    const taskName = name.trim() || fallbackName || "新检测任务";
    const key = taskNameKey(taskName);
    if (existingTasks.some((task) => taskNameKey(task.label) === key)) {
      setFormError(`已经存在名为「${taskName}」的任务，请换一个名称。`);
      return;
    }
    const expectedCount = Math.max(0, Math.round(Number(expectedProductionCount || 0)));
    if (!Number.isFinite(expectedCount) || expectedCount <= 0) {
      setFormError("请填写这个任务的预计产量。");
      return;
    }
    await onCreate({
      name: taskName,
      detection_method: "ai",
      auto_advance: false,
      expected_production_count: expectedCount,
      accessory_ids: selectedIds,
      accessory_counts: Object.fromEntries(selectedIds.map((id) => [id, Math.max(1, Number(counts[id] || 1))]))
    }).then(onClose).catch((error: Error) => {
      setFormError(error.message || "创建任务失败");
    });
  }

  return (
    <>
      <div className="modal-backdrop" role="presentation">
        <form className="modal-panel sidebar-task-modal" role="dialog" aria-modal="true" aria-label="添加任务" onSubmit={submit}>
          <header className="modal-head">
            <div>
              <h3>添加任务</h3>
              <span>创建产品/配件检测任务。</span>
            </div>
            <button className="icon-only" type="button" aria-label="关闭" onClick={onClose}>
              <X size={18} aria-hidden="true" />
            </button>
          </header>
          <div className="modal-body sidebar-task-modal-body">
            <label className="field">
              任务名称
              <input
                value={name}
                placeholder="例如：数据分析测试"
                onChange={(event) => {
                  setName(event.currentTarget.value);
                  setFormError("");
                }}
              />
            </label>
            {formError ? <div className="form-error compact-form-error">{formError}</div> : null}
            <label className="field">
              预计产量
              <input
                type="number"
                min="1"
                max="1000000"
                step="1"
                value={expectedProductionCount}
                placeholder="例如：3000"
                onChange={(event) => {
                  setExpectedProductionCount(event.currentTarget.value);
                  setFormError("");
                }}
                required
              />
            </label>
            <section className="sidebar-task-accessory-picker">
              <div className="sidebar-task-picker-head">
                <strong>检测配件与数量</strong>
                <button className="secondary compact-action" type="button" onClick={() => setPickerOpen(true)}>
                  <Plus size={15} aria-hidden="true" />
                  添加配件
                </button>
              </div>
              <div className="sidebar-task-selected-list">
                {selectedIds.length ? (
                  selectedIds.map((id) => {
                    const accessory = accessories.find((item) => item.id === id);
                    return (
                      <div className="sidebar-task-selected-row" key={id}>
                        <span>
                          <strong>{accessory?.name || id}</strong>
                          <small>{accessory?.material_type || id}</small>
                        </span>
                        <div className="sidebar-task-count-stepper" aria-label={`${accessory?.name || id} 数量`}>
                          <button type="button" disabled={(counts[id] || 1) <= 1} onClick={() => setAccessoryCount(id, (counts[id] || 1) - 1)}>
                            <Minus size={14} aria-hidden="true" />
                          </button>
                          <strong>{counts[id] || 1}</strong>
                          <button type="button" onClick={() => setAccessoryCount(id, (counts[id] || 1) + 1)}>
                            <Plus size={14} aria-hidden="true" />
                          </button>
                        </div>
                        <button className="icon-button light" type="button" aria-label={`移除 ${accessory?.name || id}`} onClick={() => removeAccessory(id)}>
                          <X size={15} aria-hidden="true" />
                        </button>
                      </div>
                    );
                  })
                ) : (
                  <div className="empty-panel compact-empty">点击加号从库存中选择这个任务需要检测的配件。</div>
                )}
              </div>
            </section>
          </div>
          <footer className="modal-footer">
            <button className="secondary compact-action" type="button" onClick={onClose}>
              取消
            </button>
            <button className="primary compact-action" type="submit" disabled={busy || !selectedIds.length}>
              <Plus size={16} aria-hidden="true" />
              创建并 Pin
            </button>
          </footer>
        </form>
      </div>

      {pickerOpen ? (
        <div className="modal-backdrop stacked" role="presentation">
          <section className="modal-panel sidebar-accessory-picker-modal" role="dialog" aria-modal="true" aria-label="选择配件">
            <header className="modal-head">
              <div>
                <h3>选择库存配件</h3>
                <span>从库存中选择这个任务需要检测的配件。</span>
              </div>
              <button className="icon-only" type="button" aria-label="关闭" onClick={() => setPickerOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="modal-body sidebar-task-modal-body">
              <section className="sidebar-inventory-list">
                {accessories.length ? (
                  accessories.map((accessory) => {
                    const selected = selectedIds.includes(accessory.id);
                    return (
                      <button
                        className={`sidebar-inventory-row ${selected ? "selected" : ""}`}
                        type="button"
                        onClick={() => addAccessory(accessory.id)}
                        key={accessory.id}
                      >
                        <span>
                          <strong>{accessory.name || accessory.id}</strong>
                          <small>{accessory.material_type || accessory.id}</small>
                        </span>
                        <em>{selected ? "已添加" : "添加"}</em>
                      </button>
                    );
                  })
                ) : (
                  <div className="empty-panel compact-empty">库存中还没有配件。</div>
                )}
              </section>
              <Link className="sidebar-create-accessory-link" to="/accessories" onClick={onClose}>
                需要创建新配件？跳转到创建配件页面
              </Link>
            </div>
            <footer className="modal-footer">
              <button className="primary compact-action" type="button" onClick={() => setPickerOpen(false)}>
                完成选择
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}

export function AppShell() {
  const auth = useAuth();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [assetsExpanded, setAssetsExpanded] = useState(() => ["/training-library", "/pipeline"].includes(window.location.pathname));
  const [createTaskOpen, setCreateTaskOpen] = useState(false);
  const canReadTaskResources = ["ai_detection", "model_library", "training_pipeline"].some((permission) => hasPermission(auth.user, permission));
  const canReadPipelineTasks = ["training_pipeline", "incoming_material_config", "inspection"].some((permission) => hasPermission(auth.user, permission));
  const { pinnedTaskIds, archivedTaskIds, preferencesExist, persistTaskPreferences } = useTaskNavigationPreferences(auth.user.id, (error) => {
    window.alert(error instanceof Error ? error.message : "保存侧边栏任务偏好失败");
  });
  const trainingResourcesQuery = useQuery({
    queryKey: queryKeys.trainingResources(auth.dataUserId),
    queryFn: () => getTrainingResources(auth),
    enabled: canReadTaskResources,
    refetchInterval: 60_000
  });
  const pipelineQuery = useQuery({
    queryKey: queryKeys.pipeline(auth.dataUserId),
    queryFn: () => getPipeline(auth),
    enabled: canReadPipelineTasks,
    refetchInterval: 60_000
  });
  const accessoriesQuery = useQuery({
    queryKey: queryKeys.accessories(auth.dataUserId),
    queryFn: () => getAccessories(auth),
    enabled: hasPermission(auth.user, "accessory_library"),
    // Accessory data is only shown inside the create-task modal, so it does not
    // need background polling while the modal is closed.
    refetchInterval: createTaskOpen ? 60_000 : false
  });
  const usersQuery = useQuery({
    queryKey: queryKeys.users,
    queryFn: getUsers,
    enabled: auth.user.role === "admin"
  });
  const deleteAiTaskMutation = useMutation({
    mutationFn: deleteAiTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.trainingResources(auth.dataUserId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.aiTasks(auth.dataUserId) });
    }
  });
  const deletePipelineTaskMutation = useMutation({
    mutationFn: deletePipelineTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(auth.dataUserId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.trainingResources(auth.dataUserId) });
    }
  });

  function removeTaskFromQueryCache(entry: TaskEntry) {
    if (entry.kind === "pipeline") {
      queryClient.setQueryData<PipelineResponse>(queryKeys.pipeline(auth.dataUserId), (current) =>
        current ? { ...current, items: (current.items || []).filter((task) => task.id !== entry.sourceId) } : current
      );
      return;
    }
    queryClient.setQueryData<TrainingResourcesResponse>(queryKeys.trainingResources(auth.dataUserId), (current) =>
      current ? { ...current, ai_detection_tasks: (current.ai_detection_tasks || []).filter((task) => task.id !== entry.sourceId) } : current
    );
    queryClient.setQueryData<AiTasksResponse>(queryKeys.aiTasks(auth.dataUserId), (current) =>
      current
        ? {
            ...current,
            selected_task_id: current.selected_task_id === entry.sourceId ? undefined : current.selected_task_id,
            task: current.task?.id === entry.sourceId ? undefined : current.task,
            tasks: (current.tasks || []).filter((task) => task.id !== entry.sourceId)
          }
        : current
    );
  }
  const createPipelineTaskMutation = useMutation({
    mutationFn: (payload: PipelineTaskPayload) => createPipelineTask(payload, auth),
    onSuccess: (task) => {
      queryClient.setQueryData<PipelineResponse>(queryKeys.pipeline(auth.dataUserId), (current) =>
        current
          ? {
              ...current,
              items: [task, ...(current.items || []).filter((item) => item.id !== task.id)]
            }
          : { items: [task], accessories: [] }
      );
      const taskKey = `pipeline:${task.id}`;
      persistTaskPreferences((current) => {
        const currentPinned = current.pinnedTaskIds.length ? current.pinnedTaskIds : effectivePinnedTaskIds;
        return {
          pinnedTaskIds: [taskKey, ...currentPinned.filter((id) => id !== taskKey)],
          archivedTaskIds: current.archivedTaskIds.filter((id) => id !== taskKey)
        };
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(auth.dataUserId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.trainingResources(auth.dataUserId) });
    }
  });

  useEffect(() => {
    if (["/training-library", "/pipeline"].includes(location.pathname)) setAssetsExpanded(true);
  }, [location.pathname]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [location.pathname, location.search]);

  const taskEntries = useMemo(
    () => taskEntriesFromTrainingResources(trainingResourcesQuery.data, pipelineQuery.data),
    [pipelineQuery.data, trainingResourcesQuery.data]
  );
  const entryById = useMemo(() => new Map(taskEntries.map((entry) => [entry.id, entry])), [taskEntries]);
  const defaultPinnedIds = useMemo(
    () => taskEntries.filter((entry) => !archivedTaskIds.includes(entry.id)).slice(0, 3).map((entry) => entry.id),
    [archivedTaskIds, taskEntries]
  );
  const effectivePinnedTaskIds = pinnedTaskIds.length || preferencesExist ? pinnedTaskIds : defaultPinnedIds;
  const pinnedTasks = effectivePinnedTaskIds
    .map((id) => entryById.get(id))
    .filter((entry): entry is TaskEntry => Boolean(entry))
    .filter((entry) => !archivedTaskIds.includes(entry.id));

  function unpinTask(entry: TaskEntry) {
    persistTaskPreferences((current) => ({
      pinnedTaskIds: (current.pinnedTaskIds.length ? current.pinnedTaskIds : effectivePinnedTaskIds).filter((id) => id !== entry.id),
      archivedTaskIds: current.archivedTaskIds
    }));
  }

  function archiveTask(entry: TaskEntry) {
    persistTaskPreferences((current) => ({
      pinnedTaskIds: (current.pinnedTaskIds.length ? current.pinnedTaskIds : effectivePinnedTaskIds).filter((id) => id !== entry.id),
      archivedTaskIds: current.archivedTaskIds.includes(entry.id)
        ? current.archivedTaskIds
        : [...current.archivedTaskIds, entry.id]
    }));
  }

  async function deleteTask(entry: TaskEntry) {
    if (!entry.canDelete) return;
    if (!window.confirm(`删除任务 ${entry.label}？`)) return;
    const previousPipeline = queryClient.getQueryData<PipelineResponse>(queryKeys.pipeline(auth.dataUserId));
    const previousResources = queryClient.getQueryData<TrainingResourcesResponse>(queryKeys.trainingResources(auth.dataUserId));
    const previousAiTasks = queryClient.getQueryData<AiTasksResponse>(queryKeys.aiTasks(auth.dataUserId));
    const previousPinned = pinnedTaskIds;
    const previousArchived = archivedTaskIds;
    persistTaskPreferences((current) => ({
      pinnedTaskIds: (current.pinnedTaskIds.length ? current.pinnedTaskIds : effectivePinnedTaskIds).filter((id) => id !== entry.id),
      archivedTaskIds: current.archivedTaskIds.filter((id) => id !== entry.id)
    }));
    removeTaskFromQueryCache(entry);
    try {
      if (entry.kind === "pipeline") {
        await deletePipelineTaskMutation.mutateAsync(entry.sourceId);
      } else {
        await deleteAiTaskMutation.mutateAsync(entry.sourceId);
      }
    } catch (error) {
      queryClient.setQueryData(queryKeys.pipeline(auth.dataUserId), previousPipeline);
      queryClient.setQueryData(queryKeys.trainingResources(auth.dataUserId), previousResources);
      queryClient.setQueryData(queryKeys.aiTasks(auth.dataUserId), previousAiTasks);
      persistTaskPreferences((current) => ({
        pinnedTaskIds: previousPinned.includes(entry.id)
          ? [entry.id, ...current.pinnedTaskIds.filter((id) => id !== entry.id)]
          : current.pinnedTaskIds.filter((id) => id !== entry.id),
        archivedTaskIds: previousArchived.includes(entry.id)
          ? [...current.archivedTaskIds.filter((id) => id !== entry.id), entry.id]
          : current.archivedTaskIds.filter((id) => id !== entry.id)
      }));
      window.alert(error instanceof Error ? error.message : "删除任务失败");
    }
  }

  const visibleTrainingAssetItems = trainingAssetNavItems.filter((item) => hasPermission(auth.user, item.permission));
  const visibleSystemItems = systemNavItems.filter((item) => hasPermission(auth.user, item.permission));
  const visibleFixedItems = [overviewNavItem, detectionCenterNavItem, textCompareBetaNavItem, dataAnalysisNavItem].filter((item) =>
    item.view === "dataAnalysis"
      ? ["ai_detection", "inspection"].some((permission) => hasPermission(auth.user, permission))
      : hasPermission(auth.user, item.permission)
  );
  const visibleTrainingChildren = assetsExpanded ? visibleTrainingAssetItems : [];
  const accountDisplayName = auth.user.display_name || auth.user.username;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            <img src="/static/brand-logo.png?v=20260614-logo" alt="" width="36" height="36" decoding="async" />
          </div>
          <div className="brand-copy">
            <h1>VantaLine</h1>
            <p>React Preview</p>
          </div>
        </div>

        <nav className="side-nav" aria-label="主导航">
          <div className="nav-group">
            {visibleFixedItems.slice(0, 3).map((item) => (
              <SidebarLink item={item} key={item.path} />
            ))}
          </div>

          {visibleTrainingAssetItems.length ? (
            <div className="nav-group">
              <button
                className="nav-item nav-item-button"
                type="button"
                onClick={() => setAssetsExpanded((value) => !value)}
                aria-expanded={assetsExpanded}
              >
                <Database size={18} aria-hidden="true" />
                <span>训练与资产</span>
                {assetsExpanded ? <ChevronDown className="nav-chevron" size={18} aria-hidden="true" /> : <ChevronRight className="nav-chevron" size={18} aria-hidden="true" />}
              </button>
              {visibleTrainingChildren.map((item) => (
                <SidebarLink item={item} indent key={item.path} />
              ))}
            </div>
          ) : null}

          <div className="nav-group">
            {visibleFixedItems.slice(3).map((item) => (
              <SidebarLink item={item} key={item.path} />
            ))}
          </div>

          <div className="nav-group pinned-task-group">
            <p className="nav-group-label">Pinned Tasks</p>
            {pinnedTasks.length ? (
              pinnedTasks.map((entry) => (
                <div className="pinned-task-row" key={entry.id}>
                  <Link className="pinned-task-link" to={entry.detailPath}>
                    <Pin size={14} aria-hidden="true" />
                    <span>
                      <strong>{entry.label}</strong>
                      <small>{entry.meta}</small>
                    </span>
                    <em className={`pill ${taskStatusTone(entry.status)}`}>{entry.status}</em>
                  </Link>
                  <details className="pinned-task-menu">
                    <summary aria-label={`${entry.label} 操作`}>
                      <MoreHorizontal size={16} aria-hidden="true" />
                    </summary>
                    <div className="pinned-task-menu-panel">
                      <Link to={entry.path}>
                        <Play size={14} aria-hidden="true" />
                        开始检测
                      </Link>
                      <button type="button" onClick={() => unpinTask(entry)}>
                        <Pin size={14} aria-hidden="true" />
                        取消 Pin
                      </button>
                      <button type="button" onClick={() => archiveTask(entry)}>
                        <Archive size={14} aria-hidden="true" />
                        存档
                      </button>
                      <button
                        type="button"
                        disabled={!entry.canDelete || deleteAiTaskMutation.isPending || deletePipelineTaskMutation.isPending}
                        onClick={() => deleteTask(entry)}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                        删除
                      </button>
                    </div>
                  </details>
                </div>
              ))
            ) : (
              <div className="pinned-task-empty">在训练与资产 / 任务库中 Pin 常用任务。</div>
            )}
          </div>

          {hasPermission(auth.user, "training_pipeline") ? (
            <div className="nav-group sidebar-task-create">
              <button className="sidebar-create-task-button" type="button" onClick={() => setCreateTaskOpen(true)}>
                <Plus size={16} aria-hidden="true" />
                添加任务
              </button>
            </div>
          ) : null}

          {visibleSystemItems.length ? (
            <div className="nav-group sidebar-bottom-nav">
              {visibleSystemItems.map((item) => (
                <SidebarLink item={item} key={item.path} />
              ))}
            </div>
          ) : null}

          <div className="account-card compact-account-card" title={accountDisplayName}>
            <span className="account-avatar" style={{ backgroundColor: userAvatarColor(accountDisplayName) }} aria-hidden="true">
              {userAvatarInitial(accountDisplayName)}
            </span>
            <div>
              <strong>{accountDisplayName}</strong>
              <span>{auth.user.role === "admin" ? "Admin" : "普通用户"}</span>
            </div>
            <button className="icon-button account-logout" type="button" title="退出登录" aria-label="退出登录" onClick={auth.logout}>
              <LogOut size={15} aria-hidden="true" />
            </button>
          </div>
        </nav>
      </aside>

      {createTaskOpen ? (
          <SidebarCreateTaskModal
          accessories={accessoriesQuery.data?.items || []}
          existingTasks={taskEntries}
          busy={createPipelineTaskMutation.isPending}
          onClose={() => setCreateTaskOpen(false)}
          onCreate={(payload) => createPipelineTaskMutation.mutateAsync(payload)}
        />
      ) : null}

      <main className="workspace">
        {auth.user.role === "admin" ? (
          <div className="top-scope-bar">
            <label>
              数据范围
              <select value={auth.dataUserId} onChange={(event) => auth.setDataUserId(event.currentTarget.value)}>
                <option value="">全部用户与历史数据</option>
                <option value="legacy_admin">历史数据</option>
                {(usersQuery.data?.users || []).map((user) => (
                  <option value={user.id} key={user.id}>
                    {user.display_name || user.username}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : null}

        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/status" element={<Navigate to="/" replace />} />
          <Route
            path="/inspect"
            element={
              <PermissionRoute permission="inspection">
                <DetectionWorkbenchPage mode="inspect" />
              </PermissionRoute>
            }
          />
          <Route
            path="/text-compare-beta"
            element={
              <PermissionRoute permission="inspection">
                <TextCompareBetaPage />
              </PermissionRoute>
            }
          />
          <Route
            path="/tasks/:taskId/inspect"
            element={<TaskInspectionRoute />}
          />
          <Route
            path="/ai-inspect"
            element={
              <PermissionRoute permission="ai_detection">
                <DetectionWorkbenchPage mode="ai" />
              </PermissionRoute>
            }
          />
          <Route
            path="/accessories"
            element={
              <PermissionRoute permission="accessory_library">
                <AccessoriesPage />
              </PermissionRoute>
            }
          />
          <Route
            path="/data-analysis"
            element={
              <AnyPermissionRoute permissions={["ai_detection", "inspection"]}>
                <DataAnalysisPage />
              </AnyPermissionRoute>
            }
          />
          <Route
            path="/training-library"
            element={
              <PermissionRoute permission="model_library">
                <TrainingLibraryPage />
              </PermissionRoute>
            }
          />
          <Route
            path="/tasks/:taskId"
            element={<TaskDetailRoute />}
          />
          <Route
            path="/pipeline"
            element={
              <PermissionRoute permission="training_pipeline">
                <TrainingPipelinePage />
              </PermissionRoute>
            }
          />
          <Route
            path="/rules"
            element={
              <PermissionRoute permission="system_settings">
                <RulesPage />
              </PermissionRoute>
            }
          />
          <Route
            path="/users"
            element={
              <PermissionRoute permission="user_management">
                <UsersPage />
              </PermissionRoute>
            }
          />
          {navItems
            .filter((item) => !["home", "inspect", "textCompareBeta", "aiInspect", "accessories", "dataAnalysis", "trainingLibrary", "pipeline", "rules", "userManagement"].includes(item.view))
            .map((item) => (
              <Route
                key={item.path}
                path={item.path}
                element={
                  <PermissionRoute permission={item.permission}>
                    <PlaceholderPage item={item} />
                  </PermissionRoute>
                }
              />
            ))}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
