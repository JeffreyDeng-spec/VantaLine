import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, Camera, CheckCircle2, ChevronDown, ChevronRight, Expand, FileImage, ImagePlus, Minus, Plus, RefreshCcw, ScanText, Trash2, Upload, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addTextInspectionStandardAsset, compareTextInspectionLabel, confirmTextInspectionStandard, getTextInspectionStandard, importTextInspectionStandard, listTextInspectionStandards, patchTextInspectionAsset } from "../../api/queries";
import type { TextCompareBetaResult, TextInspectionAsset } from "../../api/types";
import { FileDropZone } from "../../components/FileDropZone";

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

const CATEGORY_LABELS: Record<string, string> = {
  label: "标签",
  possible_label: "疑似标签",
  packaging_artwork: "包装展开图",
  dieline: "刀线或内衬",
  manual_page: "说明书页面",
  carton_artwork: "外箱图",
  placement_diagram: "贴标位置图",
  photo: "实拍图",
  other: "其他图片"
};

function assetStatusCopy(asset: TextInspectionAsset) {
  if (asset.status === "excluded") return "已移除";
  if (asset.status === "needs_confirmation") return "待确认";
  return asset.status === "page" ? "标准页面" : "已保留";
}

function isActiveAsset(asset: TextInspectionAsset) {
  return asset.status === "candidate" || asset.status === "page";
}

export function TextCompareBetaPage() {
  const queryClient = useQueryClient();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const cameraRequestRef = useRef(0);
  const cameraSurfaceActiveRef = useRef(true);
  const selectedDeviceIdRef = useRef("");
  const busyRef = useRef(false);
  const comparisonIdentityRef = useRef<{ standardAssetId: string; captured: File; id: string } | null>(null);
  const [captured, setCaptured] = useState<File | null>(null);
  const [capturedUrl, setCapturedUrl] = useState("");
  const [cameraError, setCameraError] = useState("");
  const [cameraStarting, setCameraStarting] = useState(false);
  const [cameraDevices, setCameraDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [inputError, setInputError] = useState("");
  const [inputMode, setInputMode] = useState<"camera" | "image">("camera");
  const [result, setResult] = useState<TextCompareBetaResult | null>(null);
  const [activeDifference, setActiveDifference] = useState("");
  const [zoomedImage, setZoomedImage] = useState<{ src: string; alt: string } | null>(null);
  const [zoomScale, setZoomScale] = useState(1);
  const [mode, setMode] = useState<"label" | "manual">("label");
  const [selectedStandardId, setSelectedStandardId] = useState("");
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [assetUploadFile, setAssetUploadFile] = useState<File | null>(null);
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
      const expectedSuffix = mode === "label" ? ".docx" : ".pdf";
      if (!importFile.name.toLowerCase().endsWith(expectedSuffix)) throw new Error(mode === "label" ? "标签标准请上传 DOCX 文件。" : "说明书标准请上传 PDF 文件。");
      const form = new FormData(); form.set("file", importFile); form.set("name", importName.trim()); form.set("material_code", importMaterial.trim()); form.set("version_label", importVersion.trim());
      return importTextInspectionStandard(form);
    },
    onSuccess: (value) => {
      void queryClient.invalidateQueries({ queryKey: ["text-inspection"] });
      setSelectedStandardId(value.id); setShowImport(false);
      setImportName(""); setImportMaterial(""); setImportVersion("V1"); setImportFile(null);
    },
    onError: (error: Error) => setInputError(error.message)
  });
  const assetMutation = useMutation({
    mutationFn: ({ assetId, action }: { assetId: string; action: "restore" | "remove" | "confirm" }) => patchTextInspectionAsset(selectedStandardId, assetId, action, standardQuery.data?.revision_number),
    onSuccess: (_value, variables) => {
      if (variables.action === "remove" && variables.assetId === selectedAssetId) {
        setSelectedAssetId(""); resetComparison();
      } else {
        resetComparison();
      }
      void queryClient.invalidateQueries({ queryKey: ["text-inspection"] });
    },
    onError: (error: Error) => setInputError(error.message)
  });
  const assetUploadMutation = useMutation({
    mutationFn: () => {
      if (!assetUploadFile) throw new Error("请先选择一张标签图片。");
      validateImage(assetUploadFile);
      const form = new FormData(); form.set("file", assetUploadFile);
      if (standardQuery.data?.revision_number !== undefined) form.set("expected_revision", String(standardQuery.data.revision_number));
      return addTextInspectionStandardAsset(selectedStandardId, form);
    },
    onSuccess: () => { setAssetUploadFile(null); resetComparison(); void queryClient.invalidateQueries({ queryKey: ["text-inspection"] }); },
    onError: (error: Error) => setInputError(error.message)
  });
  const confirmMutation = useMutation({ mutationFn: () => confirmTextInspectionStandard(selectedStandardId), onSuccess: () => { resetComparison(); void queryClient.invalidateQueries({ queryKey: ["text-inspection"] }); }, onError: (error: Error) => setInputError(error.message) });

  const resetComparison = (options: { clearCaptured?: boolean } = {}) => {
    comparisonIdentityRef.current = null;
    setResult(null); setActiveDifference(""); setInputError("");
    if (options.clearCaptured) {
      setCaptured(null);
      setCapturedUrl((current) => { if (current.startsWith("blob:")) URL.revokeObjectURL(current); return ""; });
    }
  };

  const chooseStandard = (standardId: string) => {
    const nextId = selectedStandardId === standardId ? "" : standardId;
    setSelectedStandardId(nextId); setSelectedAssetId(""); setAssetUploadFile(null);
    resetComparison();
  };

  const chooseAsset = (asset: TextInspectionAsset) => {
    if (!asset.content_url || asset.status === "excluded") return;
    if (standardQuery.data?.status !== "confirmed") {
      setInputError("这个订单还没有启用。请先启用候选图片并保存订单，再开始对比。");
      return;
    }
    resetComparison();
    setSelectedAssetId(asset.id);
  };
  const replaceCaptured = (file: File) => {
    if (busyRef.current) throw new Error("正在对比，请等待本次结果完成。");
    validateImage(file); setCaptured(file);
    setCapturedUrl((current) => { if (current) URL.revokeObjectURL(current); return URL.createObjectURL(file); });
    comparisonIdentityRef.current = null; setResult(null); setActiveDifference("");
  };
  const clearCaptured = () => {
    comparisonIdentityRef.current = null;
    setCaptured(null);
    setCapturedUrl((current) => { if (current) URL.revokeObjectURL(current); return ""; });
    setResult(null);
    setActiveDifference("");
  };
  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  };
  const refreshCameraDevices = async (preferredId = selectedDeviceIdRef.current) => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setCameraDevices([]);
      return { devices: [] as MediaDeviceInfo[], selectedId: "" };
    }
    const devices = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === "videoinput");
    const selectedId = preferredId && devices.some((device) => device.deviceId === preferredId) ? preferredId : (devices[0]?.deviceId || "");
    selectedDeviceIdRef.current = selectedId;
    setSelectedDeviceId(selectedId);
    setCameraDevices(devices);
    return { devices, selectedId };
  };
  const startCamera = async (deviceId = selectedDeviceIdRef.current) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("当前浏览器不支持摄像头访问。");
      return;
    }
    const requestId = ++cameraRequestRef.current;
    setCameraStarting(true);
    setCameraError("");
    stopCamera();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: deviceId
          ? { deviceId: { exact: deviceId }, width: { ideal: 1920 }, height: { ideal: 1080 } }
          : { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false
      });
      if (requestId !== cameraRequestRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const actualDeviceId = stream.getVideoTracks()[0]?.getSettings().deviceId || deviceId;
      selectedDeviceIdRef.current = actualDeviceId;
      setSelectedDeviceId(actualDeviceId);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      await refreshCameraDevices(actualDeviceId).catch(() => setCameraDevices([]));
    } catch (error) {
      if (requestId !== cameraRequestRef.current) return;
      stopCamera();
      const cameraFailure = error as DOMException;
      setCameraError(cameraFailure.name === "NotAllowedError" ? "摄像头权限被拒绝，请在浏览器地址栏中允许访问。" : cameraFailure.name === "OverconstrainedError" || cameraFailure.name === "NotFoundError" ? "选择的摄像头已断开，请选择其他设备。" : "摄像头不可用，请检查连接或是否被其他程序占用。");
      await refreshCameraDevices("").catch(() => undefined);
    } finally {
      if (requestId === cameraRequestRef.current) setCameraStarting(false);
    }
  };
  const switchInputMode = (nextMode: "camera" | "image") => {
    if (busyRef.current || nextMode === inputMode) return;
    clearCaptured();
    setInputMode(nextMode);
    setInputError("");
    if (nextMode === "image") {
      cameraSurfaceActiveRef.current = false;
      ++cameraRequestRef.current;
      stopCamera();
      setCameraStarting(false);
    } else {
      cameraSurfaceActiveRef.current = true;
      void startCamera();
    }
  };
  const openZoom = (src: string, alt: string) => {
    setZoomScale(1);
    setZoomedImage({ src, alt });
  };

  useEffect(() => {
    let cancelled = false;
    void startCamera();
    const handleDeviceChange = async () => {
      const previousId = selectedDeviceIdRef.current;
      const next = await refreshCameraDevices(previousId).catch(() => null);
      if (cancelled || !next || !cameraSurfaceActiveRef.current) return;
      const hasLiveTrack = Boolean(streamRef.current?.getVideoTracks().some((track) => track.readyState === "live"));
      if (hasLiveTrack && previousId && next.devices.some((device) => device.deviceId === previousId)) return;
      if (next.selectedId) void startCamera(next.selectedId);
      else {
        ++cameraRequestRef.current;
        stopCamera();
        setCameraError("未检测到可用摄像头，请连接设备后重试。");
      }
    };
    navigator.mediaDevices?.addEventListener?.("devicechange", handleDeviceChange);
    return () => {
      cancelled = true;
      cameraSurfaceActiveRef.current = false;
      ++cameraRequestRef.current;
      navigator.mediaDevices?.removeEventListener?.("devicechange", handleDeviceChange);
      stopCamera();
    };
  }, []);
  useEffect(() => {
    if (inputMode !== "camera" || capturedUrl || !videoRef.current || !streamRef.current) return;
    videoRef.current.srcObject = streamRef.current;
    void videoRef.current.play().catch(() => setCameraError("摄像头画面无法播放，请重新选择设备。"));
  }, [inputMode, capturedUrl, cameraStarting]);
  useEffect(() => () => { if (capturedUrl) URL.revokeObjectURL(capturedUrl); }, [capturedUrl]);
  useEffect(() => {
    if (!zoomedImage) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setZoomedImage(null); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [zoomedImage]);
  useEffect(() => {
    if (!showImport) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || importMutation.isPending || assetMutation.isPending || assetUploadMutation.isPending) return;
      setShowImport(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [showImport, importMutation.isPending, assetMutation.isPending, assetUploadMutation.isPending]);
  const captureFrame = () => new Promise<File>((resolve, reject) => {
    const video = videoRef.current;
    if (!video || video.readyState < 2 || !video.videoWidth) { reject(new Error("摄像头画面尚未就绪。")); return; }
    const canvas = document.createElement("canvas"); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob((blob) => blob ? resolve(new File([blob], "capture-" + Date.now() + ".jpg", { type: "image/jpeg" })) : reject(new Error("拍照失败，请重试。")), "image/jpeg", 0.94);
  });
  const mutation = useMutation({
    mutationFn: async () => {
      if (!selectedAsset) throw new Error("请先在左侧订单画廊中选择一张已启用的标签图片。");
      if (standardQuery.data?.status !== "confirmed") throw new Error("这个订单还没有启用，请先保存并启用标准。");
      if (inputMode === "image" && !captured) throw new Error("请先上传需要对比的实物图片。");
      const actual = captured || await captureFrame();
      if (!captured) {
        validateImage(actual); setCaptured(actual);
        setCapturedUrl((current) => { if (current) URL.revokeObjectURL(current); return URL.createObjectURL(actual); });
      }
      let identity = comparisonIdentityRef.current;
      if (!identity || identity.standardAssetId !== selectedAsset.id || identity.captured !== actual) {
        identity = { standardAssetId: selectedAsset.id, captured: actual, id: "cmp_" + crypto.randomUUID().replace(/-/g, "") };
        comparisonIdentityRef.current = identity;
      }
      const form = new FormData(); form.set("captured_file", actual);
      form.set("comparison_id", identity.id);
      form.set("standard_asset_id", selectedAsset.id); return compareTextInspectionLabel(form);
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
  const visibleStandards = (standardsQuery.data?.items || []).filter((item) => item.standard_type === mode);
  const visibleAssets = standardQuery.data?.assets || [];
  const retainedAssetCount = visibleAssets.filter(isActiveAsset).length;
  const renderAssetCards = () => <div className="text-standard-asset-grid" data-testid="standard-library-assets">
    {visibleAssets.map((asset) => {
      const selectable = mode === "label" && isActiveAsset(asset) && standardQuery.data?.status === "confirmed";
      const selected = selectedAssetId === asset.id;
      return <article className={`text-standard-asset-card ${selected ? "selected" : ""} ${asset.status === "excluded" ? "removed" : ""}`} key={asset.id}>
      <button className="text-standard-thumbnail" type="button" onClick={() => selectable ? chooseAsset(asset) : asset.content_url && openZoom(asset.content_url, `${CATEGORY_LABELS[asset.category || ""] || "标准图片"} ${asset.ordinal}`)} disabled={!asset.content_url} aria-pressed={selectable ? selected : undefined} aria-label={selectable ? `选择第 ${asset.ordinal} 张标签作为对比标准` : `查看第 ${asset.ordinal} 张标准大图`}>
        {asset.content_url ? <img src={asset.content_url} alt={`第 ${asset.ordinal} 张标准缩略图`} loading="lazy" /> : <span><FileImage size={26} />暂无预览</span>}
        <em>{asset.ordinal}</em>
        {selectable ? <i>{selected ? "已选标准" : "点击选中"}</i> : null}
      </button>
      <div className="text-standard-asset-copy"><strong>{CATEGORY_LABELS[asset.category || ""] || "标准图片"}</strong><small>{assetStatusCopy(asset)}{asset.context ? ` · ${asset.context}` : ""}</small></div>
      <div className="text-standard-asset-actions">
        {asset.content_url ? <button type="button" onClick={() => openZoom(asset.content_url!, `${CATEGORY_LABELS[asset.category || ""] || "标准图片"} ${asset.ordinal}`)}><Expand size={14} />查看大图</button> : null}
        <button className={asset.status === "excluded" ? "restore" : asset.status === "needs_confirmation" ? "restore" : "remove"} type="button" disabled={assetMutation.isPending || assetUploadMutation.isPending} onClick={() => assetMutation.mutate({ assetId: asset.id, action: asset.status === "excluded" ? "restore" : asset.status === "needs_confirmation" ? "confirm" : "remove" })}>{asset.status === "excluded" ? <><RefreshCcw size={14} />启用</> : asset.status === "needs_confirmation" ? <><CheckCircle2 size={14} />启用</> : <><Trash2 size={14} />停用</>}</button>
      </div>
    </article>})}
    {!visibleAssets.length && !standardQuery.isLoading ? <div className="text-standard-empty"><ImagePlus size={28} /><strong>还没有标准图片</strong><span>请在当前订单中添加图片，或重新导入包含图片的文档。</span></div> : null}
  </div>;

  return <section className="view active text-compare-beta">
    <header className="text-compare-beta-header">
      <div><span className="eyebrow">账号专属标准库</span><h2>文字检验</h2><p>标签严格对比与说明书逐页检验集中在一个工作台。</p></div>
    </header>
    <div className="sidebar-task-type-switch" role="tablist" aria-label="文字检验模式">
      <button className={mode === "label" ? "active" : ""} role="tab" aria-selected={mode === "label"} aria-controls="text-standard-library-panel" type="button" onClick={() => { if (mode !== "label") { setMode("label"); setSelectedStandardId(""); setSelectedAssetId(""); setShowImport(false); resetComparison({ clearCaptured: true }); if (inputMode === "camera") { cameraSurfaceActiveRef.current = true; void startCamera(); } } }}>标签对比</button>
      <button className={mode === "manual" ? "active" : ""} role="tab" aria-selected={mode === "manual"} aria-controls="text-standard-library-panel" type="button" onClick={() => { if (mode !== "manual") { setMode("manual"); setSelectedStandardId(""); setSelectedAssetId(""); setShowImport(false); resetComparison({ clearCaptured: true }); cameraSurfaceActiveRef.current = false; ++cameraRequestRef.current; stopCamera(); setCameraStarting(false); } }}>说明书逐页检验</button>
    </div>
    <div className={mode === "label" ? "text-compare-workbench" : ""}>
    <section className="text-standard-library" id="text-standard-library-panel" role="tabpanel" aria-label="我的标准库">
      <div className="text-standard-library-header"><div><span>01</span><strong>我的{mode === "label" ? "标签" : "说明书"}订单</strong><small>{mode === "label" ? "展开订单，在画廊中点击标签图片即可选作对比标准。" : "展开订单查看并维护标准页面。"}</small></div><button className="text-standard-import-button" type="button" onClick={() => { setInputError(""); setShowImport(true); }}><Upload size={16} />导入标准</button></div>
      {standardsQuery.isLoading ? <div className="text-standard-empty"><RefreshCcw className="spin" size={24} /><strong>正在加载标准库</strong></div> : null}
      {standardsQuery.isError ? <div className="text-standard-empty error"><AlertTriangle size={24} /><strong>标准库加载失败</strong><span>{(standardsQuery.error as Error).message}</span><button type="button" onClick={() => void standardsQuery.refetch()}>重新加载</button></div> : null}
      {!standardsQuery.isLoading && !standardsQuery.isError && !visibleStandards.length ? <div className="text-standard-empty"><FileImage size={28} /><strong>还没有{mode === "label" ? "标签" : "说明书"}标准</strong><span>点击“导入标准”创建第一个订单。</span></div> : null}
      <div className="text-standard-order-list">
        {visibleStandards.map((standard) => {
          const expanded = selectedStandardId === standard.id;
          return <article className={`text-standard-order ${expanded ? "expanded" : ""}`} key={standard.id}>
            <button className="text-standard-order-toggle" type="button" aria-expanded={expanded} onClick={() => chooseStandard(standard.id)}><span>{standard.standard_type === "label" ? "标" : "册"}</span><div><strong>{standard.name}</strong><small>{standard.material_code} · {standard.version_label} · {standard.asset_count} 张</small></div><em className={standard.status}>{standard.status === "confirmed" ? "已启用" : "待整理"}</em>{expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}</button>
            {expanded ? <div className="text-standard-order-detail" data-testid="standard-order-detail">
              <div className="text-standard-order-toolbar"><div><strong>{standardQuery.isLoading ? "正在读取订单…" : `${retainedAssetCount} 张图片已启用`}</strong><small>{standard.status === "confirmed" ? "点击任一已启用图片即可高亮选中；“查看大图”不会改变选择。" : "请整理候选图片，然后保存并启用订单。"}</small></div></div>
              {standardQuery.data?.standard_type === "label" ? <div className="text-standard-inline-controls"><FileDropZone className="text-standard-add-asset-drop" accept="image/png,image/jpeg,image/webp" disabled={assetUploadMutation.isPending} ariaLabel="拖拽或选择单张标准图片" onFiles={(files) => { setAssetUploadFile(files[0] || null); setInputError(""); }}><ImagePlus size={16} /><span>{assetUploadFile ? assetUploadFile.name : "拖拽或选择单张图片"}</span></FileDropZone><button type="button" disabled={!assetUploadFile || assetUploadMutation.isPending} onClick={() => assetUploadMutation.mutate()}>{assetUploadMutation.isPending ? "添加中…" : "添加到标准"}</button></div> : null}
              {standardQuery.isError ? <div className="text-standard-empty error"><AlertTriangle size={22} /><strong>订单内容加载失败</strong><button type="button" onClick={() => void standardQuery.refetch()}>重试</button></div> : renderAssetCards()}
              {inputError ? <div className="text-standard-form-error"><AlertTriangle size={16} />{inputError}</div> : null}
              {standardQuery.data?.status === "draft" ? <div className="text-standard-inline-footer"><span>启用后即可直接选择订单中的图片进行对比。</span><button type="button" disabled={!retainedAssetCount || confirmMutation.isPending || assetMutation.isPending || assetUploadMutation.isPending} onClick={() => confirmMutation.mutate()}>{confirmMutation.isPending ? "正在保存…" : "保存并启用"}</button></div> : null}
            </div> : null}
          </article>;
        })}
      </div>
    </section>
    {mode === "label" ? <article className="text-compare-panel text-compare-actual-panel">
        <div className="text-compare-panel-title"><span>02</span><div><strong>实物图片</strong><small>{inputMode === "camera" ? (captured ? "已拍照，可重新拍摄" : "来自当前摄像头画面") : (captured ? `已选择 ${captured.name}` : "上传已有图片进行对比")}</small></div><div className="text-compare-input-switch" role="group" aria-label="实物图片来源"><button className={inputMode === "camera" ? "active" : ""} type="button" disabled={mutation.isPending} onClick={() => switchInputMode("camera")}><Camera size={14} />摄像头</button><button className={inputMode === "image" ? "active" : ""} type="button" disabled={mutation.isPending} onClick={() => switchInputMode("image")}><ImagePlus size={14} />图片</button></div>{inputMode === "camera" ? <button type="button" disabled={mutation.isPending || cameraStarting} onClick={() => captureFrame().then(replaceCaptured).catch((error) => setInputError(error.message))}><Camera size={15} />{captured ? "重拍" : "拍照"}</button> : captured ? <button type="button" disabled={mutation.isPending} onClick={clearCaptured}><RefreshCcw size={15} />更换</button> : null}</div>
        <div className={`text-compare-selected-standard ${selectedAsset ? "ready" : ""}`}>{selectedAsset ? <><CheckCircle2 size={20} /><div><small>当前对比标准</small><strong>{CATEGORY_LABELS[selectedAsset.category || ""] || "标签图片"} · 第 {selectedAsset.ordinal} 张（已在左侧高亮）</strong></div></> : <><FileImage size={20} /><span>请先在左侧订单画廊中选择一张标签图片</span></>}</div>
        {inputMode === "camera" ? <label className="text-compare-camera-picker"><span>摄像头设备</span><select value={selectedDeviceId} disabled={cameraStarting || mutation.isPending || !cameraDevices.length} onChange={(event) => { const deviceId = event.currentTarget.value; selectedDeviceIdRef.current = deviceId; setSelectedDeviceId(deviceId); clearCaptured(); void startCamera(deviceId); }} aria-label="选择摄像头设备">{cameraDevices.length ? cameraDevices.map((device, index) => <option key={device.deviceId || index} value={device.deviceId}>{device.label || `摄像头 ${index + 1}`}</option>) : <option value="">{cameraStarting ? "正在读取摄像头…" : "未检测到摄像头"}</option>}</select></label> : null}
        <div className={"text-compare-stage " + inputMode + " " + (resultImage ? "has-image" : "")}>
          {resultImage ? <button className="text-compare-zoom-trigger" type="button" onClick={() => openZoom(resultImage, "实物文字对比结果")}><img src={resultImage} alt="实物文字对比结果" /><span>点击放大查看</span></button> : inputMode === "camera" ? <video ref={videoRef} playsInline muted /> : <FileDropZone className="text-compare-empty text-compare-upload-fill" disabled={mutation.isPending} accept="image/png,image/jpeg,image/webp" ariaLabel="拖拽或选择实物图片" onFiles={(files) => { const file = files[0]; if (!file) return; try { replaceCaptured(file); } catch (error) { setInputError((error as Error).message); } }}><ImagePlus size={38} /><strong>上传实物图片</strong><span>支持 PNG、JPG、WEBP，也可以直接拖入</span><em><Upload size={15} />选择图片</em></FileDropZone>}
          {inputMode === "camera" && cameraError && !captured ? <div className="text-compare-camera-error"><AlertTriangle size={28} /><strong>摄像头不可用</strong><span>{cameraError}</span></div> : null}
        </div>
      </article> : null}
    </div>
    {mode === "manual" ? <div className="text-compare-alert"><AlertTriangle size={18} />说明书逐页会话后端已启用；页面拍摄与自动页匹配正在灰度验收，系统不会在证据不足时返回通过。</div> : null}
    {mode === "label" ? <>
    <div className="text-compare-action-row">
      <button className="text-compare-primary" type="button" disabled={!selectedAsset || mutation.isPending || (inputMode === "camera" ? ((cameraStarting || !!cameraError) && !captured) : !captured)} onClick={() => { setInputError(""); mutation.mutate(); }}><ScanText size={22} />{mutation.isPending ? "正在逐字严格对比…" : "开始文字对比"}</button>
      {captured ? <button className="text-compare-next" type="button" disabled={mutation.isPending} onClick={clearCaptured}>{inputMode === "camera" ? <Camera size={18} /> : <FileImage size={18} />}{inputMode === "camera" ? "拍下一件" : "选择下一张"}</button> : null}
    </div>
    {inputError ? <div className="text-compare-alert"><AlertTriangle size={18} />{inputError}</div> : null}
    {result ? <section className={"text-compare-result " + tone}>
      <div className="text-compare-result-summary">{tone === "match" ? <CheckCircle2 /> : <AlertTriangle />}<div><small>辅助对比结果</small><strong>{result.decision === "MATCH" ? "未发现文字差异" : result.decision === "DIFFERENCES" ? "发现疑似差异" : "无法可靠判断"}</strong><p>{result.message}</p></div></div>
      {qualityCopy(result.captured_quality?.reasons) ? <div className="text-compare-quality">拍摄提示：{qualityCopy(result.captured_quality?.reasons)}</div> : null}
      {result.differences.length ? <div className="text-compare-differences">{result.differences.map((difference, index) => <button className={activeDifference === difference.id ? "active" : ""} onClick={() => setActiveDifference(difference.id)} key={difference.id}><span>{index + 1}</span><div><small>{difference.type === "missing" ? "可能漏印" : difference.type === "extra" ? "可能多印" : "文字不同"}</small><strong>标准：{difference.reference_text || "（无）"}</strong><strong>实物：{difference.actual_text || "（无）"}</strong></div><em>{Math.round(difference.confidence * 100)}%</em></button>)}</div> : null}
    </section> : <div className="text-compare-hint"><FileImage size={19} />{inputMode === "camera" ? "标准图会保留；检查下一件时只需重新拍照。" : "标准图会保留；检查下一件时只需选择新的实物图片。"}</div>}
    </> : null}
    {showImport ? <div className="text-standard-modal-backdrop" role="presentation" onMouseDown={() => !importMutation.isPending && setShowImport(false)}><section className="text-standard-modal import" role="dialog" aria-modal="true" aria-labelledby="text-standard-import-title" onMouseDown={(event) => event.stopPropagation()}>
      <header><button type="button" aria-label="返回标准库" disabled={importMutation.isPending} onClick={() => setShowImport(false)}><ArrowLeft size={18} /></button><div><strong id="text-standard-import-title">导入{mode === "label" ? "标签" : "说明书"}标准</strong><small>填写订单信息并上传标准文档</small></div><button type="button" aria-label="关闭导入" disabled={importMutation.isPending} onClick={() => setShowImport(false)}><X size={18} /></button></header>
      <div className="text-standard-modal-body text-standard-import-form">
        <label className="field">标准名称<input value={importName} onChange={(event) => setImportName(event.currentTarget.value)} placeholder="例如：电池包底部标签" autoFocus /></label>
        <label className="field">物料编码<input value={importMaterial} onChange={(event) => setImportMaterial(event.currentTarget.value)} placeholder="例如：PKG-BAT-001" /></label>
        <label className="field">版本<input value={importVersion} onChange={(event) => setImportVersion(event.currentTarget.value)} placeholder="例如：V1" /></label>
        <div className="field wide"><span>标准文档</span><FileDropZone className="dropzone compact-dropzone" accept={mode === "label" ? ".docx" : ".pdf"} disabled={importMutation.isPending} ariaLabel="拖拽或选择标准文档" onFiles={(files) => setImportFile(files[0] || null)}><strong>{importFile?.name || "拖拽标准文档到这里，或点击选择"}</strong><span>{mode === "label" ? "上传 DOCX，系统会提取其中的标签候选图片。" : "上传 PDF，系统会按页建立说明书标准。"}</span></FileDropZone></div>
        {inputError ? <div className="text-standard-form-error"><AlertTriangle size={16} />{inputError}</div> : null}
      </div>
      <footer><button type="button" disabled={importMutation.isPending} onClick={() => setShowImport(false)}>取消</button><button className="primary" type="button" disabled={importMutation.isPending} onClick={() => { setInputError(""); importMutation.mutate(); }}>{importMutation.isPending ? "正在安全解析…" : "导入并整理图片"}</button></footer>
    </section></div> : null}
    {zoomedImage ? <div className="text-compare-lightbox-backdrop" role="presentation" onMouseDown={() => setZoomedImage(null)}><section className="text-compare-lightbox" role="dialog" aria-modal="true" aria-label={`${zoomedImage.alt}放大预览`} onMouseDown={(event) => event.stopPropagation()}><header><strong>{zoomedImage.alt}</strong><div><button type="button" aria-label="缩小图片" disabled={zoomScale <= 1} onClick={() => setZoomScale((value) => Math.max(1, value - .5))}><Minus size={17} /></button><output>{Math.round(zoomScale * 100)}%</output><button type="button" aria-label="放大图片" disabled={zoomScale >= 3} onClick={() => setZoomScale((value) => Math.min(3, value + .5))}><Plus size={17} /></button><button type="button" onClick={() => setZoomScale(1)}>适合窗口</button><button type="button" aria-label="关闭放大预览" onClick={() => setZoomedImage(null)}><X size={18} /></button></div></header><div className="text-compare-lightbox-viewport"><img src={zoomedImage.src} alt={zoomedImage.alt} style={{ width: `${zoomScale * 100}%` }} /></div></section></div> : null}
  </section>;
}
