"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CatalogResponse, fetchCatalog } from "@/lib/api";
import ProductCard from "./ProductCard";

const TABS: { key: "men" | "women" | "kids"; label: string }[] = [
  { key: "women", label: "Women" },
  { key: "men", label: "Men" },
  { key: "kids", label: "Kids" },
];

export default function CatalogBrowser() {
  const searchParams = useSearchParams();
  const initial = (searchParams.get("category") as "men" | "women" | "kids") || "women";
  const [active, setActive] = useState<"men" | "women" | "kids">(
    TABS.some((t) => t.key === initial) ? initial : "women"
  );
  const [data, setData] = useState<CatalogResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCatalog()
      .then(setData)
      .catch((err) =>
        setError(
          err instanceof Error
            ? err.message
            : "Could not reach the TryFit AI backend."
        )
      );
  }, []);

  const products = useMemo(() => {
    if (!data) return [];
    return data.categories[active] || [];
  }, [data, active]);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActive(tab.key)}
            className={`rounded-full border px-5 py-2 text-sm font-semibold uppercase tracking-[0.12em] transition ${
              active === tab.key
                ? "border-emerald-deep bg-emerald-deep text-parchment"
                : "border-ink/15 text-ink/60 hover:border-emerald-deep/40 hover:text-emerald-deep"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-8 rounded-md border border-rani/30 bg-rani/5 p-4 text-sm text-rani-deep">
          <p className="font-semibold">Backend not reachable</p>
          <p className="mt-1 text-ink/70">
            {error} Make sure the TryFit AI backend is running (see
            README.md) and NEXT_PUBLIC_API_BASE_URL points to it.
          </p>
        </div>
      )}

      {!data && !error && (
        <div className="mt-16 grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="aspect-[3/4] animate-pulse rounded-md bg-ink/5" />
          ))}
        </div>
      )}

      {data && (
        <div className="mt-10 grid grid-cols-2 gap-x-6 gap-y-10 sm:grid-cols-3 lg:grid-cols-4">
          {products.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
          {products.length === 0 && (
            <p className="col-span-full text-ink/50">
              No products found in this category yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
