"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { assetUrl, CatalogProduct, fetchCatalog } from "@/lib/api";
import TryOnDrawer from "./TryOnDrawer";

export default function ProductDetail({
  category,
  productNumber,
}: {
  category: string;
  productNumber: string;
}) {
  const [product, setProduct] = useState<CatalogProduct | null | undefined>(
    undefined
  );
  const [colorIndex, setColorIndex] = useState(0);
  const [imageIndex, setImageIndex] = useState(0);
  const [favourited, setFavourited] = useState(false);
  const [added, setAdded] = useState(false);
  const [tryFitOpen, setTryFitOpen] = useState(false);

  useEffect(() => {
    fetchCatalog()
      .then((data) => {
        const list =
          data.categories[category as "men" | "women" | "kids"] || [];
        const match = list.find((p) => p.product_number === productNumber);
        setProduct(match || null);
      })
      .catch(() => setProduct(null));
  }, [category, productNumber]);

  if (product === undefined) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-16">
        <div className="grid gap-10 md:grid-cols-2">
          <div className="aspect-[3/4] animate-pulse rounded-md bg-ink/5" />
          <div className="space-y-4">
            <div className="h-8 w-2/3 animate-pulse rounded bg-ink/5" />
            <div className="h-4 w-1/3 animate-pulse rounded bg-ink/5" />
          </div>
        </div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-24 text-center">
        <p className="font-display text-2xl">Product not found</p>
        <p className="mt-2 text-ink/50">
          It may have been removed from the demo catalog.
        </p>
      </div>
    );
  }

  const color = product.colors[colorIndex] || product.colors[0];
  const activeImage = color?.assets[imageIndex] || product.thumbnail;

  function openTryFit() {
    setTryFitOpen(true);
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-14">
      <div className="grid gap-12 md:grid-cols-2">
        <div>
          <div className="relative aspect-[3/4] overflow-hidden rounded-md bg-white/40">
            {activeImage && (
              <Image
                src={assetUrl(activeImage)}
                alt={product.name}
                fill
                sizes="(max-width: 768px) 100vw, 50vw"
                className="object-cover"
                priority
              />
            )}
          </div>
          {color && color.assets.length > 1 && (
            <div className="mt-4 flex gap-3 overflow-x-auto">
              {color.assets.map((asset, idx) => (
                <button
                  key={asset}
                  onClick={() => setImageIndex(idx)}
                  className={`relative h-20 w-16 shrink-0 overflow-hidden rounded border ${
                    idx === imageIndex
                      ? "border-emerald-deep"
                      : "border-ink/10"
                  }`}
                >
                  <Image
                    src={assetUrl(asset)}
                    alt=""
                    fill
                    sizes="64px"
                    className="object-cover"
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-ink/45">
            {product.category}
          </p>
          <h1 className="mt-2 font-display text-3xl text-ink">
            {product.name}
          </h1>
          <p className="mt-2 text-sm text-ink/50">
            Product #{product.product_number} &middot; {product.image_count}{" "}
            images
          </p>

          {product.colors.length > 1 && (
            <div className="mt-8">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink/60">
                Colour — {color?.name}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {product.colors.map((c, idx) => (
                  <button
                    key={c.name}
                    onClick={() => {
                      setColorIndex(idx);
                      setImageIndex(0);
                    }}
                    className={`rounded-full border px-4 py-1.5 text-sm transition ${
                      idx === colorIndex
                        ? "border-emerald-deep bg-emerald-deep text-parchment"
                        : "border-ink/15 text-ink/70 hover:border-emerald-deep/40"
                    }`}
                  >
                    {c.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="mt-10 space-y-3">
            <button
              onClick={openTryFit}
              className="fabric-shimmer flex w-full items-center justify-center gap-2 rounded-md bg-gradient-to-r from-gold-muted via-gold to-gold-light px-6 py-4 font-display text-lg font-semibold text-emerald-deep shadow-sm transition hover:brightness-105"
            >
              ✨ Try Fit Now
            </button>

            <div className="flex gap-3">
              <button
                onClick={() => setAdded(true)}
                className="flex-1 rounded-md border border-emerald-deep bg-emerald-deep px-6 py-3 text-sm font-semibold uppercase tracking-[0.1em] text-parchment transition hover:bg-emerald-soft"
              >
                {added ? "Added ✓" : "Add to Cart"}
              </button>
              <button
                onClick={() => setFavourited((v) => !v)}
                className={`flex-1 rounded-md border px-6 py-3 text-sm font-semibold uppercase tracking-[0.1em] transition ${
                  favourited
                    ? "border-rani bg-rani/10 text-rani-deep"
                    : "border-ink/15 text-ink/70 hover:border-rani/40"
                }`}
              >
                {favourited ? "Favourited ♥" : "Add to Favourite"}
              </button>
            </div>
          </div>

          <p className="mt-6 text-xs leading-relaxed text-ink/45">
            Try Fit Now opens right here — upload or capture 3–5 clear
            photos of yourself and TryFit AI will generate a realistic
            preview of this outfit on you, same face, same body, this
            product.
          </p>
        </div>
      </div>

      {color && (
        <TryOnDrawer
          open={tryFitOpen}
          onClose={() => setTryFitOpen(false)}
          category={category}
          productNumber={productNumber}
          colorName={color.name}
        />
      )}
    </div>
  );
}
