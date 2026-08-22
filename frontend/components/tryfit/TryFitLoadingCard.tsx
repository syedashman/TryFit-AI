"use client";

export default function TryFitLoadingCard({
  index,
}: {
  index: number;
}) {
  return (
    <div
      className="group"
      role="status"
      aria-live="polite"
      aria-label={`Creating look ${index + 1}`}
    >
      <div className="tryfit-loading-card relative flex aspect-[3/4] flex-col items-center justify-center overflow-hidden rounded-lg border border-[var(--tryfit-line)] p-5 text-center">
        <div className="tryfit-loading-glow absolute inset-0" aria-hidden="true" />
        <div className="tryfit-sparkle relative mb-5 flex h-14 w-14 items-center justify-center" aria-hidden="true">
          <span className="absolute h-9 w-9 rotate-45 border border-[var(--tryfit-gold)]" />
          <span className="absolute h-3 w-3 -translate-x-4 -translate-y-4 rotate-45 bg-[var(--tryfit-gold)]" />
          <span className="absolute h-2 w-2 translate-x-5 translate-y-4 rotate-45 bg-[var(--tryfit-gold-soft)]" />
          <span className="relative h-2 w-2 rounded-full bg-white shadow-[0_0_12px_rgba(200,176,141,0.55)]" />
        </div>
        <p className="relative font-display text-xl tracking-[-0.03em] text-[var(--tryfit-ink)] sm:text-2xl">
          Creating your look…
        </p>
        <p className="relative mt-2 max-w-[13rem] text-[0.68rem] uppercase tracking-[0.14em] text-[var(--tryfit-muted)]">
          Applying this piece to your photo
        </p>
      </div>
      <div className="mt-2 text-xs uppercase tracking-[0.14em] text-ink/40">
        Look {index + 1}
      </div>
    </div>
  );
}
