"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  BatchStatus,
  fetchBatchStatus,
  generateTryOn,
  replaceJobPhoto,
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

function mergeBatchStatus(
  previous: BatchStatus | null,
  incoming: BatchStatus
): BatchStatus {
  const previousBySlot = new Map(
    (previous?.jobs || []).map((job, index) => [job.slot_index ?? index, job])
  );
  const jobs = incoming.jobs
    .map((job, index) => {
      const slotIndex = job.slot_index ?? index;
      return {
        ...previousBySlot.get(slotIndex),
        ...job,
        slot_index: slotIndex,
        slot_id:
          previousBySlot.get(slotIndex)?.slot_id ||
          job.slot_id ||
          `slot-${slotIndex}`,
      };
    });
  if (jobs.length > incoming.expected_outputs) {
    console.error("[TRYFIT] renderedSlots exceeded expected_outputs", {
      renderedSlots: jobs.length,
      expectedOutputs: incoming.expected_outputs,
    });
  }
  return { ...incoming, jobs: jobs.slice(0, incoming.expected_outputs) };
}

function optimisticBatch(photoCount: number): BatchStatus {
  const jobs = Array.from({ length: photoCount }, (_, index) => ({
    job_id: `pending-${index}`,
    slot_id: `slot-${index}`,
    slot_index: index,
    status: "queued" as const,
    message: "Creating your look…",
    result_url: null,
    error: null,
    error_code: null,
  }));

  return {
    batch_id: "pending",
    expected_outputs: photoCount,
    completed_outputs: 0,
    failed_outputs: 0,
    pending_outputs: photoCount,
    progress_percent: 0,
    all_finished: false,
    all_successful: false,
    counts: { queued: photoCount, processing: 0, completed: 0, failed: 0 },
    jobs,
  };
}

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

  const startBatchPolling = useCallback(
    (batchId: string) => {
      clearPoll();
      setStage("processing");

      const tick = async () => {
        try {
          console.log("[RETRY:UI] polling batch", batchId);
          const status = await fetchBatchStatus(batchId);
          setBatch((previous) => mergeBatchStatus(previous, status));
          setRetryingIds((previous) => {
            const next = new Set(previous);
            status.jobs.forEach((job) => {
              if (job.status === "completed" || job.status === "failed") {
                next.delete(job.job_id);
                if (job.parent_job_id) next.delete(job.parent_job_id);
              }
            });
            return next;
          });
          if (status.all_finished) {
            clearPoll();
            setStage("done");
            return;
          }
        } catch (err) {
          console.error("[RETRY:UI] batch poll failed", err);
          clearPoll();
          setStage("error");
        }
      };

      void tick();
      pollRef.current = setInterval(() => {
        void tick();
      }, POLL_INTERVAL_MS);
    },
    [clearPoll]
  );

  // Recover a previous batch for this exact product/color within the session.
  useEffect(() => {
    let cancelled = false;
    try {
      const savedId = sessionStorage.getItem(storageKey);
      if (!savedId) return;
      fetchBatchStatus(savedId)
        .then((status) => {
          if (cancelled) return;
          setBatch((previous) => mergeBatchStatus(previous, status));
          if (status.all_finished) {
            setStage("done");
          } else {
            setStage("processing");
            pollRef.current = setInterval(async () => {
              try {
                const next = await fetchBatchStatus(savedId);
                setBatch((previous) => mergeBatchStatus(previous, next));
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
    setBatch(optimisticBatch(files.length));
    setStage("processing");
    try {
      const res = await generateTryOn({
        category,
        productNumber,
        color: colorName,
        clothType: "overall",
        personImages: files,
      });
      rememberBatch(storageKey, res.batch_id);
      startBatchPolling(res.batch_id);
    } catch (err) {
      console.error("Generation request failed:", err);
      setErrorMessage(err instanceof Error ? err.message : "start");
      setBatch((previous) =>
        previous
          ? {
              ...previous,
              all_finished: true,
              all_successful: false,
              failed_outputs: previous.jobs.length,
              pending_outputs: 0,
              progress_percent: 100,
              counts: { queued: 0, processing: 0, completed: 0, failed: previous.jobs.length },
              jobs: previous.jobs.map((job) => ({
                ...job,
                status: "failed" as const,
                message: "We couldn't start this Try Fit. Please try again.",
                error: "Generation request failed.",
                error_code: "generation_start_failed",
              })),
            }
          : previous
      );
      setStage("done");
    }
  }, [category, productNumber, colorName, files, startBatchPolling, storageKey]);

  const retryPose = useCallback(
    async (oldJobId: string) => {
      if (retryingIds.has(oldJobId)) return;

      console.log("[RETRY:UI] click job=", oldJobId);
      setRetryingIds((prev) => new Set(prev).add(oldJobId));
      setBatch((prev) =>
        prev
          ? {
              ...prev,
              all_finished: false,
              all_successful: false,
              jobs: prev.jobs.map((job) =>
                job.job_id === oldJobId
                  ? {
                      ...job,
                      status: "processing",
                      message: "Reworking this look…",
                      result_url: null,
                      error: null,
                      error_code: null,
                    }
                  : job
              ),
            }
          : prev
      );

      try {
        console.log("[RETRY:UI] POST start job=", oldJobId);
        const res = await retryJob(oldJobId);
        console.log("[RETRY:UI] POST success job=", res.job_id);

        const currentBatchId = batch?.batch_id;
        if (currentBatchId) {
          console.log("[RETRY:UI] polling resumed batch=", currentBatchId);
          startBatchPolling(currentBatchId);
        }
      } catch (err) {
        console.error("[RETRY:UI] Retry failed:", err);
        setRetryingIds((prev) => {
          const next = new Set(prev);
          next.delete(oldJobId);
          return next;
        });
        setBatch((prev) =>
          prev
            ? {
                ...prev,
                jobs: prev.jobs.map((j) =>
                  j.job_id === oldJobId
                    ? {
                        ...j,
                        status: "failed",
                        message: "We couldn't retry this look. Please try again.",
                        error: "Retry request failed.",
                        error_code: "retry_failed",
                      }
                    : j
                ),
              }
            : prev
        );
      }
    },
    [batch?.batch_id, retryingIds, startBatchPolling]
  );

  const replacePhoto = useCallback(
    async (jobId: string, photo: File) => {
      if (retryingIds.has(jobId)) return;
      setRetryingIds((prev) => new Set(prev).add(jobId));
      setBatch((prev) =>
        prev
          ? {
              ...prev,
              all_finished: false,
              all_successful: false,
              jobs: prev.jobs.map((job) =>
                job.job_id === jobId
                  ? {
                      ...job,
                      status: "processing" as const,
                      message: "Checking the replacement photo…",
                      result_url: null,
                      error: null,
                      error_code: null,
                    }
                  : job
              ),
            }
          : prev
      );
      try {
        const res = await replaceJobPhoto(jobId, photo);
        if (res.batch_id) startBatchPolling(res.batch_id);
        else if (batch?.batch_id) startBatchPolling(batch.batch_id);
      } catch (err) {
        console.error("[REPLACE:UI] failed", err);
        setRetryingIds((prev) => {
          const next = new Set(prev);
          next.delete(jobId);
          return next;
        });
        setBatch((prev) =>
          prev
            ? {
                ...prev,
                jobs: prev.jobs.map((job) =>
                  job.job_id === jobId
                    ? {
                        ...job,
                        status: "failed" as const,
                        message: "We couldn't use that photo.",
                        error: "Replacement photo failed.",
                        error_code: "replacement_photo_failed",
                      }
                    : job
                ),
              }
            : prev
        );
      }
    },
    [batch?.batch_id, retryingIds, startBatchPolling]
  );

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
    replacePhoto,
    reset,
  };
}
