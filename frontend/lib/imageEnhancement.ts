function percentile(histogram: Uint32Array, total: number, ratio: number) {
  const target = total * ratio;
  let count = 0;
  for (let value = 0; value < histogram.length; value += 1) {
    count += histogram[value];
    if (count >= target) return value;
  }
  return 255;
}

function getLightingAdjustments(bitmap: ImageBitmap) {
  const analysisScale = Math.min(1, 640 / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * analysisScale));
  const height = Math.max(1, Math.round(bitmap.height * analysisScale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return { brightness: 0, contrast: 1 };
  context.drawImage(bitmap, 0, 0, width, height);
  const pixels = context.getImageData(0, 0, width, height).data;
  const histogram = new Uint32Array(256);
  let total = 0;
  for (let index = 0; index < pixels.length; index += 4) {
    if (pixels[index + 3] < 16) continue;
    const luminance = Math.round(
      pixels[index] * 0.2126 + pixels[index + 1] * 0.7152 + pixels[index + 2] * 0.0722
    );
    histogram[luminance] += 1;
    total += 1;
  }
  if (!total) return { brightness: 0, contrast: 1 };

  const low = percentile(histogram, total, 0.1);
  const mid = percentile(histogram, total, 0.5);
  const high = percentile(histogram, total, 0.9);
  const brightness =
    mid < 88 ? Math.min(12, (88 - mid) * 0.35) : mid > 178 ? -Math.min(12, (mid - 178) * 0.35) : 0;
  const contrast = high - low < 72 ? Math.min(1.12, 82 / Math.max(1, high - low)) : 1;
  return { brightness, contrast };
}

function applyLightingAdjustment(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  brightness: number,
  contrast: number
) {
  if (brightness === 0 && contrast === 1) return;
  const image = context.getImageData(0, 0, width, height);
  const pixels = image.data;
  const pivot = 128;
  for (let index = 0; index < pixels.length; index += 4) {
    for (let channel = 0; channel < 3; channel += 1) {
      pixels[index + channel] = Math.max(
        0,
        Math.min(255, (pixels[index + channel] - pivot) * contrast + pivot + brightness)
      );
    }
  }
  context.putImageData(image, 0, 0);
}

function applyMildSharpening(
  context: CanvasRenderingContext2D,
  width: number,
  height: number
) {
  if (width < 3 || height < 3) return;
  const image = context.getImageData(0, 0, width, height);
  const source = new Uint8ClampedArray(image.data);
  const strength = 0.12;
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const center = (y * width + x) * 4;
      const left = center - 4;
      const right = center + 4;
      const above = center - width * 4;
      const below = center + width * 4;
      for (let channel = 0; channel < 3; channel += 1) {
        const edge =
          source[center + channel] * 4 -
          source[left + channel] -
          source[right + channel] -
          source[above + channel] -
          source[below + channel];
        image.data[center + channel] = source[center + channel] + edge * strength;
      }
    }
  }
  context.putImageData(image, 0, 0);
}

export async function enhancePersonPhoto(file: File): Promise<File> {
  try {
    const bitmap = await createImageBitmap(file);
    try {
      const longestEdge = Math.max(bitmap.width, bitmap.height);
      const needsUpscale = longestEdge < 900;
      const { brightness, contrast } = getLightingAdjustments(bitmap);
      const needsLightingAdjustment = brightness !== 0 || contrast !== 1;
      if (!needsUpscale && !needsLightingAdjustment) return file;

      const scale = needsUpscale ? Math.min(1.35, 1200 / longestEdge) : 1;
      const width = Math.max(1, Math.round(bitmap.width * scale));
      const height = Math.max(1, Math.round(bitmap.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) return file;
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, width, height);
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = "high";
      context.drawImage(bitmap, 0, 0, width, height);
      if (needsUpscale) applyMildSharpening(context, width, height);
      applyLightingAdjustment(context, width, height, brightness, contrast);

      const mimeType = file.type === "image/png" ? "image/png" : "image/jpeg";
      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, mimeType, 0.94)
      );
      if (!blob) return file;
      const name = file.name.replace(/\.[^.]+$/, "");
      const extension = mimeType === "image/png" ? ".png" : ".jpg";
      return new File([blob], `${name}${extension}`, {
        type: mimeType,
        lastModified: file.lastModified,
      });
    } finally {
      bitmap.close();
    }
  } catch {
    return file;
  }
}