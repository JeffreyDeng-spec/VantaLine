import { useCallback, useEffect, useState } from "react";
import type { DetectionResult } from "../../api/types";

type ResultPresentation = {
  result: DetectionResult;
  source: "image" | "video" | "camera";
  context: string;
};

const CAMERA_PASS_DISPLAY_MS = 5_000;

/** Retain evidence while expiring only the current camera PASS presentation. */
export function useDetectionResultDisplay(context: string) {
  const [presentation, setPresentation] = useState<ResultPresentation | null>(null);
  const [expired, setExpired] = useState<ResultPresentation | null>(null);
  const setResult = useCallback((result: DetectionResult, source: ResultPresentation["source"]) => {
    setPresentation({ result, source, context });
  }, [context]);

  useEffect(() => {
    if (!presentation || presentation.source !== "camera" || !presentation.result.passed) return;
    if (presentation.context !== context) {
      setExpired(presentation);
      return;
    }
    if (presentation === expired) return;
    // Start after React has committed the result, independently of fullscreen/source tabs.
    const expiresAt = Date.now() + CAMERA_PASS_DISPLAY_MS;
    let cancelled = false;
    const expire = () => { if (!cancelled) setExpired(presentation); };
    const timer = window.setTimeout(expire, CAMERA_PASS_DISPLAY_MS);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible" && Date.now() >= expiresAt) expire();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [presentation, context]);

  const hidePass = presentation?.source === "camera" && presentation.result.passed
    && (presentation === expired || presentation.context !== context);
  return {
    result: presentation?.result || null,
    displayResult: hidePass ? null : presentation?.result || null,
    setResult
  };
}
