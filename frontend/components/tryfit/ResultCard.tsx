"use client";

import { useEffect, useRef } from "react";
import Image from "next/image";
import { gsap } from "gsap";
import { BatchJob, jobResultUrl } from "@/lib/api";
import { downloadImage, jobFriendlyError, prefersReducedMotion, resultFilename } from "@/lib/tryfit";

/**
 * A single fashion result card. Handles the three visual states — completed,
 * in-progress (retrying), and a shopper-safe failed state — without ever
 * surfacing raw backend error text.
 */
export default function ResultCard({
  job,
  index,
  category,
  productNumber,
  isRetrying,
  onOpen,
  onRetry,
}: {
  job: BatchJob;
  index: number;
  category: string;
  productNumber: string;
  isRetrying: boolean;
  onOpen: () => void;
  onRetry: () => void;
}) {
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (prefersReducedMotion() || !cardRef.current) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(
        cardRef.current,
        { autoAlpha: 0, y: 18 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.5,
          ease: "power2.out",
          delay: Math.min(index * 0.08, 0.4),
        }
      );
    });
    return () => ctx.revert();
  }, [index]);

  const filename = resultFilename({ category, productNumber, index: index + 1 });
  const isProcessing =
    isRetrying || job.status === "processing" || job.status === "queued";

  return (
    <div ref={cardRef} className="group">
      <div className="relative aspect-[3/4] overflow-hidden rounded-lg border border-ink/10 bg-ink/5">
        {job.status === "completed" && !isRetrying ? (
          <>
            <button
              onClick={onOpen}
              className="relative block h-full w-full"
              aria-label={`View look ${index + 1} fullscreen`}
            >
              <Image
                src={jobResultUrl(job.job_id, job.updated_at)}
                alt={`Try Fit look ${index + 1}`}
                fill
                sizes="(max-width: 768px) 50vw, 300px"
                className="object-cover transition duration-500 group-hover:scale-[1.03]"
                unoptimized
                loading="lazy"
              />
            </button>
            <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-center gap-2 bg-gradient-to-t from-ink/70 to-transparent p-3 opacity-0 transition group-hover:opacity-100 sm:pointer-events-auto">
              <button
                onClick={() => downloadImage(jobResultUrl(job.job_id, job.updated_at), filename)}
                className="pointer-events-auto rounded-full bg-parchment/90 px-4 py-1.5 text-xs font-semibold text-emerald-deep transition hover:bg-parchment"
              >
                Download
              </button>
              <button
                onClick={onRetry}
                className="pointer-events-auto rounded-full bg-parchment/20 px-4 py-1.5 text-xs font-semibold text-parchment transition hover:bg-parchment/30"
              >
                Retry
              </button>
            </div>
          </>
        ) : isProcessing ? (
          <div className="tryfit-shimmer flex h-full flex-col items-center justify-center gap-3 p-4 text-center">
            <div className="h-7 w-7 animate-spin rounded-full border-2 border-gold border-t-transparent" />
            <p className="text-xs text-ink/50">Reworking this look…</p>
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-5 text-center">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-rani/10 text-rani-deep">
              !
            </span>
            <p className="text-sm font-semibold text-ink/70">
              {jobFriendlyError(job)}
            </p>
          </div>
        )}
      </div>

      {/* Mobile-friendly controls always visible below the image */}
      <div className="mt-2 flex items-center justify-between sm:hidden">
        <span className="text-xs uppercase tracking-[0.14em] text-ink/40">
          Look {index + 1}
        </span>
        <div className="flex gap-2">
          {job.status === "completed" && !isRetrying && (
            <button
              onClick={() => downloadImage(jobResultUrl(job.job_id, job.updated_at), filename)}
              className="rounded-full border border-ink/15 px-3 py-1 text-xs font-semibold text-ink/70"
            >
              Download
            </button>
          )}
          {(job.status === "completed" || job.status === "failed") &&
            !isRetrying && (
              <button
                onClick={onRetry}
                className="rounded-full border border-ink/15 px-3 py-1 text-xs font-semibold text-ink/70"
              >
                Retry
              </button>
            )}
        </div>
      </div>
    </div>
  );
}
