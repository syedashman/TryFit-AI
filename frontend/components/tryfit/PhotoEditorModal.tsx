"use client";

import { useEffect, useRef, useState } from "react";

type PhotoEditorModalProps = {
  file: File;
  onCancel: () => void;
  onConfirm: (file: File) => void;
  onReplace: (file: File) => void;
};

type CropRect = { x: number; y: number; width: number; height: number };
type CropDrag = {
  pointerX: number;
  pointerY: number;
  crop: CropRect;
  handle: string | null;
};

const FULL_IMAGE: CropRect = { x: 0, y: 0, width: 1, height: 1 };

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export default function PhotoEditorModal({
  file,
  onCancel,
  onConfirm,
  onReplace,
}: PhotoEditorModalProps) {
  const [source, setSource] = useState("");
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [displaySize, setDisplaySize] = useState({ width: 0, height: 0 });
  const [crop, setCrop] = useState<CropRect>(FULL_IMAGE);
  const [error, setError] = useState<string | null>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const replaceInputRef = useRef<HTMLInputElement>(null);
  const dragRef = useRef<CropDrag | null>(null);

  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    setSource(objectUrl);
    setImageSize({ width: 0, height: 0 });
    setDisplaySize({ width: 0, height: 0 });
    setCrop(FULL_IMAGE);
    setError(null);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  useEffect(() => {
    const image = imageRef.current;
    if (!image) return;
    const observer = new ResizeObserver(([entry]) => {
      setDisplaySize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(image);
    return () => observer.disconnect();
  }, [source]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onCancel]);

  function updateImageSize(event: React.SyntheticEvent<HTMLImageElement>) {
    setImageSize({
      width: event.currentTarget.naturalWidth,
      height: event.currentTarget.naturalHeight,
    });
  }

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const target = event.target as HTMLElement;
    dragRef.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      crop,
      handle: target.closest<HTMLElement>("[data-crop-handle]")?.dataset.cropHandle || null,
    };
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || !displaySize.width || !displaySize.height) return;
    const dx = (event.clientX - drag.pointerX) / displaySize.width;
    const dy = (event.clientY - drag.pointerY) / displaySize.height;

    if (!drag.handle) {
      setCrop({
        ...drag.crop,
        x: clamp(drag.crop.x + dx, 0, 1 - drag.crop.width),
        y: clamp(drag.crop.y + dy, 0, 1 - drag.crop.height),
      });
      return;
    }

    let left = drag.crop.x;
    let right = drag.crop.x + drag.crop.width;
    let top = drag.crop.y;
    let bottom = drag.crop.y + drag.crop.height;
    const minimumSize = 0.08;
    if (drag.handle.includes("w")) left = clamp(left + dx, 0, right - minimumSize);
    if (drag.handle.includes("e")) right = clamp(right + dx, left + minimumSize, 1);
    if (drag.handle.includes("n")) top = clamp(top + dy, 0, bottom - minimumSize);
    if (drag.handle.includes("s")) bottom = clamp(bottom + dy, top + minimumSize, 1);
    setCrop({ x: left, y: top, width: right - left, height: bottom - top });
  }

  function handlePointerUp() {
    dragRef.current = null;
  }

  function replacePhoto(event: React.ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0];
    event.target.value = "";
    if (nextFile?.type.startsWith("image/")) onReplace(nextFile);
  }

  async function confirmPhoto() {
    if (!source || !imageRef.current || !imageSize.width || !imageSize.height) {
      return;
    }
    if (crop.x === 0 && crop.y === 0 && crop.width === 1 && crop.height === 1) {
      onConfirm(file);
      return;
    }

    try {
      const cropX = Math.round(crop.x * imageSize.width);
      const cropY = Math.round(crop.y * imageSize.height);
      const cropWidth = Math.max(1, Math.round(crop.width * imageSize.width));
      const cropHeight = Math.max(1, Math.round(crop.height * imageSize.height));
      const outputScale = Math.min(
        1,
        2048 / Math.max(cropWidth, cropHeight)
      );
      const outputCanvas = document.createElement("canvas");
      outputCanvas.width = Math.max(1, Math.round(cropWidth * outputScale));
      outputCanvas.height = Math.max(1, Math.round(cropHeight * outputScale));
      const outputContext = outputCanvas.getContext("2d");
      if (!outputContext) throw new Error("Canvas is unavailable.");
      outputContext.imageSmoothingEnabled = true;
      outputContext.imageSmoothingQuality = "high";
      outputContext.drawImage(
        imageRef.current,
        cropX,
        cropY,
        cropWidth,
        cropHeight,
        0,
        0,
        outputCanvas.width,
        outputCanvas.height
      );

      const mimeType = file.type === "image/png" ? "image/png" : "image/jpeg";
      const blob = await new Promise<Blob>((resolve, reject) => {
        outputCanvas.toBlob(
          (result) =>
            result ? resolve(result) : reject(new Error("Could not edit image.")),
          mimeType,
          0.94
        );
      });
      const name = file.name.replace(/\.[^.]+$/, "");
      const extension = mimeType === "image/png" ? ".png" : ".jpg";
      onConfirm(new File([blob], `${name}${extension}`, { type: mimeType }));
    } catch {
      setError("This photo could not be edited. Try another image.");
    }
  }

  return (
    <div
      className="fixed inset-0 z-[80] flex items-end justify-center bg-black/55 p-0 sm:items-center sm:p-5"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="photo-editor-title"
        className="max-h-[96dvh] w-full max-w-2xl overflow-y-auto bg-[var(--tryfit-card)] p-4 shadow-2xl sm:max-h-[92dvh] sm:p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="photo-editor-title" className="font-display text-2xl text-[var(--tryfit-ink)]">
              Crop your photo
            </h2>
            <p className="mt-1 text-sm text-[var(--tryfit-muted)]">
              Move and resize the frame to choose what to keep.
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Cancel photo editing"
            className="flex h-9 w-9 shrink-0 items-center justify-center border border-[var(--tryfit-line)] text-xl text-[var(--tryfit-ink)]"
          >
            ×
          </button>
        </div>

        <div
          ref={frameRef}
          className="relative mx-auto mt-5 w-fit max-h-[55dvh] max-w-full touch-none select-none overflow-hidden bg-[#e9e6df]"
          style={{
            width: displaySize.width || undefined,
            height: displaySize.height || undefined,
          }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          {source && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              ref={imageRef}
              src={source}
              alt="Photo being cropped"
              onLoad={updateImageSize}
              draggable={false}
              className="block max-h-[55dvh] max-w-full object-contain"
              style={{
                width: displaySize.width || undefined,
                height: displaySize.height || undefined,
              }}
            />
          )}
          <div className="pointer-events-none absolute inset-0">
            <div
              className="absolute inset-x-0 top-0 bg-black/50"
              style={{ height: `${crop.y * 100}%` }}
            />
            <div
              className="absolute inset-x-0 bottom-0 bg-black/50"
              style={{ height: `${(1 - crop.y - crop.height) * 100}%` }}
            />
            <div
              className="absolute left-0 bg-black/50"
              style={{ top: `${crop.y * 100}%`, width: `${crop.x * 100}%`, height: `${crop.height * 100}%` }}
            />
            <div
              className="absolute right-0 bg-black/50"
              style={{ top: `${crop.y * 100}%`, width: `${(1 - crop.x - crop.width) * 100}%`, height: `${crop.height * 100}%` }}
            />
          </div>
          <div
            className="absolute cursor-move border-2 border-white shadow-[0_0_0_9999px_rgba(0,0,0,0.01)]"
            style={{
              left: `${crop.x * 100}%`,
              top: `${crop.y * 100}%`,
              width: `${crop.width * 100}%`,
              height: `${crop.height * 100}%`,
              touchAction: "none",
            }}
          >
            <span className="pointer-events-none absolute inset-1/3 border-x border-white/50" />
            <span className="pointer-events-none absolute inset-1/3 border-y border-white/50" />
            {Object.entries({
              nw: "-left-2 -top-2 cursor-nwse-resize",
              n: "left-1/2 -top-2 h-3 w-8 -translate-x-1/2 cursor-ns-resize",
              ne: "-right-2 -top-2 cursor-nesw-resize",
              e: "-right-2 top-1/2 h-8 w-3 -translate-y-1/2 cursor-ew-resize",
              se: "-bottom-2 -right-2 cursor-nwse-resize",
              s: "-bottom-2 left-1/2 h-3 w-8 -translate-x-1/2 cursor-ns-resize",
              sw: "-bottom-2 -left-2 cursor-nesw-resize",
              w: "-left-2 top-1/2 h-8 w-3 -translate-y-1/2 cursor-ew-resize",
            }).map(([handle, position]) => (
              <button
                key={handle}
                type="button"
                data-crop-handle={handle}
                aria-label={`Resize crop ${handle}`}
                className={`pointer-events-auto absolute z-10 h-4 w-4 border-2 border-white bg-[var(--tryfit-olive)] ${position}`}
              />
            ))}
          </div>
        </div>

        <p className="mx-auto mt-3 max-w-lg text-xs text-[var(--tryfit-muted)]">
          Drag inside the frame to move it. Pull any edge or corner to resize.
        </p>

        {error && <p className="mx-auto mt-3 max-w-lg text-sm text-red-700">{error}</p>}

        <div className="mx-auto mt-5 flex max-w-lg flex-col-reverse gap-2 border-t border-[var(--tryfit-line)] pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => replaceInputRef.current?.click()}
              className="border border-[var(--tryfit-line)] px-4 py-3 text-xs font-medium uppercase tracking-[0.12em] text-[var(--tryfit-ink)]"
            >
              Retake / Change Image
            </button>
            <input
              ref={replaceInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={replacePhoto}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-3 text-xs uppercase tracking-[0.12em] text-[var(--tryfit-muted)]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={confirmPhoto}
              disabled={!imageSize.width || !displaySize.width}
              className="bg-[var(--tryfit-olive)] px-5 py-3 text-xs font-medium uppercase tracking-[0.12em] text-[#f7f5f2] disabled:opacity-45"
            >
              Use Image
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}