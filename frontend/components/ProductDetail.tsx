"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { assetUrl, CatalogProduct, fetchCatalog } from "@/lib/api";
import WishlistButton from "@/components/WishlistButton";

const SUPPORTED_CATEGORIES = ["men", "women"];

export default function ProductDetail({
  category,
  productNumber,
}: {
  category: string;
  productNumber: string;
}) {
  const router = useRouter();
  const [product, setProduct] = useState<CatalogProduct | null | undefined>(undefined);
  const [colorIndex, setColorIndex] = useState(0);
  const [imageIndex, setImageIndex] = useState(0);
  const [added, setAdded] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(true);

  const categoryKey = category.toLowerCase();
  const supported = SUPPORTED_CATEGORIES.includes(categoryKey);

  useEffect(() => {
    if (!supported) {
      setProduct(null);
      return;
    }
    fetchCatalog()
      .then((data) => {
        const list = data.categories[categoryKey as "men" | "women"] || [];
        const match = list.find((p) => p.product_number === productNumber);
        setProduct(match || null);
      })
      .catch(() => setProduct(null));
  }, [categoryKey, productNumber, supported]);

  const color = product?.colors[colorIndex] || product?.colors[0] || null;
  const activeImage = color?.assets[imageIndex] || product?.thumbnail || null;

  const pricing = useMemo(() => {
    if (!product) return "$0";
    const digits = product.product_number.replace(/\D/g, "");
    const price = digits ? Number(digits) : 195;
    return `$${price}`;
  }, [product]);

  function openTryFit() {
    const colorSlug = encodeURIComponent(color?.name || "Default");
    router.push(`/product/${categoryKey}/${productNumber}/try-fit?color=${colorSlug}`);
  }

  if (product === undefined) {
    return (
      <div className="mx-auto max-w-[1280px] px-4 py-16 sm:px-6 lg:px-8">
        <div className="grid gap-10 md:grid-cols-2">
          <div className="aspect-[3/4] animate-pulse bg-[rgba(17,17,17,0.05)]" />
          <div className="space-y-4">
            <div className="h-9 w-2/3 animate-pulse bg-[rgba(17,17,17,0.05)]" />
            <div className="h-5 w-1/3 animate-pulse bg-[rgba(17,17,17,0.05)]" />
          </div>
        </div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="mx-auto max-w-[1280px] px-4 py-24 text-center sm:px-6 lg:px-8">
        <p className="font-display text-4xl tracking-[-0.06em] text-[var(--tryfit-ink)]">
          {supported ? "Product not found" : "This collection isn't available"}
        </p>
        <p className="mt-3 text-[var(--tryfit-muted)]">
          {supported ? "This product is unavailable in the active catalog." : "Explore our Men and Women collections instead."}
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <button onClick={() => router.push("/?category=women")} className="border border-[var(--tryfit-ink)] bg-[var(--tryfit-ink)] px-6 py-3 text-[0.7rem] font-medium uppercase tracking-[0.18em] text-[#f7f5f2]">Shop Women</button>
          <button onClick={() => router.push("/?category=men")} className="border border-[rgba(17,17,17,0.2)] px-6 py-3 text-[0.7rem] font-medium uppercase tracking-[0.18em] text-[var(--tryfit-ink)]">Shop Men</button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1280px] px-4 pb-16 pt-8 sm:px-6 lg:px-8">
      <div className="grid gap-10 lg:grid-cols-[1.15fr_0.85fr] lg:gap-12">
        <div>
          <div className="relative overflow-hidden border border-[rgba(17,17,17,0.08)] bg-[#f8f7f4]">
            <div className="relative aspect-[4/5] overflow-hidden">
              {activeImage ? (
                <Image src={assetUrl(activeImage)} alt={product.name} fill className="object-cover" priority sizes="(max-width: 1024px) 100vw, 60vw" />
              ) : (
                <div className="flex h-full items-center justify-center text-[rgba(17,17,17,0.35)]">No image</div>
              )}
            </div>
            <WishlistButton product={product} className="absolute right-4 top-4" />
          </div>

          {color && color.assets.length > 1 && (
            <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
              {color.assets.map((asset, idx) => (
                <button key={asset} onClick={() => setImageIndex(idx)} className={`relative aspect-[4/5] overflow-hidden border ${idx === imageIndex ? "border-[var(--tryfit-ink)]" : "border-[rgba(17,17,17,0.1)]"}`}>
                  <Image src={assetUrl(asset)} alt="" fill className="object-cover" sizes="160px" />
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="pt-4">
          <div className="text-[0.7rem] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.55)]">
            {product.category} / {product.product_number}
          </div>
          <h1 className="mt-3 font-display text-[3.2rem] leading-[0.9] tracking-[-0.06em] text-[var(--tryfit-ink)]">
            {product.name}
          </h1>
          <div className="mt-4 flex items-center justify-between gap-4 border-b border-[rgba(17,17,17,0.12)] pb-4">
            <div className="text-[1.1rem] text-[var(--tryfit-ink)]">{pricing}</div>
            <div className="text-[0.7rem] uppercase tracking-[0.18em] text-[rgba(17,17,17,0.55)]">{product.color_count} Color{product.color_count === 1 ? "" : "s"}</div>
          </div>

          {product.colors.length > 1 && (
            <div className="mt-6">
              <div className="text-[0.7rem] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.55)]">Colour</div>
              <div className="mt-3 flex flex-wrap gap-3">
                {product.colors.map((c, idx) => (
                  <button key={c.name} onClick={() => { setColorIndex(idx); setImageIndex(0); }} className={`h-8 w-8 rounded-full border ${idx === colorIndex ? "border-[var(--tryfit-ink)] ring-2 ring-[rgba(17,17,17,0.12)]" : "border-[rgba(17,17,17,0.2)]"}`} title={c.name} style={{ background: idx % 2 === 0 ? "#d7d0ca" : "#1c1c1c" }} />
                ))}
              </div>
            </div>
          )}

          <div className="mt-8">
            <div className="text-[0.7rem] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.55)]">Size</div>
            <div className="mt-3 grid grid-cols-4 gap-3">
              {['XS', 'S', 'M', 'L'].map((size) => (
                <button key={size} className={`border px-4 py-3 text-[0.7rem] uppercase tracking-[0.18em] ${size === 'S' ? 'border-[var(--tryfit-ink)] bg-[var(--tryfit-ink)] text-[#f7f5f2]' : 'border-[rgba(17,17,17,0.15)] bg-transparent text-[var(--tryfit-ink)]'}`}>
                  {size}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            <button onClick={() => setAdded(true)} className="border border-[var(--tryfit-ink)] bg-[var(--tryfit-ink)] px-6 py-4 text-[0.7rem] font-medium uppercase tracking-[0.18em] text-[#f7f5f2] transition hover:bg-[var(--tryfit-olive)]">
              {added ? "Added ✓" : "Add to Bag"}
            </button>
            <button onClick={openTryFit} className="border border-[rgba(17,17,17,0.18)] bg-transparent px-6 py-4 text-[0.7rem] font-medium uppercase tracking-[0.18em] text-[var(--tryfit-ink)] transition hover:border-[var(--tryfit-ink)]">
              Try Fit Now
            </button>
          </div>

          <div className="mt-8 border-t border-[rgba(17,17,17,0.12)] pt-4">
            <button onClick={() => setDetailsOpen((v) => !v)} className="flex w-full items-center justify-between text-left text-[0.7rem] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.7)]">
              <span>Details</span>
              <span>{detailsOpen ? '−' : '+'}</span>
            </button>
            {detailsOpen && (
              <p className="mt-4 text-sm leading-relaxed text-[rgba(17,17,17,0.7)]">
                Crafted from premium materials for everyday wear. This selected piece is pulled directly from the existing TryFitAI catalog and is designed to be tried on using the same real-generation workflow.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
