import { useMemo, useState } from "react";
import { BarChart3, Eye, Image as ImageIcon, RefreshCw, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import {
  getDataAnalysisRecord,
  getDataAnalysisRecords,
  queryKeys
} from "../../api/queries";
import type {
  DataAnalysisAiSummary,
  DataAnalysisImageProcessingItem,
  DataAnalysisImageProcessingSummary,
  DataAnalysisRecord,
  DataAnalysisTaskGroup
} from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { formatRecordTime, recordAuditText } from "../../utils/format";
import { useAuth } from "../auth/auth-context";

type DataAnalysisView = "records" | "processing";

function cacheUrl(url = "", token = "") {
  if (!url) return "";
  const suffix = token || String(Date.now());
  return `${url}${url.includes("?") ? "&" : "?"}t=${encodeURIComponent(suffix)}`;
}

function processingStatusLabel(value = "") {
  const labels: Record<string, string> = {
    queued: "排队中",
    pending: "等待中",
    running: "处理中",
    completed: "已完成",
    rejected: "已拒绝",
    failed: "失败"
  };
  return labels[value] || value || "未知";
}

function processingTypeLabel(value = "") {
  const labels: Record<string, string> = {
    source_photo: "原始照片",
    ai_detection_overlay: "AI 检测图",
    auto_optimize_sample: "自动优化样本",
    ai_mask: "AI mask",
    ai_mask_box_overlay: "AI mask 框选图",
    roi_crop: "ROI 裁剪",
    ai_roi_mask: "AI ROI mask",
    traditional_roi_mask: "传统 ROI mask",
    transparent_sprite: "透明 sprite",
    clean_sprite: "标准 sprite",
    dataset_image: "训练图片",
    dataset_label: "训练标签"
  };
  return labels[value] || value || "处理项";
}

function processingTone(status = ""): "neutral" | "ok" | "warn" | "fail" {
  if (status === "completed") return "ok";
  if (status === "failed") return "fail";
  if (status === "rejected") return "warn";
  return "neutral";
}

function processingSummaryText(summary: DataAnalysisImageProcessingSummary | null | undefined) {
  const total = Number(summary?.total || 0);
  const active = Number(summary?.active || 0);
  const failed = Number(summary?.failed || 0);
  const rejected = Number(summary?.rejected || 0);
  if (!total) return "暂无处理项";
  return `${total} 项 · 处理中 ${active} · 失败 ${failed}${rejected ? ` · 拒绝 ${rejected}` : ""}`;
}

function aiSummaryText(summary: DataAnalysisAiSummary | null | undefined) {
  if (!summary) return "-";
  const stateText = summary.passed ? "通过" : "不通过";
  const present = Number(summary.present_count || 0);
  const missing = Number(summary.missing_count || 0);
  const mismatch = Number(summary.count_mismatch_count || 0);
  return `${stateText} · 命中 ${present} · 缺失 ${missing}${mismatch ? ` · 数量 ${mismatch}` : ""}`;
}

function aiImageUrl(record: DataAnalysisRecord | null | undefined) {
  const result = (record?.ai_detection_result || {}) as Record<string, unknown>;
  return String(result.annotated_url || result.preview_url || result["output_url"] || record?.image_url || record?.source_image?.url || "");
}

function detailTitle(record: DataAnalysisRecord | null | undefined) {
  return record?.source_image?.filename || record?.record_id || "数据分析记录";
}

function taskLabel(task: DataAnalysisTaskGroup) {
  return `${task.name || task.id} (${Number(task.count || 0)})`;
}

function processingItemTime(item: DataAnalysisImageProcessingItem) {
  return item.updated_at || item.created_at ? formatRecordTime(Number(item.updated_at || item.created_at || 0)) : "-";
}

function isProfileBackfillRecord(record: DataAnalysisRecord) {
  const items = record.image_processing_items || [];
  return Boolean(items.length) && items.every((item) => item.metrics?.backfilled === true);
}

function processingItemByType(record: DataAnalysisRecord | null | undefined, type: string) {
  const items = record?.image_processing_items || [];
  if (type === "ai_mask_box_overlay") {
    return items.find((item) => item.type === type && item.metrics?.review_unit === true) || items.find((item) => item.type === type);
  }
  return items.find((item) => item.type === type);
}

function reviewAiImageUrl(record: DataAnalysisRecord) {
  return processingItemByType(record, "ai_detection_overlay")?.url || aiImageUrl(record) || processingItemByType(record, "source_photo")?.url || "";
}

function reviewMaskBoxUrl(record: DataAnalysisRecord) {
  return processingItemByType(record, "ai_mask_box_overlay")?.url || "";
}

function reviewRecordSubtitle(record: DataAnalysisRecord) {
  const boxItem = processingItemByType(record, "ai_mask_box_overlay");
  if (boxItem?.status === "completed") return "通过";
  if (boxItem?.status === "rejected" || boxItem?.status === "failed") return "未通过";
  if (boxItem?.status) return processingStatusLabel(boxItem.status);
  return "尚未生成 AI mask bbox";
}

function DataAnalysisImagePanel({
  title,
  url,
  placeholder,
  rows,
  token
}: {
  title: string;
  url: string;
  placeholder: string;
  rows: Array<{ label: string; value?: string | number }>;
  token: string;
}) {
  return (
    <section className="analysis-compare-card">
      <div className="analysis-compare-card-head">
        <h3>{title}</h3>
        <span className={`pill ${url ? "ok" : "neutral"}`}>{url ? "图像可用" : "无图像"}</span>
      </div>
      <div className="analysis-compare-frame">
        {url ? <img src={cacheUrl(url, token)} alt={title} /> : <div className="analysis-compare-empty">{placeholder}</div>}
      </div>
      <ul className="analysis-compare-meta">
        {rows
          .filter((row) => row.value !== undefined && row.value !== null && String(row.value).trim() !== "")
          .map((row) => (
            <li key={row.label}>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </li>
          ))}
      </ul>
    </section>
  );
}

function ImageProcessingReviewUnit({
  record,
  onOpenRecord
}: {
  record: DataAnalysisRecord;
  onOpenRecord: (recordId: string) => void;
}) {
  const aiUrl = reviewAiImageUrl(record);
  const boxUrl = reviewMaskBoxUrl(record);
  const boxItem = processingItemByType(record, "ai_mask_box_overlay");
  const items = record.image_processing_items || [];
  const token = String(record.updated_at || record.created_at || record.record_id);
  const [detailsOpen, setDetailsOpen] = useState(false);

  return (
    <article className="image-processing-review-card">
      <div className="image-processing-review-head">
        <div>
          <strong>{detailTitle(record)}</strong>
          <span>{record.task?.name || record.task?.id || "AI 检测"}</span>
        </div>
        <span className={`pill ${boxItem?.status === "completed" ? "ok" : boxItem?.status === "rejected" || boxItem?.status === "failed" ? "fail" : "neutral"}`}>
          {reviewRecordSubtitle(record)}
        </span>
      </div>

      <div className="image-processing-review-pair">
        <section>
          <div className="image-processing-review-label">
            <span>AI 检测结果</span>
          </div>
          <div className="image-processing-review-frame">
            {aiUrl ? <img src={cacheUrl(aiUrl, token)} alt="AI 检测结果" /> : <span>AI 检测图未保存</span>}
          </div>
        </section>
        <section>
          <div className="image-processing-review-label">
            <span>AI mask bbox</span>
          </div>
          <div className="image-processing-review-frame">
            {boxUrl ? (
              <img src={cacheUrl(boxUrl, String(boxItem?.updated_at || token))} alt="AI mask bbox" />
            ) : (
              <span>{boxItem?.reason || "任务执行中尚未生成 bbox 图"}</span>
            )}
          </div>
        </section>
      </div>

      <div className="image-processing-review-actions">
        <button className="secondary compact-action" type="button" onClick={() => onOpenRecord(record.record_id)}>
          <Eye size={15} aria-hidden="true" />
          打开详情
        </button>
        <details className="image-processing-hidden-detail" onToggle={(event) => setDetailsOpen(event.currentTarget.open)}>
          <summary>查看中间产物</summary>
          {detailsOpen ? <ImageProcessingTimeline items={items} /> : null}
        </details>
      </div>
    </article>
  );
}

function ImageProcessingItemCard({
  item,
  onOpenRecord
}: {
  item: DataAnalysisImageProcessingItem & { record?: DataAnalysisRecord };
  onOpenRecord?: (recordId: string) => void;
}) {
  const label = item.label || item.type_label || processingTypeLabel(item.type);
  const status = item.status || "";
  const record = item.record;
  return (
    <article className="image-processing-card">
      <div className="image-processing-preview">
        {item.url ? <img src={cacheUrl(item.url, String(item.updated_at || item.created_at || ""))} alt={label} /> : <span>无预览</span>}
      </div>
      <div className="image-processing-card-body">
        <div className="image-processing-card-head">
          <strong>{label}</strong>
          <span className={`pill ${processingTone(status)}`}>{processingStatusLabel(status)}</span>
        </div>
        <div className="image-processing-meta">
          <span>{item.type_label || processingTypeLabel(item.type)}</span>
          <span>{processingItemTime(item)}</span>
          {record ? <span>{record.task?.name || record.task?.id || "AI 检测"}</span> : null}
        </div>
        {item.reason ? <p className="image-processing-reason">{item.reason}</p> : null}
        {record && onOpenRecord ? (
          <button className="secondary compact-action" type="button" onClick={() => onOpenRecord(record.record_id)}>
            <Eye size={15} aria-hidden="true" />
            查看记录
          </button>
        ) : null}
      </div>
    </article>
  );
}

function ImageProcessingTimeline({ items }: { items: DataAnalysisImageProcessingItem[] }) {
  if (!items.length) {
    return (
      <div className="empty-panel compact">
        <ImageIcon size={20} aria-hidden="true" />
        <strong>暂无图片处理记录</strong>
        <span>后台生成 mask、sprite 或训练样本后会出现在这里。</span>
      </div>
    );
  }
  return (
    <section className="data-analysis-processing-section">
      <div className="section-head compact">
        <div>
          <p className="eyebrow">后台图片处理</p>
          <h3>处理链路</h3>
        </div>
        <span className="pill neutral">{items.length} 项</span>
      </div>
      <div className="image-processing-grid detail">
        {items.map((item) => (
          <ImageProcessingItemCard item={item} key={item.id} />
        ))}
      </div>
    </section>
  );
}

function DataAnalysisDetailModal({
  recordId,
  onClose
}: {
  recordId: string;
  onClose: () => void;
}) {
  const auth = useAuth();
  const canViewDiagnostics = auth.user.role === "admin";
  const detailQuery = useQuery({
    queryKey: queryKeys.dataAnalysisRecord(recordId),
    queryFn: () => getDataAnalysisRecord(recordId)
  });
  const record = detailQuery.data?.record || null;
  const aiSummary = record?.ai_summary || {};
  const scope = record?.required_accessory_scope?.required_accessories || [];
  const aiUrl = aiImageUrl(record);
  const maskBoxItem = processingItemByType(record, "ai_mask_box_overlay");
  const maskBoxUrl = maskBoxItem?.url || "";
  const token = String(maskBoxItem?.updated_at || record?.updated_at || record?.record_id || Date.now());

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel wide data-analysis-detail-modal" role="dialog" aria-modal="true" aria-label="数据分析详情">
        <div className="modal-head">
          <div>
            <p className="eyebrow">数据分析</p>
            <h2>{detailTitle(record)}</h2>
          </div>
          <div className="modal-head-actions">
            <button className="icon-button" type="button" aria-label="关闭数据分析详情" onClick={onClose}>
              <X size={18} aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="modal-body data-analysis-modal-body">
          {detailQuery.isLoading ? <LoadingState label="正在读取记录详情" /> : null}
          {detailQuery.isError ? <ErrorState error={detailQuery.error} action={<button onClick={() => detailQuery.refetch()}>重试</button>} /> : null}
          {record ? (
            <>
              <div className="data-analysis-detail-summary">
                <div>
                  <label>任务</label>
                  <strong>{record.task?.name || record.task?.id || "AI 检测"}</strong>
                </div>
                <div>
                  <label>AI 检测</label>
                  <strong>{aiSummaryText(aiSummary)}</strong>
                </div>
                <div>
                  <label>图片处理</label>
                  <strong>{processingSummaryText(record.image_processing_summary)}</strong>
                </div>
              </div>

              {scope.length ? (
                <div className="data-analysis-scope-list">
                  <strong>必检配件</strong>
                  <div>
                    {scope.map((item) => (
                      <span key={item.accessory_id}>
                        {item.label || item.accessory_id}
                        <small>
                          AI {Number(item.ai_detection_count || 0)} / 应有 {Number(item.required_count || 1)}
                        </small>
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="analysis-compare-grid">
                <DataAnalysisImagePanel
                  title="AI 检测结果"
                  url={aiUrl}
                  placeholder="AI 检测图未保存"
                  rows={[
                    { label: "状态", value: aiSummaryText(aiSummary) },
                    { label: "检测数量", value: Number(aiSummary.detection_count || 0) },
                    { label: "请求", value: String(record.ai_detection_result?.request_id || "-") }
                  ]}
                  token={String(record.updated_at || record.created_at || record.record_id)}
                />
                <DataAnalysisImagePanel
                  title="AI mask bbox 复核图"
                  url={maskBoxUrl}
                  placeholder={maskBoxItem?.reason || "AI mask bbox 图未生成"}
                  rows={[
                    { label: "状态", value: reviewRecordSubtitle(record) },
                    { label: "候选", value: Number(maskBoxItem?.metrics?.candidate_count || 0) },
                    { label: "诊断", value: canViewDiagnostics ? maskBoxItem?.reason || "-" : "" }
                  ]}
                  token={token}
                />
              </div>

              <ImageProcessingTimeline items={record.image_processing_items || []} />

              {canViewDiagnostics ? (
                <details className="data-analysis-raw-detail">
                  <summary>管理员诊断</summary>
                  <pre className="debug-pre">{JSON.stringify(record, null, 2)}</pre>
                </details>
              ) : null}
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}

export function DataAnalysisPage() {
  const auth = useAuth();
  const [taskId, setTaskId] = useState("");
  const [view, setView] = useState<DataAnalysisView>("records");
  const [detailRecordId, setDetailRecordId] = useState("");

  const recordsQuery = useQuery({
    queryKey: queryKeys.dataAnalysisRecords(auth.dataUserId, taskId),
    // 100 latest records keep the list responsive; the header total still
    // reflects the full count from the backend.
    queryFn: () => getDataAnalysisRecords(auth, { taskId, limit: 100 }),
    refetchInterval: (query) => (Number(query.state.data?.image_processing_summary?.active || 0) > 0 ? 4000 : false)
  });

  const records = recordsQuery.data?.records || [];
  const taskOptions = recordsQuery.data?.tasks || [];
  const total = Number(recordsQuery.data?.total || records.length);
  const processingReviewRecords = useMemo(() => records.filter((record) => !isProfileBackfillRecord(record)), [records]);
  const processingSummary = recordsQuery.data?.image_processing_summary || {};
  const scopeText =
    auth.user.role === "admin"
      ? auth.dataUserId
        ? "当前使用顶部数据范围筛选。"
        : "Admin 正在查看全部用户与历史数据。"
      : "普通用户仅能查看自己的 AI 检测记录。";

  return (
    <section className="view active data-analysis-view">
      <header className="page-head">
        <div>
          <h2>数据分析</h2>
          <p className="page-desc">复核 AI 检测记录、图像处理产物和任务维度结果。</p>
        </div>
        <div className="page-head-actions">
          <button className="secondary compact-action" type="button" onClick={() => recordsQuery.refetch()} disabled={recordsQuery.isFetching}>
            <RefreshCw size={16} aria-hidden="true" />
            刷新
          </button>
        </div>
      </header>

      <div className="metric-grid four data-analysis-metrics">
        <MetricCard label="记录" value={String(total)} detail={records.length === total ? "当前范围" : `已加载 ${records.length}`} />
        <MetricCard label="图片处理" value={String(Number(processingSummary.total || 0))} detail={processingSummaryText(processingSummary)} />
        <MetricCard
          label="后台进程"
          value={String(Number(processingSummary.active || 0))}
          tone={Number(processingSummary.failed || 0) ? "warn" : Number(processingSummary.active || 0) ? "neutral" : "ok"}
          detail={`完成 ${Number(processingSummary.completed || 0)} · 失败 ${Number(processingSummary.failed || 0)}`}
        />
        <MetricCard
          label="复核样本"
          value={String(processingReviewRecords.length)}
          tone={processingReviewRecords.length ? "neutral" : "ok"}
          detail="AI 检测与 mask bbox 复核"
        />
      </div>

      <div className="tabbar data-analysis-tabs" role="tablist" aria-label="数据分析视图">
        <button className={`mode-tab ${view === "records" ? "active" : ""}`} type="button" onClick={() => setView("records")}>
          检测记录
        </button>
        <button className={`mode-tab ${view === "processing" ? "active" : ""}`} type="button" onClick={() => setView("processing")}>
          图片处理
        </button>
      </div>

      <section className="panel data-analysis-toolbar">
        <label className="toolbar-field">
          <span>任务</span>
          <select
            value={taskId}
            onChange={(event) => {
              setTaskId(event.currentTarget.value);
            }}
          >
            <option value="">全部任务</option>
            {taskOptions.map((task) => (
              <option value={task.id} key={task.id}>
                {taskLabel(task)}
              </option>
            ))}
          </select>
        </label>
        <div className="data-analysis-scope-note">
          <BarChart3 size={16} aria-hidden="true" />
          <span>{scopeText}</span>
        </div>
      </section>

      <section className="panel data-analysis-panel">
        {recordsQuery.isLoading ? <LoadingState label="正在读取数据分析记录" /> : null}
        {recordsQuery.isError ? <ErrorState error={recordsQuery.error} action={<button onClick={() => recordsQuery.refetch()}>重试</button>} /> : null}
        {!recordsQuery.isLoading && !recordsQuery.isError && view === "records" ? (
          <div className="table-wrap data-analysis-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>图片</th>
                  <th>记录</th>
                  <th>任务</th>
                  <th>AI 摘要</th>
                  <th>图片处理</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {!records.length ? (
                  <tr>
                    <td colSpan={6}>
                      <div className="empty-panel">
                        <ImageIcon size={22} aria-hidden="true" />
                        <strong>暂无 AI 检测记录</strong>
                        <span>完成一次 AI 检测后会自动出现在这里。</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  records.map((record) => {
                    const imageUrl = record.image_url || record.source_image?.url || "";
                    return (
                      <tr key={record.record_id}>
                        <td>
                          <button
                            className="analysis-thumb"
                            type="button"
                            disabled={!imageUrl}
                            onClick={() => setDetailRecordId(record.record_id)}
                          >
                            {imageUrl ? <img src={cacheUrl(imageUrl, String(record.updated_at || record.created_at || ""))} alt="" /> : <span>无图</span>}
                          </button>
                        </td>
                        <td className="data-analysis-record-cell">
                          <strong>{detailTitle(record)}</strong>
                          <span>{recordAuditText(record, { includeUpdated: true })}</span>
                        </td>
                        <td>{record.task?.name || record.task?.id || "AI 检测"}</td>
                        <td>{aiSummaryText(record.ai_summary)}</td>
                        <td>{processingSummaryText(record.image_processing_summary)}</td>
                        <td>
                          <div className="row-actions">
                            <button className="secondary compact-action" type="button" onClick={() => setDetailRecordId(record.record_id)}>
                              <Eye size={15} aria-hidden="true" />
                              详情
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        ) : null}
        {!recordsQuery.isLoading && !recordsQuery.isError && view === "processing" ? (
          <div className="image-processing-view">
            {!processingReviewRecords.length ? (
              <div className="empty-panel">
                <ImageIcon size={22} aria-hidden="true" />
                <strong>暂无任务实拍 review 记录</strong>
                <span>任务执行产生 AI 检测和 AI mask bbox 后会自动出现在这里。</span>
              </div>
            ) : (
              <>
                <div className="image-processing-view-head">
                  <div>
                    <strong>{processingReviewRecords.length} 张任务实拍图</strong>
                    <span>左侧 AI 检测结果，右侧 AI mask 推导 bbox；中间产物默认折叠。</span>
                  </div>
                  {Number(processingSummary.active || 0) > 0 ? <span className="pill neutral">后台自动刷新中</span> : null}
                </div>
                <div className="image-processing-review-list">
                  {processingReviewRecords.map((record) => (
                    <ImageProcessingReviewUnit record={record} key={record.record_id} onOpenRecord={setDetailRecordId} />
                  ))}
                </div>
              </>
            )}
          </div>
        ) : null}
      </section>

      {detailRecordId ? (
        <DataAnalysisDetailModal
          recordId={detailRecordId}
          onClose={() => setDetailRecordId("")}
        />
      ) : null}
    </section>
  );
}
