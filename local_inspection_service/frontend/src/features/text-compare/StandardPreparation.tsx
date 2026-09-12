import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import "./standard-preparation.css";

type Element = { id: string; text: string; type: string; box: number[]; state: "keep" | "exclude" | "uncertain"; reason: string };
type Revision = { id: string; clean_url: string; elements: Element[]; reasons: string[] };
type Item = { id: string; ordinal: number; source_sha256: string; original_url: string; draft?: string; active?: string;
  revisions: Revision[]; attempt?: { state: string; elements?: Element[]; result?: { kind?: string; coverage_complete?: boolean }; diagnostics?: { recovery?: { reasons?: string[]; regions: { id: string; region_url?: string; ocr_url?: string }[] }; [key: string]: unknown } } };
type Progress = { job: { state?: string; reason?: string }; items: Item[] };
export type PreparationPreview = { id: string; url: string; title: string };
const phases: Record<string, string> = { recognizing: "提取文字与编码", classifying: "判断保留与排除", supplementing: "局部补识别", ready: "已启用", review: "待确认" };
const identity = (item: Item) => `${item.id}:${item.source_sha256}:${item.draft || ""}`;
const processingItem = (item: Item) => ["recognizing", "classifying", "supplementing"].includes(item.attempt?.state || "");
const needsReview = (item: Item) => item.attempt?.state === "review" && (!item.active || item.active !== item.draft);

function Review({ item, current, standardId, remaining, queued, onClose, onSaved, onSkip }: {
  item: Item; current?: Item; standardId: string; remaining: number; queued: boolean; onClose: () => void; onSaved: () => void; onSkip: () => void;
}) {
  const latest = item.revisions.find(r => r.id === item.draft);
  const [elements, setElements] = useState<Element[]>(latest?.elements || item.attempt?.elements || []);
  const [selected, setSelected] = useState("");
  const [dirty, setDirty] = useState(false);
  const [graphicsConfirmed, setGraphicsConfirmed] = useState(false);
  const [scale, setScale] = useState(1);
  const [preview, setPreview] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [aspect, setAspect] = useState(1);
  const dialog = useRef<HTMLDivElement>(null);
  const cache = useQueryClient();
  const stale = !current || identity(current) !== identity(item);
  const busy = !!current && processingItem(current);
  const save = useMutation({ mutationFn: () => apiClient.post(`/api/text-inspection/standards/${standardId}/preparation/${item.id}/confirm`, {
    source_sha256: item.source_sha256, expected_draft: item.draft ?? null, elements, allow_graphics_only: graphicsConfirmed
  }), onSuccess: async () => { await cache.invalidateQueries({ queryKey: ["text-inspection"] }); onSaved(); } });
  const close = () => { if (!save.isPending && (!dirty || window.confirm("修改尚未保存，确定关闭并放弃修改？"))) onClose(); };
  const closeRef = useRef(close); closeRef.current = close;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closeRef.current(); }
      if (event.key === "Tab") {
        const nodes = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), summary, [tabindex="0"]') || []).filter(e => e.getClientRects().length);
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.body.style.overflow = overflow; document.removeEventListener("keydown", keydown); if (previous?.isConnected) previous.focus(); };
  }, []);
  const update = (id: string, value: Partial<Element>) => { setDirty(true); setGraphicsConfirmed(false); setElements(rows => rows.map(e => e.id === id ? { ...e, ...value } : e)); };
  const target = elements.find(e => e.id === selected);
  const disabled = busy || save.isPending || stale;
  const uncertain = elements.filter(e => e.state === "uncertain").length;
  const noRequired = !elements.some(e => e.state === "keep");
  const graphicsEligible = item.attempt?.result?.kind === "label_design" && item.attempt?.result?.coverage_complete === true && item.attempt?.diagnostics?.ok === true && !item.attempt?.diagnostics?.failure && !item.attempt?.diagnostics?.timed_out && !item.attempt?.diagnostics?.recovery?.reasons?.length;
  return <div className="standard-review-backdrop"><div ref={dialog} className="standard-review-dialog" role="dialog" aria-modal="true" aria-label={`第 ${item.ordinal} 张标签元素确认`} tabIndex={-1}>
    <header><div><strong>第 {item.ordinal} 张 · {queued ? "确认标签元素" : "查看与编辑标签"}</strong><small>{queued ? `按原图顺序确认 · 剩余 ${remaining} 张` : "修改后保存为新版本，不覆盖历史记录"}</small></div><button type="button" aria-label="关闭元素编辑" disabled={save.isPending} onClick={close}>×</button></header>
    <div className="standard-review-tools"><span>点击框切换：<b className="keep">绿＝保留</b> / <b className="exclude">红＝排除</b> / <b className="uncertain">橙＝待定（首次点击保留）</b></span><div>
      <button type="button" aria-label="缩小元素图" disabled={scale <= 1} onClick={() => setScale(v => Math.max(1, v - .5))}>−</button><output>{scale * 100}%</output><button type="button" aria-label="放大元素图" disabled={scale >= 4} onClick={() => setScale(v => v + .5)}>＋</button>
      {latest ? <button type="button" onClick={() => { setPreview(v => !v); setLoaded(false); }}>{preview ? "返回原图编辑" : "查看已保存清理图"}</button> : null}
    </div></div>
    <div className="standard-review-viewport"><div className="standard-review-image" style={{ width: `min(${scale * 100}%, ${scale * 48 * aspect}dvh)` }}>
      <img src={preview && latest ? latest.clean_url : item.original_url} alt={preview ? "已保存清理图（不含未保存修改）" : "标准原图与可点击元素框"} onLoad={event => { setAspect(event.currentTarget.naturalWidth / event.currentTarget.naturalHeight); setLoaded(true); }} onError={() => setLoaded(false)} />
      {!preview && loaded ? elements.map(e => <button key={e.id} type="button" className={`standard-element-box ${e.state}`} disabled={disabled}
        aria-label={`${e.id} ${e.text}：${e.state === "keep" ? "已保留，点击排除" : e.state === "exclude" ? "已排除，点击保留" : "待定，点击保留"}`} aria-pressed={e.state === "keep"}
        title={`${e.id} · ${e.text} · ${e.reason}`} style={{ left: `${e.box[0] * 100}%`, top: `${e.box[1] * 100}%`, width: `${e.box[2] * 100}%`, height: `${e.box[3] * 100}%` }}
        onClick={() => { setSelected(e.id); update(e.id, { state: e.state === "keep" ? "exclude" : "keep", reason: e.state === "keep" ? "人工确认：标签外围说明" : "人工确认：标签内容" }); }}><span>{e.id} {e.state === "keep" ? "✓" : e.state === "exclude" ? "×" : "?"}</span></button>) : null}
    </div></div>
    {!loaded ? <p role="status">图片加载中或加载失败，请检查网络后重新打开；暂不可保存。</p> : null}
    <div className="standard-review-details">
      {noRequired && !uncertain ? graphicsEligible ? <label><input type="checkbox" checked={graphicsConfirmed} disabled={disabled} onChange={event => { setGraphicsConfirmed(event.currentTarget.checked); setDirty(true); }} />确认主体仅含图形，保存到标准库（当前不支持文字对比）</label> : <p role="alert">没有可核对元素且识别未完整完成，不能将识别失败当作纯图形标准。</p> : null}
      {target ? <label>{target.id} 识别内容<input aria-label="选中元素识别内容" disabled={disabled} value={target.text} onChange={event => update(target.id, { text: event.currentTarget.value })} /></label> : <span>点击元素框即可编辑；放大后可更容易选中细小文字。</span>}
      <details><summary>文字与范围调整</summary>{elements.map(e => <div key={e.id} className="standard-element-fields"><strong>{e.id} · {e.state === "keep" ? "保留" : e.state === "exclude" ? "排除" : "待定"}</strong>
        <label>识别内容<input disabled={disabled} value={e.text} onChange={event => update(e.id, { text: event.currentTarget.value })} /></label>
        <label>依据<input disabled={disabled} value={e.reason} onChange={event => update(e.id, { reason: event.currentTarget.value })} /></label>
        {["左", "上", "宽", "高"].map((name, i) => <label key={name}>{name}<input type="number" min="0" max="1" step="0.001" disabled={disabled} value={e.box[i]} onChange={event => update(e.id, { box: e.box.map((v, j) => i === j ? Number(event.currentTarget.value) : v) })} /></label>)}
      </div>)}</details>
      {latest?.reasons.length ? <p>待确认原因：{latest.reasons.join("、")}</p> : null}
      <details><summary>Raw Output（默认折叠）</summary>{item.attempt?.diagnostics?.recovery?.regions.map(r => <div key={r.id}>{r.region_url ? <img style={{ maxWidth: "100%" }} src={r.region_url} alt={`${r.id} 补识别区域`} /> : null}{r.ocr_url ? <img style={{ maxWidth: "100%" }} src={r.ocr_url} alt={`${r.id} 局部 OCR 元素`} /> : null}</div>)}<pre>{JSON.stringify(item.attempt?.diagnostics, null, 2)?.slice(0, 20000)}</pre></details>
      {stale ? <p role="alert">版本已变化，未覆盖你的修改。请关闭后重新打开查看最新版本。</p> : null}
      {save.error ? <p role="alert">{(save.error as Error).message}。修改仍保留，请调整后再保存。</p> : null}
    </div>
    <footer><span>{busy ? phases[current?.attempt?.state || ""] : uncertain ? `还有 ${uncertain} 个橙色框待确认` : "保存即确认这是完整标签且元素归属正确；图形未检查。"}</span>
      {queued && remaining > 1 ? <button type="button" disabled={save.isPending} onClick={() => { if (!dirty || window.confirm("跳过此张将放弃未保存修改，之后仍可继续确认。")) onSkip(); }}>先看下一张</button> : null}
      <button type="button" disabled={save.isPending} onClick={close}>{queued ? "稍后继续" : "取消"}</button>
      <button className="primary" type="button" disabled={disabled || !loaded || uncertain > 0 || (noRequired && !(graphicsEligible && graphicsConfirmed))} onClick={() => save.mutate()}>{save.isPending ? "保存中…" : queued ? "确认保存并继续" : "保存"}</button>
    </footer>
  </div></div>;
}

export function StandardPreparation({ standardId, activation, preview, onPreviewHandled, onZoom, confirmed, disabled, onActivate }: {
  standardId: string; activation: number; preview: PreparationPreview | null; onPreviewHandled: () => void;
  onZoom: (url: string, title: string) => void; confirmed: boolean; disabled: boolean; onActivate: () => void;
}) {
  const cache = useQueryClient();
  const [modal, setModal] = useState<{ item: Item; queued: boolean } | null>(null);
  const [paused, setPaused] = useState(false);
  const [handled, setHandled] = useState<string[]>([]);
  const capability = useQuery({ queryKey: ["text-inspection", "preparation-capabilities"], queryFn: () => apiClient.get<{ enabled: boolean }>("/api/text-inspection/preparation-capabilities") });
  const query = useQuery({ queryKey: ["text-inspection", "preparation", standardId], enabled: capability.data?.enabled === true,
    queryFn: () => apiClient.get<Progress>(`/api/text-inspection/standards/${standardId}/preparation`),
    refetchInterval: q => q.state.data?.job.state === "processing" ? 2000 : false });
  useEffect(() => { setPaused(false); }, [activation]);
  const items = [...(query.data?.items || [])].sort((a, b) => a.ordinal - b.ordinal);
  const pending = items.filter(i => needsReview(i) && !handled.includes(identity(i)));
  const processing = query.data?.job.state === "processing";
  useEffect(() => {
    if (preview && (capability.isError || (capability.isSuccess && (!capability.data.enabled || query.isSuccess)))) {
      const item = query.data?.items.find(i => i.id === preview.id);
      setPaused(true);
      if (capability.data?.enabled && item?.attempt) setModal({ item, queued: false });
      else onZoom(preview.url, preview.title);
      onPreviewHandled();
    }
  }, [preview, capability.isSuccess, capability.isError, capability.data, query.isSuccess, query.data, onPreviewHandled, onZoom]);
  useEffect(() => { if (!preview && !modal && !paused && !processing && pending.length) setModal({ item: pending[0], queued: true }); }, [preview, modal, paused, processing, pending]);
  const published = items.map(i => i.active || "").join(",");
  useEffect(() => { if (published) {
    void cache.invalidateQueries({ queryKey: ["text-inspection", "standard", standardId] });
    void cache.invalidateQueries({ queryKey: ["text-inspection", "standards"] });
  } }, [published, standardId, cache]);
  if (!capability.data?.enabled) return null;
  return <div className="standard-preparation-status">
    {processing ? <span role="status" aria-live="polite">启用中：{items.filter(i => i.active).length}/{items.length} 张可用 · {phases[items.find(processingItem)?.attempt?.state || ""] || "排队中"}（可离开后恢复）</span> : pending.length ? <button type="button" onClick={() => { setPaused(false); setModal({ item: pending[0], queued: true }); }}>继续确认 · {pending.length} 张</button> : query.data?.job.state ? <span role="status">标准准备完成 · 图形未检查</span> : null}
    {confirmed && items.some(i => !i.attempt) ? <button type="button" disabled={disabled || processing} onClick={onActivate}>启用标准</button> : null}
    {query.data?.job.reason ? <p>{query.data.job.reason}</p> : null}
    {query.error ? <p role="alert">读取准备状态失败，请重试。<button type="button" onClick={() => void query.refetch()}>重试</button></p> : null}
    {modal ? <Review key={`${modal.item.id}:${modal.item.draft || ""}`} item={modal.item} current={items.find(i => i.id === modal.item.id)} standardId={standardId} remaining={pending.length} queued={modal.queued}
      onSkip={() => { const index = pending.findIndex(i => i.id === modal.item.id); const next = pending[(index + 1) % pending.length]; if (next) setModal({ item: next, queued: true }); }}
      onClose={() => { setModal(null); setPaused(true); }} onSaved={() => { setHandled(v => [...v, identity(modal.item)]); setModal(null); }} /> : null}
  </div>;
}
