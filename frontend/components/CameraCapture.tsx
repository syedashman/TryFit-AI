"use client";

import { useEffect, useRef, useState } from "react";

export default function CameraCapture({
  onCapture,
  onClose,
}: {
  onCapture: (file: File) => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user" }, audio: false })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      })
      .catch(() => setError("Could not access your camera. Check browser permissions."));

    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  function capture() {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (blob) {
        onCapture(new File([blob], `capture-${Date.now()}.jpg`, { type: "image/jpeg" }));
      }
    }, "image/jpeg", 0.92);
  }

  return (
    <div className="rounded-md border border-ink/10 bg-ink/90 p-3">
      {error ? (
        <p className="p-4 text-center text-sm text-parchment">{error}</p>
      ) : (
        <div className="relative overflow-hidden rounded" style={{ transform: "scaleX(-1)" }}>
          <video ref={videoRef} autoPlay playsInline muted className="w-full rounded" />
        </div>
      )}
      <div className="mt-3 flex gap-2">
        <button
          onClick={capture}
          disabled={!!error}
          className="flex-1 rounded-md bg-gold px-4 py-2 text-sm font-semibold text-emerald-deep disabled:opacity-40"
        >
          📸 Capture
        </button>
        <button
          onClick={onClose}
          className="rounded-md border border-parchment/30 px-4 py-2 text-sm text-parchment"
        >
          Done
        </button>
      </div>
    </div>
  );
}
