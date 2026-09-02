import { type FormEvent, type PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BoxSelect, CheckCircle2, CopyPlus, FileText, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import { cloneIncomingTextReference, getIncomingTextTask, queryKeys, saveIncomingTextRules, uploadIncomingTextReference } from "../../api/queries";
import type { IncomingTextFieldRule, IncomingTextRegion, PipelineTask } from "../../api/types";
import { FileDropZone } from "../../components/FileDropZone";

type DraftRule = Omit<IncomingTextFieldRule, "field_id"> & { field_id?: string };

function emptyRule(region: IncomingTextRegion): DraftRule {
  return { name: "", expected_text: "", region_normalized: region, match_mode: "exact", importance: "critical", case_sensitive: true, ignore_whitespace: true };
}

function statusLabel(status: string) {
  if (status === "active") return "当前启用";
  if (status === "archived") return "历史版本";
  return "草稿";
}

export function IncomingTextTaskPage({ task }: { task: PipelineTask }) {
  const queryClient = useQueryClient();
  const imageRef = useRef<HTMLImageElement>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const [selectedReferenceId, setSelectedReferenceId] = useState(task.active_reference_id || "");
  const [rules, setRules] = useState<IncomingTextFieldRule[]>([]);
  const [draftRule, setDraftRule] = useState<DraftRule | null>(null);
  const [versionLabel, setVersionLabel] = useState("");
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");

  const taskQuery = useQuery({ queryKey: queryKeys.incomingTextTask(task.id), queryFn: () => getIncomingTextTask(task.id) });
  const references = taskQuery.data?.references || [];
  const selectedReference = useMemo(
    () => references.find((reference) => reference.id === selectedReferenceId) || taskQuery.data?.active_reference || references[0],
    [references, selectedReferenceId, taskQuery.data?.active_reference]
  );

  useEffect(() => {
    if (!selectedReferenceId && selectedReference) setSelectedReferenceId(selectedReference.id);
  }, [selectedReference, selectedReferenceId]);
  useEffect(() => {
    setRules(selectedReference?.rules || []);
    setDraftRule(null);
  }, [selectedReference?.id]);

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!referenceFile || !versionLabel.trim()) throw new Error("请选择标准稿并填写版本号");
      const form = new FormData();
      form.set("file", referenceFile);
      form.set("version_label", versionLabel.trim());
      return uploadIncomingTextReference(task.id, form);
    },
    onSuccess: async (reference) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.incomingTextTask(task.id) });
      setSelectedReferenceId(reference.id);
      setReferenceFile(null);
      setVersionLabel("");
      setMessage("标准稿已保存为草稿，请框选并配置文字字段。");
    }
  });
  const rulesMutation = useMutation({
    mutationFn: ({ activate }: { activate: boolean }) => {
      if (!selectedReference) throw new Error("请先上传标准稿");
      return saveIncomingTextRules(selectedReference.id, rules, activate);
    },
    onSuccess: async (reference) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.incomingTextTask(task.id) }),
        queryClient.invalidateQueries({ queryKey: ["pipeline", "tasks"] })
      ]);
      setMessage(reference.status === "active" ? `标准 ${reference.version_label} 已启用。` : "字段规则已保存。");
    }
  });
  const cloneMutation = useMutation({
    mutationFn: async () => {
      if (!selectedReference || !versionLabel.trim()) throw new Error("请先填写新版本号");
      return cloneIncomingTextReference(selectedReference.id, versionLabel.trim());
    },
    onSuccess: async (reference) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.incomingTextTask(task.id) });
      setSelectedReferenceId(reference.id);
      setVersionLabel("");
      setMessage("已复制为新草稿，可以修改字段后启用。");
    }
  });

  function normalizedPoint(event: PointerEvent<HTMLDivElement>) {
    const image = imageRef.current;
    if (!image) return null;
    const rect = image.getBoundingClientRect();
    return { x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) };
  }

  function beginSelection(event: PointerEvent<HTMLDivElement>) {
    if (selectedReference?.status !== "draft") return;
    const point = normalizedPoint(event);
    if (!point) return;
    dragStart.current = point;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function finishSelection(event: PointerEvent<HTMLDivElement>) {
    const start = dragStart.current;
    const end = normalizedPoint(event);
    dragStart.current = null;
    if (!start || !end) return;
    const region = { x: Math.min(start.x, end.x), y: Math.min(start.y, end.y), width: Math.abs(end.x - start.x), height: Math.abs(end.y - start.y) };
    if (region.width < 0.015 || region.height < 0.015) return setMessage("框选区域太小，请重新拖动选择完整文字。");
    setDraftRule(emptyRule(region));
  }

  function addRule(event: FormEvent) {
    event.preventDefault();
    if (!draftRule?.name.trim() || !draftRule.expected_text) return setMessage("字段名称和正确文字不能为空。");
    setRules((current) => [...current, { ...draftRule, name: draftRule.name.trim(), field_id: `field_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}` } as IncomingTextFieldRule]);
    setDraftRule(null);
    setMessage("字段已加入草稿，完成后请保存或启用标准。");
  }

  if (taskQuery.isLoading) return <section className="view active incoming-text-loading">正在载入包材标准…</section>;
  if (taskQuery.isError) return <section className="view active"><div className="form-error">{(taskQuery.error as Error).message}</div></section>;
  const actionError = uploadMutation.error || rulesMutation.error;

  return (
    <section className="view active incoming-text-config-view">
      <header className="view-header incoming-text-header">
        <div><span className="eyebrow">包材文字检验</span><h2>{task.name || task.material_name || "来料文字检验"}</h2><p>物料编码 {task.material_code || "未填写"} · 标准一经启用不可修改，只能创建新版本。</p></div>
        <div className="incoming-text-safety-note"><ShieldCheck size={18} /><span>关键字段严格判定<br /><small>证据不足进入人工复核</small></span></div>
      </header>

      <div className="incoming-text-config-grid">
        <aside className="incoming-text-version-panel panel-card">
          <div className="panel-title"><FileText size={18} /><div><strong>标准版本</strong><small>PDF / PNG / JPG，PDF 仅限单页</small></div></div>
          <div className="incoming-text-version-list">
            {references.map((reference) => (
              <button className={reference.id === selectedReference?.id ? "active" : ""} type="button" onClick={() => setSelectedReferenceId(reference.id)} key={reference.id}>
                <span><strong>{reference.version_label}</strong><small>{new Date(reference.created_at * 1000).toLocaleString()}</small></span><em className={`pill ${reference.status === "active" ? "ok" : "neutral"}`}>{statusLabel(reference.status)}</em>
              </button>
            ))}
            {!references.length ? <div className="compact-empty">还没有标准稿，请先上传第一版。</div> : null}
          </div>
          <div className="incoming-text-upload-box">
            <strong><CopyPlus size={16} /> 新建标准版本</strong>
            <input value={versionLabel} onChange={(event) => setVersionLabel(event.currentTarget.value)} placeholder="例如：V3" />
            <FileDropZone className="dropzone compact-dropzone" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" disabled={uploadMutation.isPending} ariaLabel="拖拽或选择标准稿" onFiles={(files) => setReferenceFile(files[0] || null)}>
              <strong>{referenceFile?.name || "拖拽标准稿到这里，或点击选择"}</strong>
              <span>支持单页 PDF、PNG 或 JPG</span>
            </FileDropZone>
            <button className="secondary" type="button" onClick={() => uploadMutation.mutate()} disabled={uploadMutation.isPending || !referenceFile || !versionLabel.trim()}><Plus size={15} /> {uploadMutation.isPending ? "上传中…" : "上传为草稿"}</button>
            {selectedReference && selectedReference.status !== "draft" ? <button className="secondary" type="button" onClick={() => cloneMutation.mutate()} disabled={cloneMutation.isPending || !versionLabel.trim()}><CopyPlus size={15} /> 复制当前规则为新版本</button> : null}
          </div>
          <div className="incoming-task-boundary-note"><ShieldCheck size={16} /><span>此任务已自动保存到当前登录账号。</span></div>
        </aside>

        <main className="incoming-text-editor panel-card">
          <div className="incoming-text-editor-toolbar">
            <div><strong>{selectedReference ? `标准 ${selectedReference.version_label}` : "等待标准稿"}</strong><small>{selectedReference?.status === "draft" ? "在图片上拖动框选文字区域" : "已启用版本仅供查看"}</small></div>
            <div className="toolbar-actions">
              <button className="secondary" type="button" disabled={!selectedReference || selectedReference.status !== "draft" || rulesMutation.isPending} onClick={() => rulesMutation.mutate({ activate: false })}><Save size={15} /> 保存草稿</button>
              <button className="primary" type="button" disabled={!selectedReference || selectedReference.status !== "draft" || !rules.some((rule) => rule.importance === "critical" && rule.match_mode === "exact") || rulesMutation.isPending} onClick={() => window.confirm("启用后该版本和字段规则将不可修改，确认启用？") && rulesMutation.mutate({ activate: true })}><CheckCircle2 size={15} /> 启用标准</button>
            </div>
          </div>
          {message || actionError ? <div className={`incoming-text-message ${actionError ? "error" : ""}`}>{actionError ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}{actionError instanceof Error ? actionError.message : message}</div> : null}

          {selectedReference?.canonical_url ? (
            <div className={`incoming-text-reference-canvas ${selectedReference.status === "draft" ? "editable" : ""}`} onPointerDown={beginSelection} onPointerUp={finishSelection}>
              <img ref={imageRef} src={selectedReference.canonical_url} alt={`标准 ${selectedReference.version_label}`} draggable={false} />
              {rules.map((rule, index) => <div className={`incoming-text-region ${rule.importance}`} style={{ left: `${rule.region_normalized.x * 100}%`, top: `${rule.region_normalized.y * 100}%`, width: `${rule.region_normalized.width * 100}%`, height: `${rule.region_normalized.height * 100}%` }} title={`${rule.name}: ${rule.expected_text}`} key={rule.field_id}><span>{index + 1}</span></div>)}
            </div>
          ) : <div className="incoming-text-canvas-empty"><BoxSelect size={32} /><strong>上传标准稿后开始框选</strong><span>先配置型号、品牌、规格等关键字段。</span></div>}

          {draftRule ? (
            <form className="incoming-text-rule-form" onSubmit={addRule}>
              <label>字段名称<input autoFocus value={draftRule.name} onChange={(event) => setDraftRule({ ...draftRule, name: event.currentTarget.value })} placeholder="例如：产品型号" /></label>
              <label className="wide">正确文字<input value={draftRule.expected_text} onChange={(event) => setDraftRule({ ...draftRule, expected_text: event.currentTarget.value })} placeholder="例如：MODEL: PPLBP-2020" /></label>
              <label>匹配方式<select value={draftRule.match_mode} onChange={(event) => { const matchMode = event.currentTarget.value as "exact" | "regex"; setDraftRule({ ...draftRule, match_mode: matchMode, ignore_whitespace: matchMode === "exact" }); }}><option value="exact">固定文字</option><option value="regex">格式规则</option></select></label>
              <label>关键等级<select value={draftRule.importance} onChange={(event) => setDraftRule({ ...draftRule, importance: event.currentTarget.value as "critical" | "normal" })}><option value="critical">关键字段</option><option value="normal">普通文字</option></select></label>
              <label className="incoming-text-checkbox"><input type="checkbox" checked={draftRule.case_sensitive} onChange={(event) => setDraftRule({ ...draftRule, case_sensitive: event.currentTarget.checked })} /> 区分大小写</label>
              {draftRule.match_mode === "exact" ? <label className="incoming-text-checkbox"><input type="checkbox" checked={draftRule.ignore_whitespace} onChange={(event) => setDraftRule({ ...draftRule, ignore_whitespace: event.currentTarget.checked })} /> 忽略空格差异</label> : null}
              <div className="rule-form-actions"><button type="button" className="secondary" onClick={() => setDraftRule(null)}>取消</button><button type="submit" className="primary">加入字段</button></div>
            </form>
          ) : null}

          <div className="incoming-text-rule-list">
            {rules.map((rule, index) => (
              <article key={rule.field_id}><span className="incoming-text-rule-index">{index + 1}</span><div><strong>{rule.name}</strong><code>{rule.expected_text}</code><small>{rule.match_mode === "exact" ? "固定文字" : "格式规则"} · {rule.case_sensitive ? "区分大小写" : "不区分大小写"} · {rule.ignore_whitespace ? "忽略空格" : "严格空格"}</small></div><em className={`pill ${rule.importance === "critical" ? "fail" : "neutral"}`}>{rule.importance === "critical" ? "关键" : "普通"}</em>{selectedReference?.status === "draft" ? <button className="icon-button light" type="button" aria-label={`删除 ${rule.name}`} onClick={() => setRules((current) => current.filter((item) => item.field_id !== rule.field_id))}><Trash2 size={15} /></button> : null}</article>
            ))}
          </div>
        </main>
      </div>
    </section>
  );
}
