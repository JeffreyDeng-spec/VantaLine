import { useState } from "react";
export type ManualHistoryData = {
  sessions: Array<{ id: string; status?: string; decision?: string; created_at?: number; expected_page_count?: number; missing_asset_ids?: string[] }>;
  pages: Array<{ id: string; session_id?: string; standard_asset_id?: string; decision?: string; status?: string; message?: string; differences?: unknown[]; final_decision?: string; review_reason?: string; has_photo: boolean }>;
  standards: Array<{ id: string; ordinal: number; url: string }>;
};
export function ManualHistory({ taskId, history }: { taskId: string; history: ManualHistoryData }) {
  const [imageError, setImageError] = useState(false);
  const [image, setImage] = useState("");
  const show = (url: string) => { setImageError(false); setImage(url); };
  return <section className="li-manual-history">
    <h2>历史记录（只读）</h2>
    <p>保留原有检测结论。继续检测请新建任务并重新导入 PDF。</p>
    <details><summary>原标准页面（{history.standards.length}）</summary>
      {history.standards.map(a => <button key={a.id} onClick={() => show(a.url)}>原标准第 {a.ordinal} 页</button>)}
      {!history.standards.length && <p>原标准页面缺失</p>}
    </details>
    {history.sessions.map(s => <div key={s.id}><h3>会话 {s.id}</h3><p>原状态：{s.status || "未记录"} · 原结论：{s.decision || "未记录"} · 预期页数：{s.expected_page_count ?? "未记录"}</p>
      {!!s.missing_asset_ids?.length && <p>原记录缺页：{s.missing_asset_ids.join("、")}</p>}</div>)}
    {history.pages.map(p => <article key={p.id}><h3>检测 {p.id}</h3><p>会话：{p.session_id || "关联缺失"} · 标准：{p.standard_asset_id || "关联缺失"}</p><p>原状态：{p.status || "未记录"} · 原结论：{p.decision || "未记录"}</p><p>{p.message}</p>{p.final_decision && <p>原人工结论：{p.final_decision} · {p.review_reason}</p>}
      {p.differences?.map((d,i) => <p key={i}>{typeof d === "string" ? d : JSON.stringify(d)}</p>)}
      {p.has_photo ? <button onClick={() => show(`/api/label-inspection/tasks/${encodeURIComponent(taskId)}/history-media/${encodeURIComponent(p.id)}`)}>查看原照片</button> : <p>原记录未保留实物照片，无法回看图片。</p>}
    </article>)}
    {!history.pages.length && <p>没有已保存的逐页检测记录。</p>}
    {image && <div className="li-modal" role="dialog" aria-modal="true" aria-label="历史图片" onKeyDown={e => { if (e.key === "Escape") setImage(""); }}><button autoFocus onClick={() => setImage("")}>关闭</button>{imageError ? <p>原图片缺失或无法读取</p> : <img src={image} alt="历史原图" onError={() => setImageError(true)} />}</div>}
  </section>;
}
