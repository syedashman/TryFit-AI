"use client";

import { useRef, useState } from "react";
import CameraCapture from "@/components/CameraCapture";
import {
  MAX_PHOTOS,
  MIN_PHOTOS,
} from "@/lib/useTryFit";
import PhotoEditorModal from "./PhotoEditorModal";

// Framing examples per catalog category: a full-body photo works, a half-body one doesn't.
const PHOTO_GUIDES = {
  men: {
    good: "/photo-guide/full-body.avif",
    bad: "/photo-guide/cropped-half.jpg",
  },
  // Unsplash License: Anton K Wibowo (rUQSZdEQTMU) and Laura Chouette (nkWnc-W_GP8).
  women: {
    good: "/photo-guide/women-full-body.jpg",
    bad: "/photo-guide/women-half-body.jpg",
  },
};

export default function UploadPanel({
  category,
  previews,
  fileCount,
  canSubmit,
  onAddFiles,
  onAddCaptured,
  onRemove,
  onGenerate,
}: {
  category: string;
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
  const guide = category === "women" ? PHOTO_GUIDES.women : PHOTO_GUIDES.men;

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
        You can try this look on <strong className="font-semibold text-[var(--tryfit-ink)]">up to {MAX_PHOTOS} photos at once</strong>. Try Fit creates one result for each photo, keeping each uploaded pose.
      </p>

      <section aria-label="Photo framing examples" className="mt-6">
        <div className="grid max-w-sm grid-cols-2 gap-3">
          <figure className="relative aspect-[3/4] overflow-hidden border border-[var(--tryfit-line)] bg-[#e9e6df]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={guide.good} alt="Example full-body person photo" className="h-full w-full object-cover object-center" />
            <figcaption aria-label="Good example" className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-[#285641] text-lg font-semibold text-white shadow-sm">
              ✓
            </figcaption>
          </figure>
          <figure className="relative aspect-[3/4] overflow-hidden border border-[var(--tryfit-line)] bg-[#e9e6df]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={guide.bad} alt="Example half-body or cropped person photo" className="h-full w-full object-cover object-center" />
            <figcaption aria-label="Bad example: half-body photos don't work" className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-[#b3261e] text-lg font-semibold text-white shadow-sm">
              ✕
            </figcaption>
          </figure>
        </div>
        <p className="mt-3 text-sm text-[var(--tryfit-muted)]">
          Your photo remains the pose reference. The selected catalog image is used only as the garment reference.
        </p>
      </section>

      <div className="mt-6 rounded-lg border border-[rgba(17,17,17,0.12)] bg-[#f8f7f4] p-5">
        <div className="mb-4 flex items-baseline justify-between gap-3">
          <p className="text-[0.7rem] font-medium uppercase tracking-[0.18em] text-[var(--tryfit-ink)]">
            Your photos
          </p>
          <p className="text-xs text-[var(--tryfit-muted)]">
            <span className="font-semibold text-[var(--tryfit-ink)]">{fileCount} / {MAX_PHOTOS}</span> photos · 1 result each
          </p>
        </div>
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
          accept="image/*"
          multiple
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

        {/* Always show every slot so shoppers can see more than one photo is allowed. */}
        <div className="mt-5 grid max-w-md grid-cols-3 gap-3">
          {Array.from({ length: MAX_PHOTOS }).map((_, idx) => {
            const src = previews[idx];
            if (src) {
              return (
                <div key={src} className="relative aspect-[3/4] overflow-hidden border border-[rgba(17,17,17,0.08)] bg-[#efede9]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={src} alt={`Upload ${idx + 1}`} className="h-full w-full object-cover" />
                  <button onClick={() => onRemove(idx)} className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-[rgba(17,17,17,0.7)] text-[#f7f5f2]" aria-label={`Remove photo ${idx + 1}`}>
                    ×
                  </button>
                </div>
              );
            }
            return (
              <button
                key={`empty-${idx}`}
                type="button"
                onClick={() => inputRef.current?.click()}
                aria-label={`Add photo ${idx + 1}`}
                className="flex aspect-[3/4] flex-col items-center justify-center gap-1 border border-dashed border-[rgba(17,17,17,0.25)] text-[var(--tryfit-muted)] transition hover:border-[var(--tryfit-ink)] hover:text-[var(--tryfit-ink)]"
              >
                <span className="text-2xl leading-none">+</span>
                <span className="text-[0.62rem] uppercase tracking-[0.14em]">Add photo</span>
              </button>
            );
          })}
        </div>
        {fileCount > 0 && fileCount < MAX_PHOTOS && (
          <p className="mt-3 text-xs text-[var(--tryfit-muted)]">
            Add {MAX_PHOTOS - fileCount} more {MAX_PHOTOS - fileCount === 1 ? "photo" : "photos"} to get {MAX_PHOTOS - fileCount === 1 ? "another result" : `${MAX_PHOTOS - fileCount} more results`}.
          </p>
        )}
      </div>

      <button disabled={!canSubmit} onClick={onGenerate} className="fabric-shimmer mt-7 w-full border border-[var(--tryfit-ink)] bg-[var(--tryfit-ink)] px-6 py-4 text-[0.7rem] font-medium uppercase tracking-[0.2em] text-[#f7f5f2] transition hover:bg-[var(--tryfit-olive)] disabled:cursor-not-allowed disabled:opacity-45">
        Generate {fileCount} {fileCount === 1 ? "Try Fit result" : "Try Fit results"} →
      </button>
      {fileCount > 0 && fileCount < MIN_PHOTOS && (
        <p className="mt-2 text-xs text-[rgba(17,17,17,0.6)]">Upload {MIN_PHOTOS - fileCount} more {MIN_PHOTOS - fileCount === 1 ? "photo" : "photos"} to continue.</p>
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
