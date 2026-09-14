import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";
import { RefreshCcw, X } from "lucide-react";
import { estimatedProgress } from "./useComparisonTask";
import "./comparison-dialog.css";

export function ComparisonDialog({ open, startedAt, busy, phase, notice, onClose, trigger, children, title, className = "" }: {
  open: boolean; startedAt: number; busy: boolean; phase: string; notice: string;
  onClose: () => void; trigger: RefObject<HTMLButtonElement>; children: ReactNode; title?: string; className?: string;
}) {
  const titleId = useId();
  const ref = useRef<HTMLDialogElement>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const dialog = ref.current!;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) { dialog.close(); trigger.current?.focus(); }
  }, [open, trigger]);
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [open]);
  useEffect(() => {
    if (!busy || !open) return;
    setNow(current => Math.max(current, Date.now()));
    const timer = setInterval(() => setNow(current => Math.max(current, Date.now())), 500);
    return () => clearInterval(timer);
  }, [busy, open]);
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  return <dialog ref={ref} className={`comparison-dialog ${className}`} aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <header><strong id={titleId}>{title || (busy ? "文字对比进行中" : "文字对比结果")}</strong>
      <button type="button" aria-label="关闭对比窗口" onClick={onClose} autoFocus><X size={22} /></button></header>
    <div className="comparison-dialog-body">
      {notice ? <p role="status" className="text-compare-alert">{notice}</p> : null}
      {busy ? <div className="comparison-progress" role="status">
        <RefreshCcw className="spin" size={40} /><strong>{estimatedProgress(seconds)}%</strong>
        <span>{phase}</span><small>已耗时 {seconds} 秒 · 进度为估算</small>
        <progress max={100} value={estimatedProgress(seconds)} aria-label="估算进度" />
        <p>可以关闭窗口，任务会继续；稍后点击“查看进度”即可返回。</p>
      </div> : children}
    </div>
  </dialog>;
}
