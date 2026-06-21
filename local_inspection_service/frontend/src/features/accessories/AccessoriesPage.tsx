import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Eye, ImagePlus, RefreshCw, Route, Search, Sparkles, Trash2, Upload, X } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addAccessoryFiles,
  confirmAccessory,
  deleteAccessory,
  deleteAccessoryFile,
  getAccessories,
  getAccessoryCandidate,
  getAccessoryDetail,
  previewAccessory,
  queryKeys,
  setAccessoryAiReference,
  setAccessoryRoute
} from "../../api/queries";
import type {
  AccessoryCandidate,
  AccessoryCandidateResponse,
  AccessoryGalleryAsset,
  AccessoryProfileStatus,
  AccessorySummary
} from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { formatRecordTime, recordAuditText, statusLabel, toneForStatus } from "../../utils/format";
import { useAuth } from "../auth/auth-context";
import { AccessoryTextCropModal } from "./AccessoryTextCropModal";

type MaterialFilter = "all" | "object" | "text";
type StatusFilter = "all" | "active" | "pending" | "failed";

const ROUTE_OPTIONS = [
  { value: "yolo", label: "YOLO" },
  { value: "ai", label: "AI 检测" },
  { value: "locate", label: "LocateAnything" },
  { value: "archive_only", label: "仅归档" }
];

const ACTIVE_JOB_STATUSES = new Set(["queued_for_codex_image_worker", "queued", "running", "pending"]);
const TEXT_ACCESSORY_MAX_IMAGES = 2;

function profileStatusText(value: AccessoryProfileStatus | string | undefined, ready?: boolean) {
  if (typeof value === "string") return value || (ready ? "ready" : "pending");
  if (value?.source === "provider") return "AI画像已生成";
  if (value?.message) return value.message;
  if (value?.status) return statusLabel(value.status);
  return ready ? "ready" : "pending";
}

function alphaPolicyLabel(policy: string | undefined) {
  if (policy === "transparent") return "透明";
  if (policy === "opaque") return "不透明";
  return "未选择";
}

function materialLabel(value: string | undefined) {
  return value === "text" ? "文字类" : "物品类";
}

function routeLabel(value: string | undefined) {
  return ROUTE_OPTIONS.find((item) => item.value === value)?.label || value || "YOLO";
}

function formatPhysicalSize(item: AccessorySummary) {
  const size = item.physical_size;
  if (!size) return "尺寸未设置";
  if (size.kind === "paper") return `${size.preset || "custom"} ${size.width_mm || "-"}x${size.height_mm || "-"}mm`;
  if (size.kind === "object") return `${size.length_mm || "-"}x${size.width_mm || "-"}x${size.height_mm || "-"}mm`;
  return "尺寸未设置";
}

function candidateJobs(candidate: AccessoryCandidate | undefined) {
  if (!candidate) return [];
  if (Array.isArray(candidate.codex_image_jobs) && candidate.codex_image_jobs.length) return candidate.codex_image_jobs;
  return candidate.codex_image_job ? [candidate.codex_image_job] : [];
}

function candidateHasActiveJobs(candidate: AccessoryCandidate | undefined) {
  return candidateJobs(candidate).some((job) => ACTIVE_JOB_STATUSES.has(String(job.status || "")));
}

function accessoryNeedsTextCrop(item: AccessorySummary | null | undefined) {
  return item?.material_type === "text" && (item.manual_crop_required || item.status === "needs_crop");
}

function fileLooksLikeImage(file: File) {
  return file.type.startsWith("image/") || /\.(png|jpe?g|webp|bmp)$/i.test(file.name);
}

function pathLooksLikeImage(path = "") {
  return /\.(png|jpe?g|webp|bmp)$/i.test(path.split(/[?#]/, 1)[0] || "");
}

function isRectifiedTextPath(path = "") {
  const name = (path.split(/[\\/]/).pop() || path).replace(/\.[^.]+$/, "").toLowerCase();
  return name.endsWith("_rectified") || name.includes("_rectified_") || name.includes("_manual_rectified");
}

function textSourceCount(item: AccessorySummary | null | undefined) {
  const original = Array.isArray(item?.original_source_files) ? item.original_source_files : [];
  if (original.length) return original.filter((path) => pathLooksLikeImage(String(path))).length;
  const sources = Array.isArray(item?.source_files) ? item.source_files : [];
  const rawSources = sources.filter((path) => pathLooksLikeImage(String(path)) && !isRectifiedTextPath(String(path)));
  return rawSources.length || Number(item?.source_file_count || 0);
}

function validateTextFiles(files: File[], existingCount: number, notify: ReturnType<typeof useToast>["notify"]) {
  if (!files.every(fileLooksLikeImage)) {
    notify({ title: "文字类只能上传图片", description: "请移除视频或其它文件。", tone: "error" });
    return false;
  }
  if (existingCount + files.length > TEXT_ACCESSORY_MAX_IMAGES) {
    notify({ title: `文字类最多 ${TEXT_ACCESSORY_MAX_IMAGES} 张图片`, description: `当前还可上传 ${Math.max(0, TEXT_ACCESSORY_MAX_IMAGES - existingCount)} 张。`, tone: "error" });
    return false;
  }
  return true;
}

function appendFormValue(form: FormData, key: string, value: string | number | boolean | undefined) {
  if (value === undefined || value === "") return;
  form.append(key, String(value));
}

function useAccessoryRefresh() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.accessories(auth.dataUserId) });
}

function AccessoryDetailModal({
  accessoryId,
  onClose,
  onChanged,
  onTextCrop
}: {
  accessoryId: string;
  onClose: () => void;
  onChanged: () => void;
  onTextCrop: (item: AccessorySummary) => void;
}) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [route, setRoute] = useState("yolo");
  const [applyRoute, setApplyRoute] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState("");
  const detailQuery = useQuery({
    queryKey: queryKeys.accessoryDetail(accessoryId),
    queryFn: () => getAccessoryDetail(accessoryId)
  });

  const detail = detailQuery.data;
  const item = detail?.item;

  useEffect(() => {
    if (item?.detection_route) setRoute(item.detection_route);
  }, [item?.detection_route]);

  async function refreshDetail() {
    await queryClient.invalidateQueries({ queryKey: queryKeys.accessoryDetail(accessoryId) });
    onChanged();
  }

  async function uploadFiles() {
    if (!files.length) {
      notify({ title: "请选择图片", tone: "error" });
      return;
    }
    if (item?.material_type === "text" && !validateTextFiles(files, textSourceCount(item), notify)) return;
    const form = new FormData();
    files.forEach((file) => form.append("files", file, file.name));
    setBusy("upload");
    try {
      const result = await addAccessoryFiles(accessoryId, form);
      setFiles([]);
      notify({
        title: item?.material_type === "text" ? "素材已上传，继续裁剪" : "素材已添加",
        description: item?.material_type === "text" ? "文字类素材需要逐张手动裁剪。" : undefined,
        tone: "success"
      });
      await refreshDetail();
      if (item?.material_type === "text" && result.item) {
        onTextCrop(result.item);
      }
    } catch (error) {
      notify({ title: "添加素材失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function updateRoute() {
    setBusy("route");
    try {
      await setAccessoryRoute(accessoryId, { route, apply: applyRoute });
      notify({ title: "检测路线已保存", tone: "success" });
      await refreshDetail();
    } catch (error) {
      notify({ title: "保存路线失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function markAiReference(asset: AccessoryGalleryAsset) {
    if (!asset.source_path) return;
    setBusy(`ai:${asset.source_path}`);
    try {
      await setAccessoryAiReference(accessoryId, asset.source_path);
      notify({ title: "AI 素材已切换", tone: "success" });
      await refreshDetail();
    } catch (error) {
      notify({ title: "切换 AI 素材失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function removeAsset(asset: AccessoryGalleryAsset) {
    if (!asset.source_path || !window.confirm("删除这张素材？")) return;
    setBusy(`delete:${asset.source_path}`);
    try {
      await deleteAccessoryFile(accessoryId, asset.source_path);
      notify({ title: "素材已删除", tone: "success" });
      await refreshDetail();
    } catch (error) {
      notify({ title: "删除素材失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel wide" role="dialog" aria-modal="true" aria-label="配件详情">
        <header className="modal-head">
          <div>
            <h3>{item?.name || "配件详情"}</h3>
            <span>{item ? recordAuditText(item, { includeUpdated: true }) : "正在加载"}</span>
          </div>
          <button className="icon-only" type="button" aria-label="关闭" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className="modal-body">
          {detailQuery.isLoading ? <LoadingState label="正在加载配件详情" /> : null}
          {detailQuery.isError ? (
            <ErrorState error={detailQuery.error} action={<button onClick={() => detailQuery.refetch()}>重试</button>} />
          ) : null}
          {item ? (
            <>
              <section className="detail-grid">
                <div>
                  <label>类型</label>
                  <strong>{materialLabel(item.material_type)}</strong>
                </div>
                <div>
                  <label>尺寸</label>
                  <strong>{formatPhysicalSize(item)}</strong>
                </div>
                <div>
                  <label>素材</label>
                  <strong>{item.source_file_count ?? item.source_files?.length ?? 0}</strong>
                </div>
                <div>
                  <label>无背景</label>
                  <strong>{item.clean_sprite_count || 0}/{item.clean_sprite_expected_count || item.clean_sprite_count || 0}</strong>
                </div>
                <div>
                  <label>AI 画像</label>
                  <strong>{profileStatusText(item.ai_profile_status, item.ai_profile_ready)}</strong>
                </div>
                <div>
                  <label>Locate</label>
                  <strong>{profileStatusText(item.locateanything_profile_status, item.locateanything_profile_ready)}</strong>
                </div>
              </section>

              <section className="resource-edit-row route-edit-row">
                <label>
                  检测路线
                  <select value={route} onChange={(event) => setRoute(event.currentTarget.value)}>
                    {ROUTE_OPTIONS.map((option) => (
                      <option value={option.value} key={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="toggle-row compact-toggle">
                  <input
                    type="checkbox"
                    checked={applyRoute}
                    onChange={(event) => setApplyRoute(event.currentTarget.checked)}
                  />
                  同步生成配置
                </label>
                <button className="secondary compact-action" type="button" disabled={busy === "route"} onClick={updateRoute}>
                  <Route size={16} aria-hidden="true" />
                  保存路线
                </button>
              </section>

              <section className="upload-strip">
                <label>
                  添加素材
                  <input
                    type="file"
                    multiple
                    accept="image/*"
                    onChange={(event) => setFiles(Array.from(event.currentTarget.files || []))}
                  />
                </label>
                <button className="secondary compact-action" type="button" disabled={busy === "upload"} onClick={uploadFiles}>
                  <Upload size={16} aria-hidden="true" />
                  上传 {files.length ? files.length : ""}
                </button>
                {item.material_type === "text" ? <span className="hint-line">文字类最多 {TEXT_ACCESSORY_MAX_IMAGES} 张图片，上传后必须逐张裁剪。</span> : null}
              </section>

              <section className="gallery-grid">
                {detail.gallery.length ? (
                  detail.gallery.map((asset, index) => (
                    <figure className={`gallery-card ${asset.ai_reference ? "selected" : ""}`} key={`${asset.source_path || asset.url}-${index}`}>
                      {asset.url ? <img src={asset.url} alt={asset.label || "素材"} loading="lazy" /> : <div className="asset-empty">无预览</div>}
                      <figcaption>
                        <strong>{asset.label || `素材 ${index + 1}`}</strong>
                        <span>{asset.kind || "asset"} · {recordAuditText(asset, { owner: false })}</span>
                      </figcaption>
                      <div className="card-action-row">
                        <button
                          className="secondary compact-action"
                          type="button"
                          disabled={!asset.source_path || busy === `ai:${asset.source_path}`}
                          onClick={() => markAiReference(asset)}
                        >
                          <Sparkles size={15} aria-hidden="true" />
                          {asset.ai_reference ? "AI 素材" : "设为 AI"}
                        </button>
                        {asset.deletable ? (
                          <button
                            className="secondary compact-action danger"
                            type="button"
                            disabled={!asset.source_path || busy === `delete:${asset.source_path}`}
                            onClick={() => removeAsset(asset)}
                          >
                            <Trash2 size={15} aria-hidden="true" />
                            删除
                          </button>
                        ) : null}
                      </div>
                    </figure>
                  ))
                ) : (
                  <div className="empty-panel">暂无素材预览</div>
                )}
              </section>
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}

export function AccessoriesPage() {
  const auth = useAuth();
  const refreshAccessories = useAccessoryRefresh();
  const { notify } = useToast();
  const [search, setSearch] = useState("");
  const [materialFilter, setMaterialFilter] = useState<MaterialFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [detailId, setDetailId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [candidateSeed, setCandidateSeed] = useState<AccessoryCandidateResponse | null>(null);
  const [cropAccessory, setCropAccessory] = useState<AccessorySummary | null>(null);
  const [deleteCropAccessoryOnCancel, setDeleteCropAccessoryOnCancel] = useState(true);
  const [busy, setBusy] = useState("");
  const [draft, setDraft] = useState({
    name: "",
    material_type: "object",
    material_alpha_policy: "opaque",
    training_role: "detect_and_classify",
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

  const accessoriesQuery = useQuery({
    queryKey: queryKeys.accessories(auth.dataUserId),
    queryFn: () => getAccessories(auth)
  });

  const candidateQuery = useQuery({
    queryKey: queryKeys.accessoryCandidate(candidateId),
    queryFn: () => getAccessoryCandidate(candidateId),
    enabled: Boolean(candidateId),
    initialData: candidateSeed?.candidate.id === candidateId ? candidateSeed : undefined,
    refetchInterval: (query) =>
      candidateHasActiveJobs((query.state.data as AccessoryCandidateResponse | undefined)?.candidate) ? 5000 : false
  });

  const items = accessoriesQuery.data?.items || [];
  const filteredItems = useMemo(() => {
    const term = search.trim().toLowerCase();
    return items.filter((item) => {
      const text = `${item.name || ""} ${item.id || ""} ${item.label || ""}`.toLowerCase();
      const materialOk = materialFilter === "all" || item.material_type === materialFilter;
      const statusOk =
        statusFilter === "all" ||
        (statusFilter === "active" && item.status === "active") ||
        (statusFilter === "failed" && String(item.status || "").includes("fail")) ||
        (statusFilter === "pending" && !["active", "completed"].includes(String(item.status || "")));
      return (!term || text.includes(term)) && materialOk && statusOk;
    });
  }, [items, materialFilter, search, statusFilter]);

  const materialCounts = useMemo(
    () => ({
      object: items.filter((item) => item.material_type !== "text").length,
      text: items.filter((item) => item.material_type === "text").length
    }),
    [items]
  );

  async function createCandidate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.name.trim()) {
      notify({ title: "请输入配件名称", tone: "error" });
      return;
    }
    if (draft.material_type === "text" && !validateTextFiles(draftFiles, 0, notify)) return;
    const form = new FormData();
    Object.entries(draft).forEach(([key, value]) => appendFormValue(form, key, value));
    draftFiles.forEach((file) => form.append("files", file, file.name));
    setBusy("preview");
    try {
      const result = await previewAccessory(form);
      setCandidateSeed(result);
      setCandidateId(result.candidate.id);
      notify({ title: "候选配件已创建", tone: "success" });
    } catch (error) {
      notify({ title: "创建候选失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function confirmCandidate() {
    const candidate = candidateQuery.data?.candidate || candidateSeed?.candidate;
    if (!candidate?.id) return;
    setBusy("confirm");
    try {
      const result = await confirmAccessory(candidate.id);
      if (accessoryNeedsTextCrop(result.item)) {
        setDeleteCropAccessoryOnCancel(true);
        setCropAccessory(result.item || null);
        notify({ title: "候选已确认，等待裁剪", description: "请截取完整文字区域后再用于训练。", tone: "info" });
      } else {
        notify({ title: "候选已确认入库", tone: "success" });
      }
      setCandidateId("");
      setCandidateSeed(null);
      setDraftFiles([]);
      await refreshAccessories();
    } catch (error) {
      notify({ title: "确认候选失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function removeAccessory(item: AccessorySummary) {
    if (!window.confirm(`删除配件 ${item.name || item.id}？`)) return;
    setBusy(`delete:${item.id}`);
    try {
      await deleteAccessory(item.id);
      notify({ title: "配件已删除", tone: "success" });
      await refreshAccessories();
    } catch (error) {
      notify({ title: "删除配件失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  if (accessoriesQuery.isLoading) return <LoadingState label="正在加载配件库" />;
  if (accessoriesQuery.isError) {
    return <ErrorState error={accessoriesQuery.error} action={<button onClick={() => accessoriesQuery.refetch()}>重试</button>} />;
  }

  const candidate = candidateQuery.data?.candidate || candidateSeed?.candidate;
  const jobs = candidateJobs(candidate);

  return (
    <section className="view active">
      <header className="page-head">
        <div>
          <h2>配件库</h2>
          <p className="page-desc">维护检测配件、素材、AI 参考图和检测路线。</p>
        </div>
        <button className="secondary compact-action" type="button" onClick={() => accessoriesQuery.refetch()}>
          <RefreshCw size={16} aria-hidden="true" />
          刷新
        </button>
      </header>

      <section className="metric-grid">
        <MetricCard label="配件" value={items.length} detail="当前数据范围" />
        <MetricCard label="物品类" value={materialCounts.object} detail="多角度/无背景素材" />
        <MetricCard label="文字类" value={materialCounts.text} detail="文档规范化素材" />
      </section>

      <section className="panel page-panel">
        <div className="section-title">
          <h3>新增候选</h3>
        </div>
        <form className="accessory-create-form" onSubmit={createCandidate}>
          <div className="form-grid">
            <label>
              名称
              <input value={draft.name} onChange={(event) => setDraftField("name", event.currentTarget.value)} />
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
                  >
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
                  <span className="hint-line">请上传一张「配件 + 参照物」同框照片，由 Agent 推断真实尺寸。</span>
                </label>
              </>
            ) : (
              <label>
                纸张
                <select value={draft.paper_preset} onChange={(event) => setDraftField("paper_preset", event.currentTarget.value)}>
                  <option value="A4">A4</option>
                  <option value="A5">A5</option>
                  <option value="A6">A6</option>
                  <option value="custom">自定义</option>
                </select>
              </label>
            )}
            <label>
              素材
              <input
                type="file"
                multiple
                accept={draft.material_type === "text" ? "image/*" : "image/*,video/*"}
                onChange={(event) => setDraftFiles(Array.from(event.currentTarget.files || []))}
              />
            </label>
          </div>
          <div className="button-row">
            <button className="primary compact-action" type="submit" disabled={busy === "preview"}>
              <ImagePlus size={16} aria-hidden="true" />
              创建候选
            </button>
            <span className="hint-line">
              {draftFiles.length
                ? `${draftFiles.length} 个文件已选择`
                : draft.material_type === "text"
                  ? `文字类最多 ${TEXT_ACCESSORY_MAX_IMAGES} 张图片，确认入库后逐张裁剪`
                  : "可先无文件建档，稍后在详情中补充素材"}
            </span>
          </div>
        </form>
        {candidate ? (
          <div className="candidate-panel">
            <div>
              <strong>{candidate.name || candidate.id}</strong>
              <span>{materialLabel(candidate.material_type)} · {alphaPolicyLabel(candidate.material_alpha_policy)} · {statusLabel(candidate.status)}</span>
              <span>{recordAuditText(candidate, { includeUpdated: true })}</span>
            </div>
            <div className="job-chip-list">
              {jobs.length ? (
                jobs.map((job) => (
                  <span className={`pill ${toneForStatus(job.status)}`} key={job.job_id || job.task_id || job.label}>
                    {job.label || job.job_id || "生成任务"} · {statusLabel(job.status)} {job.progress !== undefined ? `${job.progress}%` : ""}
                  </span>
                ))
              ) : (
                <span className="pill neutral">无生成任务</span>
              )}
            </div>
            <div className="card-action-row">
              <button className="secondary compact-action" type="button" onClick={() => candidateQuery.refetch()}>
                <RefreshCw size={16} aria-hidden="true" />
                更新
              </button>
              <button className="primary compact-action" type="button" disabled={busy === "confirm"} onClick={confirmCandidate}>
                <CheckCircle2 size={16} aria-hidden="true" />
                确认入库
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="panel page-panel">
        <div className="section-title">
          <h3>配件列表</h3>
        </div>
        <div className="filter-grid">
          <label className="search-field">
            <Search size={16} aria-hidden="true" />
            <input placeholder="搜索名称或 ID" value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
          </label>
          <label>
            类型
            <select value={materialFilter} onChange={(event) => setMaterialFilter(event.currentTarget.value as MaterialFilter)}>
              <option value="all">全部</option>
              <option value="object">物品类</option>
              <option value="text">文字类</option>
            </select>
          </label>
          <label>
            进度
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.currentTarget.value as StatusFilter)}>
              <option value="all">全部</option>
              <option value="active">启用</option>
              <option value="pending">待处理</option>
              <option value="failed">失败</option>
            </select>
          </label>
        </div>

        <div className="resource-list accessory-list">
          {filteredItems.length ? (
            filteredItems.map((item) => (
              <article className="resource-card accessory-card" key={item.id}>
                <div className="resource-thumb">
                  {item.thumbnail_url ? <img src={item.thumbnail_url} alt="" loading="lazy" /> : <ImagePlus size={22} aria-hidden="true" />}
                </div>
                <div className="accessory-main">
                  <strong>{item.name || item.id}</strong>
                  <span className="record-meta">{recordAuditText(item, { includeUpdated: true })}</span>
                  <span>
                    {materialLabel(item.material_type)} · 类别 {item.class_id ?? "-"} · {item.source_file_count ?? item.source_files?.length ?? 0} 个素材 · {formatPhysicalSize(item)}
                  </span>
                  <span>
                    路线：{routeLabel(item.detection_route)} · AI：{profileStatusText(item.ai_profile_status, item.ai_profile_ready)} · Locate：
                    {profileStatusText(item.locateanything_profile_status, item.locateanything_profile_ready)}
                  </span>
                </div>
                <div className="resource-status-column">
                  <span className={`pill ${toneForStatus(item.status)}`}>{statusLabel(item.status)}</span>
                  {item.clean_sprite_count ? (
                    <span className="pill neutral">sprite {item.clean_sprite_count}/{item.clean_sprite_expected_count || item.clean_sprite_count}</span>
                  ) : null}
                </div>
                <div className="card-action-row vertical">
                  <button className="secondary compact-action" type="button" onClick={() => setDetailId(item.id)}>
                    <Eye size={15} aria-hidden="true" />
                    查看
                  </button>
                  <button
                    className="secondary compact-action danger"
                    type="button"
                    disabled={busy === `delete:${item.id}`}
                    onClick={() => removeAccessory(item)}
                  >
                    <Trash2 size={15} aria-hidden="true" />
                    删除
                  </button>
                </div>
              </article>
            ))
          ) : (
            <div className="empty-panel">当前筛选暂无配件</div>
          )}
        </div>
      </section>

      {detailId ? (
        <AccessoryDetailModal
          accessoryId={detailId}
          onClose={() => setDetailId("")}
          onChanged={refreshAccessories}
          onTextCrop={(item) => {
            setDeleteCropAccessoryOnCancel(false);
            setCropAccessory(item);
          }}
        />
      ) : null}
      {cropAccessory ? (
        <AccessoryTextCropModal
          accessory={cropAccessory}
          onClose={() => setCropAccessory(null)}
          onCancel={async () => {
            if (deleteCropAccessoryOnCancel) {
              await deleteAccessory(cropAccessory.id);
            }
            await refreshAccessories();
          }}
          cancelLabel={deleteCropAccessoryOnCancel ? "取消并删除" : "稍后裁剪"}
          cancelSuccessTitle={deleteCropAccessoryOnCancel ? "已取消裁剪并删除配件" : "已保留配件，可稍后继续裁剪"}
          onSaved={async () => {
            await refreshAccessories();
          }}
        />
      ) : null}
    </section>
  );
}
