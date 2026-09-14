import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronRight } from "lucide-react";
import type { TextCompareBetaResult, TextInspectionDiagnostics } from "../../api/types";
import { apiClient } from "../../api/client";
import { EvidenceResults } from "./EvidenceResults";
import { ModelAuditLinks } from "./ModelAuditLinks";
import { RereadEvidence } from "./RereadEvidence";

export type SavedComparison = TextCompareBetaResult & {
  source_url?: string; source_preview_url?: string; annotated_preview_url?: string;
  history_warning?: string; diagnostics_url?: string;
};
function qualityCopy(reasons?: string[]) {
  const labels: Record<string, string> = { resolution_too_low: "分辨率太低", blurred: "画面模糊", underexposed: "画面太暗", overexposed_or_glare: "过曝或反光明显" };
  return (reasons || []).map(reason => labels[reason] || reason).join("、");
}
const MAX_DIAGNOSTIC_OUTPUT_CHARS = 20_000;
function formatDiagnosticOutput(value: unknown) {
  let output: string;
  try { output = typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? String(value); }
  catch { output = String(value); }
  return output.length > MAX_DIAGNOSTIC_OUTPUT_CHARS ? `${output.slice(0, MAX_DIAGNOSTIC_OUTPUT_CHARS)}\n…（显示内容已截断）` : output;
}
export function EvidenceImage({ src, alt, onZoom }: { src: string; alt: string; onZoom?: (src: string, alt: string) => void }) {
  const [failed, setFailed] = useState(false);
  return failed ? <p role="status">{alt}不可用或未留存</p> : <button type="button" disabled={!onZoom} onClick={() => onZoom?.(src, alt)}><img loading="lazy" src={src} alt={alt} onError={() => setFailed(true)} /></button>;
}
export function ComparisonResult({ result, onZoom, obscured = false }: {
  result: SavedComparison; onZoom: (src: string, alt: string) => void; obscured?: boolean;
}) {
  const [activeDifference, setActiveDifference] = useState("");
  const [loaded, setLoaded] = useState<TextInspectionDiagnostics | null>(null);
  const [rawOpen, setRawOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const diagnostics = loaded || result.diagnostics;
  const providerDiagnostics = diagnostics?.provider_result;
  const rawProviderOutput = providerDiagnostics?.response_preview ?? providerDiagnostics?.parsed_response;
  const normalizedOutput = diagnostics?.normalized_response;
  const hasDiagnosticOutput = !!result.diagnostics_url || !!diagnostics;
  const tone = result.decision === "MATCH" ? "match" : result.decision === "DIFFERENCES" ? "differences" : "review";
  async function loadRaw() {
    if (!result.diagnostics_url || loaded || loading) return;
    setLoading(true); setError("");
    try { setLoaded(await apiClient.get<TextInspectionDiagnostics>(result.diagnostics_url)); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }
  return <section ref={node => { if (node) node.inert = obscured; }} className={"text-compare-result " + tone}>
    {result.status === "completed" ? <small>100% · 结果已保存</small> : null}
    <div className="text-compare-result-summary">{tone === "match" ? <CheckCircle2 /> : <AlertTriangle />}<div><small>辅助对比结果</small><strong>{result.decision === "MATCH" ? "未发现文字差异" : result.decision === "DIFFERENCES" ? "发现疑似差异" : "无法可靠判断"}</strong><p>{result.message}</p></div></div>
    {result.history_warning ? <p role="status">{result.history_warning}</p> : null}
    {qualityCopy(result.captured_quality?.reasons) ? <div className="text-compare-quality">拍摄提示：{qualityCopy(result.captured_quality?.reasons)}</div> : null}
    {result.source_preview_url ? <details><summary>查看本次实拍图</summary><EvidenceImage src={result.source_preview_url} alt="历史实拍预览" onZoom={onZoom} />{result.source_url ? <button type="button" onClick={() => onZoom(result.source_url!, "原分辨率实拍图")}>加载原图检查小字</button> : null}</details> : null}
    {result.annotated_preview_url || result.annotated_image_data_url ? <EvidenceImage src={(result.annotated_preview_url || result.annotated_image_data_url)!} alt="实拍标注结果" onZoom={onZoom} /> : null}
    {result.reference_overlay_url ? <EvidenceResults key={result.id} value={diagnostics?.provider === "qwen_ocr" && result.id ? normalizedOutput : undefined} reference={result.reference_overlay_url} source={result.source_url || (result.id ? `/api/text-inspection/prepared-comparisons/${result.id}/media/source` : "")} onZoom={onZoom} /> : null}
    {result.differences.length ? <div className="text-compare-differences">{result.differences.map((difference, index) => <button type="button" className={activeDifference === difference.id ? "active" : ""} onClick={() => setActiveDifference(difference.id)} key={difference.id}><span>{index + 1}</span><div><small>{difference.type === "missing" ? "可能漏印" : difference.type === "extra" ? "可能多印" : "文字不同"}</small><strong>标准：{difference.reference_text || "（无）"}</strong><strong>实物：{difference.actual_text || "（无）"}</strong></div><em>{Number.isFinite(difference.confidence) ? `${Math.round(difference.confidence * 100)}%` : "未提供置信度"}</em></button>)}</div> : null}
    {hasDiagnosticOutput ? <details className="text-compare-raw-output" onToggle={event => { setRawOpen(event.currentTarget.open); if (event.currentTarget.open) void loadRaw(); }}>
      <summary><ChevronRight size={15} /><span>Raw Output（调试信息）</span><small>默认折叠</small></summary>
      {rawOpen ? <div className="text-compare-raw-output-body">
        {loading ? <p>正在读取日志…</p> : null}{error ? <p role="alert">{error}<button onClick={() => void loadRaw()}>重试</button></p> : null}
        {result.id ? <ModelAuditLinks value={diagnostics?.model_audits} recordId={result.id} /> : null}
        {result.id ? <RereadEvidence value={diagnostics?.rereads} recordId={result.id} onZoom={onZoom} /> : null}
        {diagnostics?.provider === "qwen_ocr" ? <section><header><strong>OCR 与证据匹配诊断</strong></header><pre>{formatDiagnosticOutput(diagnostics)}</pre></section> : null}
        {rawProviderOutput !== undefined ? <section><header><strong>模型原始输出</strong><small>{providerDiagnostics?.response_preview !== undefined ? "原始文本预览" : "解析后的 JSON"}</small></header><pre>{formatDiagnosticOutput(rawProviderOutput)}</pre></section> : null}
        {normalizedOutput !== undefined ? <section><header><strong>系统适配结果</strong><small>进入业务校验前的数据</small></header><pre>{formatDiagnosticOutput(normalizedOutput)}</pre></section> : null}
        {diagnostics?.provider !== "qwen_ocr" ? <pre>{formatDiagnosticOutput(diagnostics || {})}</pre> : null}
      </div> : null}
    </details> : null}
  </section>;
}
