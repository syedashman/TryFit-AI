"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { assetUrl, CatalogProduct, fetchCatalog } from "@/lib/api";
import WishlistButton from "@/components/WishlistButton";

export default function WishlistPage() {
  const [items, setItems] = useState<Array<{ id: string; product_number: string; category: string; name: string }>>([]);
  const [products, setProducts] = useState<CatalogProduct[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const raw = window.localStorage.getItem("tryfit-wishlist");
    let parsed: Array<{ id: string; product_number: string; category: string; name: string }> = [];
    try {
      parsed = raw ? JSON.parse(raw) : [];
    } catch {
      parsed = [];
    }
    setItems(Array.isArray(parsed) ? parsed : []);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    fetchCatalog().then((data) => {
      const all = [...(data.categories.men || []), ...(data.categories.women || [])];
      setProducts(
        all.filter((product) =>
          items.some((item) => item.id === product.id || item.product_number === product.product_number)
        )
      );
    });
  }, [items, ready]);

  return (
    <div className="mx-auto max-w-[1280px] px-4 pb-16 pt-10 sm:px-6 lg:px-8">
      <div className="mb-12 text-center">
        <h1 className="font-display text-[3.5rem] leading-[0.9] tracking-[-0.06em] text-[var(--tryfit-ink)]">
          Your Wishlist
        </h1>
        <p className="mt-4 text-base text-[rgba(17,17,17,0.6)]">
          Curated pieces waiting to elevate your wardrobe.
        </p>
      </div>

      {products.length === 0 ? (
        <div className="rounded border border-[rgba(17,17,17,0.12)] bg-white/30 px-10 py-20 text-center text-[rgba(17,17,17,0.6)]">
          No saved pieces yet. Add a few favourites from the collection.
        </div>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {products.map((product) => (
            <article key={product.id} className="group">
              <div className="relative overflow-hidden border border-[rgba(17,17,17,0.08)] bg-[#f8f7f4]">
                <Link href={`/product/${product.category.toLowerCase()}/${product.product_number}`}>
                  <div className="relative aspect-[3/4] bg-[#efede9]">
                    {product.thumbnail ? (
                      <Image
                        src={assetUrl(product.thumbnail)}
                        alt={product.name}
                        fill
                        className="object-cover transition duration-500 group-hover:scale-[1.04]"
                        sizes="(max-width: 768px) 50vw, 25vw"
                      />
                    ) : null}
                  </div>
                </Link>
                <WishlistButton product={product} className="absolute right-3 top-3 z-10" />
              </div>

              <Link href={`/product/${product.category.toLowerCase()}/${product.product_number}`}>
                <div className="mt-3 font-display text-[1.3rem] leading-tight tracking-[-0.04em] text-[var(--tryfit-ink)]">
                  {product.name}
                </div>
              </Link>
              <div className="mt-1 text-base text-[var(--tryfit-ink)]">${195}</div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
