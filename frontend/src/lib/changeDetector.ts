// Detector de "carta nueva" para el modo ráfaga, en el navegador.
//
// Cada fotograma se reduce a una miniatura en escala de grises de 64×48 px y se
// compara con el anterior (diferencia media por píxel, 0–255):
//   1. Movimiento por encima de `motion` → hay una mano cambiando la carta.
//   2. Después, imagen quieta (diferencia < `still`) durante `stableMs`.
//   3. Si esa imagen quieta es distinta de la última capturada (`change`) y
//      distinta del fondo vacío del inicio (`present`) → hay una carta nueva:
//      se dispara la captura.
// Si la imagen quieta vuelve a parecerse al fondo, es que se retiró la carta:
// no dispara, pero la siguiente carta (aunque sea la misma) volverá a contar.
//
// Fondo vacío: se aprende tras reset() cuando la imagen lleva `backgroundMs`
// quieta (no del primer fotograma: al pulsar "Empezar" en el móvil, el
// soporte se mueve o sale la mano y el fondo quedaba mal, con lo que cada vez
// que se retiraba una carta se disparaba sobre la zona vacía). Si aun así se
// dispara en vacío, el servidor lo detecta y adoptBackground() corrige el
// fondo con ese fotograma.
// Si la sesión empieza con una carta puesta, esa primera carta no se captura
// sola (se puede capturar a mano); las siguientes sí.

const W = 64;
const H = 48;

export interface DetectorOptions {
  motion: number;
  still: number;
  stableMs: number;
  change: number;
  present: number;
  backgroundMs: number;
}

export const DEFAULT_DETECTOR_OPTIONS: DetectorOptions = {
  motion: 10,
  still: 4,
  stableMs: 700,
  change: 10,
  present: 10,
  backgroundMs: 1000,
};

export type DetectorState = "learning" | "idle" | "moving" | "settling";

type Source = HTMLVideoElement | HTMLImageElement;

function meanDiff(a: Float32Array, b: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += Math.abs(a[i] - b[i]);
  return sum / a.length;
}

export class ChangeDetector {
  state: DetectorState = "learning";
  /** Últimas lecturas, útiles para ajustar los umbrales con datos reales. */
  last = { motion: 0, fromBackground: 0, fromCaptured: 0 };

  private readonly ctx: CanvasRenderingContext2D | null;
  private prev: Float32Array | null = null;
  private background: Float32Array | null = null;
  private lastCaptured: Float32Array | null = null;
  private stillSince = 0;

  constructor(private readonly opts: DetectorOptions = DEFAULT_DETECTOR_OPTIONS) {
    const canvas = document.createElement("canvas");
    canvas.width = W;
    canvas.height = H;
    this.ctx = canvas.getContext("2d", { willReadFrequently: true });
  }

  /** Empieza de cero: el siguiente fotograma se toma como fondo vacío. */
  reset() {
    this.prev = this.background = this.lastCaptured = null;
    this.stillSince = 0;
    this.state = "learning";
  }

  /** Miniatura del último fotograma que disparó una captura. */
  snapshot(): Float32Array | null {
    return this.lastCaptured;
  }

  /** El servidor dijo que esa captura no tenía carta: es el fondo vacío real. */
  adoptBackground(thumb: Float32Array) {
    this.background = thumb;
  }

  /** Procesa un fotograma. Devuelve true si hay que capturar una carta nueva. */
  feed(src: Source, now: number): boolean {
    const cur = this.luma(src);
    if (!cur) return false;
    if (!this.prev) {
      this.prev = cur;
      return false;
    }
    const motion = meanDiff(cur, this.prev);
    this.prev = cur;
    this.last.motion = motion;

    if (!this.background || !this.lastCaptured) {
      // Aprendiendo el fondo: esperar a que la imagen esté quieta un rato.
      if (motion > this.opts.still) {
        this.stillSince = 0;
      } else if (!this.stillSince) {
        this.stillSince = now;
      } else if (now - this.stillSince >= this.opts.backgroundMs) {
        this.background = this.lastCaptured = cur;
        this.stillSince = 0;
        this.state = "idle";
      }
      return false;
    }
    if (motion > this.opts.motion) {
      this.state = "moving";
      this.stillSince = 0;
      return false;
    }
    if (this.state === "idle") return false;
    if (motion > this.opts.still) {
      this.stillSince = 0;
      return false;
    }
    if (!this.stillSince) {
      this.stillSince = now;
      this.state = "settling";
    }
    if (now - this.stillSince < this.opts.stableMs) return false;

    // Imagen quieta tras un movimiento: ¿hay una carta nueva?
    this.state = "idle";
    this.stillSince = 0;
    this.last.fromCaptured = meanDiff(cur, this.lastCaptured);
    this.last.fromBackground = meanDiff(cur, this.background);
    if (this.last.fromCaptured <= this.opts.change) return false; // lo mismo que antes
    this.lastCaptured = cur;
    return this.last.fromBackground > this.opts.present; // si no, se retiró la carta
  }

  private luma(src: Source): Float32Array | null {
    const ready = src instanceof HTMLVideoElement ? src.videoWidth > 0 : src.complete && src.naturalWidth > 0;
    if (!ready || !this.ctx) return null;
    this.ctx.drawImage(src, 0, 0, W, H);
    const px = this.ctx.getImageData(0, 0, W, H).data;
    const out = new Float32Array(W * H);
    for (let i = 0, j = 0; i < out.length; i++, j += 4) {
      out[i] = 0.299 * px[j] + 0.587 * px[j + 1] + 0.114 * px[j + 2];
    }
    return out;
  }
}
