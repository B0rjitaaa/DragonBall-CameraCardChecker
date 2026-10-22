// Prepara una foto (sobre todo del móvil) antes de subirla al servidor:
// - la reduce a MAX_SIDE px en su lado mayor: una foto de móvil pesa 4–8 MB y
//   reducida ~300 KB, así que sube al instante por Wi-Fi;
// - aplica la orientación EXIF (si no, las fotos en vertical llegan giradas);
// - la recodifica a JPEG: los iPhone guardan en HEIC y OpenCV no sabe leerlo.
// Al identificar, el recorte de la carta se normaliza a 315×440 px, así que
// 1920 px sobran.

const MAX_SIDE = 1920;
const JPEG_QUALITY = 0.9;

async function decode(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if ("createImageBitmap" in window) {
    try {
      return await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch {
      /* algunos navegadores no aceptan la opción: probamos con <img> */
    }
  }
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode(); // <img> ya aplica la orientación EXIF en los navegadores actuales
    return img;
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function preparePhoto(file: File): Promise<File> {
  let image: ImageBitmap | HTMLImageElement;
  try {
    image = await decode(file);
  } catch {
    // El navegador no sabe decodificarla (p. ej. HEIC en Chrome de escritorio):
    // se sube tal cual y el servidor dirá si puede leerla.
    return file;
  }

  const width = image instanceof HTMLImageElement ? image.naturalWidth : image.width;
  const height = image instanceof HTMLImageElement ? image.naturalHeight : image.height;
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return file;
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
  if ("close" in image) image.close();

  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
  );
  if (!blob) return file;
  return new File([blob], "foto.jpg", { type: "image/jpeg" });
}

/** Zona de un fotograma, en píxeles del vídeo. */
export interface Region {
  x: number;
  y: number;
  width: number;
  height: number;
}

// Margen alrededor del marco guía: el detector necesita ver el borde de la
// carta aunque no llene el marco exactamente.
const GUIDE_MARGIN = 0.08;

/**
 * Zona de la imagen que queda dentro del marco guía (más un margen), en
 * píxeles de la imagen, teniendo en cuenta que se pinta con object-fit:
 * contain (bandas negras). Vale para el vídeo del dispositivo y para la
 * vista previa de la webcam del escáner.
 */
export function guideRegion(media: HTMLVideoElement | HTMLImageElement, guide: HTMLElement): Region | null {
  const vw = media instanceof HTMLVideoElement ? media.videoWidth : media.naturalWidth;
  const vh = media instanceof HTMLVideoElement ? media.videoHeight : media.naturalHeight;
  if (!vw || !vh) return null;
  const v = media.getBoundingClientRect();
  const g = guide.getBoundingClientRect();
  const scale = Math.min(v.width / vw, v.height / vh);
  if (!scale) return null;
  const offX = v.left + (v.width - vw * scale) / 2;
  const offY = v.top + (v.height - vh * scale) / 2;
  const mx = g.width * GUIDE_MARGIN;
  const my = g.height * GUIDE_MARGIN;
  const x0 = Math.max(0, (g.left - mx - offX) / scale);
  const y0 = Math.max(0, (g.top - my - offY) / scale);
  const x1 = Math.min(vw, (g.right + mx - offX) / scale);
  const y1 = Math.min(vh, (g.bottom + my - offY) / scale);
  if (x1 - x0 < 50 || y1 - y0 < 50) return null;
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

/** La zona del marco en fracciones 0-1 (para que el servidor recorte su propia captura). */
export function guideFraction(media: HTMLImageElement, guide: HTMLElement): { x: number; y: number; w: number; h: number } | null {
  const r = guideRegion(media, guide);
  if (!r) return null;
  const round = (n: number) => Math.round(n * 10000) / 10000;
  return {
    x: round(r.x / media.naturalWidth),
    y: round(r.y / media.naturalHeight),
    w: round(r.width / media.naturalWidth),
    h: round(r.height / media.naturalHeight),
  };
}

/** Captura el fotograma actual de un <video> (o solo `region`) como JPEG (lado mayor ≤ MAX_SIDE). */
export async function frameFromVideo(video: HTMLVideoElement, region?: Region | null): Promise<File> {
  if (!video.videoWidth || !video.videoHeight) throw new Error("La cámara todavía no da imagen");
  const r = region ?? { x: 0, y: 0, width: video.videoWidth, height: video.videoHeight };
  const scale = Math.min(1, MAX_SIDE / Math.max(r.width, r.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(r.width * scale);
  canvas.height = Math.round(r.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("No se pudo capturar la imagen");
  ctx.drawImage(video, r.x, r.y, r.width, r.height, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
  );
  if (!blob) throw new Error("No se pudo capturar la imagen");
  return new File([blob], "captura.jpg", { type: "image/jpeg" });
}
