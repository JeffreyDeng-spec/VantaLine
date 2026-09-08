import { useEffect, useId, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { GuideOverlay, type Guide } from "./LabelExtraction";

type Result = { id: string; version: number; status: string; reason: string; box?: number[]; media: Record<string, string> };
type Item = { id: string; ordinal: number; status: string; review_reason: string; size: number[]; media: Record<string, string>; result: Result | null };
type Job = { id: string; status: string; stage: string; reason: string; counts: Record<string, number>; items: Item[]; diagnostics: unknown };
const statusCopy: Record<string, string> = { candidate: "已接纳裁剪", excluded: "已排除", needs_confirmation: "待确认", pending: "等待处理" };

function Review({ item, jobId, close, done }: { item: Item; jobId: string; close: () => void; done: () => void }) {
  const box = item.result?.box || [0, 0, 1, 1];
  const [guide, setGuide] = useState<Guide>([box[0], box[1], box[2] - box[0], box[3] - box[1]]);
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const clipId = useId();
  const retryIdentity = useRef(crypto.randomUUID());
  const source = item.media.normalized;
  const validGuide = guide.every(v => Number.isFinite(v) && v >= 0 && v <= 1) && guide[2] > 0 && guide[3] > 0 && guide[0] + guide[2] <= 1 && guide[1] + guide[3] <= 1;
  const change = (value: Guide) => { setGuide(value); setAcknowledged(false); };
  const act = async (action: "confirm" | "exclude" | "retry") => {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const endpoint = `/api/text-inspection/document-imports/${jobId}/items/${item.id}/${action === "retry" ? "retry" : "review"}`;
      await apiClient.post(endpoint, { version: item.result?.version ?? -1, action,
        box: [guide[0], guide[1], guide[0] + guide[2], guide[1] + guide[3]], request_id: retryIdentity.current });
      done(); close();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const [w, h] = item.size;
  return <div className="text-standard-modal-backdrop" role="presentation" onMouseDown={() => !busy && close()}>
    <section className="text-standard-modal" role="dialog" aria-modal="true" aria-label="确认文档标签裁剪" onMouseDown={e => e.stopPropagation()} style={{ width: "min(1100px, 96vw)", maxHeight: "94vh", overflow: "auto", padding: 16 }}>
      <header><h3>图片 {item.ordinal} · 只保留标签本身</h3><button type="button" disabled={busy} onClick={close}>关闭</button></header>
      <p>{item.review_reason || item.result?.reason || "拖动框或修改位置和大小；调整不会调用模型。"}</p>
      {source ? <>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
          <div style={{ position: "relative", height: "50vh" }}><img src={source} alt="文档原始图片，含外围说明" style={{ width: "100%", height: "100%", objectFit: "contain" }} /><GuideOverlay value={guide} onChange={change} disabled={busy || !!item.review_reason} /></div>
          <div><svg role="img" aria-label="待确认裁剪预览" viewBox={`${guide[0] * w} ${guide[1] * h} ${guide[2] * w} ${guide[3] * h}`} style={{ width: "100%", height: "50vh", background: "white" }}><defs><clipPath id={clipId}><rect x={guide[0] * w} y={guide[1] * h} width={guide[2] * w} height={guide[3] * h} /></clipPath></defs><image href={source} width={w} height={h} clipPath={`url(#${clipId})`} /></svg></div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{["左边距", "上边距", "宽", "高"].map((label, i) => <label key={label}>{label} % <input aria-label={label} type="number" min={0} max={100} step={0.1} value={Number((guide[i] * 100).toFixed(2))} disabled={busy || !!item.review_reason} onChange={e => { const next: Guide = [...guide]; next[i] = Number(e.target.value) / 100; change(next); }} style={{ width: 80 }} /></label>)}</div>
        <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}><input type="checkbox" style={{ width: 18, height: 18, flexShrink: 0 }} checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} disabled={busy} />我已核实标签完整，所有文字和图标均保留，没有外围说明或其他标签</label>
        <p><a href={source} target="_blank" rel="noreferrer">打开原图大图</a>{item.result?.media.crop ? <> · <a href={item.result.media.crop} target="_blank" rel="noreferrer">打开服务器实际裁剪</a></> : null}</p>
      </> : <p>此对象不能安全预览。请查看原文档并提供完整渲染图，不能直接启用底层图片。</p>}
      {error ? <p role="alert">{error}</p> : null}
      <footer style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <button type="button" disabled={busy || !source || !!item.review_reason || !acknowledged || !validGuide} onClick={() => void act("confirm")}>确认裁剪并加入候选</button>
        <button type="button" disabled={busy || item.status === "candidate"} onClick={() => void act("exclude")}>排除此图片</button>
        <button type="button" disabled={busy || !!item.review_reason || item.status === "candidate"} onClick={() => void act("retry")}>新尝试（最多两次模型调用）</button>
      </footer>
    </section>
  </div>;
}

export function DocumentImportProgress({ jobId }: { jobId: string }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Item | null>(null);
  const query = useQuery({ queryKey: ["document-import", jobId, open], queryFn: () => apiClient.get<Job>(`/api/text-inspection/document-imports/${jobId}?diagnostics=${open}`), refetchInterval: 2000 });
  const job = query.data;
  const signature = job ? JSON.stringify([job.status, job.items.map(v => [v.id, v.result?.version])]) : "";
  useEffect(() => { if (signature) void client.invalidateQueries({ queryKey: ["text-inspection", "standard"] }); }, [signature, client]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setSelected(null); setOpen(false); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return <div className="document-import-progress">
    {query.isError ? <p role="alert">处理状态查询失败；不会重新导入或重发模型请求。<button type="button" onClick={() => void query.refetch()}>重新查询</button></p> : null}
    <p aria-live="polite">{job ? `${job.stage} · 接纳 ${job.counts.candidate} / 排除 ${job.counts.excluded} / 待确认 ${job.counts.needs_confirmation} / 等待 ${job.counts.pending}` : "查询文档处理进度…"}</p>
    {job?.reason ? <p>{job.reason}</p> : null}
    <button type="button" onClick={() => setOpen(v => !v)}>{open ? "收起" : "查看图片处理结果"}</button>
    {open && job ? <div>
      <div className="text-standard-asset-grid">{job.items.map(item => <article className="text-standard-asset-card" key={item.id}>
        {item.media.input ? <img src={item.result?.media.crop || item.media.input} alt={`文档图片 ${item.ordinal}`} loading="lazy" style={{ width: "100%", height: 150, objectFit: "contain" }} /> : <p>组合/矢量对象，无安全预览</p>}
        <p>{item.ordinal} · {statusCopy[item.status]}<br />{item.review_reason || item.result?.reason}</p>
        <button type="button" disabled={job.status === "processing"} onClick={() => setSelected(item)}>查看与调整</button>
      </article>)}</div>
      <details><summary>Raw Output（文档处理诊断）</summary><pre style={{ whiteSpace: "pre-wrap", maxHeight: 300, overflow: "auto" }}>{JSON.stringify(job.diagnostics, null, 2).slice(0, 20000)}</pre></details>
    </div> : null}
    {selected ? <Review key={`${selected.id}-${selected.result?.version}`} item={selected} jobId={jobId} close={() => setSelected(null)} done={() => { void query.refetch(); void client.invalidateQueries({ queryKey: ["text-inspection"] }); }} /> : null}
  </div>;
}
