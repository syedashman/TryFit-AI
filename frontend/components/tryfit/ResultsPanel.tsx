"use client";

import { useMemo, useState } from "react";
import { BatchStatus, jobResultUrl } from "@/lib/api";
import { downloadImage, resultFilename } from "@/lib/tryfit";
import ResultCard from "./ResultCard";
import TryFitLoadingCard from "./TryFitLoadingCard";
import ImageLightbox from "@/components/ImageLightbox";

export default function ResultsPanel({
  batch,
  category,
  productNumber,
  retryingIds,
  onRetry,
  onReplacePhoto,
  onReset,
}: {
  batch: BatchStatus;
  category: string;
  productNumber: string;
  retryingIds: Set<string>;
  onRetry: (jobId: string) => void;
  onReplacePhoto: (jobId: string, photo: File) => void;
  onReset: () => void;
}) {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const completedIndexes = useMemo(
    () =>
      batch.jobs
        .map((job, idx) => ({ job, idx }))
        .filter(({ job }) => job.status === "completed"),
    [batch.jobs]
  );

  // Map an absolute job index to its position within the completed subset for
  // fullscreen prev/next navigation.
  const completedOrder = completedIndexes.map(({ idx }) => idx);
  const lightboxPos =
    lightboxIndex === null ? -1 : completedOrder.indexOf(lightboxIndex);

  function openLightbox(idx: number) {
    setLightboxIndex(idx);
  }

  function step(delta: number) {
    if (lightboxPos < 0) return;
    const nextPos = lightboxPos + delta;
    if (nextPos < 0 || nextPos >= completedOrder.length) return;
    setLightboxIndex(completedOrder[nextPos]);
  }

  async function downloadAll() {
    for (const { job, idx } of completedIndexes) {
      await downloadImage(
        jobResultUrl(job.job_id, job.updated_at),
        resultFilename({ category, productNumber, index: idx + 1 })
      );
    }
  }

  const heading = batch.all_successful
    ? "Here's how it looks on you"
    : "Here's what we created for you";

  return (
    <div>
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-ink/45">
            Your AI Try-On
          </p>
          <h1 className="mt-1 font-display text-3xl text-ink">{heading}</h1>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
        {batch.jobs.map((job, idx) => (
          job.status === "queued" ||
          job.status === "processing" ||
          retryingIds.has(job.job_id) ? (
            <TryFitLoadingCard key={job.slot_id || job.job_id} index={idx} />
          ) : (
            <ResultCard
              key={job.slot_id || job.job_id}
              job={job}
              index={idx}
              category={category}
              productNumber={productNumber}
              isRetrying={false}
              onOpen={() => openLightbox(idx)}
              onRetry={() => onRetry(job.job_id)}
              onReplacePhoto={(photo) => onReplacePhoto(job.job_id, photo)}
            />
          )
        ))}
      </div>

      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <button
          onClick={onReset}
          className="flex-1 rounded-md border border-emerald-deep px-6 py-3 text-sm font-semibold uppercase tracking-[0.1em] text-emerald-deep transition hover:bg-emerald-deep hover:text-parchment"
        >
          Try Different Photos
        </button>
        {completedIndexes.length > 1 && (
          <button
            onClick={downloadAll}
            className="flex-1 rounded-md border border-ink/15 px-6 py-3 text-sm font-semibold uppercase tracking-[0.1em] text-ink/70 transition hover:border-emerald-deep/40"
          >
            Download All
          </button>
        )}
      </div>

      {lightboxIndex !== null && batch.jobs[lightboxIndex] && (
        <ImageLightbox
          src={jobResultUrl(
            batch.jobs[lightboxIndex].job_id,
            batch.jobs[lightboxIndex].updated_at
          )}
          alt={`Try Fit look ${lightboxIndex + 1}`}
          filename={resultFilename({
            category,
            productNumber,
            index: lightboxIndex + 1,
          })}
          onClose={() => setLightboxIndex(null)}
          onPrev={() => step(-1)}
          onNext={() => step(1)}
          hasPrev={lightboxPos > 0}
          hasNext={lightboxPos >= 0 && lightboxPos < completedOrder.length - 1}
        />
      )}
    </div>
  );
}
