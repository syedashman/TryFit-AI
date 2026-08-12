"use client";

import { useEffect } from "react";
import TryOnStudio from "./TryOnStudio";

export default function TryOnDrawer({
  open,
  onClose,
  category,
  productNumber,
  colorName,
}: {
  open: boolean;
  onClose: () => void;
  category: string;
  productNumber: string;
  colorName: string;
}) {
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      <button
        aria-label="Close try fit panel"
        onClick={onClose}
        className="absolute inset-0 bg-transparent"
      />
      <div className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-parchment shadow-2xl drawer-slide-in">
        <div className="flex items-center justify-between border-b border-gold/20 px-5 py-4">
          <span className="font-display text-lg text-emerald-deep">
            ✨ Try Fit
          </span>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-1.5 text-ink/50 hover:bg-ink/5 hover:text-ink"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-6">
          <TryOnStudio
            category={category}
            productNumber={productNumber}
            colorName={colorName}
          />
        </div>
      </div>
    </div>
  );
}
