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

/** Captura el fotograma actual de un <video> como JPEG (lado mayor ≤ MAX_SIDE). */
export async function frameFromVideo(video: HTMLVideoElement): Promise<File> {
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (!width || !height) throw new Error("La cámara todavía no da imagen");
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("No se pudo capturar la imagen");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
  );
  if (!blob) throw new Error("No se pudo capturar la imagen");
  return new File([blob], "captura.jpg", { type: "image/jpeg" });
}
