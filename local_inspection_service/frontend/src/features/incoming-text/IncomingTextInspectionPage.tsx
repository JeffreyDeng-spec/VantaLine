import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Camera, CheckCircle2, RotateCcw, ShieldAlert, ThumbsDown, ThumbsUp } from "lucide-react";
import { getIncomingTextTask, inspectIncomingText, queryKeys, reviewIncomingTextInspection } from "../../api/queries";
import type { IncomingTextInspection, PipelineTask } from "../../api/types";

interface BrowserQuality { accepted: boolean; message: string; sharpness: number; brightness: number }

function evaluateFrame(video: HTMLVideoElement, canvas: HTMLCanvasElement): BrowserQuality {
  const width = Math.min(320, video.videoWidth || 0);
  const height = Math.round(width * (video.videoHeight || 1) / (video.videoWidth || 1));
  if (width < 160 || height < 100) return { accepted: false, message: "等待摄像头画面", sharpness: 0, brightness: 0 };
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return { accepted: false, message: "无法检查画面", sharpness: 0, brightness: 0 };
  context.drawImage(video, 0, 0, width, height);
  const pixels = context.getImageData(0, 0, width, height).data;
  let brightness = 0;
  let edges = 0;
  for (let y = 1; y < height; y += 2) {
    for (let x = 1; x < width; x += 2) {
      const index = (y * width + x) * 4;
      const gray = pixels[index] * 0.299 + pixels[index + 1] * 0.587 + pixels[index + 2] * 0.114;
      const left = pixels[index - 4] * 0.299 + pixels[index - 3] * 0.587 + pixels[index - 2] * 0.114;
      brightness += gray;
      edges += Math.abs(gray - left);
    }
  }
  const samples = Math.ceil((height - 1) / 2) * Math.ceil((width - 1) / 2);
  const mean = brightness / Math.max(samples, 1);
  const sharpness = edges / Math.max(samples, 1);
  if (mean < 35) return { accepted: false, message: "光线太暗，请增加补光", sharpness, brightness: mean };
  if (mean > 225) return { accepted: false, message: "画面过曝，请减少反光", sharpness, brightness: mean };
  if (sharpness < 7) return { accepted: false, message: "画面模糊，请固定包材并重新对焦", sharpness, brightness: mean };
  return { accepted: true, message: "画面质量合格，可以拍照", sharpness, brightness: mean };
}

function decisionCopy(result: IncomingTextInspection) {
  if (result.status === "processing") return { title: "处理中", detail: "同一拍照编号正在处理，请稍后重试查询，不会重复检测。", tone: "review" };
  if (result.status === "completed_with_error") return { title: "系统异常", detail: "本次没有形成可放行结论，请重新拍照或联系管理员。", tone: "review" };
  if (result.auto_decision === "PASS") return { title: "通过", detail: "关键文字与当前标准一致。", tone: "pass" };
  if (result.auto_decision === "FAIL") return { title: "不通过", detail: "检测到明确的关键文字错误。", tone: "fail" };
  return { title: "需复核", detail: "证据不足或普通文字存在差异，请人工确认。", tone: "review" };
}

export function IncomingTextInspectionPage({ task }: { task: PipelineTask }) {
  const queryClient = useQueryClient();
  const videoRef = useRef<HTMLVideoElement>(null);
  const qualityCanvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const pendingCapture = useRef<{ file: File; captureId: string } | null>(null);
  const [cameraError, setCameraError] = useState("");
  const [quality, setQuality] = useState<BrowserQuality>({ accepted: false, message: "正在启动摄像头…", sharpness: 0, brightness: 0 });
  const [result, setResult] = useState<IncomingTextInspection | null>(null);
  const [reviewReason, setReviewReason] = useState("");

  const taskQuery = useQuery({ queryKey: queryKeys.incomingTextTask(task.id), queryFn: () => getIncomingTextTask(task.id) });
  const inspectMutation = useMutation({
    mutationFn: async ({ file, captureId }: { file: File; captureId: string }) => {
      const form = new FormData();
      form.set("file", file);
      form.set("capture_id", captureId);
      return inspectIncomingText(task.id, form);
    },
    onSuccess: (next) => {
      pendingCapture.current = null;
      setResult(next);
      void queryClient.invalidateQueries({ queryKey: queryKeys.incomingTextInspections("", task.id) });
    }
  });
  const reviewMutation = useMutation({
    mutationFn: ({ decision }: { decision: "RELEASED" | "REJECTED" }) => {
      if (!result) throw new Error("没有待复核记录");
      return reviewIncomingTextInspection(result.id, decision, reviewReason);
    },
    onSuccess: setResult
  });

  useEffect(() => {
    let active = true;
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
      .then((stream) => {
        if (!active) return stream.getTracks().forEach((track) => track.stop());
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      })
      .catch((error: Error) => setCameraError(error.message || "摄像头授权失败"));
    return () => {
      active = false;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (videoRef.current && qualityCanvasRef.current && !result && !inspectMutation.isPending) {
        setQuality(evaluateFrame(videoRef.current, qualityCanvasRef.current));
      }
    }, 500);
    return () => window.clearInterval(timer);
  }, [inspectMutation.isPending, result]);

  const capture = useCallback(() => {
    const video = videoRef.current;
    if (!video || !quality.accepted || inspectMutation.isPending || result) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return setCameraError("拍照失败，请重试");
      const item = { file: new File([blob], `incoming-${Date.now()}.jpg`, { type: "image/jpeg" }), captureId: crypto.randomUUID() };
      pendingCapture.current = item;
      inspectMutation.mutate(item);
    }, "image/jpeg", 0.94);
  }, [inspectMutation, quality.accepted, result]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Enter" && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLTextAreaElement)) {
        event.preventDefault();
        capture();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [capture]);

  const copy = result ? decisionCopy(result) : null;
  const activeReference = taskQuery.data?.active_reference;
  const canInspect = Boolean(activeReference && quality.accepted && !cameraError && !inspectMutation.isPending);

  return (
    <section className="view active incoming-text-inspection-view">
      <header className="view-header incoming-text-header"><div><span className="eyebrow">包材文字全检</span><h2>{task.name || task.material_name}</h2><p>{task.material_code} · {activeReference ? `标准 ${activeReference.version_label}` : "尚未启用标准"}</p></div><div className={`incoming-text-ready ${canInspect ? "ready" : ""}`}><span />{canInspect ? (taskQuery.data?.automatic_decisions_verified ? "拍照工位已就绪" : "试点模式 · 结果需复核") : "拍照工位未就绪"}</div></header>
      <div className="incoming-text-inspection-grid">
        <main className="incoming-text-camera-card panel-card">
          <div className="incoming-text-camera-stage">
            <video ref={videoRef} autoPlay playsInline muted />
            <canvas ref={qualityCanvasRef} hidden />
            {result?.annotated_url ? <img className="incoming-text-result-overlay" src={result.annotated_url} alt="文字差异标注" /> : null}
            {!activeReference ? <div className="incoming-text-camera-blocker"><ShieldAlert size={28} /><strong>当前任务没有已启用标准</strong><span>请由标准配置人员完成字段框选并启用。</span></div> : null}
            {cameraError ? <div className="incoming-text-camera-blocker"><AlertTriangle size={28} /><strong>摄像头不可用</strong><span>{cameraError}</span></div> : null}
          </div>
          {!result ? (
            <div className="incoming-text-capture-bar">
              <div className={quality.accepted ? "quality-ok" : "quality-warn"}>{quality.accepted ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}<span><strong>{quality.message}</strong><small>固定支架、距离和补光；后端会再次进行权威质量检查。</small></span></div>
              <button className="primary incoming-text-capture-button" type="button" onClick={capture} disabled={!canInspect}><Camera size={20} />{inspectMutation.isPending ? "正在检验…" : "拍照检验（回车）"}</button>
            </div>
          ) : null}
          {inspectMutation.error ? <div className="incoming-text-message error"><AlertTriangle size={16} />{(inspectMutation.error as Error).message}<button className="secondary" type="button" onClick={() => pendingCapture.current && inspectMutation.mutate(pendingCapture.current)}>使用同一拍照编号重试</button></div> : null}
        </main>

        <aside className="incoming-text-result-card panel-card">
          {!result ? <div className="incoming-text-result-empty"><Camera size={30} /><strong>等待拍照</strong><span>系统会逐项比对关键字段，并保留字符证据。</span></div> : (
            <>
              <div className={`incoming-text-decision ${copy?.tone}`}><span>{copy?.tone === "pass" ? <CheckCircle2 /> : <AlertTriangle />}</span><div><small>自动结论</small><strong>{copy?.title}</strong><p>{copy?.detail}</p></div></div>
              <div className="incoming-text-field-results">
                {(result.fields || []).map((field) => <article className={field.outcome.toLowerCase()} key={field.field_id}><div><strong>{field.name}</strong><em>{field.importance === "critical" ? "关键" : "普通"}</em></div><dl><dt>正确文字</dt><dd>{field.expected_text}</dd><dt>识别文字</dt><dd>{field.observed_text || "未识别"}</dd></dl><small>置信度 {(field.confidence * 100).toFixed(1)}% · {field.outcome === "PASS" ? "一致" : field.outcome === "FAIL" ? "明确错误" : "需要确认"}</small></article>)}
              </div>
              {result.status === "completed" && result.auto_decision === "REVIEW_REQUIRED" && !result.final_decision ? <div className="incoming-text-review-box"><strong>人工复核</strong><textarea value={reviewReason} onChange={(event) => setReviewReason(event.currentTarget.value)} placeholder="请填写放行或退货原因" maxLength={500} /><div><button className="secondary review-release" type="button" disabled={!reviewReason.trim() || reviewMutation.isPending} onClick={() => reviewMutation.mutate({ decision: "RELEASED" })}><ThumbsUp size={16} /> 放行</button><button className="secondary review-reject" type="button" disabled={!reviewReason.trim() || reviewMutation.isPending} onClick={() => reviewMutation.mutate({ decision: "REJECTED" })}><ThumbsDown size={16} /> 退货</button></div>{reviewMutation.error ? <small className="form-error">{(reviewMutation.error as Error).message}</small> : null}</div> : null}
              {result.final_decision ? <div className="incoming-text-final-decision"><strong>最终结论：{result.final_decision === "RELEASED" ? "人工放行" : result.final_decision === "REJECTED" ? "人工退货" : copy?.title}</strong>{result.review_reason ? <span>{result.review_reason}</span> : null}</div> : null}
              <button className="secondary incoming-text-next" type="button" onClick={() => { setResult(null); setReviewReason(""); inspectMutation.reset(); }}><RotateCcw size={16} /> 检验下一件</button>
            </>
          )}
        </aside>
      </div>
    </section>
  );
}
