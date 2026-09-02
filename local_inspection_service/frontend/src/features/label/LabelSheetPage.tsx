import { useEffect, useMemo, useRef, useState } from "react";
import { Camera, FileImage, Play, RefreshCw, Save, X } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { addLabelSheetReferences, getLabelSheetReferences, matchLabelSheet, queryKeys } from "../../api/queries";
import type { LabelSheetCandidate, LabelSheetMatchResult, LabelSheetReference } from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { FileDropZone } from "../../components/FileDropZone";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { useAuth } from "../auth/auth-context";

type InputMode = "image" | "camera";

function cacheUrl(url = "", token = "") {
  if (!url) return "";
  const suffix = token || String(Date.now());
  return `${url}${url.includes("?") ? "&" : "?"}t=${encodeURIComponent(suffix)}`;
}

function statusText(status = "") {
  return (
    {
      matched: "已匹配",
      unclear: "需复核",
      no_label_reference: "无参考",
      error: "错误"
    }[status] || status || "等待输入"
  );
}

function statusTone(status = ""): "neutral" | "ok" | "fail" | "warn" {
  if (status === "matched") return "ok";
  if (status === "unclear" || status === "no_label_reference") return "warn";
  if (status === "error") return "fail";
  return "neutral";
}

function statusBadgeClass(result: LabelSheetMatchResult | null, busy: boolean) {
  if (busy) return "result-badge waiting";
  if (!result) return "result-badge waiting";
  if (result.status === "matched") return "result-badge pass";
  return "result-badge fail";
}

function scoreText(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(4) : "-";
}

function referenceLabel(reference: LabelSheetReference) {
  return String(reference.name || reference.label || reference.annotation || reference.reference_id || "-");
}

function candidateMetric(candidate: LabelSheetCandidate, key: string) {
  const value = candidate.metrics?.[key];
  if (typeof value === "number") return scoreText(value);
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

async function captureVideoFrame(video: HTMLVideoElement | null) {
  if (!video) throw new Error("摄像头画面尚未准备好");
  if (video.paused && video.srcObject) await video.play().catch(() => undefined);
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (!video.videoWidth || !video.videoHeight) throw new Error("摄像头画面尚未准备好");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("无法读取摄像头画面");
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((next) => (next ? resolve(next) : reject(new Error("拍照失败"))), "image/jpeg", 0.92);
  });
  return new File([blob], `label_sheet_capture_${Date.now()}.jpg`, { type: "image/jpeg" });
}

export function LabelSheetPage() {
  const auth = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<InputMode>("image");
  const [annotation, setAnnotation] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [result, setResult] = useState<LabelSheetMatchResult | null>(null);
  const [busy, setBusy] = useState<"reference" | "match" | "camera" | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [cameraStatus, setCameraStatus] = useState("摄像头图片会走本地标签匹配。");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [referenceFiles, setReferenceFiles] = useState<File[]>([]);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const canViewDiagnostics = auth.user.role === "admin";

  const referencesQuery = useQuery({
    queryKey: queryKeys.labelSheetReferences(auth.dataUserId),
    queryFn: () => getLabelSheetReferences(auth)
  });

  const references = referencesQuery.data?.references || [];
  const filterStats = referencesQuery.data?.doc_filter_stats || {};
  const matchToken = result?.request_id || String(result?.score || "");
  const bestReferenceUrl = result?.matched_reference_image_url || result?.best_reference_image_url || "";
  const matchedName =
    result?.matched_reference_name || result?.matched_reference_label || result?.best_reference_name || result?.best_reference_label || "-";
  const reviewState = result
    ? result.status === "matched"
      ? "自动通过"
      : result.low_confidence_reason || result.review_status || "needs_review"
    : "-";
  const filteredCount = Number((filterStats as { filtered_count?: number }).filtered_count || 0);
  const keptCount = Number((filterStats as { kept_count?: number }).kept_count || references.length);

  const inputPreviewUrl = useMemo(() => (imageFile ? URL.createObjectURL(imageFile) : ""), [imageFile]);
  useEffect(() => () => {
    if (inputPreviewUrl) URL.revokeObjectURL(inputPreviewUrl);
  }, [inputPreviewUrl]);

  function stopCamera() {
    for (const track of streamRef.current?.getTracks?.() || []) track.stop();
    streamRef.current = null;
    setStream(null);
    if (videoRef.current) videoRef.current.srcObject = null;
  }

  useEffect(() => () => stopCamera(), []);

  async function refreshCameras() {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setCameraStatus("当前浏览器不支持摄像头枚举。");
      setDevices([]);
      return [];
    }
    const nextDevices = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === "videoinput");
    setDevices(nextDevices);
    if (!selectedDeviceId && nextDevices[0]?.deviceId) setSelectedDeviceId(nextDevices[0].deviceId);
    return nextDevices;
  }

  async function startCamera(deviceId = selectedDeviceId) {
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraStatus("当前浏览器不支持摄像头预览。");
      return null;
    }
    setBusy("camera");
    setCameraStatus("正在打开摄像头...");
    try {
      stopCamera();
      const nextStream = await navigator.mediaDevices.getUserMedia({
        video: deviceId ? { deviceId: { exact: deviceId } } : true,
        audio: false
      });
      streamRef.current = nextStream;
      setStream(nextStream);
      if (videoRef.current) {
        videoRef.current.srcObject = nextStream;
        await videoRef.current.play();
      }
      const track = nextStream.getVideoTracks()[0];
      const settings = track?.getSettings?.() || {};
      if (settings.deviceId) setSelectedDeviceId(settings.deviceId);
      await refreshCameras();
      setCameraStatus(`摄像头已连接：${track?.label || "当前摄像头"}`);
      return nextStream;
    } catch (error) {
      stopCamera();
      const message = error instanceof Error ? error.message : "摄像头不可用";
      setCameraStatus(`摄像头不可用：${message}`);
      toast.notify({ title: "摄像头不可用", description: message, tone: "error" });
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function addReference() {
    const files = referenceFiles;
    const cleanAnnotation = annotation.trim();
    if (!cleanAnnotation) {
      toast.notify({ title: "请填写左列标注", tone: "error" });
      return;
    }
    if (!files.length) {
      toast.notify({ title: "请选择标签参考图", tone: "error" });
      return;
    }
    setBusy("reference");
    try {
      const form = new FormData();
      form.append("annotation", cleanAnnotation);
      for (const file of files) form.append("files", file);
      await addLabelSheetReferences(form);
      setAnnotation("");
      setReferenceFiles([]);
      await queryClient.invalidateQueries({ queryKey: queryKeys.labelSheetReferences(auth.dataUserId) });
      toast.notify({ title: "标签参考已保存", tone: "success" });
    } catch (error) {
      toast.notify({
        title: "保存标签参考失败",
        description: error instanceof Error ? error.message : "请求失败",
        tone: "error"
      });
    } finally {
      setBusy(null);
    }
  }

  async function runMatch(file: File | null) {
    if (!file) {
      toast.notify({ title: "请先选择标签纸图片", tone: "error" });
      return;
    }
    setBusy("match");
    try {
      const form = new FormData();
      form.append("file", file);
      const nextResult = await matchLabelSheet(form);
      setResult(nextResult);
      toast.notify({
        title: nextResult.status === "matched" ? "标签纸匹配完成" : "标签纸需要复核",
        description: statusText(nextResult.status),
        tone: nextResult.status === "matched" ? "success" : "info"
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "请求失败";
      setResult({ status: "error", passed: false, error: message });
      toast.notify({ title: "标签纸匹配失败", description: message, tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function runCameraMatch() {
    setBusy("camera");
    try {
      if (!streamRef.current) await startCamera();
      const file = await captureVideoFrame(videoRef.current);
      setImageFile(file);
      await runMatch(file);
    } catch (error) {
      toast.notify({
        title: "摄像头标签匹配失败",
        description: error instanceof Error ? error.message : "请求失败",
        tone: "error"
      });
    } finally {
      setBusy(null);
    }
  }

  if (referencesQuery.isLoading) return <LoadingState label="读取标签参考库" />;
  if (referencesQuery.isError) {
    return <ErrorState error={referencesQuery.error} action={<button className="secondary compact-action" type="button" onClick={() => referencesQuery.refetch()}>重试</button>} />;
  }

  return (
    <section className="view active">
      <header className="page-head">
        <div>
          <h2>标签匹配</h2>
          <p className="page-desc">本地 OpenCV 相似度匹配，核对标签纸是否与参考一致。</p>
        </div>
        <div className="page-head-actions">
          <div className={statusBadgeClass(result, Boolean(busy))}>{busy ? "处理中" : statusText(result?.status)}</div>
          <button className="secondary compact-action" type="button" onClick={() => referencesQuery.refetch()}>
            <RefreshCw size={15} aria-hidden="true" />
            刷新
          </button>
        </div>
      </header>

      <div className="inspect-grid label-sheet-grid">
        <section className="panel page-panel input-panel">
          <div className="section-title title-with-action">
            <h3>标签参考库</h3>
            <span className="pill neutral">保留 {keptCount} / 过滤 {filteredCount}</span>
          </div>
          <div className="field">
            <label htmlFor="label-reference-annotation">左列标注</label>
            <input
              id="label-reference-annotation"
              type="text"
              value={annotation}
              placeholder="标签 / label / sticker"
              onChange={(event) => setAnnotation(event.currentTarget.value)}
            />
          </div>
          <FileDropZone className="dropzone compact-dropzone" accept="image/*" multiple disabled={busy === "reference"} ariaLabel="拖拽或选择标签参考图" onFiles={setReferenceFiles}>
            <strong>上传参考图</strong>
            <span>{referenceFiles.length ? `已选择 ${referenceFiles.length} 张图片` : "拖拽图片到这里，或点击选择；只保留标签类标注"}</span>
          </FileDropZone>
          <button className="secondary icon-label" type="button" disabled={busy === "reference" || !referenceFiles.length} onClick={addReference}>
            <Save size={15} aria-hidden="true" />
            保存参考
          </button>
          <div className="label-reference-list">
            {references.length ? (
              references.slice(0, 8).map((reference) => (
                <article className="reference-row" key={`${reference.reference_id || reference.source_path}`}>
                  <div className="resource-thumb">
                    {reference.image_url ? <img src={cacheUrl(reference.image_url, String(reference.reference_id || reference.source_path || ""))} alt={referenceLabel(reference)} /> : <span>无图</span>}
                  </div>
                  <div>
                    <strong>{referenceLabel(reference)}</strong>
                    <span>{reference.reference_id || reference.accessory_id || "-"}</span>
                  </div>
                </article>
              ))
            ) : (
              <div className="empty-state compact-empty">暂无标签参考</div>
            )}
          </div>
        </section>

        <section className="panel page-panel input-panel">
          <div className="section-title">
            <h3>标签纸输入</h3>
          </div>
          <div className="tabbar" role="tablist" aria-label="标签纸输入源">
            <button className={`mode-tab ${mode === "image" ? "active" : ""}`} type="button" role="tab" aria-selected={mode === "image"} onClick={() => setMode("image")}>
              <FileImage size={15} aria-hidden="true" />
              图片
            </button>
            <button className={`mode-tab ${mode === "camera" ? "active" : ""}`} type="button" role="tab" aria-selected={mode === "camera"} onClick={() => setMode("camera")}>
              <Camera size={15} aria-hidden="true" />
              摄像头
            </button>
          </div>

          {mode === "image" ? (
            <div className="tabpane active">
              <FileDropZone accept="image/*" disabled={Boolean(busy)} ariaLabel="拖拽或选择标签纸图片" onFiles={(files) => setImageFile(files[0] || null)}>
                <strong>上传标签纸图片</strong>
                <span>{imageFile?.name || "拖拽图片到这里，或点击选择"}</span>
              </FileDropZone>
              <button className="primary icon-label" type="button" disabled={!imageFile || Boolean(busy)} onClick={() => runMatch(imageFile)}>
                <Play size={15} aria-hidden="true" />
                本地匹配
              </button>
            </div>
          ) : null}

          {mode === "camera" ? (
            <div className="tabpane active">
              <label className="toolbar-field">
                摄像头
                <select value={selectedDeviceId} onChange={(event) => {
                  setSelectedDeviceId(event.currentTarget.value);
                  if (event.currentTarget.value) startCamera(event.currentTarget.value);
                }}>
                  {devices.length ? (
                    devices.map((device, index) => (
                      <option value={device.deviceId} key={device.deviceId || index}>
                        {device.label || `摄像头 ${index + 1}`}
                      </option>
                    ))
                  ) : (
                    <option value="">未检测到摄像头</option>
                  )}
                </select>
              </label>
              <div className="camera-preview">
                <video ref={videoRef} autoPlay playsInline muted />
                {!stream ? <div className="camera-empty">选择摄像头后显示实时画面</div> : null}
              </div>
              <div className="camera-actions">
                <button className="secondary compact-action" type="button" disabled={busy === "camera"} onClick={async () => {
                  await refreshCameras();
                  await startCamera();
                }}>
                  <RefreshCw size={15} aria-hidden="true" />
                  检测摄像头
                </button>
                <button className="primary compact-action" type="button" disabled={Boolean(busy)} onClick={runCameraMatch}>
                  <Camera size={15} aria-hidden="true" />
                  拍照匹配
                </button>
              </div>
              <p className="hint-line">{cameraStatus}</p>
            </div>
          ) : null}
        </section>
      </div>

      <section className="panel page-panel label-match-panel">
        <div className="section-title title-with-action">
          <h3>匹配结果</h3>
          {canViewDiagnostics ? (
            <button className="secondary compact-action" type="button" onClick={() => setDebugOpen(true)}>
              开发诊断
            </button>
          ) : null}
        </div>
        <div className="metric-grid four">
          <MetricCard label="结果" value={statusText(result?.status)} tone={statusTone(result?.status)} />
          <MetricCard label="分数" value={scoreText(result?.score)} detail={result?.thresholds ? `阈值 ${String(result.thresholds.match_score ?? "-")}` : undefined} />
          <MetricCard label="匹配项" value={matchedName} />
          <MetricCard label="复核" value={reviewState} tone={result?.status === "matched" ? "ok" : result ? "warn" : "neutral"} />
        </div>

        <div className="label-match-images">
          <div>
            <label>文档参考图</label>
            <div className="preview-frame label-match-frame">
              {bestReferenceUrl ? <img src={cacheUrl(bestReferenceUrl, matchToken)} alt="匹配到的文档标签图" /> : <div className="empty-state">文档标签图</div>}
            </div>
          </div>
          <div>
            <label>物理标签裁剪</label>
            <div className="preview-frame label-match-frame">
              {result?.input_crop_image_url ? <img src={cacheUrl(result.input_crop_image_url, matchToken)} alt="用于匹配的物理标签裁剪" /> : inputPreviewUrl ? <img src={inputPreviewUrl} alt="待匹配标签纸" /> : <div className="empty-state">标签纸裁剪</div>}
            </div>
          </div>
          <div>
            <label>分割证据</label>
            <div className="preview-frame label-match-frame">
              {result?.sheet_overlay_url ? <img src={cacheUrl(result.sheet_overlay_url, matchToken)} alt="标签纸分割证据" /> : <div className="empty-state">分割证据图</div>}
            </div>
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>候选参考</th>
                <th>分数</th>
                <th>严格门禁</th>
                <th>模板相似度</th>
                <th>裁剪</th>
              </tr>
            </thead>
            <tbody>
              {(result?.candidates || []).length ? (
                (result?.candidates || []).slice(0, 8).map((candidate) => (
                  <tr key={`${candidate.reference_id || candidate.matched_reference_id}-${candidate.candidate_id}`}>
                    <td>{candidate.matched_reference_name || candidate.matched_reference_label || candidate.reference_id || "-"}</td>
                    <td>{scoreText(candidate.score)}</td>
                    <td>{candidateMetric(candidate, "strict_gate")}</td>
                    <td>{candidateMetric(candidate, "template_similarity")}</td>
                    <td>{candidate.candidate_id || "-"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5}>暂无候选</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {debugOpen && canViewDiagnostics ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-panel wide" role="dialog" aria-modal="true" aria-label="标签匹配开发诊断">
            <header className="modal-head">
              <div>
                <h3>开发诊断</h3>
                <span>{result?.request_id || "暂无匹配结果"}</span>
              </div>
              <button className="icon-only" type="button" aria-label="关闭" onClick={() => setDebugOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="modal-body">
              <pre className="json-panel">{JSON.stringify(result || { message: "暂无匹配结果。" }, null, 2)}</pre>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
