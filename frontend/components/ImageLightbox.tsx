"use client";

import { useEffect, useState } from "react";

export default function ImageLightbox({
  src,
  alt,
  onClose,
}: {
  src: string;
  alt: string;
  onClose: () => void;
}) {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "+" || e.key === "=") setScale((s) => Math.min(s + 0.25, 3));
      if (e.key === "-") setScale((s) => Math.max(s - 0.25, 1));
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  async function handleDownload() {
    try {
      const res = await fetch(src);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "tryfit-result.jpg";
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      window.open(src, "_blank");
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex flex-col bg-ink/95">
      <div className="flex items-center justify-between px-5 py-4">
        <button
          onClick={onClose}
          className="rounded-full p-2 text-parchment/80 hover:bg-parchment/10 hover:text-parchment"
          aria-label="Close"
        >
          ✕
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setScale((s) => Math.max(s - 0.25, 1))}
            className="rounded-full bg-parchment/10 px-3 py-1.5 text-sm text-parchment hover:bg-parchment/20"
          >
            −
          </button>
          <span className="w-12 text-center text-sm text-parchment/70">
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={() => setScale((s) => Math.min(s + 0.25, 3))}
            className="rounded-full bg-parchment/10 px-3 py-1.5 text-sm text-parchment hover:bg-parchment/20"
          >
            +
          </button>
          <button
            onClick={handleDownload}
            className="ml-2 rounded-full bg-gold px-4 py-1.5 text-sm font-semibold text-emerald-deep hover:brightness-105"
          >
            ⬇ Download
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="flex min-h-full items-center justify-center p-6">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={alt}
            style={{ transform: `scale(${scale})`, transition: "transform 0.15s ease" }}
            className="max-h-[80vh] max-w-full object-contain"
          />
        </div>
      </div>
    </div>
  );
}