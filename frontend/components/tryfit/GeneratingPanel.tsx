"use client";

export default function GeneratingPanel({
  expected,
  progress,
}: {
  expected: number;
  progress: number;
}) {
  const slots = Math.max(expected, 3);
  return (
    <div>
      <h1 className="tryfit-pulse font-display text-3xl text-ink">
        Creating your Try Fit
      </h1>
      <p className="mt-2 text-sm text-ink/55">
        Applying this look to your photos… this can take up to a minute.
      </p>

      <div className="mt-6 h-1.5 w-full overflow-hidden rounded-full bg-ink/10">
        <div
          className="h-full rounded-full bg-gradient-to-r from-gold-muted to-gold transition-all duration-700"
          style={{ width: `${Math.max(progress, 6)}%` }}
        />
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
        {Array.from({ length: slots }).map((_, i) => (
          <div
            key={i}
            className="tryfit-shimmer aspect-[3/4] rounded-lg border border-ink/10"
          />
        ))}
      </div>

      <p className="mt-5 text-xs text-ink/40" role="status" aria-live="polite">
        Generating {expected} personalized {expected === 1 ? "look" : "looks"}…
      </p>
    </div>
  );
}
