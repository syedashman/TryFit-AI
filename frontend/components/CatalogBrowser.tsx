"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CatalogResponse, fetchCatalog } from "@/lib/api";
import ProductCard from "./ProductCard";

const TABS: { key: "men" | "women"; label: string }[] = [
  { key: "women", label: "Women" },
  { key: "men", label: "Men" },
];

export default function CatalogBrowser() {
  const searchParams = useSearchParams();
  const initial = (searchParams.get("category") as "men" | "women") || "women";
  const [active, setActive] = useState<"men" | "women">(
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
      <div className="flex items-center justify-between border-b border-[rgba(17,17,17,0.12)] pb-4 pt-2">
        <div className="text-[0.64rem] font-medium uppercase tracking-[0.22em] text-[rgba(17,17,17,0.7)]">
          {active === "men" ? "Men" : "Women"}
        </div>
        <div className="flex items-center gap-2">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActive(tab.key)}
              className={`border px-4 py-2 text-[0.68rem] font-medium uppercase tracking-[0.18em] transition ${
                active === tab.key
                  ? "border-[var(--tryfit-ink)] bg-[var(--tryfit-ink)] text-[#f8f7f4]"
                  : "border-[rgba(17,17,17,0.2)] bg-transparent text-[var(--tryfit-ink)] hover:border-[var(--tryfit-ink)]"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mt-8 rounded-md border border-rani/30 bg-rani/5 p-4 text-sm text-rani-deep">
          <p className="font-semibold">Backend not reachable</p>
          <p className="mt-1 text-ink/70">
            {error} Make sure the TryFit AI backend is running and the API base URL is configured.
          </p>
        </div>
      )}

      {!data && !error && (
        <div className="mt-10 grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="aspect-[3/4] animate-pulse bg-[rgba(17,17,17,0.04)]" />
          ))}
        </div>
      )}

      {data && (
        <div className="mt-8 grid grid-cols-2 gap-x-5 gap-y-10 sm:grid-cols-3 lg:grid-cols-4">
          {products.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
          {products.length === 0 && (
            <p className="col-span-full text-[rgba(17,17,17,0.5)]">
              No products found in this category yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
