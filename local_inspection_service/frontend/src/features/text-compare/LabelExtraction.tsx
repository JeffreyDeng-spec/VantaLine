import { useEffect, useRef, useState } from "react";
import { apiClient } from "../../api/client";

export type Guide = [number, number, number, number];
type Point = [number, number];
export type Extraction = {
  id: string; root_id: string; version: number; status: string; error_code?: string;
  polygon?: Point[]; media: { source?: string; crop?: string; mask?: string };
  diagnostics?: Record<string, unknown>;
};
export const DEFAULT_GUIDE: Guide = [.15, .15, .7, .7];
const clamp = (v: number, min = 0, max = 1) => Math.max(min, Math.min(max, v));

// Coordinates are measured against contained image pixels, never the letterbox.
export function containedRect(width: number, height: number, imageWidth: number, imageHeight: number) {
  const scale = Math.min(width / imageWidth, height / imageHeight);
  const w = imageWidth * scale, h = imageHeight * scale;
  return { left: (width - w) / 2, top: (height - h) / 2, width: w, height: h };
}

export function GuideOverlay({ value, onChange, disabled }: { value: Guide; onChange: (v: Guide) => void; disabled: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState({ left: 0, top: 0, width: 0, height: 0 });
  const drag = useRef<{ x: number; y: number; value: Guide; resize: boolean } | null>(null);
  useEffect(() => {
    const parent = root.current?.parentElement;
    if (!parent) return;
    const update = () => {
      const media = parent.querySelector("video, img");
      const w = media instanceof HTMLVideoElement ? media.videoWidth : media instanceof HTMLImageElement ? media.naturalWidth : 0;
      const h = media instanceof HTMLVideoElement ? media.videoHeight : media instanceof HTMLImageElement ? media.naturalHeight : 0;
      setRect(w && h ? containedRect(parent.clientWidth, parent.clientHeight, w, h) : { left: 0, top: 0, width: 0, height: 0 });
    };
    const observer = new ResizeObserver(update);
    observer.observe(parent);
    // load doesn't bubble, so capture media replacement/metadata events.
    parent.addEventListener("load", update, true); parent.addEventListener("loadedmetadata", update, true);
    const mutation = new MutationObserver(update); mutation.observe(parent, { childList: true, subtree: true });
    update();
    return () => { observer.disconnect(); mutation.disconnect(); parent.removeEventListener("load", update, true); parent.removeEventListener("loadedmetadata", update, true); };
  }, []);
  return <div ref={root} className="label-guide-container" style={rect}>
    {rect.width > 0 ? <div className="label-guide" style={{ left: `${value[0]*100}%`, top: `${value[1]*100}%`, width: `${value[2]*100}%`, height: `${value[3]*100}%` }}
      role="group" aria-label="单标签取景框" onPointerDown={e => { if (disabled) return; e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); drag.current = { x: e.clientX, y: e.clientY, value: [...value], resize: (e.target as HTMLElement).dataset.resize === "true" }; }}
      onPointerMove={e => { const d = drag.current; if (!d || disabled) return; const dx = (e.clientX-d.x)/rect.width, dy = (e.clientY-d.y)/rect.height; const [x,y,w,h] = d.value; onChange(d.resize ? [x,y,clamp(w+dx,.05,1-x),clamp(h+dy,.05,1-y)] : [clamp(x+dx,0,1-w),clamp(y+dy,0,1-h),w,h]); }}
      onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <span className="label-guide-center">+</span><span className="label-guide-caption">完整标签放入框内，四周留空隙</span>
      <button type="button" data-resize="true" aria-label="调整取景框大小" disabled={disabled} onKeyDown={e => { const delta = e.key === "ArrowUp" || e.key === "ArrowLeft" ? -.01 : e.key === "ArrowDown" || e.key === "ArrowRight" ? .01 : 0; if (delta) { e.preventDefault(); onChange([value[0],value[1],clamp(value[2]+delta,.05,1-value[0]),clamp(value[3]+delta,.05,1-value[1])]); } }}>↘</button>
    </div> : null}
  </div>;
}

const errors: Record<string,string> = {
  draft_expired: "未使用的草稿已过期，请重新提取。",
  multiple_labels: "发现多个标签，请缩小目标框或手动描边。", no_label: "未找到标签，请重拍或手动描边。",
  target_not_centered: "标签没有对准框中心，请调整。", label_touches_image_edge: "标签贴近照片边缘，请重拍并留出空隙。",
  label_outside_guide: "标签超出目标框，请扩大框或重新取景。", mask_aspect_mismatch: "模型返回的画面比例改变，请手动描边或重新提取。",
  not_binary_mask: "模型未返回有效掩膜，请手动描边。", weak_edge_support: "轮廓与原图边缘对应不足，请检查并保存修正后的轮廓。",
  segmentation_not_configured: "AI 分割尚未配置或启用，可以手动描边。", provider_outcome_unknown: "模型请求结果不明，不会自动重试。可新建手动提取。", manual_selection: "请描出一个完整标签，然后保存预览。"
};

export function LabelExtractionPanel({ file, capture, onCaptured, onSourceReady, onInvalidate, aiAvailable = true, guide, onGuide, standardId, standardRevision, onCompare, comparing, onZoom }: {
  file: File | null; capture: () => Promise<File>; onCaptured: (f: File) => void;
  onSourceReady?: (url: string) => void;
  onInvalidate?: () => void; aiAvailable?: boolean;
  guide: Guide; onGuide: (v: Guide) => void; standardId: string; standardRevision: string;
  onCompare: (id: string) => void; comparing: boolean; onZoom: (src: string, alt: string) => void;
}) {
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [points, setPoints] = useState<Point[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [rotation, setRotation] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const generation = useRef(0);
  const currentFile = useRef(file);
  const expectedStandard = useRef(standardId + standardRevision);
  const svg = useRef<SVGSVGElement>(null);
  const moving = useRef<number | null>(null);
  const inFlight = useRef(false);
  const requestIdentity = useRef<{ file: File; guide: string; method: string; id: string } | null>(null);
  const guideKey = JSON.stringify(guide);
  const previousGuide = useRef(guideKey);
  useEffect(() => {
    if (currentFile.current === file) return;
    currentFile.current = file; ++generation.current; inFlight.current = false; setExtraction(null); setPoints([]); setDirty(false); setBusy(false); setError(""); requestIdentity.current = null;
  }, [file]);
  expectedStandard.current = standardId + standardRevision;
  useEffect(() => {
    if (previousGuide.current === guideKey) return;
    previousGuide.current = guideKey; ++generation.current; inFlight.current = false; setBusy(false); setExtraction(null); setPoints([]); setDirty(false); requestIdentity.current = null;
    onInvalidate?.();
  }, [guideKey]);
  useEffect(() => () => { ++generation.current; }, []);
  useEffect(() => {
    if (!expanded) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setExpanded(false); };
    window.addEventListener("keydown",close);
    return () => window.removeEventListener("keydown",close);
  }, [expanded]);
  useEffect(() => {
    if (!extraction || extraction.status !== "attempting") return;
    let stopped = false;
    const epoch = generation.current;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await apiClient.get<Extraction>(`/api/text-inspection/extractions/${extraction.root_id}`);
        if (stopped || epoch !== generation.current) return;
        setExtraction(result); setPoints(result.polygon || []);
        if (result.status === "attempting") timer = setTimeout(poll, 1500);
      } catch { if (!stopped) { setError("状态查询暂时失败，正在重新查询；不会重新调用模型。"); timer = setTimeout(poll, 3000); } }
    };
    timer = setTimeout(poll, 1000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [extraction?.id, extraction?.status]);
  const start = async (method: "ai" | "manual") => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    onInvalidate?.();
    const epoch = ++generation.current;
    try {
      const actual = file || await capture();
      if (epoch !== generation.current) return;
      if (!file) { currentFile.current = actual; onCaptured(actual); }
      const frozenGuide = JSON.stringify(guide);
      let identity = requestIdentity.current;
      if (!identity || identity.file !== actual || identity.guide !== frozenGuide || identity.method !== method) {
        identity = { file: actual, guide: frozenGuide, method, id: crypto.randomUUID() }; requestIdentity.current = identity;
      }
      const form = new FormData(); form.set("file",actual); form.set("target",frozenGuide); form.set("request_id",identity.id); form.set("method",method);
      const result = await apiClient.upload<Extraction>("/api/text-inspection/extractions",form);
      if (epoch !== generation.current) return;
      setExtraction(result); setPoints(result.polygon || []); setDirty(false);
      if (result.media.source) onSourceReady?.(result.media.source);
      if (result.status !== "attempting") requestIdentity.current = null;
    } catch (e) { if (epoch === generation.current) setError((e as Error).message); }
    finally { if (epoch === generation.current) { inFlight.current = false; setBusy(false); } }
  };
  const revise = async (confirm: boolean) => {
    if (!extraction || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    const epoch = generation.current;
    const standard = expectedStandard.current;
    try {
      const result = await apiClient.post<Extraction>(`/api/text-inspection/extractions/${extraction.id}/revise`, { version: extraction.version, polygon: points, confirm, standard_asset_id: standardId });
      if (epoch !== generation.current) return;
      setExtraction(result); setPoints(result.polygon || []); setDirty(false);
      if (confirm && expectedStandard.current === standard) onCompare(result.id);
    } catch (e) { if (epoch === generation.current) setError((e as Error).message); }
    finally { if (epoch === generation.current) { inFlight.current = false; setBusy(false); } }
  };
  const editing = busy || comparing || extraction?.status === "attempting";
  const change = (next: Point[]) => { setPoints(next); setDirty(true); onInvalidate?.(); };
  const pointer = (e: { clientX: number; clientY: number }): Point => {
    const bounds = svg.current!.getBoundingClientRect();
    return [clamp((e.clientX-bounds.left)/bounds.width),clamp((e.clientY-bounds.top)/bounds.height)];
  };
  return <section className="label-extraction-panel">
    <div className="label-extraction-toolbar">
      <button type="button" disabled={busy || comparing} onClick={() => onGuide([...DEFAULT_GUIDE])}>重置取景框</button>
      <button type="button" disabled={busy || comparing} onClick={() => onGuide([clamp(guide[0]-.02,0,1-guide[2]),guide[1],guide[2],guide[3]])} aria-label="取景框左移">←</button>
      <button type="button" disabled={busy || comparing} onClick={() => onGuide([clamp(guide[0]+.02,0,1-guide[2]),guide[1],guide[2],guide[3]])} aria-label="取景框右移">→</button>
      <button type="button" disabled={busy || comparing} onClick={() => onGuide([guide[0],clamp(guide[1]-.02,0,1-guide[3]),guide[2],guide[3]])} aria-label="取景框上移">↑</button>
      <button type="button" disabled={busy || comparing} onClick={() => onGuide([guide[0],clamp(guide[1]+.02,0,1-guide[3]),guide[2],guide[3]])} aria-label="取景框下移">↓</button>
      <button type="button" disabled={!!editing || !aiAvailable} onClick={() => { if (extraction) requestIdentity.current = null; void start("ai"); }}>{extraction?.status === "attempting" ? "正在提取…" : file ? "提取框内标签" : "拍照并提取"}</button>
      <button type="button" disabled={busy || comparing} onClick={() => void start("manual")}>手动描边</button>
    </div>
    {!aiAvailable ? <p>图像生成服务尚未配置或启用。可以先手动描边；AI 配置完成后刷新页面。</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {extraction ? <>
      {extraction.error_code ? <p role="status">{errors[extraction.error_code] || `提取未完成（${extraction.error_code}），请手动描边或重拍。`}</p> : null}
      <div className="label-extraction-previews">
        <div className={expanded ? "label-editor-expanded" : ""} role={expanded ? "dialog" : undefined} aria-modal={expanded || undefined} aria-label={expanded ? "标签轮廓放大编辑" : undefined}><strong>原图轮廓 · 拖动顶点，点击边线添加</strong><button type="button" onClick={()=>setExpanded(v=>!v)}>{expanded ? "关闭放大编辑" : "放大编辑轮廓"}</button>
          <div className="label-contour-editor">
            <img src={extraction.media.source} alt="标签提取原始照片" />
            <svg ref={svg} viewBox="0 0 1 1" preserveAspectRatio="none" onPointerMove={e => { if (moving.current === null || editing) return; const next = [...points]; next[moving.current] = pointer(e); change(next); }} onPointerUp={() => { moving.current = null; }} onPointerCancel={() => { moving.current = null; }}>
              <polygon points={points.map(p=>p.join(",")).join(" ")} fill="rgba(0,255,0,.10)" stroke="#00ff88" strokeWidth=".003" />
              {points.map((p,i) => <g key={i}><line x1={p[0]} y1={p[1]} x2={points[(i+1)%points.length][0]} y2={points[(i+1)%points.length][1]} stroke="transparent" strokeWidth=".018" onPointerDown={e => { if (editing || points.length>=128) return; e.stopPropagation(); const next=[...points]; next.splice(i+1,0,pointer(e)); change(next); setSelected(i+1); }} /><circle cx={p[0]} cy={p[1]} r=".007" fill={selected===i ? "#ffb700" : "white"} onPointerDown={e => { if (editing) return; e.stopPropagation(); setSelected(i); moving.current=i; svg.current?.setPointerCapture(e.pointerId); }} /></g>)}
            </svg>
          </div>
          <button type="button" onClick={() => onZoom(extraction.media.source!,"提取原图")}>放大原图</button>
        </div>
        <div><strong>{dirty ? "轮廓已修改，请保存以更新预览" : "提取预览 · 请核对完整性"}</strong>{extraction.media.crop ? <button type="button" className="label-crop-preview" onClick={() => onZoom(extraction.media.crop!,"实际参与比较的标签")}><img src={extraction.media.crop} alt="从原图提取的单标签" style={{ transform: `rotate(${rotation}deg)` }} /></button> : <p>保存轮廓后生成预览</p>}<button type="button" onClick={() => setRotation(v=>(v+90)%360)}>旋转预览</button></div>
      </div>
      <div className="label-extraction-toolbar">
        <button type="button" disabled={!!editing} onClick={() => { const [x,y,w,h]=guide; change([[x,y],[x+w,y],[x+w,y+h],[x,y+h]]); }}>四角轮廓</button>
        <button type="button" disabled={!!editing} onClick={() => { const [x,y,w,h]=guide; change(Array.from({length:32},(_,i)=>[x+w/2+Math.cos(i*Math.PI/16)*w/2,y+h/2+Math.sin(i*Math.PI/16)*h/2])); }}>圆形轮廓</button>
        <label>顶点<select value={selected ?? ""} onChange={e=>setSelected(Number(e.target.value))}><option value="" disabled>选择顶点</option>{points.map((_,i)=><option key={i} value={i}>{i+1}</option>)}</select></label>
        {selected !== null && points[selected] ? <><label>X<input aria-label="顶点 X" type="number" min="0" max="1" step=".001" value={points[selected][0]} disabled={!!editing} onChange={e=>{const next=[...points];next[selected]=[clamp(Number(e.target.value)),next[selected][1]];change(next);}} /></label><label>Y<input aria-label="顶点 Y" type="number" min="0" max="1" step=".001" value={points[selected][1]} disabled={!!editing} onChange={e=>{const next=[...points];next[selected]=[next[selected][0],clamp(Number(e.target.value))];change(next);}} /></label></> : null}
        <button type="button" disabled={!!editing || selected===null || points.length<=3} onClick={()=>{change(points.filter((_,i)=>i!==selected));setSelected(null);}}>删除顶点</button>
        <button type="button" disabled={!!editing || selected===null || points.length>=128} onClick={()=>{if(selected===null)return;const a=points[selected],b=points[(selected+1)%points.length];const next=[...points];next.splice(selected+1,0,[(a[0]+b[0])/2,(a[1]+b[1])/2]);change(next);setSelected(selected+1);}}>在下一条边添加顶点</button>
        <button type="button" disabled={!!editing || points.length<3} onClick={()=>void revise(false)}>保存轮廓并预览</button>
        <button className="text-compare-primary" type="button" disabled={!!editing || dirty || !standardId || !extraction.media.crop || !["ready","confirmed"].includes(extraction.status)} onClick={()=>void revise(true)}>{comparing ? "正在对比…" : "确认标签并对比"}</button>
      </div>
      <small>确认即表示：这是目标标签、边缘完整且没有相邻标签。修改轮廓后需要重新保存预览。</small>
      <details><summary>Raw Output · 分割诊断</summary><pre>{JSON.stringify(extraction.diagnostics,null,2)?.slice(0,20000)}</pre>{extraction.media.mask ? <button type="button" onClick={()=>onZoom(extraction.media.mask!,"AI 分割掩膜")}>查看掩膜</button> : null}</details>
    </> : null}
  </section>;
}
