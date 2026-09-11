import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import "./standard-preparation.css";

type Element = { id: string; text: string; type: string; box: number[]; state: "keep" | "exclude" | "uncertain"; reason: string };
type Revision = { id: string; clean_url: string; overlay_url: string; elements: Element[]; reasons: string[]; human: boolean };
type Item = { id: string; ordinal: number; source_sha256: string; original_url: string; draft?: string; active?: string;
  revisions: Revision[]; attempt?: { state: string; elements?: Element[]; diagnostics?: { recovery?: { regions: { id: string; region_url?: string; ocr_url?: string }[] }; [key: string]: unknown } } };
type Progress = { job: { state?: string; reason?: string }; items: Item[] };
const phases: Record<string, string> = { recognizing: "提取文字与编码", classifying: "判断保留与排除", supplementing: "局部补识别漏检文字", ready: "已准备并启用", review: "需要人工确认" };

function Review({ item, standardId, onZoom }: { item: Item; standardId: string; onZoom: (url: string, title: string) => void }) {
  const latest = item.revisions.find(r => r.id === item.draft);
  const [elements, setElements] = useState<Element[]>(latest?.elements || item.attempt?.elements || []);
  const [confirmLabel, setConfirmLabel] = useState(false);
  const cache = useQueryClient();
  useEffect(() => { setElements(latest?.elements || item.attempt?.elements || []); setConfirmLabel(false); }, [item.draft, item.attempt?.state]);
  const save = useMutation({ mutationFn: () => apiClient.post(`/api/text-inspection/standards/${standardId}/preparation/${item.id}/confirm`, {
    source_sha256: item.source_sha256, expected_draft: item.draft ?? null, elements
  }), onSuccess: () => { void cache.invalidateQueries({ queryKey: ["text-inspection"] }); } });
  const update = (index: number, value: Partial<Element>) => { setConfirmLabel(false); setElements(current => current.map((e, i) => i === index ? { ...e, ...value } : e)); };
  const processing = ["recognizing", "classifying", "supplementing"].includes(item.attempt?.state || "");
  return <details className="standard-preparation-item">
    <summary>第 {item.ordinal} 张 · {phases[item.attempt?.state || ""] || "等待处理"}{item.active ? " · 有可用版本" : ""}</summary>
    <div className="standard-preparation-images">
      {[{ url: item.original_url, title: "原图" }, ...(latest ? [{ url: latest.overlay_url, title: "元素归属：绿保留／红排除／橙待定" }, { url: latest.clean_url, title: "清理预览" }] : [])].map(v =>
        <button type="button" key={v.title} onClick={() => onZoom(v.url, v.title)}><img src={v.url} alt={v.title} /><span>{v.title} · 点击放大</span></button>)}
    </div>
    {latest?.reasons.length ? <p role="status">待确认原因：{latest.reasons.join("、")}</p> : null}
    <div className="standard-preparation-elements">{elements.map((e, index) => <div key={e.id}>
      <strong>{e.id} · {e.type === "code" ? "编码" : "文字"}</strong>
      <label>识别内容<input disabled={processing || save.isPending} value={e.text} onChange={event => update(index, { text: event.currentTarget.value })} /></label>
      <span className={`element-state ${e.state}`}>{e.state === "keep" ? "已保留" : e.state === "exclude" ? "已排除" : "待确认"}</span>
      <button type="button" disabled={processing || save.isPending} onClick={() => update(index, { state: e.state === "keep" ? "exclude" : "keep" })}>{e.state === "keep" ? "改为排除" : "改为保留"}</button>
      <label>归属依据<input disabled={processing || save.isPending} value={e.reason} onChange={event => update(index, { reason: event.currentTarget.value })} /></label>
      <details><summary>调整元素范围（原图比例）</summary>{["左", "上", "宽", "高"].map((name, coordinate) => <label key={name}>{name}<input type="number" min="0" max="1" step="0.001" value={e.box[coordinate]} disabled={processing || save.isPending} onChange={event => update(index, { box: e.box.map((v, i) => i === coordinate ? Number(event.currentTarget.value) : v) })} /></label>)}</details>
    </div>)}</div>
    <label><input type="checkbox" checked={confirmLabel} disabled={processing || save.isPending} onChange={event => setConfirmLabel(event.currentTarget.checked)} />我已核对这是一个完整标签设计，保留内容正确，排除区域不属于标签。</label>
    <button type="button" disabled={processing || save.isPending || !confirmLabel || !elements.length || elements.some(e => e.state === "uncertain")} onClick={() => save.mutate()}>{save.isPending ? "保存中…" : "确认修改并启用新版本"}</button>
    {save.error ? <p role="alert">{(save.error as Error).message}</p> : null}
    <details><summary>Raw Output（默认折叠）</summary>
      <div className="standard-preparation-images">{item.attempt?.diagnostics?.recovery?.regions.flatMap(region =>
        [{ url: region.region_url, title: `${region.id} 补识别区域` }, { url: region.ocr_url, title: `${region.id} 局部 OCR 元素` }]
          .filter(v => v.url).map(v => <button type="button" key={v.title} onClick={() => onZoom(v.url!, v.title)}><img src={v.url} alt={v.title} /><span>{v.title} · 点击放大</span></button>))}</div>
      <pre>{JSON.stringify(item.attempt?.diagnostics, null, 2)?.slice(0, 20000)}</pre></details>
  </details>;
}

export function StandardPreparation({ standardId, onZoom }: { standardId: string; onZoom: (url: string, title: string) => void }) {
  const cache = useQueryClient();
  const capability = useQuery({ queryKey: ["text-inspection", "preparation-capabilities"], queryFn: () => apiClient.get<{ enabled: boolean }>("/api/text-inspection/preparation-capabilities") });
  const query = useQuery({ queryKey: ["text-inspection", "preparation", standardId], enabled: capability.data?.enabled === true,
    queryFn: () => apiClient.get<Progress>(`/api/text-inspection/standards/${standardId}/preparation`),
    refetchInterval: q => q.state.data?.job.state === "processing" ? 2000 : false });
  const start = useMutation({ mutationFn: () => apiClient.post(`/api/text-inspection/standards/${standardId}/preparation`),
    onSuccess: () => { void cache.invalidateQueries({ queryKey: ["text-inspection"] }); } });
  const published = query.data?.items.map(i => i.active || "").join(",");
  useEffect(() => { if (published) {
    void cache.invalidateQueries({ queryKey: ["text-inspection", "standard", standardId] });
    void cache.invalidateQueries({ queryKey: ["text-inspection", "standards"] });
  } }, [published, standardId, cache]);
  if (!capability.data?.enabled) return null;
  const processing = query.data?.job.state === "processing";
  return <section className="standard-preparation" aria-label="标准清理与元素准备">
    <div role="status" aria-live="polite">{processing ? `正在准备：${query.data?.items.filter(i => i.active).length || 0}/${query.data?.items.length || 0} 张可用` : "启用时自动清理与提取元素；图形未检查"}</div>
    <button type="button" disabled={processing || start.isPending} onClick={() => start.mutate()}>{processing ? "处理中，可离开后恢复查看" : "准备并启用标准／处理新增图片"}</button>
    {query.data?.job.reason ? <p>{query.data.job.reason}</p> : null}
    {start.error || query.error ? <p role="alert">{((start.error || query.error) as Error).message}</p> : null}
    {query.data?.items.filter(i => i.attempt).map(i => <Review key={i.id} item={i} standardId={standardId} onZoom={onZoom} />)}
  </section>;
}
