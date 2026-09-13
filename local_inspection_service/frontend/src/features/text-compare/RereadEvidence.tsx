export function RereadEvidence({ value, recordId }: { value: unknown; recordId: string }) {
  if (!Array.isArray(value) || !/^ins_[a-zA-Z0-9_-]+$/.test(recordId)) return null;
  const traces = value.filter((v): v is { id: string; mode: string; state: string; elapsed_ms?: number } =>
    !!v && typeof v === "object" && /^ocr_[a-f0-9]{64}$/.test(v.id) && typeof v.mode === "string").slice(0, 16);
  return <section aria-label="局部复读输入证据">
    <p>局部复读只读取实拍区域，不向 OCR 发送标准答案。第二轮框是区域范围，不是逐字定位。</p>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
      {traces.map(t => <figure key={t.id} style={{ margin: 0, maxWidth: 280 }}>
        <a href={`/api/text-inspection/prepared-comparisons/${recordId}/media/${t.id}`} target="_blank" rel="noreferrer">
          <img loading="lazy" src={`/api/text-inspection/prepared-comparisons/${recordId}/media/${t.id}`} alt="OCR 实际输入区域，点击放大" style={{ maxWidth: "100%", maxHeight: 160 }} />
        </a>
        <figcaption>{t.mode === "text_recognition" ? "第二轮文字复读" : "第一轮带位置复读"} · {t.state} · {t.elapsed_ms ?? 0}ms</figcaption>
      </figure>)}
    </div>
  </section>;
}
