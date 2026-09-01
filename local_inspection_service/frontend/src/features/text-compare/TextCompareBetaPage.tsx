import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Camera, CheckCircle2, Clipboard, FileImage, RefreshCcw, ScanText, Upload } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { analyzeTextCompareBeta, compareTextInspectionLabel, confirmTextInspectionStandard, getTextInspectionStandard, importTextInspectionStandard, listTextInspectionStandards, patchTextInspectionAsset } from "../../api/queries";
import type { TextCompareBetaResult } from "../../api/types";

const ACCEPTED_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const MAX_FILE_BYTES = 10 * 1024 * 1024;
function validateImage(file: File) {
  if (!ACCEPTED_TYPES.has(file.type)) throw new Error("仅支持 PNG、JPG 或 WEBP 图片。");
  if (!file.size || file.size > MAX_FILE_BYTES) throw new Error("图片必须小于 10MB。");
}
function qualityCopy(reasons?: string[]) {
  const labels: Record<string, string> = { resolution_too_low: "分辨率太低", blurred: "画面模糊", underexposed: "画面太暗", overexposed_or_glare: "过曝或反光明显" };
  return (reasons || []).map((reason) => labels[reason] || reason).join("、");
}

export function TextCompareBetaPage() {
  const queryClient = useQueryClient();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const busyRef = useRef(false);
  const comparisonIdentityRef = useRef<{ reference: File; captured: File; id: string } | null>(null);
  const [reference, setReference] = useState<File | null>(null);
  const [referenceUrl, setReferenceUrl] = useState("");
  const [captured, setCaptured] = useState<File | null>(null);
  const [capturedUrl, setCapturedUrl] = useState("");
  const [cameraError, setCameraError] = useState("");
  const [inputError, setInputError] = useState("");
  const [result, setResult] = useState<TextCompareBetaResult | null>(null);
  const [activeDifference, setActiveDifference] = useState("");
  const [mode, setMode] = useState<"label" | "manual">("label");
  const [selectedStandardId, setSelectedStandardId] = useState("");
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [importName, setImportName] = useState("");
  const [importMaterial, setImportMaterial] = useState("");
  const [importVersion, setImportVersion] = useState("V1");
  const [importFile, setImportFile] = useState<File | null>(null);
  const standardsQuery = useQuery({ queryKey: ["text-inspection", "standards"], queryFn: listTextInspectionStandards });
  const standardQuery = useQuery({ queryKey: ["text-inspection", "standard", selectedStandardId], queryFn: () => getTextInspectionStandard(selectedStandardId), enabled: !!selectedStandardId });
  const selectedAsset = standardQuery.data?.assets?.find((asset) => asset.id === selectedAssetId);
  const importMutation = useMutation({
    mutationFn: () => {
      if (!importFile || !importName.trim() || !importMaterial.trim() || !importVersion.trim()) throw new Error("请填写标准名称、物料编码、版本并选择 DOCX 或 PDF。");
      const form = new FormData(); form.set("file", importFile); form.set("name", importName.trim()); form.set("material_code", importMaterial.trim()); form.set("version_label", importVersion.trim());
      return importTextInspectionStandard(form);
    },
    onSuccess: (value) => { void queryClient.invalidateQueries({ queryKey: ["text-inspection"] }); setSelectedStandardId(value.id); setShowImport(false); },
    onError: (error: Error) => setInputError(error.message)
  });
  const assetMutation = useMutation({
    mutationFn: ({ assetId, action }: { assetId: string; action: "restore" | "exclude" | "confirm" }) => patchTextInspectionAsset(selectedStandardId, assetId, action),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["text-inspection", "standard", selectedStandardId] })
  });
  const confirmMutation = useMutation({ mutationFn: () => confirmTextInspectionStandard(selectedStandardId), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["text-inspection"] }); }, onError: (error: Error) => setInputError(error.message) });

  const replaceReference = (file: File) => {
    if (busyRef.current) throw new Error("正在对比，请等待本次结果完成。");
    validateImage(file); setReference(file);
    setReferenceUrl((current) => { if (current) URL.revokeObjectURL(current); return URL.createObjectURL(file); });
    comparisonIdentityRef.current = null; setResult(null); setInputError("");
  };
  const replaceCaptured = (file: File) => {
    if (busyRef.current) throw new Error("正在对比，请等待本次结果完成。");
    validateImage(file); setCaptured(file);
    setCapturedUrl((current) => { if (current) URL.revokeObjectURL(current); return URL.createObjectURL(file); });
    comparisonIdentityRef.current = null; setResult(null); setActiveDifference("");
  };

  useEffect(() => {
    let cancelled = false;
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((track) => track.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) { videoRef.current.srcObject = stream; void videoRef.current.play(); }
      })
      .catch((error: Error) => setCameraError(error.name === "NotAllowedError" ? "摄像头权限被拒绝，请在浏览器地址栏中允许访问。" : "摄像头不可用，请检查连接或是否被其他程序占用。"));
    return () => { cancelled = true; streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = null; };
  }, []);
  useEffect(() => () => { if (referenceUrl) URL.revokeObjectURL(referenceUrl); if (capturedUrl) URL.revokeObjectURL(capturedUrl); }, [referenceUrl, capturedUrl]);
  useEffect(() => {
    const paste = (event: ClipboardEvent) => {
      if (busyRef.current) { setInputError("正在对比，请等待本次结果完成。"); return; }
      const file = Array.from(event.clipboardData?.files || []).find((item) => item.type.startsWith("image/"));
      if (!file) { setInputError("剪贴板里没有图片，请先复制标准图片。"); return; }
      try { replaceReference(file); } catch (error) { setInputError((error as Error).message); }
    };
    window.addEventListener("paste", paste);
    return () => window.removeEventListener("paste", paste);
  }, []);

  const captureFrame = () => new Promise<File>((resolve, reject) => {
    const video = videoRef.current;
    if (!video || video.readyState < 2 || !video.videoWidth) { reject(new Error("摄像头画面尚未就绪。")); return; }
    const canvas = document.createElement("canvas"); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob((blob) => blob ? resolve(new File([blob], "capture-" + Date.now() + ".jpg", { type: "image/jpeg" })) : reject(new Error("拍照失败，请重试。")), "image/jpeg", 0.94);
  });
  const mutation = useMutation({
    mutationFn: async () => {
      if (!reference && !selectedAsset) throw new Error("请先从标准库选择标签，或在左侧粘贴标准图片。");
      const actual = captured || await captureFrame();
      if (!captured) {
        validateImage(actual); setCaptured(actual);
        setCapturedUrl((current) => { if (current) URL.revokeObjectURL(current); return URL.createObjectURL(actual); });
      }
      let identity = comparisonIdentityRef.current;
      const identityReference = reference || actual;
      if (!identity || identity.reference !== identityReference || identity.captured !== actual) {
        identity = { reference: identityReference, captured: actual, id: "cmp_" + crypto.randomUUID().replace(/-/g, "") };
        comparisonIdentityRef.current = identity;
      }
      const form = new FormData(); form.set("captured_file", actual);
      form.set("comparison_id", identity.id);
      if (selectedAsset) { form.set("standard_asset_id", selectedAsset.id); return compareTextInspectionLabel(form); }
      form.set("reference_file", reference as File); return analyzeTextCompareBeta(form);
    },
    onMutate: () => { busyRef.current = true; },
    onSuccess: (value) => {
      if (comparisonIdentityRef.current?.id !== value.comparison_id) return;
      setResult(value); setActiveDifference(value.differences[0]?.id || "");
    },
    onError: (error: Error) => setInputError(error.message),
    onSettled: () => { busyRef.current = false; }
  });
  const resultImage = result?.annotated_image_data_url || capturedUrl;
  const tone = result?.decision === "MATCH" ? "match" : result?.decision === "DIFFERENCES" ? "differences" : "review";

  return <section className="view active text-compare-beta">
    <header className="text-compare-beta-header">
      <div><span className="eyebrow">账号专属标准库</span><h2>文字检验</h2><p>标签严格对比与说明书逐页检验集中在一个工作台。</p></div>
      <div className="text-compare-beta-boundary"><AlertTriangle size={17} /><span>仅辅助检查文字<br /><small>颜色、材质与印刷质量仍需肉眼确认</small></span></div>
    </header>
    <div className="sidebar-task-type-switch" role="tablist" aria-label="文字检验模式">
      <button className={mode === "label" ? "active" : ""} type="button" onClick={() => setMode("label")}>标签对比</button>
      <button className={mode === "manual" ? "active" : ""} type="button" onClick={() => setMode("manual")}>说明书逐页检验</button>
    </div>
    <section className="text-compare-result review">
      <div className="text-compare-panel-title"><span>库</span><div><strong>我的标准库</strong><small>只显示当前账号保存的标准</small></div><button type="button" onClick={() => setShowImport((value) => !value)}><Upload size={15} />导入标准</button></div>
      {showImport ? <div className="incoming-task-create-fields">
        <label className="field">标准名称<input value={importName} onChange={(event) => setImportName(event.currentTarget.value)} placeholder="例如：电池包底部标签" /></label>
        <label className="field">物料编码<input value={importMaterial} onChange={(event) => setImportMaterial(event.currentTarget.value)} placeholder="例如：PKG-BAT-001" /></label>
        <label className="field">版本<input value={importVersion} onChange={(event) => setImportVersion(event.currentTarget.value)} /></label>
        <label className="field">标准文档<input type="file" accept=".docx,.pdf" onChange={(event) => setImportFile(event.currentTarget.files?.[0] || null)} /></label>
        <button className="text-compare-primary" type="button" disabled={importMutation.isPending} onClick={() => importMutation.mutate()}>{importMutation.isPending ? "正在安全解析…" : "提取标准内容"}</button>
      </div> : null}
      <div className="text-compare-differences">{(standardsQuery.data?.items || []).filter((item) => item.standard_type === mode).map((standard) => <button key={standard.id} className={selectedStandardId === standard.id ? "active" : ""} onClick={() => { setSelectedStandardId(standard.id); setSelectedAssetId(""); }}><span>{standard.standard_type === "label" ? "标" : "册"}</span><div><strong>{standard.name}</strong><small>{standard.material_code} · {standard.version_label} · {standard.status === "confirmed" ? "已确认" : "待确认"}</small></div></button>)}</div>
      {selectedStandardId && standardQuery.data ? <>
        <div className="text-compare-differences">{(standardQuery.data.assets || []).map((asset) => <button key={asset.id} className={selectedAssetId === asset.id ? "active" : ""} onClick={() => { if (asset.content_url && asset.status !== "excluded") { setSelectedAssetId(asset.id); setReference(null); setReferenceUrl(asset.content_url); } }}><span>{asset.ordinal}</span><div><strong>{asset.category || "标准页"}</strong><small>{asset.status === "excluded" ? "已排除（可恢复）" : asset.status === "needs_confirmation" ? "需要确认" : "候选"} · {asset.context || "无章节说明"}</small></div>{standardQuery.data?.status === "draft" ? <em onClick={(event) => { event.stopPropagation(); assetMutation.mutate({ assetId: asset.id, action: asset.status === "excluded" ? "restore" : "exclude" }); }}>{asset.status === "excluded" ? "恢复" : "排除"}</em> : null}</button>)}</div>
        {standardQuery.data.status === "draft" ? <button className="text-compare-next" type="button" disabled={confirmMutation.isPending} onClick={() => confirmMutation.mutate()}>确认并冻结此版本</button> : null}
      </> : null}
    </section>
    {mode === "manual" ? <div className="text-compare-alert"><AlertTriangle size={18} />说明书逐页会话后端已启用；页面拍摄与自动页匹配正在灰度验收，系统不会在证据不足时返回通过。</div> : null}
    {mode === "label" ? <>
    <div className="text-compare-beta-grid">
      <article className="text-compare-panel">
        <div className="text-compare-panel-title"><span>01</span><div><strong>标准图片</strong><small>Ctrl+V 粘贴、拖入或选择文件</small></div>{reference ? <button type="button" disabled={mutation.isPending} onClick={() => { comparisonIdentityRef.current = null; setReference(null); setReferenceUrl(""); setResult(null); }}><RefreshCcw size={15} />更换</button> : null}</div>
        <label className={"text-compare-stage reference " + (referenceUrl ? "has-image " : "") + (mutation.isPending ? "locked" : "")} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const file = event.dataTransfer.files[0]; if (file) try { replaceReference(file); } catch (error) { setInputError((error as Error).message); } }}>
          {referenceUrl ? <img src={referenceUrl} alt="标准图片" /> : <div className="text-compare-empty"><Clipboard size={38} /><strong>把标准图片粘贴到这里</strong><span>也可以拖入图片或点击选择</span><em><Upload size={15} />选择图片</em></div>}
          <input type="file" disabled={mutation.isPending} accept="image/png,image/jpeg,image/webp" onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) try { replaceReference(file); } catch (error) { setInputError((error as Error).message); } event.currentTarget.value = ""; }} />
        </label>
      </article>
      <article className="text-compare-panel">
        <div className="text-compare-panel-title"><span>02</span><div><strong>实物图片</strong><small>{captured ? "已拍照，可重新拍摄" : "来自当前摄像头画面"}</small></div><button type="button" disabled={mutation.isPending} onClick={() => captureFrame().then(replaceCaptured).catch((error) => setInputError(error.message))}><Camera size={15} />{captured ? "重拍" : "拍照"}</button></div>
        <div className={"text-compare-stage camera " + (resultImage ? "has-image" : "")}>
          {resultImage ? <img src={resultImage} alt="实物文字对比结果" /> : <video ref={videoRef} playsInline muted />}
          {cameraError && !captured ? <div className="text-compare-camera-error"><AlertTriangle size={28} /><strong>摄像头不可用</strong><span>{cameraError}</span></div> : null}
        </div>
      </article>
    </div>
    <div className="text-compare-action-row">
      <button className="text-compare-primary" type="button" disabled={(!reference && !selectedAsset) || mutation.isPending || (!!cameraError && !captured)} onClick={() => { setInputError(""); mutation.mutate(); }}><ScanText size={22} />{mutation.isPending ? "正在逐字严格对比…" : "开始文字对比"}</button>
      {captured ? <button className="text-compare-next" type="button" disabled={mutation.isPending} onClick={() => { comparisonIdentityRef.current = null; setCaptured(null); if (capturedUrl) URL.revokeObjectURL(capturedUrl); setCapturedUrl(""); setResult(null); setActiveDifference(""); }}><Camera size={18} />拍下一件</button> : null}
    </div>
    {inputError ? <div className="text-compare-alert"><AlertTriangle size={18} />{inputError}</div> : null}
    {result ? <section className={"text-compare-result " + tone}>
      <div className="text-compare-result-summary">{tone === "match" ? <CheckCircle2 /> : <AlertTriangle />}<div><small>辅助对比结果</small><strong>{result.decision === "MATCH" ? "未发现文字差异" : result.decision === "DIFFERENCES" ? "发现疑似差异" : "无法可靠判断"}</strong><p>{result.message}</p></div></div>
      {qualityCopy(result.captured_quality?.reasons) ? <div className="text-compare-quality">拍摄提示：{qualityCopy(result.captured_quality?.reasons)}</div> : null}
      {result.differences.length ? <div className="text-compare-differences">{result.differences.map((difference, index) => <button className={activeDifference === difference.id ? "active" : ""} onClick={() => setActiveDifference(difference.id)} key={difference.id}><span>{index + 1}</span><div><small>{difference.type === "missing" ? "可能漏印" : difference.type === "extra" ? "可能多印" : "文字不同"}</small><strong>标准：{difference.reference_text || "（无）"}</strong><strong>实物：{difference.actual_text || "（无）"}</strong></div><em>{Math.round(difference.confidence * 100)}%</em></button>)}</div> : null}
    </section> : <div className="text-compare-hint"><FileImage size={19} />标准图会保留；检查下一件时只需重新拍照。</div>}
    </> : null}
  </section>;
}
