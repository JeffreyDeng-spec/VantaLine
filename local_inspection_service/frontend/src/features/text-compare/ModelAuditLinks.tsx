export function ModelAuditLinks({ value, recordId }: { value: unknown; recordId: string }) {
  if (!Array.isArray(value)) return null;
  const prefix = `/api/text-inspection/prepared-comparisons/${recordId}/media/audit-`;
  return <section aria-label="完整模型调用记录"><strong>完整模型调用记录（仅当前账户可访问）</strong>
    {value.map((entry, index) => {
      if (!entry || typeof entry !== "object" || !entry.files || typeof entry.files !== "object") return null;
      return <div key={index}><span>{String(entry.name || "调用")}: </span>{Object.entries(entry.files).map(([event, file]) => {
        if (!file || typeof file !== "object" || !("url" in file) || typeof file.url !== "string" || !file.url.startsWith(prefix) || !/^[-a-zA-Z0-9_/]+$/.test(file.url)) return null;
        return <a key={event} href={file.url} download style={{ marginRight: 12 }}>{event}</a>;
      })}</div>;
    })}
  </section>;
}
