"use client";

import { useRef, useState } from "react";
import CameraCapture from "@/components/CameraCapture";
import { MAX_PHOTOS, MIN_PHOTOS } from "@/lib/useTryFit";

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
  onAddFiles: (list: FileList | null) => void;
  onAddCaptured: (file: File) => void;
  onRemove: (idx: number) => void;
  onGenerate: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [showCamera, setShowCamera] = useState(false);

  return (
    <div>
      <h1 className="font-display text-[3.3rem] leading-[0.9] tracking-[-0.06em] text-[var(--tryfit-ink)]">See this look on you</h1>
      <p className="mt-3 max-w-xl text-base leading-relaxed text-[rgba(17,17,17,0.62)]">
        Upload {MIN_PHOTOS}–{MAX_PHOTOS} clear photos. Each photo creates one Try Fit result.
      </p>

      <div className="mt-6 rounded-lg border border-[rgba(17,17,17,0.12)] bg-[#f8f7f4] p-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <button onClick={() => inputRef.current?.click()} disabled={fileCount >= MAX_PHOTOS} className="flex items-center justify-center gap-3 border border-[rgba(17,17,17,0.2)] bg-transparent px-4 py-4 text-[0.7rem] font-medium uppercase tracking-[0.18em] text-[var(--tryfit-ink)] transition hover:border-[var(--tryfit-ink)] disabled:cursor-not-allowed disabled:opacity-40">
            <span>Upload Photos</span>
          </button>
          <button onClick={() => setShowCamera((v) => !v)} disabled={fileCount >= MAX_PHOTOS} className="flex items-center justify-center gap-3 border border-[rgba(17,17,17,0.2)] bg-transparent px-4 py-4 text-[0.7rem] font-medium uppercase tracking-[0.18em] text-[var(--tryfit-ink)] transition hover:border-[var(--tryfit-ink)] disabled:cursor-not-allowed disabled:opacity-40">
            <span>Use Camera</span>
          </button>
        </div>

        <input ref={inputRef} type="file" multiple accept="image/*" className="hidden" onChange={(e) => onAddFiles(e.target.files)} />

        {showCamera && (
          <div className="mt-4">
            <CameraCapture
              onCapture={(file) => {
                onAddCaptured(file);
                if (fileCount + 1 >= MAX_PHOTOS) setShowCamera(false);
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
    </div>
  );
}
