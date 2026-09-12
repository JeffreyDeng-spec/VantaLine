import { useState } from "react";

type Box = [number, number, number, number];
type Span = { evidence_id: string; start: number; end: number };
type Element = { element_id: string; expected: string; standard_box: Box; state: string; reason: string; evidence: Span[]; conflicts?: Span[] };
type Observation = { id: string; text: string; type: string; box: Box };
type Evidence = { elements: Element[]; observations: Observation[] };

export function EvidenceResults({ value, reference, source }: { value: unknown; reference: string; source: string }) {
  const [selected, select] = useState("");
  if (!value || typeof value !== "object" || !("elements" in value) || !("observations" in value) || !Array.isArray(value.elements) || !Array.isArray(value.observations)) return null;
  const data = value as Evidence;
  if (!data.elements.every(e => typeof e.element_id === "string" && Array.isArray(e.standard_box) && e.standard_box.length === 4 && Array.isArray(e.evidence))) return null;
  const element = data.elements.find(e => e.element_id === selected) || data.elements[0];
  const spans = element?.conflicts?.length ? element.conflicts : element?.evidence || [];
  const observation = data.observations.find(o => o.id === spans[0]?.evidence_id);
  const color = (state: string) => state === "matched" ? "#16a34a" : state === "difference" ? "#dc2626" : "#d97706";
  const placement = ([x, y, w, h]: Box) => ({ left: `${100*x}%`, top: `${100*y}%`, width: `${100*w}%`, height: `${100*h}%` });
  const actualBox: Box | undefined = observation && (observation.type === "code" ? observation.box : [observation.box[0], observation.box[1], observation.box[2]-observation.box[0], observation.box[3]-observation.box[1]]);
  return <section aria-label="逐元素匹配证据">
    <p>点击标准框查看实拍证据。绿色：字符一致；黄色：待复核；红色：候选文字不同，仍需人工核实。</p>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-start" }}>
      <div style={{ position: "relative", width: 360, maxWidth: "100%" }}>
        <img src={reference} alt="标准元素位置" style={{ width: "100%", display: "block" }} />
        {data.elements.map(e => <button key={e.element_id} type="button" title={e.expected} aria-label={`查看元素 ${e.element_id}: ${e.expected}`} aria-pressed={element === e} onClick={() => select(e.element_id)} style={{ position: "absolute", ...placement(e.standard_box), border: `2px solid ${color(e.state)}`, background: "transparent", cursor: "pointer", padding: 0, outline: element === e ? "2px solid #2563eb" : undefined }} />)}
      </div>
      <div style={{ flex: "1 1 300px", minWidth: 0 }}>
        <strong>{element?.element_id} · {element?.state === "matched" ? "字符一致" : "需要复核"}</strong>
        <p>标准：{element?.expected}</p>
        <p>实拍：{spans.length ? spans.map(s => data.observations.find(o => o.id === s.evidence_id)?.text.slice(s.start, s.end) || "").join(" ") : "未找到可靠对应证据"}</p>
        <small>{element?.reason}</small>
        {actualBox ? <div style={{ position: "relative", marginTop: 12 }}><img src={source} alt="实拍匹配证据，点击图片可通过浏览器查看原图" style={{ width: "100%", display: "block" }} /><span style={{ pointerEvents: "none", position: "absolute", ...placement(actualBox), border: "3px solid #2563eb" }} /></div> : null}
      </div>
    </div>
  </section>;
}
