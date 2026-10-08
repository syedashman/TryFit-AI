"use client";

import { useRef, useState } from "react";
import Image from "next/image";
import { BatchJob, jobResultUrl } from "@/lib/api";
import { downloadImage, jobFriendlyError, resultFilename } from "@/lib/tryfit";
import PhotoEditorModal from "./PhotoEditorModal";

export default function ResultCard({
  job,
  index,
  category,
  productNumber,
  isRetrying,
  onOpen,
  onRetry,
  onReplacePhoto,
}: {
  job: BatchJob;
  index: number;
  category: string;
  productNumber: string;
  isRetrying: boolean;
  onOpen: () => void;
  onRetry: () => void;
  onReplacePhoto: (photo: File) => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [editingPhoto, setEditingPhoto] = useState<File | null>(null);
  const [actionsRevealed, setActionsRevealed] = useState(false);
  const filename = resultFilename({ category, productNumber, index: index + 1 });
  const isProcessing =
    isRetrying || job.status === "processing" || job.status === "queued";
  const resultUrl = job.job_id
    ? jobResultUrl(job.job_id, job.updated_at)
    : null;

  function handleReplacement(event: React.ChangeEvent<HTMLInputElement>) {
    const photo = event.target.files?.[0];
    event.target.value = "";
    if (photo?.type.startsWith("image/")) setEditingPhoto(photo);
  }

  function handleImageClick() {
    if (window.matchMedia("(hover: none), (pointer: coarse)").matches && !actionsRevealed) {
      setActionsRevealed(true);
      return;
    }
    setActionsRevealed(false);
    onOpen();
  }

  return (
    <div>
      <div
        className={`group relative aspect-square overflow-hidden border border-[var(--tryfit-line)] bg-[var(--tryfit-panel)] ${actionsRevealed ? "tryfit-actions-revealed" : ""}`}
      >
        {job.status === "completed" && !isRetrying && resultUrl ? (
          <button
            onClick={handleImageClick}
            className="relative block h-full w-full"
            aria-label={`View look ${index + 1} fullscreen`}
          >
            <Image
              src={resultUrl}
              alt={`Try Fit look ${index + 1}`}
              fill
              sizes="(max-width: 768px) 50vw, 300px"
              className="object-contain"
              unoptimized
              loading="lazy"
            />
          </button>
        ) : isProcessing ? (
          <div
            className="flex h-full flex-col items-center justify-center gap-3 text-center"
            role="status"
            aria-live="polite"
          >
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--tryfit-line)] border-t-[var(--tryfit-olive)]" />
            <span className="text-sm text-[var(--tryfit-muted)]">
              Creating image…
            </span>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center p-5 text-center text-sm text-[var(--tryfit-muted)]">
            {jobFriendlyError(job)}
          </div>
        )}
        {!isProcessing && (
          <div className="tryfit-result-actions pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-end gap-2 bg-gradient-to-t from-black/65 via-black/20 to-transparent px-3 pb-3 pt-10 opacity-0 transition-opacity duration-200 ease-out motion-reduce:transition-none group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100">
            {job.status === "completed" && resultUrl && (
              <button
                onClick={() => downloadImage(resultUrl, filename)}
                type="button"
                aria-label="Download image"
                className="pointer-events-auto min-h-8 border border-[var(--tryfit-line)] bg-white px-3 py-1.5 text-xs text-[var(--tryfit-ink)] shadow-sm transition-colors hover:bg-white focus-visible:bg-white"
              >
                Download
              </button>
            )}
            <button
              onClick={onRetry}
              type="button"
              aria-label="Retry image generation"
              className="pointer-events-auto min-h-8 border border-[var(--tryfit-line)] bg-white px-3 py-1.5 text-xs text-[var(--tryfit-ink)] shadow-sm transition-colors hover:bg-white focus-visible:bg-white"
            >
              Try Again
            </button>
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-[var(--tryfit-muted)]">Look {index + 1}</span>
        {!isProcessing && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-2 py-2 text-xs text-[var(--tryfit-muted)] underline underline-offset-4 hover:text-[var(--tryfit-ink)]"
            >
              Change Photo
            </button>
          </div>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleReplacement}
      />
      {editingPhoto && (
        <PhotoEditorModal
          file={editingPhoto}
          onCancel={() => setEditingPhoto(null)}
          onConfirm={(photo) => {
            onReplacePhoto(photo);
            setEditingPhoto(null);
          }}
          onReplace={setEditingPhoto}
        />
      )}
    </div>
  );
}
