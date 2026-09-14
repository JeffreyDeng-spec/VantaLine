import { useState } from "react";
import { Expand } from "lucide-react";

type Box = [number, number, number, number];
type Span = { evidence_id: string; start: number; end: number };
type Element = { element_id: string; expected: string; standard_box: Box; state: string; reason: string; evidence: Span[]; conflicts?: Span[] };
type Observation = { id: string; text: string; type: string; box: Box; coordinate_precision?: string };
type Evidence = { elements: Element[]; observations: Observation[] };

export function EvidenceResults({ value, reference, source, onZoom }: { value: unknown; reference: string; source: string; onZoom: (src: string, alt: string) => void }) {
  const [selected, select] = useState("");
  const [highResolution, setHighResolution] = useState(false);
  const [referenceFailed, setReferenceFailed] = useState(false);
  const [sourceFailed, setSourceFailed] = useState(false);
  const color = (state: string) => state === "matched" ? "#16a34a" : state === "difference" ? "#dc2626" : "#d97706";
  const placement = ([x, y, w, h]: Box) => ({ left: `${100*x}%`, top: `${100*y}%`, width: `${100*w}%`, height: `${100*h}%` });
  const referenceImage = (elements: Element[] = [], active?: Element) => <div style={{ position: "relative", width: 360, maxWidth: "100%" }}>
    {referenceFailed ? <p role="status">当次标准图片不可用或未留存</p> : <img src={reference} alt="标准元素位置" onError={() => setReferenceFailed(true)} style={{ width: "100%", display: "block" }} />}
    {!referenceFailed && elements.map(e => <button key={e.element_id} type="button" title={e.expected} aria-label={`查看元素 ${e.element_id}: ${e.expected}`} aria-pressed={active === e} onClick={() => select(e.element_id)} style={{ position: "absolute", ...placement(e.standard_box), border: `2px solid ${color(e.state)}`, background: "transparent", cursor: "pointer", padding: 0, outline: active === e ? "2px solid #2563eb" : undefined }} />)}
    {!referenceFailed ? <button className="text-compare-reference-expand" type="button" aria-label="查看标准元素核对图" title="放大标准元素核对图（图形未检查）" onClick={() => onZoom(reference, "标准元素核对图（图形未检查）")}><Expand size={16} />放大</button> : null}
  </div>;
  if (!value || typeof value !== "object" || !("elements" in value) || !("observations" in value) || !Array.isArray(value.elements) || !Array.isArray(value.observations)) return referenceImage();
  const data = value as Evidence;
  if (!data.elements.every(e => e && typeof e.element_id === "string" && Array.isArray(e.standard_box) && e.standard_box.length === 4 && Array.isArray(e.evidence))) return referenceImage();
  const element = data.elements.find(e => e.element_id === selected) || data.elements[0];
  const spans = element?.evidence?.length ? element.evidence : element?.conflicts || [];
  const observation = data.observations.find(o => o.id === spans[0]?.evidence_id);
  const actualBox: Box | undefined = observation && (observation.type === "code" ? observation.box : [observation.box[0], observation.box[1], observation.box[2]-observation.box[0], observation.box[3]-observation.box[1]]);
  return <section aria-label="逐元素匹配证据">
    <p>点击标准框查看实拍证据。绿色：至少一处字符一致；黄色：待复核；红色：尚无严格匹配，候选文字不同。</p>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-start" }}>
      {referenceImage(data.elements, element)}
      <div style={{ flex: "1 1 300px", minWidth: 0 }}>
        <strong>{element?.element_id} · {element?.state === "matched" ? "字符一致" : "需要复核"}</strong>
        <p>标准：{element?.expected}</p>
        <p>实拍：{spans.length ? spans.map(s => data.observations.find(o => o.id === s.evidence_id)?.text.slice(s.start, s.end) || "").join(" ") : "未找到可靠对应证据"}</p>
        <small>{element?.reason}</small>
        {observation?.coordinate_precision === "crop_region_only" ? <p>该证据来自局部文字复读；蓝框表示输入区域，不是逐字定位。请结合原图确认。</p> : null}
        {element?.state === "matched" && !!element.conflicts?.length ? <p>其他位置有不同识别结果，已保留在诊断中；不影响此元素已找到的严格匹配。</p> : null}
        {sourceFailed ? <p role="status">实拍证据不可用或未留存</p> : actualBox ? <><button type="button" onClick={() => setHighResolution(v => !v)}>{highResolution ? "返回快速预览" : "加载原图检查小字"}</button><div style={{ position: "relative", marginTop: 12 }}><img onError={() => setSourceFailed(true)} src={highResolution ? source : source.replace(/\/source$/, "/preview")} alt={highResolution ? "原分辨率实拍证据" : "压缩预览，检查小字请加载原图"} style={{ width: "100%", display: "block" }} /><span style={{ pointerEvents: "none", position: "absolute", ...placement(actualBox), border: "3px solid #2563eb" }} /></div></> : null}
      </div>
    </div>
  </section>;
}
