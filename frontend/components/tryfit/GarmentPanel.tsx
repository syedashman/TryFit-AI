"use client";

import { useEffect, useRef } from "react";
import Image from "next/image";
import { gsap } from "gsap";
import { CatalogProduct, assetUrl } from "@/lib/api";
import { prefersReducedMotion } from "@/lib/tryfit";

export default function GarmentPanel({
  product,
  colorName,
  referenceImage,
}: {
  product: CatalogProduct;
  colorName: string;
  referenceImage: string | null;
}) {
  const imageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (prefersReducedMotion() || !imageRef.current) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(
        imageRef.current,
        { autoAlpha: 0, scale: 0.98, y: 12 },
        { autoAlpha: 1, scale: 1, y: 0, duration: 0.6, ease: "power2.out" }
      );
    });
    return () => ctx.revert();
  }, []);

  return (
    <aside className="lg:sticky lg:top-24">
      <p className="text-[0.68rem] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.55)]">
        Selected garment
      </p>
      <div ref={imageRef} className="relative mt-4 aspect-[4/5] overflow-hidden border border-[rgba(17,17,17,0.07)] bg-[#f8f7f4] shadow-[0_18px_30px_rgba(17,17,17,0.04)]">
        {referenceImage ? (
          <Image
            src={assetUrl(referenceImage)}
            alt={`${product.name} — ${colorName}`}
            fill
            sizes="(max-width: 1024px) 100vw, 40vw"
            className="object-cover"
            priority
          />
        ) : (
          <div className="flex h-full items-center justify-center text-[rgba(17,17,17,0.3)]">No image</div>
        )}
      </div>

      <div className="mt-5">
        <p className="text-[0.68rem] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.58)]">{product.category}</p>
        <h2 className="mt-2 font-display text-[2.1rem] leading-none tracking-[-0.05em] text-[var(--tryfit-ink)]">{product.name}</h2>
        <div className="mt-4 flex items-center gap-2 text-sm text-[rgba(17,17,17,0.66)]">
          <span className="inline-flex h-3.5 w-3.5 rounded-full border border-[rgba(17,17,17,0.12)] bg-[#d8c8af]" />
          <span>{colorName}</span>
        </div>
        <p className="mt-4 max-w-sm text-sm leading-relaxed text-[rgba(17,17,17,0.65)]">
          A premium {product.category.toLowerCase()} look from the TryFit collection. Upload your photos and see this exact product styled on you.
        </p>
      </div>
    </aside>
  );
}
