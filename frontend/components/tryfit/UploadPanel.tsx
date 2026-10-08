"use client";

import { useRef, useState } from "react";
import CameraCapture from "@/components/CameraCapture";
import { MAX_PHOTOS, MIN_PHOTOS } from "@/lib/useTryFit";
import PhotoEditorModal from "./PhotoEditorModal";

export default function UploadPanel({
  previews,
  fileCount,
  canSubmit,
  onAddFiles,
  onAddCaptured,
  onRemove,
  onGenerate,
}: {
  previews: string[];
  fileCount: number;
  canSubmit: boolean;
  onAddFiles: (list: FileList | File[] | null) => void;
  onAddCaptured: (file: File) => void;
  onRemove: (idx: number) => void;
  onGenerate: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [showCamera, setShowCamera] = useState(false);
  const [editQueue, setEditQueue] = useState<File[]>([]);
  const [editSource, setEditSource] = useState<"upload" | "camera" | null>(null);

  function queueImages(files: File[], source: "upload" | "camera") {
    const availableSlots = Math.max(0, MAX_PHOTOS - fileCount);
    const images = files
      .filter((file) => file.type.startsWith("image/"))
      .slice(0, availableSlots);
    if (images.length) {
      setEditQueue(images);
      setEditSource(source);
    }
  }

  function confirmEditedImage(file: File) {
    if (editSource === "camera") onAddCaptured(file);
    else onAddFiles([file]);
    if (editQueue.length <= 1) setEditSource(null);
    setEditQueue((pending) => pending.slice(1));
  }

  function replaceEditingImage(file: File) {
    setEditQueue((pending) => [file, ...pending.slice(1)]);
  }

  return (
    <div>
      <h1 className="font-display text-[3.3rem] leading-[0.9] tracking-[-0.06em] text-[var(--tryfit-ink)]">See this look on you</h1>
      <p className="mt-3 max-w-xl text-base leading-relaxed text-[rgba(17,17,17,0.62)]">
        Upload {MIN_PHOTOS}–{MAX_PHOTOS} clear photos. Each photo creates one Try Fit result.
      </p>

      <section aria-label="Photo framing examples" className="mt-6">
        <div className="grid max-w-sm grid-cols-2 gap-3">
          <figure className="relative aspect-[3/4] overflow-hidden border border-[var(--tryfit-line)] bg-[#e9e6df]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/photo-guide/full-body.avif" alt="Example full-body person photo" className="h-full w-full object-cover object-center" />
            <figcaption aria-label="Good example" className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-[#285641] text-lg font-semibold text-white shadow-sm">
              ✓
            </figcaption>
          </figure>
          <figure className="relative aspect-[3/4] overflow-hidden border border-[var(--tryfit-line)] bg-[#e9e6df]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/photo-guide/cropped-half.jpg" alt="Example half-body, cropped person photo" className="h-full w-full object-cover object-center" />
            <figcaption aria-label="Cropped example" className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-[#963930] text-lg font-semibold text-white shadow-sm">
              ✕
            </figcaption>
          </figure>
        </div>
        <p className="mt-3 text-sm text-[var(--tryfit-muted)]">
          Upload a full-body image for better results.
        </p>
      </section>

      <div className="mt-6 rounded-lg border border-[rgba(17,17,17,0.12)] bg-[#f8f7f4] p-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <button onClick={() => inputRef.current?.click()} disabled={fileCount >= MAX_PHOTOS} className="flex items-center justify-center gap-3 border border-[rgba(17,17,17,0.2)] bg-transparent px-4 py-4 text-[0.7rem] font-medium uppercase tracking-[0.18em] text-[var(--tryfit-ink)] transition hover:border-[var(--tryfit-ink)] disabled:cursor-not-allowed disabled:opacity-40">
            <span>Upload Photos</span>
          </button>
          <button onClick={() => setShowCamera((v) => !v)} disabled={fileCount >= MAX_PHOTOS} className="flex items-center justify-center gap-3 border border-[rgba(17,17,17,0.2)] bg-transparent px-4 py-4 text-[0.7rem] font-medium uppercase tracking-[0.18em] text-[var(--tryfit-ink)] transition hover:border-[var(--tryfit-ink)] disabled:cursor-not-allowed disabled:opacity-40">
            <span>Use Camera</span>
          </button>
        </div>

        <input
          ref={inputRef}
          type="file"
          multiple
          accept="image/*"
          className="hidden"
          onChange={(event) => {
            queueImages(Array.from(event.currentTarget.files || []), "upload");
            event.currentTarget.value = "";
          }}
        />
        {showCamera && (
          <div className="mt-4">
            <CameraCapture
              onCapture={(file) => {
                queueImages([file], "camera");
                setShowCamera(false);
              }}
              onClose={() => setShowCamera(false)}
            />
          </div>
        )}

        {previews.length > 0 && (
          <div className="mt-5 grid grid-cols-3 gap-3 sm:grid-cols-5">
            {previews.map((src, idx) => (
              <div key={src} className="relative aspect-[3/4] overflow-hidden border border-[rgba(17,17,17,0.08)] bg-[#efede9]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={src} alt={`Upload ${idx + 1}`} className="h-full w-full object-cover" />
                <button onClick={() => onRemove(idx)} className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-[rgba(17,17,17,0.7)] text-[#f7f5f2]" aria-label={`Remove photo ${idx + 1}`}>
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <button disabled={!canSubmit} onClick={onGenerate} className="fabric-shimmer mt-7 w-full border border-[var(--tryfit-ink)] bg-[var(--tryfit-ink)] px-6 py-4 text-[0.7rem] font-medium uppercase tracking-[0.2em] text-[#f7f5f2] transition hover:bg-[var(--tryfit-olive)] disabled:cursor-not-allowed disabled:opacity-45">
        Generate {fileCount} Try Fit{fileCount === 1 ? "" : "s"} →
      </button>
      {fileCount > 0 && fileCount < MIN_PHOTOS && (
        <p className="mt-2 text-xs text-[rgba(17,17,17,0.6)]">Upload at least {MIN_PHOTOS} photos to continue.</p>
      )}

      {editQueue[0] && (
        <PhotoEditorModal
          file={editQueue[0]}
          onCancel={() => {
            setEditQueue([]);
            setEditSource(null);
          }}
          onConfirm={confirmEditedImage}
          onReplace={replaceEditingImage}
        />
      )}
    </div>
  );
}
