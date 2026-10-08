const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
export const API_BASE = (
  configuredApiBase ||
  (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8001" : "")
).replace(/\/+$/, "");

const RETRYABLE_STATUS_CODES = new Set([408, 429, 500, 502, 503, 504]);

function apiUrl(path: string): string {
  if (!API_BASE) {
    throw new Error(
      "Backend URL is not configured. Set NEXT_PUBLIC_API_BASE_URL to the Render service URL."
    );
  }
  return `${API_BASE}${path}`;
}

async function fetchWithRetry(
  path: string,
  init: RequestInit = {},
  timeoutMs = 15_000
): Promise<Response> {
  const maxAttempts = 4;
  let lastError: unknown;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(apiUrl(path), {
        ...init,
        signal: controller.signal,
      });
      if (
        !RETRYABLE_STATUS_CODES.has(response.status) ||
        attempt === maxAttempts - 1
      ) {
        return response;
      }
      await response.body?.cancel();
      lastError = new Error(`Backend temporarily returned ${response.status}.`);
    } catch (error) {
      lastError = error;
      if (attempt === maxAttempts - 1) throw error;
    } finally {
      window.clearTimeout(timeout);
    }

    await new Promise((resolve) =>
      window.setTimeout(resolve, 500 * 2 ** attempt)
    );
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("Backend request failed.");
}

export type CatalogColor = {
  name: string;
  count: number;
  assets: string[];
};

export type CatalogProduct = {
  id: string;
  category: string;
  name: string;
  product_number: string;
  thumbnail: string | null;
  image_count: number;
  color_count: number;
  colors: CatalogColor[];
};

export type CatalogResponse = {
  categories: {
    men: CatalogProduct[];
    women: CatalogProduct[];
    kids: CatalogProduct[];
  };
  total_products: number;
  total_images: number;
  age_policy: string;
};

export function assetUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  if (!API_BASE) return "";
  return `${API_BASE}${path}`;
}

export async function fetchCatalog(): Promise<CatalogResponse> {
  const res = await fetchWithRetry("/api/catalog", { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load catalog (${res.status})`);
  }
  return res.json();
}

export type BatchJob = {
  job_id: string | null;
  slot_id?: string;
  slot_index?: number | null;
  parent_job_id?: string | null;
  status: "queued" | "processing" | "completed" | "failed";
  message: string;
  error?: string | null;
  error_code?: string | null;
  result_url?: string | null;
  updated_at?: string;
  provider_metadata?: Record<string, unknown>;
};

export type BatchStatus = {
  batch_id: string;
  expected_outputs: number;
  completed_outputs: number;
  failed_outputs: number;
  pending_outputs: number;
  progress_percent: number;
  all_finished: boolean;
  all_successful: boolean;
  counts: Record<string, number>;
  jobs: BatchJob[];
};

export async function generateTryOn(params: {
  category: string;
  productNumber: string;
  color: string;
  clothType: "upper" | "lower" | "overall";
  garmentDescription?: string;
  personImages: File[];
}): Promise<{ batch_id: string; expected_outputs: number; message: string; jobs?: BatchJob[] }> {
  const form = new FormData();
  form.append("category", params.category);
  form.append("product_number", params.productNumber);
  form.append("color", params.color);
  form.append("cloth_type", params.clothType);
  form.append("garment_description", params.garmentDescription || "complete outfit");
  form.append("quality_preset", "balanced");
  params.personImages.forEach((file) => form.append("person_images", file));

  const res = await fetch(apiUrl("/api/catalog/generate"), {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    const message =
      (detail && (detail.detail?.message || detail.detail)) ||
      `Request failed (${res.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return res.json();
}

export async function fetchBatchStatus(batchId: string): Promise<BatchStatus> {
  const res = await fetchWithRetry(`/api/catalog/batch/${batchId}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const error = new Error(`Failed to load batch status (${res.status})`) as Error & { status?: number };
    error.status = res.status;
    throw error;
  }
  return res.json();
}

export async function retryJob(jobId: string): Promise<{ job_id: string; message: string }> {
  const res = await fetch(apiUrl(`/api/catalog/retry/${jobId}`), {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(`Failed to retry (${res.status})`);
  }
  return res.json();
}

export async function fetchJobStatus(jobId: string): Promise<BatchJob> {
  const res = await fetchWithRetry(`/api/jobs/${jobId}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load job status (${res.status})`);
  }
  return res.json();
}

export function jobResultUrl(jobId: string, version?: string): string {
  const base = apiUrl(`/api/jobs/${jobId}/result`);
  return version ? `${base}?v=${encodeURIComponent(version)}` : base;
}

export async function replaceJobPhoto(
  jobId: string,
  photo: File
): Promise<{ job_id: string; batch_id?: string; slot_index?: number | null; message: string }> {
  const form = new FormData();
  form.append("photo", photo);
  const res = await fetch(apiUrl(`/api/catalog/retry/${jobId}/replace-photo`), {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    const message = detail?.detail?.message || detail?.detail || `Failed to replace photo (${res.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return res.json();
}