import Link from "next/link";
import Image from "next/image";
import { assetUrl, CatalogProduct } from "@/lib/api";

export default function ProductCard({ product }: { product: CatalogProduct }) {
  const swatchColors = product.colors.slice(0, 5);

  return (
    <Link
      href={`/product/${product.category.toLowerCase()}/${product.product_number}`}
      className="group block"
    >
      <div className="relative aspect-[3/4] overflow-hidden rounded-md bg-white/40">
        {product.thumbnail ? (
          <Image
            src={assetUrl(product.thumbnail)}
            alt={product.name}
            fill
            sizes="(max-width: 768px) 50vw, 25vw"
            className="object-cover transition duration-500 group-hover:scale-[1.04]"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-ink/30">
            No image
          </div>
        )}
        <span className="absolute left-3 top-3 rounded-full bg-emerald-deep/90 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-gold-light opacity-0 transition group-hover:opacity-100">
          Try Fit Now
        </span>
      </div>
      <div className="mt-3 flex items-start justify-between gap-2">
        <div>
          <p className="font-display text-base text-ink">{product.name}</p>
          <p className="text-xs uppercase tracking-[0.1em] text-ink/45">
            {product.color_count} colour{product.color_count === 1 ? "" : "s"}
          </p>
        </div>
        <div className="flex gap-1 pt-1">
          {swatchColors.map((color) => (
            <span
              key={color.name}
              title={color.name}
              className="h-3 w-3 rounded-full border border-ink/10 bg-gold/40"
            />
          ))}
        </div>
      </div>
    </Link>
  );
}
