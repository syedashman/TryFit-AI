import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "TryFit AI — See it on, before you buy it",
  description:
    "Virtual try-on for online fashion stores. Upload a few photos, see the outfit on you, buy with confidence.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-body">
        <header className="sticky top-0 z-40 border-b border-gold/30 bg-parchment/90 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="font-display text-2xl font-semibold tracking-tight text-emerald-deep">
                TryFit
              </span>
              <span className="rounded-full bg-emerald-deep px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-gold-light">
                AI
              </span>
            </Link>
            <nav className="hidden gap-8 text-sm font-medium uppercase tracking-[0.14em] text-ink/70 md:flex">
              <Link href="/?category=men" className="hover:text-emerald-deep">Men</Link>
              <Link href="/?category=women" className="hover:text-emerald-deep">Women</Link>
              <Link href="/?category=kids" className="hover:text-emerald-deep">Kids</Link>
            </nav>
            <div className="text-xs uppercase tracking-[0.14em] text-ink/50">
              Demo storefront
            </div>
          </div>
          <div className="thread-divider" />
        </header>
        <main>{children}</main>
        <footer className="mt-24 border-t border-gold/30 bg-emerald-deep text-parchment/80">
          <div className="mx-auto max-w-6xl px-6 py-10 text-sm">
            <p className="font-display text-lg text-parchment">TryFit AI</p>
            <p className="mt-2 max-w-xl text-parchment/60">
              A virtual try-on layer any fashion store can plug in next to
              their Add to Cart button. This storefront is a demo shell used
              to preview the try-on experience end to end.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
