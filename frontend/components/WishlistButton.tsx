"use client";

import { useEffect, useState } from "react";
import { CatalogProduct } from "@/lib/api";

const STORAGE_KEY = "tryfit-wishlist";

type WishlistEntry = {
  id: string;
  category: string;
  product_number: string;
  name: string;
};

function readWishlist(): WishlistEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function WishlistButton({
  product,
  className = "",
  compact = false,
}: {
  product?: CatalogProduct;
  className?: string;
  compact?: boolean;
}) {
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!product) return;
    setSaved(readWishlist().some((item) => item.id === product.id));
  }, [product]);

  const toggle = () => {
    if (!product) return;
    const next = readWishlist();
    const exists = next.some((item) => item.id === product.id);
    const updated = exists
      ? next.filter((item) => item.id !== product.id)
      : [
          ...next,
          {
            id: product.id,
            category: product.category,
            product_number: product.product_number,
            name: product.name,
          },
        ];

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    setSaved(!exists);
  };

  if (!product) return null;

  const buttonClasses = compact
    ? "flex h-10 w-10 items-center justify-center rounded-full border border-[rgba(17,17,17,0.12)] bg-white/80 text-[var(--tryfit-ink)] transition hover:-translate-y-0.5 hover:bg-white"
    : "flex h-11 w-11 items-center justify-center rounded-full border border-[rgba(17,17,17,0.14)] bg-white/80 text-[var(--tryfit-ink)] transition hover:border-[var(--tryfit-ink)] hover:bg-white";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={saved ? "Remove from wishlist" : "Add to wishlist"}
      className={`${buttonClasses} ${className}`.trim()}
    >
      <svg
        viewBox="0 0 24 24"
        className={`h-4 w-4 ${saved ? "fill-current" : "fill-none stroke-current stroke-[1.7]"}`}
        aria-hidden="true"
      >
        <path d="M12 20.2 4.7 13a4.8 4.8 0 0 1 6.8-6.8L12 6.7l.5-.5a4.8 4.8 0 1 1 6.8 6.8L12 20.2Z" />
      </svg>
    </button>
  );
}

export function getWishlistProducts(): WishlistEntry[] {
  return readWishlist();
}
