"use client";

import { useEffect, useState } from "react";

const PROGRESS_MESSAGES = [
  "Preparing your photo…",
  "Building your look…",
  "Adjusting the fit…",
  "Finishing your image…",
];

export default function TryFitLoadingCard({
  index,
}: {
  index: number;
}) {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setMessageIndex((index) => (index + 1) % PROGRESS_MESSAGES.length);
    }, 2200);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div>
      <div
        className="flex aspect-square flex-col items-center justify-center gap-3 border border-[var(--tryfit-line)] bg-[var(--tryfit-card)]"
        role="status"
        aria-live="polite"
        aria-label={`Creating look ${index + 1}`}
      >
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--tryfit-line)] border-t-[var(--tryfit-olive)]" />
        <p className="text-sm text-[var(--tryfit-muted)]">
          {PROGRESS_MESSAGES[messageIndex]}
        </p>
      </div>
      <div className="mt-3 text-xs text-[var(--tryfit-muted)]">
        Look {index + 1}
      </div>
    </div>
  );
}
