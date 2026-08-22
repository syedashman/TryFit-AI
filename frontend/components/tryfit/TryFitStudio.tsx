"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { gsap } from "gsap";
import { CatalogProduct, fetchCatalog } from "@/lib/api";
import { useTryFit } from "@/lib/useTryFit";
import { friendlyError, prefersReducedMotion } from "@/lib/tryfit";
import GarmentPanel from "./GarmentPanel";
import UploadPanel from "./UploadPanel";
import ResultsPanel from "./ResultsPanel";

const SUPPORTED = ["men", "women"];

export default function TryFitStudio({
  category,
  productNumber,
  initialColor,
}: {
  category: string;
  productNumber: string;
  initialColor?: string;
}) {
  const router = useRouter();
  const categoryKey = category.toLowerCase();
  const supported = SUPPORTED.includes(categoryKey);

  const [product, setProduct] = useState<CatalogProduct | null | undefined>(
    undefined
  );
  const workspaceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!supported) {
      setProduct(null);
      return;
    }
    fetchCatalog()
      .then((data) => {
        const list = data.categories[categoryKey as "men" | "women"] || [];
        setProduct(list.find((p) => p.product_number === productNumber) || null);
      })
      .catch(() => setProduct(null));
  }, [categoryKey, productNumber, supported]);

  const resolvedColor =
    product?.colors.find(
      (c) => c.name.toLowerCase() === (initialColor || "").toLowerCase()
    ) ||
    product?.colors[0] ||
    null;
  const colorName = resolvedColor?.name || initialColor || "Default";

  const tf = useTryFit({ category: categoryKey, productNumber, colorName });

  // Page entrance stagger for the workspace column.
  useEffect(() => {
    if (prefersReducedMotion() || !workspaceRef.current || !product) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(
        workspaceRef.current,
        { autoAlpha: 0, y: 16 },
        { autoAlpha: 1, y: 0, duration: 0.5, ease: "power2.out" }
      );
    }, workspaceRef);
    return () => ctx.revert();
  }, [product]);

  const backHref = `/product/${categoryKey}/${productNumber}`;

  if (product === undefined) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-16">
        <div className="grid gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="aspect-[3/4] animate-pulse rounded-lg bg-ink/5" />
          <div className="space-y-4">
            <div className="h-8 w-2/3 animate-pulse rounded bg-ink/5" />
            <div className="grid grid-cols-2 gap-3">
              <div className="aspect-[3/4] animate-pulse rounded bg-ink/5" />
              <div className="aspect-[3/4] animate-pulse rounded bg-ink/5" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-24 text-center">
        <p className="font-display text-2xl">
          {supported ? "Product not found" : "This collection isn't available"}
        </p>
        <p className="mt-2 text-ink/50">
          Explore our Men and Women collections instead.
        </p>
        <button
          onClick={() => router.push("/?category=women")}
          className="mt-6 rounded-md border border-emerald-deep bg-emerald-deep px-6 py-3 text-sm font-semibold uppercase tracking-[0.1em] text-parchment"
        >
          Back to shop
        </button>
      </div>
    );
  }

  const referenceImage = resolvedColor?.assets[0] || product.thumbnail || null;

  return (
    <div className="mx-auto max-w-[1280px] px-4 py-8 sm:px-6 lg:px-8">
      <div className="flex items-center justify-between border-b border-[rgba(17,17,17,0.12)] pb-4">
        <Link href={backHref} className="nav-link text-[0.7rem] uppercase tracking-[0.18em]">
          ← Back to Product
        </Link>
        <div className="font-display text-[2.1rem] tracking-[-0.06em] text-[var(--tryfit-ink)]">TRYFIT</div>
      </div>

      <div className="mt-8 grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:gap-12">
        <GarmentPanel product={product} colorName={colorName} referenceImage={referenceImage} />

        <div ref={workspaceRef}>
          {tf.stage === "upload" && (
            <UploadPanel
              previews={tf.previews}
              fileCount={tf.files.length}
              canSubmit={tf.canSubmit}
              onAddFiles={tf.addFiles}
              onAddCaptured={tf.addCapturedFile}
              onRemove={tf.removeFile}
              onGenerate={tf.startGeneration}
            />
          )}

          {tf.batch && (tf.stage === "submitting" || tf.stage === "processing" || tf.stage === "done") && (
            <ResultsPanel
              batch={tf.batch}
              category={categoryKey}
              productNumber={productNumber}
              retryingIds={tf.retryingIds}
              onRetry={tf.retryPose}
              onReplacePhoto={tf.replacePhoto}
              onReset={tf.reset}
            />
          )}

          {tf.stage === "error" && (
            <div className="rounded-lg border border-[rgba(17,17,17,0.12)] bg-[#f8f7f4] p-8">
              <p className="font-display text-3xl tracking-[-0.05em] text-[var(--tryfit-ink)]">Try Fit is temporarily unavailable</p>
              <p className="mt-3 text-[rgba(17,17,17,0.7)]">{friendlyError({ message: tf.errorMessage })}</p>
              <button onClick={tf.reset} className="mt-6 border border-[var(--tryfit-ink)] bg-[var(--tryfit-ink)] px-6 py-3 text-[0.7rem] uppercase tracking-[0.18em] text-[#f7f5f2]">Try again</button>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
