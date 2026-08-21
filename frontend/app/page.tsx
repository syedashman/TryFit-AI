"use client";

import { Suspense, useEffect, useRef } from "react";
import { gsap } from "gsap";
import CatalogBrowser from "@/components/CatalogBrowser";
import { prefersReducedMotion } from "@/lib/tryfit";

const HERO_IMAGE = "http://127.0.0.1:8001/static/catalog/Women/1/010.webp";

export default function HomePage() {
  const heroRef = useRef<HTMLElement | null>(null);
  const imageRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!heroRef.current || !imageRef.current) return;
    if (prefersReducedMotion()) {
      gsap.set("[data-hero-reveal]", { autoAlpha: 1, y: 0, x: 0, scale: 1 });
      return;
    }

    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: "power3.out" } });

      tl.fromTo(
        "[data-hero-reveal='eyebrow']",
        { autoAlpha: 0, y: 18 },
        { autoAlpha: 1, y: 0, duration: 0.55 }
      )
        .fromTo(
          "[data-hero-reveal='headline']",
          { autoAlpha: 0, y: 30 },
          { autoAlpha: 1, y: 0, duration: 0.7 },
          "-=0.25"
        )
        .fromTo(
          "[data-hero-reveal='description']",
          { autoAlpha: 0, y: 18 },
          { autoAlpha: 1, y: 0, duration: 0.55 },
          "-=0.18"
        )
        .fromTo(
          "[data-hero-reveal='cta']",
          { autoAlpha: 0, y: 14 },
          { autoAlpha: 1, y: 0, duration: 0.55 },
          "-=0.12"
        )
        .fromTo(
          imageRef.current,
          { autoAlpha: 0, scale: 1.04, x: 18, y: 12 },
          { autoAlpha: 1, scale: 1, x: 0, y: 0, duration: 1.1 },
          "-=0.2"
        );

      const onPointerMove = (event: PointerEvent) => {
        const isTouch = window.matchMedia("(pointer: coarse)").matches;
        if (isTouch) return;

        const rect = heroRef.current!.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - 0.5;
        const y = (event.clientY - rect.top) / rect.height - 0.5;

        gsap.to(imageRef.current, {
          x: x * 10,
          y: y * 8,
          duration: 0.45,
          ease: "power2.out",
          overwrite: true,
        });
      };

      const onPointerLeave = () => {
        gsap.to(imageRef.current, {
          x: 0,
          y: 0,
          duration: 0.5,
          ease: "power2.out",
          overwrite: true,
        });
      };

      heroRef.current.addEventListener("pointermove", onPointerMove);
      heroRef.current.addEventListener("pointerleave", onPointerLeave);

      return () => {
        heroRef.current?.removeEventListener("pointermove", onPointerMove);
        heroRef.current?.removeEventListener("pointerleave", onPointerLeave);
      };
    }, heroRef);

    return () => ctx.revert();
  }, []);

  return (
    <div className="mx-auto max-w-[1280px] px-4 pb-10 pt-4 sm:px-6 lg:px-8">
      <section
        ref={heroRef}
        className="relative overflow-hidden border border-[rgba(17,17,17,0.1)] bg-[#ece7e0]"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_28%,rgba(255,255,255,0.95),rgba(242,239,233,0.6)_32%,transparent_70%)]" />
        <div className="relative grid min-h-[620px] items-end gap-10 px-5 pb-8 pt-8 md:px-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:pb-10">
          <div className="max-w-[560px]">
            <p
              data-hero-reveal="eyebrow"
              className="text-[0.7rem] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.55)]"
            >
              Premium essentials for modern movement.
            </p>
            <h1
              data-hero-reveal="headline"
              className="mt-4 font-display text-[3.2rem] leading-[0.88] tracking-[-0.06em] text-[var(--tryfit-ink)] sm:text-[4.5rem] lg:text-[5.2rem]"
            >
              The Form Collection.
            </h1>
            <p
              data-hero-reveal="description"
              className="mt-5 max-w-lg text-base leading-relaxed text-[rgba(17,17,17,0.68)]"
            >
              Elevated technical silhouettes designed to move with you. Discover
              premium pieces for every day, from refined tailoring to all-season
              essentials.
            </p>
            <div data-hero-reveal="cta" className="mt-8 flex flex-wrap gap-3">
              <a
                href="#catalog"
                className="fabric-shimmer inline-flex items-center justify-center rounded-none border border-[var(--tryfit-ink)] bg-[var(--tryfit-ink)] px-7 py-4 text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-[#f5f3ee] transition hover:bg-[var(--tryfit-olive)]"
              >
                Shop Men
              </a>
              <a
                href="#catalog"
                className="inline-flex items-center justify-center border border-[rgba(17,17,17,0.35)] bg-transparent px-7 py-4 text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-[var(--tryfit-ink)] transition hover:border-[var(--tryfit-ink)]"
              >
                Shop Women
              </a>
            </div>
          </div>

          <div ref={imageRef} className="relative h-[500px] overflow-hidden lg:h-[560px]">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_25%,rgba(255,255,255,0.72),transparent_38%)]" />
            <div className="absolute inset-x-0 bottom-0 top-10 mx-auto h-[92%] w-[72%] rounded-t-[160px] bg-[linear-gradient(180deg,#dbd5ce_0%,#c5b7a8_35%,#a7a19b_100%)] opacity-20 blur-2xl" />
            <div className="absolute right-0 top-6 z-10 rounded-full border border-[rgba(17,17,17,0.18)] bg-[rgba(255,255,255,0.38)] px-3 py-1.5 text-[0.64rem] font-medium uppercase tracking-[0.2em] text-[rgba(17,17,17,0.68)] backdrop-blur-sm">
              New Collection
            </div>
            <div className="absolute bottom-8 left-1/2 z-10 -translate-x-1/2 rounded-full border border-[rgba(17,17,17,0.12)] bg-[rgba(255,255,255,0.38)] px-5 py-2 text-[0.62rem] uppercase tracking-[0.28em] text-[rgba(17,17,17,0.52)] backdrop-blur-sm">
              2026
            </div>
            <div className="absolute inset-x-0 bottom-0 top-16 z-0 flex items-end justify-center px-3 sm:px-8">
              <img
                src={HERO_IMAGE}
                alt="Premium editorial fashion look"
                className="h-[94%] w-full max-w-[430px] object-cover shadow-[0_28px_80px_rgba(17,17,17,0.14)]"
              />
            </div>
          </div>
        </div>
      </section>

      <section id="catalog" className="mt-10">
        <Suspense fallback={null}>
          <CatalogBrowser />
        </Suspense>
      </section>
    </div>
  );
}
