import Link from "next/link";
import Image from "next/image";
import { assetUrl, CatalogProduct } from "@/lib/api";
import WishlistButton from "@/components/WishlistButton";

export default function ProductCard({ product }: { product: CatalogProduct }) {
  const swatchColors = product.colors.slice(0, 5);

  return (
    <article className="group">
      <div className="relative overflow-hidden border border-[rgba(17,17,17,0.08)] bg-[#f8f7f4]">
        <Link
          href={`/product/${product.category.toLowerCase()}/${product.product_number}`}
          className="block"
        >
          <div className="relative aspect-[3/4] overflow-hidden bg-[#efede9]">
            {product.thumbnail ? (
              <Image
                src={assetUrl(product.thumbnail)}
                alt={product.name}
                fill
                sizes="(max-width: 768px) 50vw, 25vw"
                className="object-cover transition duration-500 group-hover:scale-[1.04]"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-[rgba(17,17,17,0.3)]">
                No image
              </div>
            )}
          </div>
        </Link>
        <WishlistButton product={product} className="absolute right-3 top-3 z-10" />
      </div>

      <div className="mt-4 flex items-start justify-between gap-3">
        <Link
          href={`/product/${product.category.toLowerCase()}/${product.product_number}`}
          className="min-w-0"
        >
          <div className="font-display text-[1.1rem] leading-tight tracking-[-0.03em] text-[var(--tryfit-ink)]">
            {product.name}
          </div>
          <div className="mt-1 text-[0.65rem] uppercase tracking-[0.14em] text-[rgba(17,17,17,0.48)]">
            {product.category}
          </div>
          <div className="mt-2 text-base text-[var(--tryfit-ink)]">
            ${Number(product.product_number.replace(/\D/g, "")) > 0 ? Number(product.product_number.replace(/\D/g, "")) : 195}
          </div>
        </Link>

        <div className="flex gap-1 pt-1">
          {swatchColors.map((color) => (
            <span
              key={color.name}
              title={color.name}
              className="h-3.5 w-3.5 rounded-full border border-[rgba(17,17,17,0.12)] bg-[rgba(142,126,109,0.25)]"
            />
          ))}
        </div>
      </div>
    </article>
  );
}
