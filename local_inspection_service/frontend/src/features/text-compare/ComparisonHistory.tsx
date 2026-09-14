import { useEffect, useRef, useState } from "react";
import { History, ArrowLeft, RefreshCcw, X } from "lucide-react";
import { apiClient } from "../../api/client";
import { ComparisonDialog } from "./ComparisonDialog";
import { ComparisonResult, EvidenceImage, type SavedComparison } from "./ComparisonResult";
import "./comparison-history.css";

type Summary = {
  id: string; standard_id: string; created_at: number; status: string; decision: string;
  standard_revision_number?: number; display: { name?: string; material_code?: string; version_label?: string; ordinal?: number };
  metadata_source: string; execution_state: string; phase?: string; elapsed_ms?: number; preview_url?: string;
};
type Page = { items: Summary[]; next_cursor: string | null };
type Detail = SavedComparison & { history: Summary };
const states: Record<string, string> = { processing: "处理中", completed: "已完成", failed: "执行失败", timeout: "超时／中断", review: "待复核" };
const decisions: Record<string, string> = { MATCH: "未发现文字差异", DIFFERENCES: "发现疑似差异", REVIEW_REQUIRED: "需要复核" };
const phases: Record<string, string> = { queued: "排队", extracting_text: "提取文字", direct_matching: "直接核对", mapping_unmatched: "疑难对应", rereading_regions: "局部复读", transcribing_regions: "局部文字复读", verifying_saving: "验证保存", recognizing: "识别文字" };
function Caption({ row }: { row: Summary }) {
  return <><strong>{row.display?.name || row.standard_id}</strong><small>{row.display?.material_code || "物料信息未留存"} · {row.display?.version_label || "版本名未留存"} · 修订 {row.standard_revision_number ?? "未留存"}{row.display?.ordinal ? ` · 第 ${row.display.ordinal} 张` : ""}</small>
    {row.metadata_source !== "snapshot" ? <small>{row.metadata_source === "current" ? "名称为当前订单信息；图片与结果仍为当次证据" : "订单显示信息未留存"}</small> : null}</>;
}
export function ComparisonHistory({ owner }: { owner: string }) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const [q, setQ] = useState(""); const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [rows, setRows] = useState<Summary[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  const [selected, select] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [retry, setRetry] = useState(0);
  const [zoom, setZoom] = useState<{ src: string; alt: string } | null>(null);
  const [scale, setScale] = useState(1);
  const listAbort = useRef<AbortController | null>(null);
  const zoomTrigger = useRef<HTMLElement | null>(null);
  const zoomClose = useRef<HTMLButtonElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; listAbort.current?.abort(); }, []);
  useEffect(() => {
    if (content.current) content.current.inert = !!zoom;
    if (zoom) zoomClose.current?.focus(); else zoomTrigger.current?.focus();
  }, [zoom]);
  function showZoom(src: string, alt: string) { zoomTrigger.current = document.activeElement as HTMLElement; setScale(1); setZoom({ src, alt }); }
  async function load(cursor = "") {
    listAbort.current?.abort();
    const controller = new AbortController(); listAbort.current = controller;
    const epoch = ++generation.current;
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ q: search, result: filter, limit: "20", cursor });
      const page = await apiClient.get<Page>(`/api/text-inspection/history?${params}`, { signal: controller.signal });
      if (epoch !== generation.current) return;
      setRows(previous => cursor ? [...previous, ...page.items.filter(r => !previous.some(p => p.id === r.id))] : page.items);
      setNext(page.next_cursor);
    } catch (e) { if (!controller.signal.aborted && epoch === generation.current) setError((e as Error).message); }
    finally { if (epoch === generation.current) setLoading(false); }
  }
  useEffect(() => {
    if (!open) { generation.current++; listAbort.current?.abort(); return; }
    setRows([]); setNext(null); void load();
    return () => { generation.current++; listAbort.current?.abort(); };
    // A new filter starts a fresh list. Detail navigation never changes filters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, owner, search, filter]);
  useEffect(() => {
    if (!open || !selected) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    async function poll() {
      controller = new AbortController();
      try {
        const value = await apiClient.get<Detail>(`/api/text-inspection/history/${encodeURIComponent(selected)}`, { signal: controller.signal });
        if (disposed) return;
        if (value.id !== selected) throw new Error("历史记录标识不一致");
        setDetail(value); setDetailError("");
        setRows(previous => previous.map(r => r.id === selected ? { ...r, ...value.history } : r));
        if (value.history.execution_state === "processing") timer = setTimeout(poll, 1500);
      } catch (e) { if (!disposed) setDetailError((e as Error).message); }
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); };
  }, [open, selected, owner, retry]);
  function close() { zoomTrigger.current = null; setZoom(null); setOpen(false); }
  return <>
    <button className="text-history-entry" ref={trigger} type="button" onClick={() => { select(""); setDetail(null); setOpen(true); }}><History size={17} />历史记录</button>
    <ComparisonDialog className="comparison-history-dialog" open={open} title={selected ? "历史对比结果" : "文字检验历史记录"} startedAt={0} busy={false} phase="" notice="" onClose={close} trigger={trigger}>
      <div ref={content}>
        <div hidden={!!selected}>
          <form className="text-history-filters" onSubmit={e => { e.preventDefault(); setSearch(q.trim()); }}>
            <input aria-label="搜索订单或标准" value={q} onChange={e => setQ(e.target.value)} placeholder="搜索订单、物料或标准" maxLength={120} />
            <button type="submit">搜索</button>
            <select aria-label="按结果筛选" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">全部结果</option>{Object.entries(decisions).map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select>
            <button type="button" disabled={loading} onClick={() => void load()}>刷新</button>
          </form>
          <p>仅显示当前账户的标签文字对比；历史查看不会重新识别或计费。</p>
          <div className="text-history-list" aria-label="历史对比列表">
            {rows.map(row => <button type="button" className="text-history-row" key={row.id} onClick={() => { setDetail(null); setDetailError(""); select(row.id); }}>
              {row.preview_url ? <HistoryThumbnail key={row.preview_url} src={row.preview_url} /> : <span className="text-history-thumbnail">无预览</span>}
              <span className="text-history-description"><Caption row={row} /><time>{new Date(row.created_at * 1000).toLocaleString()}</time></span>
              <span className={`text-history-status ${row.execution_state}`}><strong>{states[row.execution_state] || row.status}</strong><small>{row.execution_state === "processing" ? phases[row.phase || ""] || "等待结果" : decisions[row.decision] || "结果未留存"}</small>{typeof row.elapsed_ms === "number" ? <small>{(row.elapsed_ms / 1000).toFixed(1)} 秒</small> : null}</span>
            </button>)}
            {!rows.length && !loading && !error ? <p className="text-standard-empty">暂无符合条件的对比记录</p> : null}
            {loading ? <p role="status">正在读取记录…</p> : null}
            {error ? <p role="alert">{error}<button type="button" onClick={() => void load(rows.length ? next || "" : "")}>重试</button></p> : null}
            {next ? <button type="button" disabled={loading} onClick={() => void load(next)}>加载更多</button> : null}
          </div>
        </div>
        {selected ? <div className="text-history-detail">
          <button type="button" onClick={() => { select(""); setDetail(null); }}><ArrowLeft size={16} />返回历史</button>
          {detailError ? <p role="alert">{detailError}<button onClick={() => setRetry(v => v + 1)}>重试读取</button></p> : null}
          {!detail && !detailError ? <p role="status">正在读取当次结果…</p> : null}
          {detail ? <><div className="text-history-caption"><Caption row={detail.history} /><time>{new Date(detail.history.created_at * 1000).toLocaleString()}</time><strong>{states[detail.history.execution_state]}</strong></div>
            {detail.history.execution_state === "processing" ? <p role="status"><RefreshCcw className="spin" />{phases[detail.history.phase || ""] || "等待结果"}；关闭不取消任务。</p> : <ComparisonResult key={selected} result={detail} onZoom={showZoom} />}
          </> : null}
        </div> : null}
      </div>
      {zoom ? <div className="text-history-zoom" role="region" aria-label="历史图片放大" onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setZoom(null); } }}>
        <header><strong>{zoom.alt}</strong><button onClick={() => setScale(v => Math.max(1, v - .5))}>缩小</button><span>{scale * 100}%</span><button onClick={() => setScale(v => Math.min(3, v + .5))}>放大</button><button ref={zoomClose} aria-label="关闭历史图片放大" onClick={() => setZoom(null)}><X /></button></header>
        <div><section style={{ width: `${scale * 100}%` }}><EvidenceImage key={zoom.src} src={zoom.src} alt={zoom.alt} /></section></div>
      </div> : null}
    </ComparisonDialog>
  </>;
}
function HistoryThumbnail({ src }: { src: string }) {
  const [failed, setFailed] = useState(false);
  return failed ? <span className="text-history-thumbnail">预览未留存</span> : <img className="text-history-thumbnail" src={src} alt="实拍缩略图" loading="lazy" onError={() => setFailed(true)} />;
}
