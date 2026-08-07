import { Suspense } from "react";
import CatalogBrowser from "@/components/CatalogBrowser";

export default function HomePage() {
  return (
    <div>
      <section className="border-b border-gold/20 bg-gradient-to-b from-emerald-deep to-emerald px-6 py-20 text-parchment">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs uppercase tracking-[0.3em] text-gold-light">
            Virtual try-on, built for Pakistani fashion retail
          </p>
          <h1 className="mt-4 max-w-2xl font-display text-4xl font-medium leading-tight sm:text-5xl">
            See it on yourself, before it&apos;s in your cart.
          </h1>
          <p className="mt-5 max-w-xl text-parchment/70">
            Pick anything from the rack, tap{" "}
            <span className="font-semibold text-gold-light">Try Fit Now</span>,
            upload a few clear photos of yourself, and watch the outfit
            appear on you in seconds — full body, realistic, same face,
            same you.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-14">
        <Suspense fallback={null}>
          <CatalogBrowser />
        </Suspense>
      </section>
    </div>
  );
}
