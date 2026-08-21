import { BatchJob } from "./api";

/**
 * Maps raw backend / provider error text or codes into calm, shopper-safe
 * copy. Technical details (Vertex, credentials, timeouts, stack traces, job
 * IDs) must never reach the storefront UI — they stay in the console/logs.
 */
export function friendlyError(input?: {
  code?: string | null;
  message?: string | null;
}): string {
  const code = (input?.code || "").toLowerCase();
  const raw = (input?.message || "").toLowerCase();

  // Photo suitability issues — actionable for the shopper.
  if (
    code.includes("person_images_rejected") ||
    code.includes("photo_category_mismatch") ||
    code.includes("invalid_person_image") ||
    raw.includes("photo") ||
    raw.includes("full-body") ||
    raw.includes("full body")
  ) {
    return "This photo wasn't suitable for Try Fit. Choose another clear, well-lit photo.";
  }

  // Temporary infrastructure / auth / quota issues — retryable, not the user's fault.
  if (
    code.includes("auth") ||
    code.includes("credential") ||
    code.includes("unavailable") ||
    code.includes("circuit") ||
    code.includes("quota") ||
    code.includes("timeout") ||
    raw.includes("credential") ||
    raw.includes("google_application") ||
    raw.includes("permission") ||
    raw.includes("timeout") ||
    raw.includes("temporarily")
  ) {
    return "Try Fit is temporarily unavailable for this photo. Please try again.";
  }

  // Generation / fidelity / distortion failures — most common case.
  // Also the safe default for anything we don't explicitly recognise.
  return "We couldn't create this look from this photo. Try again.";
}

/**
 * Returns a shopper-safe message for a single result slot, or null when the
 * job hasn't failed.
 */
export function jobFriendlyError(job: BatchJob): string | null {
  if (job.status !== "failed") return null;
  return friendlyError({ code: job.error_code, message: job.error });
}

/**
 * Builds a meaningful download filename such as
 * `tryfit-men-outfit-6-look-2.png`.
 */
export function resultFilename(params: {
  category: string;
  productNumber: string;
  index: number;
  ext?: string;
}): string {
  const category = (params.category || "look").toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const product = String(params.productNumber || "0").replace(/[^a-z0-9]+/gi, "-");
  const ext = params.ext || "png";
  return `tryfit-${category}-outfit-${product}-look-${params.index}.${ext}`;
}

/**
 * Downloads an image from a same-origin/backend result URL using a blob so the
 * browser saves it with a meaningful filename. Falls back to opening the URL
 * in a new tab if a cross-origin fetch is blocked.
 */
export async function downloadImage(src: string, filename: string): Promise<void> {
  try {
    const res = await fetch(src);
    if (!res.ok) throw new Error(`status ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    // Keep technical detail in the console only.
    console.error("Download fell back to new-tab open:", err);
    window.open(src, "_blank", "noopener,noreferrer");
  }
}

/** True when the user has asked the OS to minimise motion. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

const BATCH_STORAGE_PREFIX = "tryfit:batch:";

export function batchStorageKey(
  category: string,
  productNumber: string,
  color: string
): string {
  return `${BATCH_STORAGE_PREFIX}${category.toLowerCase()}:${productNumber}:${color.toLowerCase()}`;
}

export function rememberBatch(key: string, batchId: string): void {
  try {
    sessionStorage.setItem(key, batchId);
  } catch {
    /* storage may be unavailable (private mode) — non-fatal */
  }
}

export function recallBatch(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

export function forgetBatch(key: string): void {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* non-fatal */
  }
}
