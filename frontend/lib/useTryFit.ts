"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  BatchStatus,
  fetchBatchStatus,
  fetchJobStatus,
  generateTryOn,
  retryJob,
} from "./api";
import { batchStorageKey, forgetBatch, rememberBatch } from "./tryfit";

export type TryFitStage =
  | "upload"
  | "submitting"
  | "processing"
  | "done"
  | "error";

export const MIN_PHOTOS = 3;
export const MAX_PHOTOS = 5;

const POLL_INTERVAL_MS = 2500;
const MAX_RETRY_POLLS = 40;

/**
 * Encapsulates the full Try Fit lifecycle (photo selection, generation,
 * batch polling, per-slot retry) so the studio page and any other surface can
 * reuse it without duplicating API logic. Results are held in React state for
 * the session and the batch id is mirrored to sessionStorage so an accidental
 * remount doesn't wipe generated looks.
 */
export function useTryFit({
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
  const [stage, setStage] = useState<TryFitStage>("upload");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [batch, setBatch] = useState<BatchStatus | null>(null);
  const [retryingIds, setRetryingIds] = useState<Set<string>>(new Set());

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const storageKey = batchStorageKey(category, productNumber, colorName);

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  // Recover a previous batch for this exact product/color within the session.
  useEffect(() => {
    let cancelled = false;
    try {
      const savedId = sessionStorage.getItem(storageKey);
      if (!savedId) return;
      fetchBatchStatus(savedId)
        .then((status) => {
          if (cancelled) return;
          setBatch(status);
          if (status.all_finished) {
            setStage("done");
          } else {
            setStage("processing");
            pollRef.current = setInterval(async () => {
              try {
                const next = await fetchBatchStatus(savedId);
                setBatch(next);
                if (next.all_finished) {
                  clearPoll();
                  setStage("done");
                }
              } catch {
                clearPoll();
              }
            }, POLL_INTERVAL_MS);
          }
        })
        .catch(() => {
          // Stale/expired reference — clear it and stay on upload.
          forgetBatch(storageKey);
        });
    } catch {
      /* sessionStorage unavailable — nothing to recover */
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  // Cleanup object URLs and timers on unmount.
  useEffect(() => {
    return () => {
      previews.forEach((url) => URL.revokeObjectURL(url));
      clearPoll();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setPreviewsFrom = useCallback((combined: File[]) => {
    setPreviews((prev) => {
      prev.forEach((url) => URL.revokeObjectURL(url));
      return combined.map((f) => URL.createObjectURL(f));
    });
  }, []);

  const addFiles = useCallback(
    (list: FileList | File[] | null) => {
      if (!list) return;
      setFiles((prev) => {
        const incoming = Array.from(list).slice(0, MAX_PHOTOS - prev.length);
        const combined = [...prev, ...incoming].slice(0, MAX_PHOTOS);
        setPreviewsFrom(combined);
        return combined;
      });
    },
    [setPreviewsFrom]
  );

  const addCapturedFile = useCallback(
    (file: File) => {
      setFiles((prev) => {
        if (prev.length >= MAX_PHOTOS) return prev;
        const combined = [...prev, file];
        setPreviewsFrom(combined);
        return combined;
      });
    },
    [setPreviewsFrom]
  );

  const removeFile = useCallback(
    (idx: number) => {
      setFiles((prev) => {
        const combined = prev.filter((_, i) => i !== idx);
        setPreviewsFrom(combined);
        return combined;
      });
    },
    [setPreviewsFrom]
  );

  const startGeneration = useCallback(async () => {
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
      rememberBatch(storageKey, res.batch_id);
      setStage("processing");
      clearPoll();
      pollRef.current = setInterval(async () => {
        try {
          const status = await fetchBatchStatus(res.batch_id);
          setBatch(status);
          if (status.all_finished) {
            clearPoll();
            setStage("done");
          }
        } catch (err) {
          clearPoll();
          setStage("error");
          // Raw reason stays in the console for debugging only.
          console.error("Batch polling failed:", err);
          setErrorMessage("connection");
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      setStage("error");
      console.error("Generation request failed:", err);
      setErrorMessage(err instanceof Error ? err.message : "start");
    }
  }, [category, productNumber, colorName, files, storageKey, clearPoll]);

  const retryPose = useCallback(async (oldJobId: string) => {
    setRetryingIds((prev) => new Set(prev).add(oldJobId));
    try {
      const res = await retryJob(oldJobId);
      const newId = res.job_id;
      setBatch((prev) =>
        prev
          ? {
              ...prev,
              jobs: prev.jobs.map((j) =>
                j.job_id === oldJobId
                  ? {
                      ...j,
                      job_id: newId,
                      status: "processing",
                      message: "Reworking this look…",
                      error: null,
                      error_code: null,
                    }
                  : j
              ),
            }
          : prev
      );
      setRetryingIds((prev) => {
        const next = new Set(prev);
        next.delete(oldJobId);
        next.add(newId);
        return next;
      });

      for (let attempt = 0; attempt < MAX_RETRY_POLLS; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        const status = await fetchJobStatus(newId);
        if (status.status === "completed" || status.status === "failed") {
          setBatch((prev) =>
            prev
              ? {
                  ...prev,
                  jobs: prev.jobs.map((j) => (j.job_id === newId ? status : j)),
                }
              : prev
          );
          setRetryingIds((prev) => {
            const next = new Set(prev);
            next.delete(newId);
            return next;
          });
          return;
        }
      }
      setRetryingIds((prev) => {
        const next = new Set(prev);
        next.delete(newId);
        return next;
      });
    } catch (err) {
      console.error("Retry failed:", err);
      setRetryingIds((prev) => {
        const next = new Set(prev);
        next.delete(oldJobId);
        return next;
      });
    }
  }, []);

  const reset = useCallback(() => {
    clearPoll();
    forgetBatch(storageKey);
    setStage("upload");
    setBatch(null);
    setErrorMessage(null);
    setFiles([]);
    setPreviews((prev) => {
      prev.forEach((url) => URL.revokeObjectURL(url));
      return [];
    });
  }, [clearPoll, storageKey]);

  const canSubmit = files.length >= MIN_PHOTOS && files.length <= MAX_PHOTOS;

  return {
    files,
    previews,
    stage,
    errorMessage,
    batch,
    retryingIds,
    canSubmit,
    addFiles,
    addCapturedFile,
    removeFile,
    startGeneration,
    retryPose,
    reset,
  };
}
