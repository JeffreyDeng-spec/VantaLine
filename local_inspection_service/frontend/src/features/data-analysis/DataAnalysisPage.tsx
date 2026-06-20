import { useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, CheckSquare, Eye, Image as ImageIcon, ListChecks, Play, RefreshCw, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { hasPermission } from "../../app/permissions";
import {
  getDataAnalysisRecord,
  getDataAnalysisRecords,
  locateDataAnalysisRecord,
  locateDataAnalysisRecords,
  queryKeys
} from "../../api/queries";
import type {
  DataAnalysisAiSummary,
  DataAnalysisComparisonSummary,
  DataAnalysisLocateRun,
  DataAnalysisRecord,
  DataAnalysisTaskGroup
} from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { formatRecordTime, recordAuditText } from "../../utils/format";
import { useAuth } from "../auth/auth-context";

type LocateTarget = { ids: string[]; mode: "one" | "selected" | "visible" };

function cacheUrl(url = "", token = "") {
  if (!url) return "";
  const suffix = token || String(Date.now());
  return `${url}${url.includes("?") ? "&" : "?"}t=${encodeURIComponent(suffix)}`;
}

function statusLabel(value = "") {
  const labels: Record<string, string> = {
    same: "一致",
    different: "有差异",
    completed: "已定位",
    failed: "定位失败",
    unavailable: "服务不可用",
    stopped: "已停止",
    running: "运行中",
    queued: "排队中"
  };
  return labels[value] || value || "未定位";
}

function compareTone(summary: DataAnalysisComparisonSummary | null | undefined): "neutral" | "ok" | "warn" | "fail" {
  if (summary?.status === "same") return "ok";
  if (summary?.status === "different") return "warn";
  if (summary?.status) return "fail";
  return "neutral";
}

function aiSummaryText(summary: DataAnalysisAiSummary | null | undefined) {
  if (!summary) return "-";
  const stateText = summary.passed ? "通过" : "不通过";
  const present = Number(summary.present_count || 0);
  const missing = Number(summary.missing_count || 0);
  const mismatch = Number(summary.count_mismatch_count || 0);
  return `${stateText} · 命中 ${present} · 缺失 ${missing}${mismatch ? ` · 数量 ${mismatch}` : ""}`;
}

function locateSummaryText(record: DataAnalysisRecord | null | undefined) {
  const latest = record?.latest_locateanything_run || {};
  if (!record?.locateanything_run_count) return "未定位";
  if (latest.status === "completed") {
    return `${latest.overall_pass ? "通过" : "不通过"} · ${Number(latest.box_count || 0)} 框 · ${Number(latest.latency_ms || 0)} ms`;
  }
  return latest.error || statusLabel(latest.status);
}

function runSummaryText(run: DataAnalysisLocateRun | null | undefined) {
  if (!run?.run_id) return "未定位";
  if (run.status === "completed") {
    return `${run.overall_pass ? "通过" : "不通过"} · ${Number(run.box_count || 0)} 框 · ${Number(run.latency_ms || 0)} ms`;
  }
  return run.error || statusLabel(run.status);
}

function comparisonText(summary: DataAnalysisComparisonSummary | null | undefined) {
  const parts = [statusLabel(summary?.status)];
  const differenceCount = Number(summary?.difference_count);
  if (Number.isFinite(differenceCount) && summary?.status) parts.push(`差异 ${differenceCount}`);
  return parts.join(" · ");
}

function latestRun(record: DataAnalysisRecord | null | undefined) {
  const runs = Array.isArray(record?.locateanything_runs) ? record.locateanything_runs.filter(Boolean) : [];
  return runs.length ? runs[runs.length - 1] : record?.latest_locateanything_run || {};
}

function aiImageUrl(record: DataAnalysisRecord | null | undefined) {
  const result = (record?.ai_detection_result || {}) as Record<string, unknown>;
  return String(result.annotated_url || result.preview_url || result["output_url"] || record?.image_url || record?.source_image?.url || "");
}

function locateImageUrl(record: DataAnalysisRecord | null | undefined, run: DataAnalysisLocateRun | null | undefined) {
  return run?.overlay_url || record?.latest_locateanything_run?.overlay_url || "";
}

function detailTitle(record: DataAnalysisRecord | null | undefined) {
  return record?.source_image?.filename || record?.record_id || "数据分析记录";
}

function taskLabel(task: DataAnalysisTaskGroup) {
  return `${task.name || task.id} (${Number(task.count || 0)})`;
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

function DataAnalysisDetailModal({
  recordId,
  onClose,
  onLocate
}: {
  recordId: string;
  onClose: () => void;
  onLocate: (target: LocateTarget) => void;
}) {
  const auth = useAuth();
  const canLocate = hasPermission(auth.user, "locate_anything");
  const canViewDiagnostics = auth.user.role === "admin";
  const detailQuery = useQuery({
    queryKey: queryKeys.dataAnalysisRecord(recordId),
    queryFn: () => getDataAnalysisRecord(recordId)
  });
  const record = detailQuery.data?.record || null;
  const run = latestRun(record);
  const comparison = record?.comparison_summary || {};
  const aiSummary = record?.ai_summary || {};
  const scope = record?.required_accessory_scope?.required_accessories || [];
  const aiUrl = aiImageUrl(record);
  const locateUrl = locateImageUrl(record, run);
  const token = String(run.run_id || record?.updated_at || record?.record_id || Date.now());

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel wide data-analysis-detail-modal" role="dialog" aria-modal="true" aria-label="数据分析详情">
        <div className="modal-head">
          <div>
            <p className="eyebrow">数据分析</p>
            <h2>{detailTitle(record)}</h2>
          </div>
          <div className="modal-head-actions">
            {record ? (
              <button
                className="secondary compact-action"
                type="button"
                disabled={!canLocate}
                onClick={() => onLocate({ ids: [record.record_id], mode: "one" })}
              >
                <Play size={15} aria-hidden="true" />
                定位本条
              </button>
            ) : null}
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
                  <label>LocateAnything</label>
                  <strong>{runSummaryText(run)}</strong>
                </div>
                <div>
                  <label>对比</label>
                  <strong className={`status-text ${compareTone(comparison)}`}>{comparisonText(comparison)}</strong>
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
                  title="LocateAnything 框选图"
                  url={locateUrl}
                  placeholder={run?.run_id ? run.error || "本次定位未生成框选图" : "尚未运行 LocateAnything"}
                  rows={[
                    { label: "状态", value: runSummaryText(run) },
                    { label: "运行", value: run?.created_at ? formatRecordTime(run.created_at) : "未运行" },
                    { label: "诊断", value: canViewDiagnostics ? run?.diagnostic_url || "-" : "" }
                  ]}
                  token={token}
                />
              </div>

              {comparison.differences?.length ? (
                <div className="data-analysis-diff-list">
                  <strong>差异明细</strong>
                  <div>
                    {comparison.differences.slice(0, 12).map((item) => {
                      const delta = Number(item.delta || 0);
                      return (
                        <span key={`${item.accessory_id || item.label}-${delta}`}>
                          {item.label || item.accessory_id || "未命名"}
                          <small>
                            AI {Number(item.ai_count || 0)} / LA {Number(item.locateanything_count || 0)} / {delta > 0 ? `+${delta}` : delta}
                          </small>
                        </span>
                      );
                    })}
                  </div>
                </div>
              ) : null}

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
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const canLocate = hasPermission(auth.user, "locate_anything");
  const [taskId, setTaskId] = useState("");
  const [selectedRecordIds, setSelectedRecordIds] = useState<Set<string>>(() => new Set());
  const [detailRecordId, setDetailRecordId] = useState("");
  const [runningMode, setRunningMode] = useState<LocateTarget["mode"] | "">("");
  const selectAllRef = useRef<HTMLInputElement | null>(null);

  const recordsQuery = useQuery({
    queryKey: queryKeys.dataAnalysisRecords(auth.dataUserId, taskId),
    queryFn: () => getDataAnalysisRecords(auth, { taskId, limit: 200 })
  });

  const records = recordsQuery.data?.records || [];
  const taskOptions = recordsQuery.data?.tasks || [];
  const batchLimit = Number(recordsQuery.data?.batch_limit || 25);
  const total = Number(recordsQuery.data?.total || records.length);
  const selectedRecords = useMemo(
    () => records.filter((record) => selectedRecordIds.has(record.record_id)),
    [records, selectedRecordIds]
  );
  const allVisibleSelected = Boolean(records.length) && records.every((record) => selectedRecordIds.has(record.record_id));
  const someVisibleSelected = records.some((record) => selectedRecordIds.has(record.record_id));

  useEffect(() => {
    const visibleIds = new Set(records.map((record) => record.record_id));
    setSelectedRecordIds((current) => new Set(Array.from(current).filter((id) => visibleIds.has(id))));
  }, [records]);

  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = someVisibleSelected && !allVisibleSelected;
  }, [allVisibleSelected, someVisibleSelected]);

  const locateMutation = useMutation({
    mutationFn: async (target: LocateTarget) => {
      const ids = Array.from(new Set(target.ids.filter(Boolean)));
      if (!ids.length) throw new Error("请先选择记录。");
      if (ids.length > batchLimit) throw new Error(`一次最多处理 ${batchLimit} 条。`);
      setRunningMode(target.mode);
      if (target.mode === "one" && ids.length === 1) {
        return locateDataAnalysisRecord(ids[0], {});
      }
      return locateDataAnalysisRecords({ record_ids: ids });
    },
    onSuccess: async (_result, target) => {
      notify({ title: target.ids.length > 1 ? "批量定位完成" : "定位完成", tone: "success" });
      await queryClient.invalidateQueries({ queryKey: queryKeys.dataAnalysisRecords(auth.dataUserId, taskId) });
      await Promise.all(
        target.ids.map((id) => queryClient.invalidateQueries({ queryKey: queryKeys.dataAnalysisRecord(id) }))
      );
    },
    onError: (error) => {
      notify({ title: "定位失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    },
    onSettled: () => setRunningMode("")
  });

  function toggleRecord(recordId: string, checked: boolean) {
    setSelectedRecordIds((current) => {
      const next = new Set(current);
      if (checked) next.add(recordId);
      else next.delete(recordId);
      return next;
    });
  }

  function toggleVisible(checked: boolean) {
    setSelectedRecordIds((current) => {
      const next = new Set(current);
      records.forEach((record) => {
        if (checked) next.add(record.record_id);
        else next.delete(record.record_id);
      });
      return next;
    });
  }

  const locateBusy = locateMutation.isPending;
  const visibleLimited = records.length > batchLimit;
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
          <p className="page-desc">复核 AI 检测记录，并运行 LocateAnything 对比保存的定位结果。</p>
        </div>
        <div className="page-head-actions">
          <strong className="pill neutral">{selectedRecords.length} 已选</strong>
          <button className="secondary compact-action" type="button" onClick={() => recordsQuery.refetch()} disabled={recordsQuery.isFetching}>
            <RefreshCw size={16} aria-hidden="true" />
            刷新
          </button>
        </div>
      </header>

      <div className="metric-grid four data-analysis-metrics">
        <MetricCard label="记录" value={String(total)} detail={records.length === total ? "当前范围" : `已加载 ${records.length}`} />
        <MetricCard label="任务" value={String(taskOptions.length)} detail="AI 检测来源" />
        <MetricCard label="已定位" value={String(records.filter((record) => record.locateanything_run_count).length)} detail="有保存结果" />
        <MetricCard
          label="LocateAnything"
          value={recordsQuery.data?.locateanything?.configured ? "已配置" : "未配置"}
          tone={recordsQuery.data?.locateanything?.configured ? "ok" : "warn"}
          detail={canLocate ? `批量上限 ${batchLimit}` : "当前账号无定位权限"}
        />
      </div>

      <section className="panel data-analysis-toolbar">
        <label className="toolbar-field">
          <span>任务</span>
          <select
            value={taskId}
            onChange={(event) => {
              setTaskId(event.currentTarget.value);
              setSelectedRecordIds(new Set());
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
        <div className="data-analysis-actions">
          <button
            className="primary compact-action"
            type="button"
            disabled={!canLocate || locateBusy || selectedRecords.length === 0}
            onClick={() => locateMutation.mutate({ ids: selectedRecords.map((record) => record.record_id), mode: "selected" })}
          >
            <CheckSquare size={16} aria-hidden="true" />
            定位已选
          </button>
          <button
            className="secondary compact-action"
            type="button"
            disabled={!canLocate || locateBusy || records.length === 0 || visibleLimited}
            title={visibleLimited ? `当前列表超过批量上限 ${batchLimit} 条，请先筛选或选择记录。` : "定位当前筛选列表"}
            onClick={() => locateMutation.mutate({ ids: records.map((record) => record.record_id), mode: "visible" })}
          >
            <ListChecks size={16} aria-hidden="true" />
            定位当前列表
          </button>
          {locateBusy ? <span className="hint">定位中：{runningMode === "selected" ? "已选记录" : runningMode === "visible" ? "当前列表" : "单条记录"}</span> : null}
        </div>
      </section>

      <section className="panel data-analysis-panel">
        {recordsQuery.isLoading ? <LoadingState label="正在读取数据分析记录" /> : null}
        {recordsQuery.isError ? <ErrorState error={recordsQuery.error} action={<button onClick={() => recordsQuery.refetch()}>重试</button>} /> : null}
        {!recordsQuery.isLoading && !recordsQuery.isError ? (
          <div className="table-wrap data-analysis-table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="select-cell">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      aria-label="选择当前列表"
                      checked={allVisibleSelected}
                      onChange={(event) => toggleVisible(event.currentTarget.checked)}
                    />
                  </th>
                  <th>图片</th>
                  <th>记录</th>
                  <th>任务</th>
                  <th>AI 摘要</th>
                  <th>LocateAnything</th>
                  <th>对比</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {!records.length ? (
                  <tr>
                    <td colSpan={8}>
                      <div className="empty-panel">
                        <ImageIcon size={22} aria-hidden="true" />
                        <strong>暂无 AI 检测记录</strong>
                        <span>完成一次 AI 检测后会自动出现在这里。</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  records.map((record) => {
                    const comparison = record.comparison_summary || {};
                    const latest = record.latest_locateanything_run || {};
                    const compareStatus = comparison.status || latest.status || "";
                    const imageUrl = record.image_url || record.source_image?.url || latest.overlay_url || "";
                    return (
                      <tr key={record.record_id}>
                        <td className="select-cell">
                          <input
                            type="checkbox"
                            aria-label="选择记录"
                            checked={selectedRecordIds.has(record.record_id)}
                            onChange={(event) => toggleRecord(record.record_id, event.currentTarget.checked)}
                          />
                        </td>
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
                        <td>{locateSummaryText(record)}</td>
                        <td>
                          <span className={`pill ${compareTone(comparison)}`}>{statusLabel(compareStatus)}</span>
                        </td>
                        <td>
                          <div className="row-actions">
                            <button
                              className="secondary compact-action"
                              type="button"
                              disabled={!canLocate || locateBusy}
                              onClick={() => locateMutation.mutate({ ids: [record.record_id], mode: "one" })}
                            >
                              <Play size={15} aria-hidden="true" />
                              定位
                            </button>
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
      </section>

      {detailRecordId ? (
        <DataAnalysisDetailModal
          recordId={detailRecordId}
          onClose={() => setDetailRecordId("")}
          onLocate={(target) => locateMutation.mutate(target)}
        />
      ) : null}
    </section>
  );
}
