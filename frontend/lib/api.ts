export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8001";

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
  return `${API_BASE}${path}`;
}

export async function fetchCatalog(): Promise<CatalogResponse> {
  const res = await fetch(`${API_BASE}/api/catalog`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load catalog (${res.status})`);
  }
  return res.json();
}

export type BatchJob = {
  job_id: string;
  status: "queued" | "processing" | "completed" | "failed";
  message: string;
  error?: string | null;
  error_code?: string | null;
  result_url?: string | null;
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
}): Promise<{ batch_id: string; expected_outputs: number; message: string }> {
  const form = new FormData();
  form.append("category", params.category);
  form.append("product_number", params.productNumber);
  form.append("color", params.color);
  form.append("cloth_type", params.clothType);
  form.append("garment_description", params.garmentDescription || "complete outfit");
  form.append("quality_preset", "balanced");
  params.personImages.forEach((file) => form.append("person_images", file));

  const res = await fetch(`${API_BASE}/api/catalog/generate`, {
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
  const res = await fetch(`${API_BASE}/api/catalog/batch/${batchId}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to load batch status (${res.status})`);
  }
  return res.json();
}

export function jobResultUrl(jobId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/result`;
}
