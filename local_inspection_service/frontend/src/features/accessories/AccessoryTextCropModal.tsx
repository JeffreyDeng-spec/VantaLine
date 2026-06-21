import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import { Crop, Loader2, Trash2, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { cropAccessoryTextImage, getAccessoryDetail, queryKeys } from "../../api/queries";
import type { AccessoryGalleryAsset, AccessoryMutationResponse, AccessorySummary } from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { useToast } from "../../components/ToastProvider";

type CornerKey = "tl" | "tr" | "br" | "bl";

interface CropPoint {
  x: number;
  y: number;
}

type CropPoints = Record<CornerKey, CropPoint>;

interface SourceAsset {
  url: string;
  sourcePath: string;
  label: string;
}

interface AccessoryTextCropModalProps {
  accessory: AccessorySummary;
  onClose: () => void;
  onCancel: () => Promise<void> | void;
  onSaved: (result: AccessoryMutationResponse) => Promise<void> | void;
  cancelLabel?: string;
  cancelSuccessTitle?: string;
}

const DEFAULT_POINTS: CropPoints = {
  tl: { x: 8, y: 8 },
  tr: { x: 92, y: 8 },
  br: { x: 92, y: 92 },
  bl: { x: 8, y: 92 }
};

const CORNER_LABELS: Record<CornerKey, string> = {
  tl: "左上",
  tr: "右上",
  br: "右下",
  bl: "左下"
};

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function cacheUrl(url: string, token: string) {
  if (!url) return "";
  return `${url}${url.includes("?") ? "&" : "?"}t=${encodeURIComponent(token)}`;
}

function pathStem(value = "") {
  const clean = value.split(/[?#]/, 1)[0] || "";
  const name = clean.split(/[\\/]/).pop() || clean;
  return name.replace(/\.[^.]+$/, "").toLowerCase();
}

function isRectifiedSourcePath(value = "") {
  const stem = pathStem(value);
  return stem.endsWith("_rectified") || stem.includes("_rectified_") || stem.includes("_manual_rectified");
}

function hasRectifiedAssetForSource(sourcePath: string, gallery: AccessoryGalleryAsset[] | undefined) {
  const rawStem = pathStem(sourcePath);
  const prefix = `${rawStem}_manual_rectified`;
  return Boolean(
    gallery?.some((asset) => {
      const source = String(asset.source_path || "");
      if (!source || !isRectifiedSourcePath(source)) return false;
      const stem = pathStem(source);
      return stem === prefix || stem.startsWith(`${prefix}_`);
    })
  );
}

function cropSourceAssets(gallery: AccessoryGalleryAsset[] | undefined): SourceAsset[] {
  const sourceAssets = (gallery || []).filter((asset) => asset.kind === "source" && asset.url && asset.source_path);
  const candidates = sourceAssets.length ? sourceAssets : (gallery || []).filter((asset) => asset.url && asset.source_path);
  return candidates
    .filter((asset) => {
      const sourcePath = String(asset.source_path || "");
      return sourcePath && !isRectifiedSourcePath(sourcePath) && !hasRectifiedAssetForSource(sourcePath, gallery);
    })
    .map((asset, index) => ({
      url: String(asset.url || ""),
      sourcePath: String(asset.source_path || ""),
      label: String(asset.label || `原图 ${index + 1}`)
    }));
}

function pointList(points: CropPoints) {
  return [points.tl, points.tr, points.br, points.bl];
}

function polygonPoints(points: CropPoints) {
  return pointList(points).map((point) => `${point.x},${point.y}`).join(" ");
}

export function AccessoryTextCropModal({
  accessory,
  onClose,
  onCancel,
  onSaved,
  cancelLabel = "取消并删除",
  cancelSuccessTitle = "已取消裁剪并删除配件"
}: AccessoryTextCropModalProps) {
  const { notify } = useToast();
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [points, setPoints] = useState<CropPoints>(DEFAULT_POINTS);
  const [activeCorner, setActiveCorner] = useState<CornerKey | null>(null);
  const [sourceIndex, setSourceIndex] = useState(0);
  const [busy, setBusy] = useState<"save" | "cancel" | "">("");
  const detailQuery = useQuery({
    queryKey: queryKeys.accessoryDetail(accessory.id),
    queryFn: () => getAccessoryDetail(accessory.id)
  });
  const sources = useMemo(() => cropSourceAssets(detailQuery.data?.gallery), [detailQuery.data?.gallery]);
  const source = sources[Math.min(sourceIndex, Math.max(0, sources.length - 1))] || null;
  const previewUrl = useMemo(
    () => cacheUrl(source?.url || "", `${accessory.updated_at || accessory.created_at || Date.now()}-${sourceIndex}`),
    [source?.url, accessory.created_at, accessory.updated_at, sourceIndex]
  );

  useEffect(() => {
    setPoints(DEFAULT_POINTS);
    setActiveCorner(null);
    setSourceIndex(0);
  }, [accessory.id]);

  function resetCropState(nextIndex: number) {
    setPoints(DEFAULT_POINTS);
    setActiveCorner(null);
    setSourceIndex(nextIndex);
  }

  function updateCornerFromPointer(event: PointerEvent<Element>, corner: CornerKey) {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect?.width || !rect.height) return;
    const x = clampPercent(((event.clientX - rect.left) / rect.width) * 100);
    const y = clampPercent(((event.clientY - rect.top) / rect.height) * 100);
    setPoints((prev) => ({ ...prev, [corner]: { x, y } }));
  }

  function startDrag(event: PointerEvent<SVGCircleElement>, corner: CornerKey) {
    event.preventDefault();
    setActiveCorner(corner);
    wrapRef.current?.setPointerCapture?.(event.pointerId);
    updateCornerFromPointer(event, corner);
  }

  function moveDrag(event: PointerEvent<HTMLDivElement>) {
    if (!activeCorner) return;
    updateCornerFromPointer(event, activeCorner);
  }

  function stopDrag(event: PointerEvent<HTMLDivElement>) {
    if (activeCorner) {
      wrapRef.current?.releasePointerCapture?.(event.pointerId);
      setActiveCorner(null);
    }
  }

  async function cancelCrop() {
    setBusy("cancel");
    try {
      await onCancel();
      notify({ title: cancelSuccessTitle, tone: "info" });
      onClose();
    } catch (error) {
      notify({ title: "取消裁剪失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function submitCrop() {
    if (!source?.sourcePath) return;
    setBusy("save");
    try {
      const result = await cropAccessoryTextImage(accessory.id, {
        source_path: source.sourcePath,
        corners: pointList(points).map((point) => ({ x: Number(point.x.toFixed(3)), y: Number(point.y.toFixed(3)) }))
      });
      const nextIndex = sourceIndex + 1;
      if (nextIndex < sources.length) {
        notify({ title: `第 ${nextIndex}/${sources.length} 张已保存`, description: "继续裁剪下一张文字素材。", tone: "success" });
        resetCropState(nextIndex);
      } else {
        notify({ title: "裁剪图已全部保存", description: "文字配件已透视矫正并重新规范化。", tone: "success" });
        await onSaved(result);
        onClose();
      }
    } catch (error) {
      notify({ title: "保存裁剪图失败", description: error instanceof Error ? error.message : String(error), tone: "error" });
    } finally {
      setBusy("");
    }
  }

  const disabled = Boolean(busy);
  const currentNumber = sources.length ? Math.min(sourceIndex + 1, sources.length) : 0;

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel wide text-crop-modal" role="dialog" aria-modal="true" aria-label="裁剪文字配件">
        <header className="modal-head">
          <div>
            <h3>裁剪文字配件{sources.length ? ` ${currentNumber}/${sources.length}` : ""}</h3>
            <span>{accessory.name || accessory.id} 需要按顺序拖拽四角截取完整文本区域。</span>
          </div>
          <button className="icon-only" type="button" aria-label={cancelLabel} disabled={disabled} onClick={cancelCrop}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="modal-body text-crop-body">
          {detailQuery.isLoading ? <LoadingState label="正在加载原始图片" /> : null}
          {detailQuery.isError ? <ErrorState error={detailQuery.error} action={<button onClick={() => detailQuery.refetch()}>重试</button>} /> : null}
          {!detailQuery.isLoading && !detailQuery.isError ? (
            <>
              <div className="text-crop-stage">
                {previewUrl ? (
                  <div
                    className="text-crop-image-wrap"
                    ref={wrapRef}
                    onPointerMove={moveDrag}
                    onPointerUp={stopDrag}
                    onPointerCancel={stopDrag}
                    onPointerLeave={stopDrag}
                  >
                    <img src={previewUrl} alt={source?.label || "待裁剪文字配件"} draggable={false} />
                    <svg className="text-crop-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                      <polygon className="text-crop-polygon" points={polygonPoints(points)} />
                      {(Object.keys(points) as CornerKey[]).map((corner) => (
                        <circle
                          className="text-crop-handle"
                          cx={points[corner].x}
                          cy={points[corner].y}
                          r={2.6}
                          key={corner}
                          onPointerDown={(event) => startDrag(event, corner)}
                        />
                      ))}
                    </svg>
                  </div>
                ) : (
                  <div className="empty-state">没有需要裁剪的原始图片</div>
                )}
              </div>
              <div className="text-crop-point-list">
                {(Object.keys(points) as CornerKey[]).map((corner) => (
                  <span className="pill neutral" key={corner}>
                    {CORNER_LABELS[corner]} {points[corner].x.toFixed(1)}%, {points[corner].y.toFixed(1)}%
                  </span>
                ))}
              </div>
            </>
          ) : null}
        </div>
        <footer className="modal-footer">
          <button className="secondary compact-action" type="button" disabled={disabled} onClick={cancelCrop}>
            {busy === "cancel" ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <Trash2 size={16} aria-hidden="true" />}
            {cancelLabel}
          </button>
          <button className="primary compact-action" type="button" disabled={disabled || !source?.sourcePath} onClick={submitCrop}>
            {busy === "save" ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <Crop size={16} aria-hidden="true" />}
            保存并继续
          </button>
        </footer>
      </section>
    </div>
  );
}
