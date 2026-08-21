import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import WishlistButton from "@/components/WishlistButton";

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
      <body className="font-body bg-[var(--tryfit-bg)] text-[var(--tryfit-ink)]">
        <header className="sticky top-0 z-40 border-b border-[rgba(17,17,17,0.12)] bg-[rgba(242,239,233,0.92)] backdrop-blur-md">
          <div className="mx-auto flex max-w-[1280px] items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
            <nav className="hidden items-center gap-7 md:flex">
              <Link href="/?category=men" className="nav-link">Men</Link>
              <Link href="/?category=women" className="nav-link">Women</Link>
              <Link href="/?category=women" className="nav-link">New Arrivals</Link>
              <Link href="/?category=men" className="nav-link">Collections</Link>
            </nav>

            <Link href="/" className="absolute left-1/2 -translate-x-1/2 text-center">
              <span className="font-display text-[2rem] leading-none tracking-[-0.06em] text-[var(--tryfit-ink)]">
                TRYFIT
              </span>
            </Link>

            <div className="ml-auto flex items-center gap-3 pl-8">
              <WishlistButton compact />
              <Link href="/wishlist" aria-label="Wishlist" className="flex h-10 w-10 items-center justify-center rounded-full border border-[rgba(17,17,17,0.12)] bg-white/40 text-[var(--tryfit-ink)] transition hover:-translate-y-0.5 hover:bg-white/70">
                <svg viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current stroke-[1.6]">
                  <path d="M7 4.5A4.5 4.5 0 0 1 11.5 3a4.5 4.5 0 0 1 4.3 6.5l-4.5 5.1-4.4-5.2A4.5 4.5 0 0 1 7 4.5Z" />
                </svg>
              </Link>
            </div>
          </div>
          <div className="thread-divider" />
        </header>
        <main>{children}</main>
        <footer className="mt-24 border-t border-[rgba(17,17,17,0.12)] bg-[var(--tryfit-bg)]">
          <div className="mx-auto grid max-w-[1280px] gap-10 px-4 py-8 sm:px-6 lg:grid-cols-[1fr_auto] lg:px-8">
            <div>
              <div className="font-display text-[2rem] leading-none tracking-[-0.06em] text-[var(--tryfit-ink)]">TRYFIT</div>
              <p className="mt-3 text-xs uppercase tracking-[0.18em] text-[var(--tryfit-muted)]">© 2024 TRYFIT. ALL RIGHTS RESERVED.</p>
            </div>
            <div className="grid grid-cols-2 gap-x-10 gap-y-2 text-[0.72rem] uppercase tracking-[0.12em] text-[var(--tryfit-muted)] sm:grid-cols-3 lg:grid-cols-5">
              <span>Men</span>
              <span>Women</span>
              <span>Collections</span>
              <span>About</span>
              <span>Contact</span>
              <span>Privacy</span>
              <span>Terms</span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
