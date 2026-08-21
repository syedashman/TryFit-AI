"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { gsap } from "gsap";
import { downloadImage, prefersReducedMotion } from "@/lib/tryfit";

const MIN_ZOOM = 1;
const MAX_ZOOM = 4;

type FitSize = {
  width: number;
  height: number;
};

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
  const stageRef = useRef<HTMLDivElement>(null);
  const entranceRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const dragRef = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [fitSize, setFitSize] = useState<FitSize>({ width: 0, height: 0 });

  const clampZoom = useCallback((value: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value)), []);

  const clampPan = useCallback(
    (x: number, y: number, scale: number, baseWidth: number, baseHeight: number) => {
      if (scale <= 1) return { x: 0, y: 0 };

      const maxX = ((baseWidth * scale) - baseWidth) / 2;
      const maxY = ((baseHeight * scale) - baseHeight) / 2;

      return {
        x: Math.min(maxX, Math.max(-maxX, x)),
        y: Math.min(maxY, Math.max(-maxY, y)),
      };
    },
    []
  );

  const resetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  const measureFit = useCallback(() => {
    const stageEl = stageRef.current;
    const imgEl = imageRef.current;

    if (!stageEl || !imgEl) return;

    const stageRect = stageEl.getBoundingClientRect();
    const naturalWidth = imgEl.naturalWidth || imgEl.width || 1;
    const naturalHeight = imgEl.naturalHeight || imgEl.height || 1;
    const stageWidth = Math.max(1, stageRect.width);
    const stageHeight = Math.max(1, stageRect.height);
    const fitScale = Math.min(stageWidth / naturalWidth, stageHeight / naturalHeight, 1);
    const width = Math.max(1, naturalWidth * fitScale);
    const height = Math.max(1, naturalHeight * fitScale);

    setFitSize({ width, height });

    if (process.env.NODE_ENV === "development") {
      console.log({
        naturalWidth,
        naturalHeight,
        stageWidth,
        stageHeight,
        fitScale,
        width,
        height,
      });
    }
  }, []);

  const updateZoom = useCallback(
    (nextScale: number) => {
      const clamped = clampZoom(nextScale);
      setZoom(clamped);
      setPan((current) => clampPan(current.x, current.y, clamped, fitSize.width, fitSize.height));
    },
    [clampPan, clampZoom, fitSize.height, fitSize.width]
  );

  useLayoutEffect(() => {
    measureFit();
  }, [measureFit, src]);

  useEffect(() => {
    const handleResize = () => measureFit();
    window.addEventListener("resize", handleResize);
    window.addEventListener("orientationchange", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("orientationchange", handleResize);
    };
  }, [measureFit]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && hasPrev) onPrev?.();
      if (e.key === "ArrowRight" && hasNext) onNext?.();
      if (e.key === "+" || e.key === "=") updateZoom(zoom + 0.5);
      if (e.key === "-") updateZoom(zoom - 0.5);
      if (e.key === "0" || e.key.toLowerCase() === "f") {
        resetView();
      }
    }

    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [hasNext, hasPrev, onClose, onNext, onPrev, resetView, updateZoom, zoom]);

  useEffect(() => {
    if (prefersReducedMotion()) return;

    const ctx = gsap.context(() => {
      gsap.fromTo(
        entranceRef.current,
        { autoAlpha: 0, scale: 0.98 },
        { autoAlpha: 1, scale: 1, duration: 0.25, ease: "power2.out", clearProps: "transform,opacity" }
      );
    });

    return () => ctx.revert();
  }, [src]);

  useEffect(() => {
    resetView();
  }, [resetView, src]);

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

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (zoom <= 1) return;
      dragRef.current = {
        x: event.clientX,
        y: event.clientY,
        startX: pan.x,
        startY: pan.y,
      };
    },
    [pan.x, pan.y, zoom]
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!dragRef.current) return;

      const dx = event.clientX - dragRef.current.x;
      const dy = event.clientY - dragRef.current.y;
      const next = clampPan(dragRef.current.startX + dx, dragRef.current.startY + dy, zoom, fitSize.width, fitSize.height);
      setPan(next);
    },
    [clampPan, fitSize.height, fitSize.width, zoom]
  );

  const handlePointerUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[100] h-[100dvh] w-[100vw] overflow-hidden bg-[rgba(13,14,14,0.93)]"
      role="dialog"
      aria-modal="true"
      aria-label="Try Fit result viewer"
      style={{
        display: "grid",
        gridTemplateRows: "auto minmax(0, 1fr) auto",
      }}
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

      <div
        ref={stageRef}
        className="min-h-0 min-w-0 overflow-hidden p-3 sm:p-6"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
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

        <div className="flex h-full w-full min-h-0 min-w-0 items-center justify-center overflow-hidden rounded-[18px]">
          <div
            ref={entranceRef}
            className="flex h-full w-full items-center justify-center overflow-hidden"
            style={{
              width: "100%",
              height: "100%",
            }}
          >
            <div
              className="flex items-center justify-center"
              style={{
                width: fitSize.width || "auto",
                height: fitSize.height || "auto",
                maxWidth: "100%",
                maxHeight: "100%",
                cursor: zoom > 1 ? "grab" : "default",
              }}
            >
              <div
                style={{
                  width: fitSize.width || "auto",
                  height: fitSize.height || "auto",
                  transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                  transformOrigin: "center center",
                  willChange: "transform",
                  transition: prefersReducedMotion() ? "none" : "transform 180ms ease-out",
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  ref={imageRef}
                  src={src}
                  alt={alt}
                  className="block rounded-[10px] shadow-[0_18px_60px_rgba(0,0,0,0.35)]"
                  style={{
                    display: "block",
                    width: fitSize.width || "auto",
                    height: fitSize.height || "auto",
                    maxWidth: "100%",
                    maxHeight: "100%",
                    objectFit: "contain",
                    objectPosition: "center center",
                  }}
                  onLoad={measureFit}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="pointer-events-none px-3 pb-3 pt-2 sm:px-4">
        <div className="pointer-events-auto mx-auto flex w-fit items-center gap-2 rounded-full border border-parchment/20 bg-[rgba(20,20,20,0.72)] px-2 py-2 shadow-lg backdrop-blur-sm sm:gap-3">
          {hasPrev && (
            <button onClick={onPrev} className="rounded-full border border-parchment/20 px-3 py-2 text-xs font-medium text-parchment/80 hover:bg-parchment/10">
              Prev
            </button>
          )}
          <button
            onClick={() => updateZoom(zoom - 0.5)}
            className="rounded-full border border-parchment/20 px-3 py-2 text-lg leading-none text-parchment/80 hover:bg-parchment/10"
            aria-label="Zoom out"
          >
            −
          </button>
          <button
            onClick={resetView}
            className="rounded-full border border-parchment/20 px-3 py-2 text-[0.7rem] font-medium uppercase tracking-[0.14em] text-parchment/80 hover:bg-parchment/10"
            aria-label="Reset to fit"
          >
            Fit
          </button>
          <button
            onClick={() => updateZoom(zoom + 0.5)}
            className="rounded-full border border-parchment/20 px-3 py-2 text-lg leading-none text-parchment/80 hover:bg-parchment/10"
            aria-label="Zoom in"
          >
            +
          </button>
          {hasNext && (
            <button onClick={onNext} className="rounded-full border border-parchment/20 px-3 py-2 text-xs font-medium text-parchment/80 hover:bg-parchment/10">
              Next
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
