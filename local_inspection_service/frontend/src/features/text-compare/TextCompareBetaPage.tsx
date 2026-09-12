import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, Camera, CheckCircle2, ChevronDown, ChevronRight, Expand, FileImage, ImagePlus, Minus, Plus, RefreshCcw, ScanText, Upload, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addTextInspectionStandardAsset, classifyTextInspectionStandard, deleteTextInspectionStandard, compareTextInspectionLabel, confirmTextInspectionStandard, getTextInspectionStandard, importTextInspectionStandard, listTextInspectionStandards, patchTextInspectionAsset } from "../../api/queries";
import type { TextCompareBetaResult, TextInspectionAsset } from "../../api/types";
import { FileDropZone } from "../../components/FileDropZone";
import { apiClient } from "../../api/client";
import { useAgentActions } from "../agent/useAgentActions";
import { getFile, rememberFile } from "../agent/files";
import { useAgentState } from "../agent/useAgentState";
import { cameraPermissionRequired } from "../agent/nativePermissions";
import { StandardPreparation, type PreparationPreview } from "./StandardPreparation";
import { EvidenceResults } from "./EvidenceResults";

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const IMAGE_ACCEPT = "image/*,.jpg,.jpeg,.png,.webp,.avif,.heic,.heif,.mpo,.bmp,.gif,.tif,.tiff";
function validateImage(file: File) {
  if (!file.size || file.size > MAX_FILE_BYTES) throw new Error("图片必须小于 10MB。");
}
function qualityCopy(reasons?: string[]) {
  const labels: Record<string, string> = { resolution_too_low: "分辨率太低", blurred: "画面模糊", underexposed: "画面太暗", overexposed_or_glare: "过曝或反光明显" };
  return (reasons || []).map((reason) => labels[reason] || reason).join("、");
}

const MAX_DIAGNOSTIC_OUTPUT_CHARS = 20_000;
function formatDiagnosticOutput(value: unknown) {
  let output: string;
  if (typeof value === "string") output = value;
  else {
    try { output = JSON.stringify(value, null, 2) ?? String(value); }
    catch { output = String(value); }
  }
  return output.length > MAX_DIAGNOSTIC_OUTPUT_CHARS
    ? `${output.slice(0, MAX_DIAGNOSTIC_OUTPUT_CHARS)}\n…（显示内容已截断）`
    : output;
}

const CATEGORY_LABELS: Record<string, string> = {
  label: "标签",
  label_design: "标签设计图",
  physical_photo: "实物照片",
  manual: "说明书",
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
  if (asset.status === "excluded") return "非标签 · 不保留";
  if (asset.status === "needs_confirmation") return "待定 · 需要确认";
  return asset.status === "page" ? "标准页面" : "标签 · 保留";
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
  const [comparisonPhase, setComparisonPhase] = useState("");
  const [activeDifference, setActiveDifference] = useState("");
  const [zoomedImage, setZoomedImage] = useState<{ src: string; alt: string } | null>(null);
  const [zoomScale, setZoomScale] = useState(1);
  const [preparationPreview, setPreparationPreview] = useState<PreparationPreview | null>(null);
  const [activation, setActivation] = useState(0);
  const [mode, setMode] = useState<"label" | "manual">("label");
  const [selectedStandardId, setSelectedStandardId] = useState("");
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [assetFilter, setAssetFilter] = useState("all");
  const [reviewNotice, setReviewNotice] = useState("");
  useEffect(() => { setAssetFilter("all"); setReviewNotice(""); }, [selectedStandardId]);
  const [assetUploadFile, setAssetUploadFile] = useState<File | null>(null);
  const [importName, setImportName] = useState("");
  const [importMaterial, setImportMaterial] = useState("");
  const [importVersion, setImportVersion] = useState("V1");
  const [importFile, setImportFile] = useState<File | null>(null);
  const providerDiagnostics = result?.diagnostics?.provider_result;
  const rawProviderOutput = providerDiagnostics?.response_preview !== undefined
    ? providerDiagnostics.response_preview
    : providerDiagnostics?.parsed_response;
  const normalizedOutput = result?.diagnostics?.normalized_response;
  const hasDiagnosticOutput = rawProviderOutput !== undefined || normalizedOutput !== undefined || result?.diagnostics?.provider === "qwen_ocr";
  const standardsQuery = useQuery({ queryKey: ["text-inspection", "standards"], queryFn: listTextInspectionStandards });
  const standardQuery = useQuery({ queryKey: ["text-inspection", "standard", selectedStandardId], queryFn: () => getTextInspectionStandard(selectedStandardId), enabled: !!selectedStandardId, refetchInterval: (query) => query.state.data?.classification?.state === "processing" ? 2000 : false });
  const selectedOrderRef = useRef(selectedStandardId); selectedOrderRef.current = selectedStandardId;
  const classifyMutation = useMutation({ mutationFn: classifyTextInspectionStandard, onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["text-inspection"] }); }, onError: (error: Error) => setInputError(error.message) });
  const deleteOrderMutation = useMutation({ mutationFn: deleteTextInspectionStandard, onSuccess: (_value, id) => {
    if (selectedOrderRef.current === id) { setSelectedStandardId(""); setSelectedAssetId(""); resetComparison(); }
    void queryClient.invalidateQueries({ queryKey: ["text-inspection"] });
  }, onError: (error: Error) => setInputError(error.message) });
  const selectedAsset = standardQuery.data?.status === "confirmed"
    ? standardQuery.data.assets?.find((asset) => asset.id === selectedAssetId && isActiveAsset(asset) && asset.comparison_ready !== false) : undefined;
  const importMutation = useMutation({
    mutationFn: () => {
      if (!importFile || !importName.trim() || !importMaterial.trim() || !importVersion.trim()) throw new Error("请填写标准名称、物料编码、版本并选择 DOC、DOCX 或 PDF。");
      const expectedSuffixes = mode === "label" ? [".doc", ".docx"] : [".pdf"];
      if (!expectedSuffixes.some((suffix) => importFile.name.toLowerCase().endsWith(suffix))) throw new Error(mode === "label" ? "标签标准请上传 DOC 或 DOCX 文件。" : "说明书标准请上传 PDF 文件。");
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
    mutationFn: ({ standardId, assetId, action, revision }: { standardId: string; assetId: string; action: "restore" | "remove" | "confirm" | "review"; revision?: number }) => patchTextInspectionAsset(standardId, assetId, action, revision),
    onSuccess: async (_value, variables) => {
      if (variables.standardId !== selectedStandardId) {
        await queryClient.invalidateQueries({ queryKey: ["text-inspection"] });
        return;
      }
      if ((variables.action === "remove" || variables.action === "review") && variables.assetId === selectedAssetId) {
        setSelectedAssetId(""); resetComparison();
      } else {
        resetComparison();
      }
      setReviewNotice("人工选择已保存。可随时重新修改，原图片不会删除。");
      await queryClient.invalidateQueries({ queryKey: ["text-inspection"] });
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
  const confirmMutation = useMutation({ mutationFn: () => confirmTextInspectionStandard(selectedStandardId), onSuccess: () => { resetComparison(); setActivation(v => v + 1); void queryClient.invalidateQueries({ queryKey: ["text-inspection"] }); }, onError: (error: Error) => setInputError(error.message) });

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
    if (asset.comparison_ready === false) { setInputError(asset.comparison_unavailable_reason || "此图片尚未完成标准准备，请先查看处理进度或确认异常项。"); return; }
    if (standardQuery.data?.status !== "confirmed") {
      setInputError("这个订单还没有启用。请先启用候选图片并保存订单，再开始对比。");
      return;
    }
    resetComparison();
    setSelectedAssetId(asset.id);
  };
  useEffect(() => { resetComparison(); }, [selectedAsset?.active_preparation?.id, standardQuery.data?.current_revision_id]);
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
  const switchInputMode = (nextMode: "camera" | "image", deviceId?: string) => {
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
      void startCamera(deviceId);
    }
  };
  const openZoom = (src: string, alt: string) => {
    setZoomScale(1);
    setZoomedImage({ src, alt });
  };
  const openStandardPreview = (asset: TextInspectionAsset) => {
    if (!asset.content_url) return;
    const title = `${CATEGORY_LABELS[asset.category || ""] || "标准图片"} ${asset.ordinal}`;
    if (mode === "label") setPreparationPreview({ id: asset.id, url: asset.content_url, title });
    else openZoom(asset.content_url, title);
  };
  useEffect(() => { setPreparationPreview(null); }, [selectedStandardId, mode]);

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
      if (!selectedAsset.active_preparation) throw new Error("请先在左侧启用标准并完成元素模板准备；无需提取实拍标签。");
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
      form.set("standard_asset_id", selectedAsset.id);
      let response = await compareTextInspectionLabel(form);
      const showPhase = (value: TextCompareBetaResult) => {
        if (comparisonIdentityRef.current?.id !== identity.id) return;
        const labels: Record<string, string> = { queued: "排队", extracting_text: "提取文字", direct_matching: "直接核对", mapping_unmatched: "疑难对应", verifying_saving: "验证保存", recognizing: "识别文字" };
        setComparisonPhase(labels[String(value.diagnostics?.phase)] || "等待结果");
      };
      showPhase(response);
      const deadline = Date.now() + 125000;
      while (response.preparation_compare && response.status === "attempting" && response.id && Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 1500));
        if (comparisonIdentityRef.current?.id !== identity.id) return response;
        response = await apiClient.get<TextCompareBetaResult>(`/api/text-inspection/prepared-comparisons/${response.id}`);
        showPhase(response);
      }
      return response;
    },
    onMutate: () => { busyRef.current = true; setComparisonPhase("上传图片"); },
    onSuccess: (value) => {
      if (comparisonIdentityRef.current?.id !== value.comparison_id) return;
      setResult(value); setActiveDifference(value.differences[0]?.id || "");
    },
    onError: (error: Error) => setInputError(error.message),
    onSettled: () => { busyRef.current = false; setComparisonPhase(""); }
  });
  const resultImage = result?.annotated_image_data_url || capturedUrl;
  const tone = result?.decision === "MATCH" ? "match" : result?.decision === "DIFFERENCES" ? "differences" : "review";
  const visibleStandards = (standardsQuery.data?.items || []).filter((item) => item.standard_type === mode);
  const visibleAssets = standardQuery.data?.assets || [];
  const retainedAssetCount = visibleAssets.filter(isActiveAsset).length;
  const pendingAssetCount = visibleAssets.filter((asset) => asset.status === "needs_confirmation").length;
  const excludedAssetCount = visibleAssets.filter((asset) => asset.status === "excluded").length;
  // Sort the display copy only: retain source ordinals, IDs and immutable snapshots.
  const reviewRank = (asset: TextInspectionAsset) => isActiveAsset(asset) ? 0 : asset.status === "excluded" ? 2 : 1;
  const filteredAssets = visibleAssets.filter((asset) => assetFilter === "all" || asset.status === assetFilter)
    .sort((a, b) => reviewRank(a) - reviewRank(b) || a.ordinal - b.ordinal);
  const classification = standardQuery.data?.classification;
  const reviewBusy = assetMutation.isPending || assetUploadMutation.isPending || confirmMutation.isPending || standardQuery.isFetching || deleteOrderMutation.isPending;
  const renderAssetCards = () => <>
    {mode === "label" ? <div className="text-standard-review-summary">
      <strong>确认要保留的标签设计图</strong><p>绿色为标签，琥珀色为待定，灰色为非标签。分类仅作建议，所有图片都能放大查看和手动修改，不会删除原图。</p>
      <div className="text-standard-review-filters" role="group" aria-label="筛选图片分类">{[["all", `全部 ${visibleAssets.length}`], ["candidate", `标签 ${retainedAssetCount}`], ["needs_confirmation", `待定 ${pendingAssetCount}`], ["excluded", `非标签 ${excludedAssetCount}`]].map(([value, label]) => <button type="button" key={value} aria-pressed={assetFilter === value} onClick={() => setAssetFilter(value)}>{label}</button>)}</div>
      <div role="status" aria-live="polite">{assetMutation.isPending ? "正在保存人工选择…" : reviewNotice}</div>
    </div> : null}
    <div className="text-standard-asset-grid" data-testid="standard-library-assets">
    {(mode === "label" ? filteredAssets : visibleAssets).map((asset) => {
      const selectable = mode === "label" && isActiveAsset(asset) && standardQuery.data?.status === "confirmed" && asset.comparison_ready !== false;
      const selected = selectedAssetId === asset.id;
      return <article className={`text-standard-asset-card ${mode === "label" ? `classification-${asset.status}` : ""} ${selected ? "selected" : ""} ${asset.status === "excluded" ? "removed" : ""}`} key={asset.id}>
      <button className="text-standard-thumbnail" type="button" onClick={() => selectable ? chooseAsset(asset) : asset.content_url && openZoom(asset.content_url, `${CATEGORY_LABELS[asset.category || ""] || "标准图片"} ${asset.ordinal}`)} disabled={!asset.content_url} aria-pressed={selectable ? selected : undefined} aria-label={selectable ? `选择第 ${asset.ordinal} 张标签作为对比标准` : `查看第 ${asset.ordinal} 张标准大图`}>
        {asset.content_url ? <img src={asset.content_url} alt={`第 ${asset.ordinal} 张标准缩略图`} loading="lazy" /> : <span><FileImage size={26} />暂无预览</span>}
        <em>{asset.ordinal}</em>
        {selectable ? <i>{selected ? "已选标准" : "点击选中"}</i> : null}
      </button>
      {asset.comparison_unavailable_reason ? <small role="status">{asset.comparison_unavailable_reason}</small> : null}
      <div className="text-standard-asset-copy"><span className="text-standard-classification-badge">{asset.status === "needs_confirmation" ? <AlertTriangle size={15} /> : isActiveAsset(asset) ? <CheckCircle2 size={15} /> : <X size={15} />}{assetStatusCopy(asset)}</span><strong>{CATEGORY_LABELS[asset.category || ""] || "标准图片"}</strong><small>{asset.classification_source === "human" ? "人工已修改" : "系统建议，尚未经人工确认"}{asset.context ? ` · ${asset.context}` : ""}</small>{asset.classification_reason ? <details><summary>查看分类依据</summary><p>{asset.classification_reason}</p></details> : null}</div>
      <div className="text-standard-asset-actions">
        {asset.content_url ? <button type="button" onClick={() => openStandardPreview(asset)}><Expand size={14} />查看大图</button> : null}
        {selectable ? <button type="button" disabled={mutation.isPending} onClick={() => chooseAsset(asset)} aria-pressed={selected} className="text-standard-select-reference">{selected ? "已选为对比标准" : "用作对比标准"}</button> : null}
        {mode === "label" ? <div className={`text-standard-retention-control retention-${asset.status}`}>
        <span className="text-standard-retention-state">{asset.status === "candidate" ? <CheckCircle2 size={16} /> : asset.status === "excluded" ? <X size={16} /> : <AlertTriangle size={16} />}{asset.status === "candidate" ? "已保留" : asset.status === "excluded" ? "未保留" : "待确认"}</span>
        <button
          type="button"
          className="text-standard-retention-toggle"
          aria-label={`第 ${asset.ordinal} 张图片：${asset.status === "candidate" ? "改为不保留" : "改为保留"}`}
          title={asset.status === "candidate" ? "点击改为不保留" : "点击改为保留"}
          disabled={reviewBusy}
          onClick={() => { setInputError(""); assetMutation.mutate({ standardId: selectedStandardId, assetId: asset.id, revision: standardQuery.data?.revision_number, action: asset.status === "candidate" ? "remove" : "confirm" }); }}
        >{asset.status === "candidate" ? "改为不保留" : "改为保留"}</button></div> : <button type="button" disabled={reviewBusy} onClick={() => assetMutation.mutate({ standardId: selectedStandardId, assetId: asset.id, revision: standardQuery.data?.revision_number, action: asset.status === "excluded" ? "restore" : "remove" })}>{asset.status === "excluded" ? "启用" : "停用"}</button>}
      </div>
    </article>})}
    {!visibleAssets.length && !standardQuery.isLoading ? <div className="text-standard-empty"><ImagePlus size={28} /><strong>还没有标准图片</strong><span>请在当前订单中添加图片，或重新导入包含图片的文档。</span></div> : null}
    {mode === "label" && visibleAssets.length > 0 && !filteredAssets.length ? <div className="text-standard-empty"><strong>这个分类下暂无图片</strong><button type="button" onClick={() => setAssetFilter("all")}>查看全部图片</button></div> : null}
  </div></>;

  useAgentState("text_import", "text", {
    name:{value:importName,schema:{type:"string",maxLength:200},set:setImportName},
    material_code:{value:importMaterial,schema:{type:"string",maxLength:200},set:setImportMaterial},
    version_label:{value:importVersion,schema:{type:"string",maxLength:100},set:setImportVersion}
  });
  useAgentActions([
    {name:"text_prepare_import",domain:"text",description:"Open the document import form and optionally select a file handle. Edit fields with text_import_set_fields, then submit with text_import_current.",readOnly:false,inputSchema:{type:"object",properties:{file_id:{type:"string"}},additionalProperties:false},execute:input=>{setShowImport(true);if(input.file_id)setImportFile(getFile(String(input.file_id)));}},
    {name:"text_filter_assets",domain:"text",description:"Filter the current standard gallery using the same status filter as the page.",readOnly:false,inputSchema:{type:"object",properties:{filter:{type:"string",enum:["all","candidate","excluded","needs_confirmation","pending","page"]}},required:["filter"],additionalProperties:false},execute:input=>setAssetFilter(String(input.filter))},
    {name:"text_get_state",domain:"text",description:"Read the current standard, selected reference, captured asset and comparison evidence.",readOnly:true,inputSchema:{type:"object",properties:{},additionalProperties:false},execute:()=>({mode,inputMode,selectedStandardId,selectedAssetId,captured_file_id:captured ? rememberFile(captured) : null,result,inputError,cameraError,busy:mutation.isPending})},
    {name:"text_select_standard",domain:"text",description:"Select a standard and invalidate stale comparison state using the existing workspace action.",readOnly:false,inputSchema:{type:"object",properties:{standard_id:{type:"string"}},required:["standard_id"],additionalProperties:false},execute:input=>{const id=String(input.standard_id);if(!standardsQuery.data?.items.some(item=>item.id===id)) throw new Error("Standard is not in the current authorized library");chooseStandard(id);}},
    {name:"text_select_asset",domain:"text",description:"Select a confirmed enabled reference asset from the current standard.",readOnly:false,inputSchema:{type:"object",properties:{asset_id:{type:"string"}},required:["asset_id"],additionalProperties:false},execute:input=>{const asset=visibleAssets.find(item=>item.id===input.asset_id);if(!asset || !isActiveAsset(asset) || standardQuery.data?.status!=="confirmed")throw new Error("Reference is not confirmed and enabled");chooseAsset(asset);}},
    {name:"text_set_actual_image",domain:"text",description:"Use an explicitly selected file as the actual image and clear stale comparison results.",readOnly:false,inputSchema:{type:"object",properties:{file_id:{type:"string"}},required:["file_id"],additionalProperties:false},execute:input=>{switchInputMode("image");replaceCaptured(getFile(String(input.file_id)));}},
    {name:"text_compare",domain:"text",description:"Compare the full actual image against saved standard elements; no extraction required.",readOnly:false,inputSchema:{type:"object",properties:{},additionalProperties:false},available:()=>mutation.isPending ? "Comparison is already running" : null,execute:()=>mutation.mutateAsync()},
    {name:"text_import_current",domain:"text",description:"Import the document selected in the current standard form using its validated fields.",readOnly:false,inputSchema:{type:"object",properties:{},additionalProperties:false},execute:()=>importMutation.mutateAsync()},
    {name:"text_start_camera",domain:"text",description:"Start a camera for text inspection; the browser may request native permission.",readOnly:false,inputSchema:{type:"object",properties:{device_id:{type:"string"}},additionalProperties:false},execute:async input=>{if(!streamRef.current && await cameraPermissionRequired())return {status:"requires_user_input",data:{instruction:"Authorize the camera using the visible camera control."},next_action:"text_get_state"};if(inputMode!=="camera")switchInputMode("camera",String(input.device_id||selectedDeviceId));else await startCamera(String(input.device_id||selectedDeviceId));return {status:"accepted",next_action:"text_get_state"};}},
    {name:"text_stop_camera",domain:"text",description:"Stop the text inspection camera.",readOnly:false,inputSchema:{type:"object",properties:{},additionalProperties:false},execute:stopCamera}
  ]);
  return <section className="view active text-compare-beta">
    <div className="text-compare-compact-topbar">
      <header className="text-compare-beta-header">
        <div><span className="eyebrow">账号专属标准库</span><h2>文字检验</h2><p>标签严格对比与说明书逐页检验集中在一个工作台。</p></div>
      </header>
      <div className="sidebar-task-type-switch" role="tablist" aria-label="文字检验模式">
        <button className={mode === "label" ? "active" : ""} role="tab" aria-selected={mode === "label"} aria-controls="text-standard-library-panel" type="button" onClick={() => { if (mode !== "label") { setMode("label"); setSelectedStandardId(""); setSelectedAssetId(""); setShowImport(false); resetComparison({ clearCaptured: true }); if (inputMode === "camera") { cameraSurfaceActiveRef.current = true; void startCamera(); } } }}>标签对比</button>
        <button className={mode === "manual" ? "active" : ""} role="tab" aria-selected={mode === "manual"} aria-controls="text-standard-library-panel" type="button" onClick={() => { if (mode !== "manual") { setMode("manual"); setSelectedStandardId(""); setSelectedAssetId(""); setShowImport(false); resetComparison({ clearCaptured: true }); cameraSurfaceActiveRef.current = false; ++cameraRequestRef.current; stopCamera(); setCameraStarting(false); } }}>说明书逐页检验</button>
      </div>
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
              {mode === "label" ? <div className="text-standard-document-actions">
                <div role="status" aria-live="polite">{classification?.state === "processing" ? `正在识别 ${classification.done || 0}/${classification.total || 0} 张图片…` : classification?.state === "completed" ? "视觉分类完成，请检查并确认保留的标签。" : classification?.reason || "此订单尚未进行视觉分类。"}</div>
                {standardQuery.data?.status === "draft" && !classification?.id ? <button type="button" disabled={classifyMutation.isPending || reviewBusy} onClick={() => classifyMutation.mutate(standard.id)}>{classifyMutation.isPending ? "正在启动…" : "识别标签"}</button> : null}
                <button type="button" className="text-standard-delete-order" disabled={deleteOrderMutation.isPending || assetMutation.isPending} onClick={() => { if (window.confirm(`删除标签订单“${standard.name}”？订单将从列表隐藏，原图和历史对比记录仍保留。`)) deleteOrderMutation.mutate(standard.id); }}>删除标签订单</button>
              </div> : null}
              {standardQuery.data?.standard_type === "label" ? <div className="text-standard-inline-controls"><FileDropZone className="text-standard-add-asset-drop" accept={IMAGE_ACCEPT} disabled={assetUploadMutation.isPending} ariaLabel="拖拽或选择单张标准图片" onFiles={(files) => { setAssetUploadFile(files[0] || null); setInputError(""); }}><ImagePlus size={16} /><span>{assetUploadFile ? assetUploadFile.name : "拖拽或选择单张图片"}</span></FileDropZone><button type="button" disabled={!assetUploadFile || assetUploadMutation.isPending} onClick={() => assetUploadMutation.mutate()}>{assetUploadMutation.isPending ? "添加中…" : "添加到标准"}</button></div> : null}
              {standardQuery.isError ? <div className="text-standard-empty error"><AlertTriangle size={22} /><strong>订单内容加载失败</strong><button type="button" onClick={() => void standardQuery.refetch()}>重试</button></div> : renderAssetCards()}
              {mode === "label" ? <StandardPreparation key={standard.id} standardId={standard.id} onZoom={openZoom} activation={activation} preview={preparationPreview} onPreviewHandled={() => setPreparationPreview(null)} confirmed={standardQuery.data?.status === "confirmed"} disabled={reviewBusy || pendingAssetCount > 0 || !retainedAssetCount} onActivate={() => confirmMutation.mutate()} /> : null}
              {inputError ? <div className="text-standard-form-error"><AlertTriangle size={16} />{inputError}</div> : null}
              {standardQuery.data?.status === "draft" ? <div className="text-standard-inline-footer"><span>{pendingAssetCount ? `还有 ${pendingAssetCount} 张待定图片，请选择保留或排除。` : `将保留 ${retainedAssetCount} 张，排除 ${excludedAssetCount} 张；排除的图片仍可恢复。`}</span>{pendingAssetCount ? <button type="button" onClick={() => setAssetFilter("needs_confirmation")}>查看待定项</button> : null}<button type="button" disabled={!retainedAssetCount || pendingAssetCount > 0 || reviewBusy || classification?.state === "processing"} onClick={() => confirmMutation.mutate()}>{confirmMutation.isPending ? "正在保存…" : `确认保留 ${retainedAssetCount} 张并启用`}</button></div> : null}
            </div> : null}
          </article>;
        })}
      </div>
    </section>
    {mode === "label" ? <article className="text-compare-panel text-compare-actual-panel">
        <div className="text-compare-panel-title"><span>02</span><div><strong>实物图片</strong><small>{inputMode === "camera" ? (captured ? "已拍照，可重新拍摄" : "来自当前摄像头画面") : (captured ? `已选择 ${captured.name}` : "上传已有图片进行对比")}</small></div><div className="text-compare-input-switch" role="group" aria-label="实物图片来源"><button className={inputMode === "camera" ? "active" : ""} type="button" disabled={mutation.isPending} onClick={() => switchInputMode("camera")}><Camera size={14} />摄像头</button><button className={inputMode === "image" ? "active" : ""} type="button" disabled={mutation.isPending} onClick={() => switchInputMode("image")}><ImagePlus size={14} />图片</button></div>{inputMode === "camera" ? <button type="button" disabled={mutation.isPending || cameraStarting} onClick={() => captured ? clearCaptured() : captureFrame().then(replaceCaptured).catch((error) => setInputError(error.message))}><Camera size={15} />{captured ? "重拍" : "拍照"}</button> : captured ? <button type="button" disabled={mutation.isPending} onClick={clearCaptured}><RefreshCcw size={15} />更换</button> : null}</div>
        <div className={`text-compare-selected-standard ${selectedAsset ? "ready" : ""}`}>{selectedAsset ? <><CheckCircle2 size={20} /><div><small>当前对比标准</small><strong>{CATEGORY_LABELS[selectedAsset.category || ""] || "标签图片"} · 第 {selectedAsset.ordinal} 张（已在左侧高亮）</strong></div></> : <><FileImage size={20} /><span>请先在左侧订单画廊中选择一张标签图片</span></>}</div>
        {inputMode === "camera" ? <label className="text-compare-camera-picker"><span>摄像头设备</span><select value={selectedDeviceId} disabled={cameraStarting || mutation.isPending || !cameraDevices.length} onChange={(event) => { const deviceId = event.currentTarget.value; selectedDeviceIdRef.current = deviceId; setSelectedDeviceId(deviceId); clearCaptured(); void startCamera(deviceId); }} aria-label="选择摄像头设备">{cameraDevices.length ? cameraDevices.map((device, index) => <option key={device.deviceId || index} value={device.deviceId}>{device.label || `摄像头 ${index + 1}`}</option>) : <option value="">{cameraStarting ? "正在读取摄像头…" : "未检测到摄像头"}</option>}</select></label> : null}
        <div className={"text-compare-stage " + inputMode + " " + (resultImage ? "has-image" : "")}>
          {resultImage ? <button className="text-compare-zoom-trigger" type="button" onClick={() => openZoom(resultImage, "实物文字对比结果")}><img src={resultImage} alt="实物文字对比结果" /><span>点击放大查看</span></button> : inputMode === "camera" ? <video ref={videoRef} playsInline muted /> : <FileDropZone className="text-compare-empty text-compare-upload-fill" disabled={mutation.isPending} accept={IMAGE_ACCEPT} ariaLabel="拖拽或选择实物图片" onFiles={(files) => { const file = files[0]; if (!file) return; try { replaceCaptured(file); } catch (error) { setInputError((error as Error).message); } }}><ImagePlus size={38} /><strong>上传实物图片</strong><span>支持常见图片格式，也可以直接拖入；系统会按实际内容识别</span><em><Upload size={15} />选择图片</em></FileDropZone>}
          {inputMode === "camera" && cameraError && !captured ? <div className="text-compare-camera-error"><AlertTriangle size={28} /><strong>摄像头不可用</strong><span>{cameraError}</span></div> : null}
        </div>
    <div className="text-compare-action-row">
      <button className="text-compare-primary" type="button" disabled={!selectedAsset?.active_preparation || mutation.isPending || (inputMode === "camera" ? ((cameraStarting || !!cameraError) && !captured) : !captured)} onClick={() => { setInputError(""); mutation.mutate(); }}><ScanText size={22} />{mutation.isPending ? `${comparisonPhase || "正在逐字严格对比"}…` : "开始文字对比"}</button>
      <p>整页核对：每个标准元素找到一次严格匹配即可；不检查每枚标签的漏印或混印，图形未检查。</p>
      {selectedAsset && !selectedAsset.active_preparation ? <p role="status">此标准尚无元素模板，请在左侧启用标准并完成准备；不需要对实拍图抠图。</p> : null}
      {captured && result && result.status !== "attempting" ? <button className="text-compare-next" type="button" disabled={mutation.isPending} onClick={clearCaptured}>{inputMode === "camera" ? <Camera size={18} /> : <FileImage size={18} />}{inputMode === "camera" ? "拍下一件" : "选择下一张"}</button> : null}
    </div>
      </article> : null}
    </div>
    {mode === "manual" ? <div className="text-compare-alert"><AlertTriangle size={18} />说明书逐页会话后端已启用；页面拍摄与自动页匹配正在灰度验收，系统不会在证据不足时返回通过。</div> : null}
    {mode === "label" ? <>
    {inputError ? <div className="text-compare-alert"><AlertTriangle size={18} />{inputError}</div> : null}
    {result ? <section className={"text-compare-result " + tone}>
      <div className="text-compare-result-summary">{tone === "match" ? <CheckCircle2 /> : <AlertTriangle />}<div><small>辅助对比结果</small><strong>{result.decision === "MATCH" ? "未发现文字差异" : result.decision === "DIFFERENCES" ? "发现疑似差异" : "无法可靠判断"}</strong><p>{result.message}</p></div></div>
      {qualityCopy(result.captured_quality?.reasons) ? <div className="text-compare-quality">拍摄提示：{qualityCopy(result.captured_quality?.reasons)}</div> : null}
      {result.diagnostics?.provider === "qwen_ocr" && result.reference_overlay_url && result.id ? <EvidenceResults key={result.id} value={normalizedOutput} reference={result.reference_overlay_url} source={`/api/text-inspection/prepared-comparisons/${result.id}/media/source`} /> : null}
      {result.reference_overlay_url ? <button type="button" onClick={() => openZoom(result.reference_overlay_url!, "标准元素：绿色已匹配，黄色待复核")}><img src={result.reference_overlay_url} alt="标准元素核对结果：绿色已匹配，黄色待复核" style={{ maxWidth: "100%", maxHeight: 320 }} />查看标准元素核对图（图形未检查）</button> : null}
      {result.differences.length ? <div className="text-compare-differences">{result.differences.map((difference, index) => <button className={activeDifference === difference.id ? "active" : ""} onClick={() => setActiveDifference(difference.id)} key={difference.id}><span>{index + 1}</span><div><small>{difference.type === "missing" ? "可能漏印" : difference.type === "extra" ? "可能多印" : "文字不同"}</small><strong>标准：{difference.reference_text || "（无）"}</strong><strong>实物：{difference.actual_text || "（无）"}</strong></div><em>{Math.round(difference.confidence * 100)}%</em></button>)}</div> : null}
      {hasDiagnosticOutput ? <details className="text-compare-raw-output">
        <summary><ChevronRight size={15} /><span>Raw Output（调试信息）</span><small>默认折叠</small></summary>
        <div className="text-compare-raw-output-body">
          {result.diagnostics?.provider === "qwen_ocr" ? <section><header><strong>OCR 与证据匹配诊断</strong></header><pre>{formatDiagnosticOutput(result.diagnostics)}</pre></section> : null}
          {rawProviderOutput !== undefined ? <section><header><strong>模型原始输出</strong><small>{providerDiagnostics?.response_preview !== undefined ? "原始文本预览" : "解析后的 JSON"}</small></header><pre>{formatDiagnosticOutput(rawProviderOutput)}</pre></section> : null}
          {normalizedOutput !== undefined ? <section><header><strong>系统适配结果</strong><small>进入业务校验前的数据</small></header><pre>{formatDiagnosticOutput(normalizedOutput)}</pre></section> : null}
        </div>
      </details> : null}
    </section> : <div className="text-compare-hint"><FileImage size={19} />{inputMode === "camera" ? "标准图会保留；检查下一件时只需重新拍照。" : "标准图会保留；检查下一件时只需选择新的实物图片。"}</div>}
    </> : null}
    {showImport ? <div className="text-standard-modal-backdrop" role="presentation" onMouseDown={() => !importMutation.isPending && setShowImport(false)}><section className="text-standard-modal import" role="dialog" aria-modal="true" aria-labelledby="text-standard-import-title" onMouseDown={(event) => event.stopPropagation()}>
      <header><button type="button" aria-label="返回标准库" disabled={importMutation.isPending} onClick={() => setShowImport(false)}><ArrowLeft size={18} /></button><div><strong id="text-standard-import-title">导入{mode === "label" ? "标签" : "说明书"}标准</strong><small>填写订单信息并上传标准文档</small></div><button type="button" aria-label="关闭导入" disabled={importMutation.isPending} onClick={() => setShowImport(false)}><X size={18} /></button></header>
      <div className="text-standard-modal-body text-standard-import-form">
        <label className="field">标准名称<input value={importName} onChange={(event) => setImportName(event.currentTarget.value)} placeholder="例如：电池包底部标签" autoFocus /></label>
        <label className="field">物料编码<input value={importMaterial} onChange={(event) => setImportMaterial(event.currentTarget.value)} placeholder="例如：PKG-BAT-001" /></label>
        <label className="field">版本<input value={importVersion} onChange={(event) => setImportVersion(event.currentTarget.value)} placeholder="例如：V1" /></label>
        <div className="field wide"><span>标准文档</span><FileDropZone className="dropzone compact-dropzone" accept={mode === "label" ? ".doc,.docx" : ".pdf"} disabled={importMutation.isPending} ariaLabel="拖拽或选择标准文档" onFiles={(files) => setImportFile(files[0] || null)}><strong>{importFile?.name || "拖拽标准文档到这里，或点击选择"}</strong><span>{mode === "label" ? "支持 DOC / DOCX。直接提取内嵌图片，不合并 Word 文字或叠加图形；导入后逐张确认。" : "上传 PDF，系统会按页建立说明书标准。"}</span></FileDropZone></div>
        {inputError ? <div className="text-standard-form-error"><AlertTriangle size={16} />{inputError}</div> : null}
      </div>
      <footer><button type="button" disabled={importMutation.isPending} onClick={() => setShowImport(false)}>取消</button><button className="primary" type="button" disabled={importMutation.isPending} onClick={() => { setInputError(""); importMutation.mutate(); }}>{importMutation.isPending ? "正在提取内嵌图片，请稍候…" : "导入并整理图片"}</button></footer>
    </section></div> : null}
    {zoomedImage ? <div className="text-compare-lightbox-backdrop" role="presentation" onMouseDown={() => setZoomedImage(null)}><section className="text-compare-lightbox" role="dialog" aria-modal="true" aria-label={`${zoomedImage.alt}放大预览`} onMouseDown={(event) => event.stopPropagation()}><header><strong>{zoomedImage.alt}</strong><div><button type="button" aria-label="缩小图片" disabled={zoomScale <= 1} onClick={() => setZoomScale((value) => Math.max(1, value - .5))}><Minus size={17} /></button><output>{Math.round(zoomScale * 100)}%</output><button type="button" aria-label="放大图片" disabled={zoomScale >= 3} onClick={() => setZoomScale((value) => Math.min(3, value + .5))}><Plus size={17} /></button><button type="button" onClick={() => setZoomScale(1)}>适合窗口</button><button type="button" aria-label="关闭放大预览" onClick={() => setZoomedImage(null)}><X size={18} /></button></div></header><div className="text-compare-lightbox-viewport"><img src={zoomedImage.src} alt={zoomedImage.alt} style={{ width: `${zoomScale * 100}%` }} /></div></section></div> : null}
  </section>;
}
