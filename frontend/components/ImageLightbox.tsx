"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { downloadImage, prefersReducedMotion } from "@/lib/tryfit";

const MIN_ZOOM = 1;
const MAX_ZOOM = 4;

export default function ImageLightbox({
  src,
  alt,
  filename,
  onClose,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: {
  src: string;
  alt: string;
  filename?: string;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const dragRef = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  const clampZoom = useCallback((value: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value)), []);

  const clampPan = useCallback(
    (x: number, y: number, scale: number) => {
      const maxX = (scale - 1) * 140;
      const maxY = (scale - 1) * 160;
      return {
        x: Math.min(maxX, Math.max(-maxX, x)),
        y: Math.min(maxY, Math.max(-maxY, y)),
      };
    },
    []
  );

  const updateZoom = useCallback(
    (nextScale: number) => {
      const clamped = clampZoom(nextScale);
      setZoom(clamped);
      setPan((current) => clampPan(current.x, current.y, clamped));
    },
    [clampPan, clampZoom]
  );

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && hasPrev) onPrev?.();
      if (e.key === "ArrowRight" && hasNext) onNext?.();
      if (e.key === "+" || e.key === "=") updateZoom(zoom + 0.5);
      if (e.key === "-") updateZoom(zoom - 0.5);
      if (e.key === "0") {
        setZoom(1);
        setPan({ x: 0, y: 0 });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [hasNext, hasPrev, onClose, onNext, onPrev, updateZoom, zoom]);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(
        overlayRef.current,
        { autoAlpha: 0 },
        { autoAlpha: 1, duration: 0.25, ease: "power2.out" }
      );
      gsap.fromTo(
        imageRef.current,
        { autoAlpha: 0, scale: 0.97 },
        { autoAlpha: 1, scale: 1, duration: 0.35, ease: "power2.out" }
      );
    });
    return () => ctx.revert();
  }, [src]);

  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, [src]);

  const handleDownload = useCallback(() => {
    downloadImage(src, filename || "tryfit-look.png");
  }, [src, filename]);

  const handleWheel = useCallback(
    (event: React.WheelEvent<HTMLDivElement>) => {
      event.preventDefault();
      const delta = event.deltaY > 0 ? -0.25 : 0.25;
      updateZoom(zoom + delta);
    },
    [updateZoom, zoom]
  );

  const handlePointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (zoom <= 1) return;
    dragRef.current = {
      x: event.clientX,
      y: event.clientY,
      startX: pan.x,
      startY: pan.y,
    };
  }, [pan.x, pan.y, zoom]);

  const handlePointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    const dx = event.clientX - dragRef.current.x;
    const dy = event.clientY - dragRef.current.y;
    const next = clampPan(dragRef.current.startX + dx, dragRef.current.startY + dy, zoom);
    setPan(next);
  }, [clampPan, zoom]);

  const handlePointerUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[60] flex flex-col bg-[rgba(13,14,14,0.93)]"
      role="dialog"
      aria-modal="true"
      aria-label="Try Fit result viewer"
    >
      <div className="flex items-center justify-between px-4 py-3 sm:px-5">
        <button
          onClick={onClose}
          className="rounded-full border border-parchment/20 px-3 py-2 text-sm font-medium text-parchment/80 transition hover:bg-parchment/10 hover:text-parchment"
          aria-label="Close"
        >
          Close
        </button>
        <button
          onClick={handleDownload}
          className="rounded-full bg-gold px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-deep transition hover:brightness-105"
        >
          Download
        </button>
      </div>

      <div className="relative flex flex-1 items-center justify-center overflow-hidden px-3 py-4 sm:px-6">
        {hasPrev && (
          <button
            onClick={onPrev}
            aria-label="Previous look"
            className="absolute left-4 top-1/2 z-20 hidden -translate-y-1/2 rounded-full border border-parchment/20 bg-[rgba(255,255,255,0.04)] p-3 text-xl text-parchment transition hover:bg-[rgba(255,255,255,0.1)] sm:block"
          >
            ‹
          </button>
        )}
        {hasNext && (
          <button
            onClick={onNext}
            aria-label="Next look"
            className="absolute right-4 top-1/2 z-20 hidden -translate-y-1/2 rounded-full border border-parchment/20 bg-[rgba(255,255,255,0.04)] p-3 text-xl text-parchment transition hover:bg-[rgba(255,255,255,0.1)] sm:block"
          >
            ›
          </button>
        )}

        <div
          className="relative flex h-full w-full items-center justify-center overflow-hidden rounded-[18px]"
          onWheel={handleWheel}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
        >
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.08),transparent_58%)]" />
          <div className="relative flex h-full w-full items-center justify-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              ref={imageRef}
              src={src}
              alt={alt}
              className="max-h-[80vh] max-w-[calc(100vw-2.25rem)] rounded-[10px] object-contain shadow-[0_18px_60px_rgba(0,0,0,0.35)]"
              style={{
                transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                transition: prefersReducedMotion() ? "none" : "transform 180ms ease-out",
                transformOrigin: "center center",
                cursor: zoom > 1 ? "grab" : "default",
              }}
            />
          </div>
        </div>
      </div>

      <div className="pointer-events-none fixed inset-x-0 bottom-3 z-30 flex justify-center px-3">
        <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-parchment/20 bg-[rgba(20,20,20,0.72)] px-2 py-2 shadow-lg backdrop-blur-sm sm:gap-3">
          {hasPrev && (
            <button onClick={onPrev} className="rounded-full border border-parchment/20 px-3 py-2 text-xs font-medium text-parchment/80 hover:bg-parchment/10">
              Prev
            </button>
          )}
          <button onClick={() => updateZoom(zoom - 0.5)} className="rounded-full border border-parchment/20 px-3 py-2 text-lg leading-none text-parchment/80 hover:bg-parchment/10">
            −
          </button>
          <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} className="rounded-full border border-parchment/20 px-3 py-2 text-[0.7rem] font-medium uppercase tracking-[0.14em] text-parchment/80 hover:bg-parchment/10">
            {Math.round(zoom * 100)}%
          </button>
          <button onClick={() => updateZoom(zoom + 0.5)} className="rounded-full border border-parchment/20 px-3 py-2 text-lg leading-none text-parchment/80 hover:bg-parchment/10">
            +
          </button>
          {hasNext && (
            <button onClick={onNext} className="rounded-full border border-parchment/20 px-3 py-2 text-xs font-medium text-parchment/80 hover:bg-parchment/10">
              Next
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
