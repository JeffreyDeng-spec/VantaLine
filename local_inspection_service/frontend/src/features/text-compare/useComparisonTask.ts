import { useEffect, useRef, useState } from "react";
import { ApiError, apiClient } from "../../api/client";
import type { TextCompareBetaResult } from "../../api/types";

export interface ComparisonSession {
  owner: string;
  requestId: string;
  recordId?: string;
  standardId: string;
  assetId: string;
  photoId: string;
  startedAt: number;
  open: boolean;
  rejected?: boolean;
}
export function estimatedProgress(seconds: number) {
  const s = Math.max(0, seconds);
  if (s <= 10) return Math.floor(1 + s * 3.4);
  if (s <= 30) return Math.floor(35 + (s - 10) * 1.75);
  if (s <= 60) return Math.floor(70 + (s - 30) * 2 / 3);
  return Math.min(95, Math.floor(90 + (s - 60) / 12));
}
const phases: Record<string, string> = {
  queued: "排队", extracting_text: "提取文字", direct_matching: "直接核对",
  mapping_unmatched: "疑难对应", rereading_regions: "局部文字复读（第1轮）",
  transcribing_regions: "局部文字复读（第2轮）", verifying_saving: "验证保存", recognizing: "识别文字"
};
export function useComparisonTask(owner: string) {
  const key = `text-comparison:v1:${owner}`;
  const [task, setTask] = useState<ComparisonSession | null>(() => {
    try {
      const t = JSON.parse(sessionStorage.getItem(key) || "null");
      return t?.owner === owner && typeof t.requestId === "string" && t.requestId.length < 128
        && typeof t.standardId === "string" && typeof t.assetId === "string"
        && typeof t.photoId === "string" && typeof t.open === "boolean"
        && (t.rejected === undefined || typeof t.rejected === "boolean")
        && (t.recordId === undefined || typeof t.recordId === "string")
        && Number.isFinite(t.startedAt) && t.startedAt > 0 ? t : null;
    } catch { return null; }
  });
  const current = useRef(task);
  const alive = useRef(true);
  const uploading = useRef("");
  const [result, setResult] = useState<TextCompareBetaResult | null>(null);
  const [notice, setNotice] = useState("");
  const [blocked, setBlocked] = useState(false);
  const [phase, setPhase] = useState(task ? "恢复任务" : "");
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  function save(next: ComparisonSession | null) {
    current.current = next;
    setTask(next);
    try { if (next) sessionStorage.setItem(key, JSON.stringify(next)); else sessionStorage.removeItem(key); }
    catch { setNotice("浏览器无法保存任务状态，刷新后可能无法恢复；当前任务继续运行。"); }
  }
  function accept(value: TextCompareBetaResult, requestId: string) {
    if (!alive.current || current.current?.requestId !== requestId) return;
    if (value.comparison_id !== requestId || !value.id) throw new Error("比较记录标识不一致，已拒绝显示。");
    save({ ...current.current, recordId: value.id });
    setResult(value); setNotice(""); setBlocked(false);
    setPhase(phases[String(value.diagnostics?.phase)] || "等待结果");
  }
  useEffect(() => {
    if (!task || task.rejected) return;
    const requestId = task.requestId;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | undefined;
    async function poll() {
      if (disposed || current.current?.requestId !== requestId || current.current.rejected) return;
      if (uploading.current === requestId) { timer = setTimeout(poll, 1500); return; }
      const snapshot = current.current;
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 10000);
      let stop = false;
      try {
        const path = snapshot.recordId ? encodeURIComponent(snapshot.recordId) : `by-request/${encodeURIComponent(requestId)}`;
        const value = await apiClient.get<TextCompareBetaResult>(`/api/text-inspection/prepared-comparisons/${path}`, { signal: controller.signal });
        if (disposed) return;
        accept(value, requestId);
        stop = value.status !== "attempting";
      } catch (error) {
        if (disposed || current.current?.requestId !== requestId) return;
        const code = error instanceof ApiError ? error.status : 0;
        if (code === 403 || (code === 404 && snapshot.recordId)) {
          setNotice("当前账户无法访问此比较记录（记录不存在或权限已改变）。"); stop = true; setBlocked(true);
        } else if (code === 404 && Date.now() - snapshot.startedAt > 30000) {
          setNotice("服务器未找到本次任务，图片可能尚未上传完成。请重新选择图片；不会自动重复提交。"); stop = true; setBlocked(true);
        } else if (code === 401) setNotice("登录已过期，请重新登录；登录后恢复查询，不重新提交。");
        else if (code === 404) setNotice("正在查找已提交的任务，请稍候…");
        else setNotice("连接中断，正在恢复查询；不会重新提交任务。");
      } finally { clearTimeout(timeout); }
      if (!disposed && !stop) timer = setTimeout(poll, 1500);
    }
    timer = setTimeout(poll, 1500);
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); };
    // Dialog visibility and result updates must never restart submission or polling.
  }, [task?.requestId]);
  async function start(binding: Pick<ComparisonSession, "standardId" | "assetId" | "photoId">,
    submit: (requestId: string) => Promise<TextCompareBetaResult>) {
    if (current.current) { save({ ...current.current, open: true }); return; }
    const requestId = "cmp_" + crypto.randomUUID().replace(/-/g, "");
    uploading.current = requestId;
    save({ ...binding, owner, requestId, startedAt: Date.now(), open: true });
    setResult(null); setBlocked(false); setNotice(""); setPhase("上传图片");
    try { accept(await submit(requestId), requestId); }
    catch (error) {
      if (alive.current && (current.current as ComparisonSession | null)?.requestId === requestId) {
        if (error instanceof ApiError && [400, 403, 404, 409, 413, 415, 422].includes(error.status)) {
          save({ ...current.current!, rejected: true });
          setBlocked(true); setNotice(`提交被拒绝：${error.message}。请重新选择图片或标准。`);
        } else setNotice(`${(error as Error).message}。正在查询提交结果，不自动重试上传。`);
      }
    } finally { if (uploading.current === requestId) uploading.current = ""; }
  }
  function reset() { save(null); setResult(null); setNotice(""); setBlocked(false); }
  return { task, result, notice: notice || (task?.rejected ? "提交未成功，请重新选择图片或标准；不会自动重试。" : ""), blocked, phase, start, reset,
    busy: !!task && !task.rejected && !blocked && (!result || result.status === "attempting"),
    setOpen: (open: boolean) => { if (current.current) save({ ...current.current, open }); }
  };
}
