"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import {
  BatchStatus,
  fetchBatchStatus,
  generateTryOn,
  jobResultUrl,
} from "@/lib/api";
import CameraCapture from "./CameraCapture";

type Stage = "upload" | "submitting" | "processing" | "done" | "error";

const MIN_PHOTOS = 3;
const MAX_PHOTOS = 5;

export default function TryOnStudio({
  category,
  productNumber,
  colorName,
}: {
  category: string;
  productNumber: string;
  colorName: string;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [stage, setStage] = useState<Stage>("upload");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [batch, setBatch] = useState<BatchStatus | null>(null);
  const [showCamera, setShowCamera] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      previews.forEach((url) => URL.revokeObjectURL(url));
      if (pollRef.current) clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleFiles(list: FileList | null) {
    if (!list) return;
    const incoming = Array.from(list).slice(0, MAX_PHOTOS - files.length);
    const combined = [...files, ...incoming].slice(0, MAX_PHOTOS);
    setFiles(combined);
    setPreviews((prev) => {
      prev.forEach((url) => URL.revokeObjectURL(url));
      return combined.map((f) => URL.createObjectURL(f));
    });
  }

  function addCapturedFile(file: File) {
    setFiles((prev) => {
      if (prev.length >= MAX_PHOTOS) return prev;
      const combined = [...prev, file];
      setPreviews((prevPreviews) => {
        prevPreviews.forEach((url) => URL.revokeObjectURL(url));
        return combined.map((f) => URL.createObjectURL(f));
      });
      return combined;
    });
  }

  function removeFile(idx: number) {
    const combined = files.filter((_, i) => i !== idx);
    setFiles(combined);
    setPreviews((prev) => {
      prev.forEach((url) => URL.revokeObjectURL(url));
      return combined.map((f) => URL.createObjectURL(f));
    });
  }

  async function startGeneration() {
    setStage("submitting");
    setErrorMessage(null);
    try {
      const res = await generateTryOn({
        category,
        productNumber,
        color: colorName,
        clothType: "overall",
        personImages: files,
      });
      setStage("processing");
      pollRef.current = setInterval(async () => {
        try {
          const status = await fetchBatchStatus(res.batch_id);
          setBatch(status);
          if (status.all_finished) {
            if (pollRef.current) clearInterval(pollRef.current);
            setStage("done");
          }
        } catch (err) {
          if (pollRef.current) clearInterval(pollRef.current);
          setStage("error");
          setErrorMessage(
            err instanceof Error ? err.message : "Lost connection to backend."
          );
        }
      }, 2500);
    } catch (err) {
      setStage("error");
      setErrorMessage(
        err instanceof Error ? err.message : "Could not start generation."
      );
    }
  }

  function reset() {
    setStage("upload");
    setBatch(null);
    setErrorMessage(null);
  }

  const canSubmit = files.length >= MIN_PHOTOS && files.length <= MAX_PHOTOS;

  return (
    <div>
      <p className="text-xs uppercase tracking-[0.2em] text-ink/45">
        {category} &middot; #{productNumber} &middot; {colorName}
      </p>
      <h1 className="mt-1 font-display text-2xl text-ink">Try Fit Studio</h1>

      {stage === "upload" && (
        <div className="mt-6">
          <p className="text-sm text-ink/60">
            Upload {MIN_PHOTOS}–{MAX_PHOTOS} clear photos of yourself
            (good lighting, face and body visible). TryFit AI will generate
            a realistic preview of this outfit on you.
          </p>

          <div className="mt-5 grid grid-cols-2 gap-3">
            <button
              onClick={() => inputRef.current?.click()}
              className="flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed border-gold/50 bg-white/40 px-4 py-8 text-center transition hover:border-gold"
            >
              <span className="font-display text-base text-emerald-deep">
                📁 Upload photos
              </span>
              <span className="text-xs text-ink/45">
                {files.length}/{MAX_PHOTOS} selected
              </span>
            </button>
            <button
              onClick={() => setShowCamera((v) => !v)}
              disabled={files.length >= MAX_PHOTOS}
              className="flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed border-gold/50 bg-white/40 px-4 py-8 text-center transition hover:border-gold disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span className="font-display text-base text-emerald-deep">
                📷 Capture photo
              </span>
              <span className="text-xs text-ink/45">Use your camera</span>
            </button>
          </div>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept="image/*"
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />

          {showCamera && (
            <div className="mt-4">
              <CameraCapture
                onCapture={(file) => {
                  addCapturedFile(file);
                  if (files.length + 1 >= MAX_PHOTOS) setShowCamera(false);
                }}
                onClose={() => setShowCamera(false)}
              />
            </div>
          )}


          {previews.length > 0 && (
            <div className="mt-4 grid grid-cols-5 gap-2">
              {previews.map((src, idx) => (
                <div
                  key={src}
                  className="relative aspect-[3/4] overflow-hidden rounded border border-ink/10"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={src}
                    alt={`Upload ${idx + 1}`}
                    className="h-full w-full object-cover"
                  />
                  <button
                    onClick={() => removeFile(idx)}
                    className="absolute right-1 top-1 rounded-full bg-ink/70 px-1.5 text-xs text-parchment"
                    aria-label="Remove photo"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          <button
            disabled={!canSubmit}
            onClick={startGeneration}
            className="fabric-shimmer mt-6 w-full rounded-md bg-gradient-to-r from-gold-muted via-gold to-gold-light px-6 py-4 font-display text-lg font-semibold text-emerald-deep disabled:cursor-not-allowed disabled:opacity-40"
          >
            Generate my try-on
          </button>
          {files.length > 0 && files.length < MIN_PHOTOS && (
            <p className="mt-2 text-xs text-rani-deep">
              Upload at least {MIN_PHOTOS} photos to continue.
            </p>
          )}
        </div>
      )}

      {(stage === "submitting" || stage === "processing") && (
        <div className="mt-10 flex flex-col items-center gap-4 py-10 text-center">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-gold border-t-transparent" />
          <p className="font-display text-lg text-ink">
            {stage === "submitting"
              ? "Uploading your photos..."
              : "Generating your try-on..."}
          </p>
          <div className="w-full max-w-xs">
            <div className="h-2 w-full overflow-hidden rounded-full bg-ink/10">
              <div
                className="h-full rounded-full bg-gradient-to-r from-gold-muted to-gold transition-all duration-500"
                style={{ width: `${batch ? batch.progress_percent : 8}%` }}
              />
            </div>
            <p className="mt-2 text-sm font-semibold text-emerald-deep">
              {batch ? `${batch.progress_percent}%` : "Starting..."}
            </p>
          </div>
          <p className="max-w-xs text-xs text-ink/40">
            This can take up to a minute. Keep this panel open.
          </p>
        </div>
      )}

      {stage === "error" && (
        <div className="mt-8 rounded-md border border-rani/30 bg-rani/5 p-5">
          <p className="font-semibold text-rani-deep">
            Something went wrong
          </p>
          <p className="mt-2 text-sm text-ink/70">{errorMessage}</p>
          <button
            onClick={reset}
            className="mt-4 rounded-md border border-ink/20 px-4 py-2 text-sm font-semibold"
          >
            Try again
          </button>
        </div>
      )}

      {stage === "done" && batch && (
        <div className="mt-8">
          <p className="font-display text-lg text-ink">
            {batch.all_successful
              ? "Here's how it looks on you"
              : "Couldn't generate this one"}
          </p>
          <div className="mt-4">
            {batch.jobs.map((job) => (
              <div
                key={job.job_id}
                className="overflow-hidden rounded-md border border-ink/10"
              >
                {job.status === "completed" ? (
                  <div className="relative aspect-[3/4]">
                    <Image
                      src={jobResultUrl(job.job_id)}
                      alt="Try-on result"
                      fill
                      sizes="480px"
                      className="object-cover"
                      unoptimized
                    />
                  </div>
                ) : (
                  <div className="flex aspect-[3/4] flex-col items-center justify-center gap-2 bg-ink/5 p-6 text-center">
                    <p className="text-sm font-semibold text-rani-deep">
                      Couldn&apos;t generate this one
                    </p>
                    <p className="text-xs text-ink/50">
                      {job.error || job.message}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>

          <button
            onClick={reset}
            className="mt-6 w-full rounded-md border border-emerald-deep px-6 py-3 text-sm font-semibold uppercase tracking-[0.1em] text-emerald-deep"
          >
            Try different photos
          </button>
        </div>
      )}
    </div>
  );
}
