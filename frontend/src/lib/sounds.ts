// Avisos sonoros del modo ráfaga, para no tener que mirar la pantalla.
// iOS solo deja reproducir sonido tras un toque del usuario: unlockAudio() se
// llama desde el botón "Empezar sesión".

type AudioContextCtor = typeof AudioContext;

let ctx: AudioContext | null = null;

export function unlockAudio() {
  try {
    const Ctor: AudioContextCtor | undefined =
      window.AudioContext ?? (window as unknown as { webkitAudioContext?: AudioContextCtor }).webkitAudioContext;
    if (!Ctor) return;
    ctx ??= new Ctor();
    void ctx.resume();
  } catch {
    ctx = null;
  }
}

function tone(freq: number, start: number, duration: number) {
  if (!ctx) return;
  const t0 = ctx.currentTime + start;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0.0001, t0);
  gain.gain.exponentialRampToValueAtTime(0.25, t0 + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
  osc.connect(gain).connect(ctx.destination);
  osc.start(t0);
  osc.stop(t0 + duration + 0.02);
}

export const sounds = {
  /** Carta añadida a la colección: dos tonos ascendentes. */
  added() {
    tone(880, 0, 0.12);
    tone(1320, 0.13, 0.16);
  },
  /** Carta por revisar: un tono grave. */
  review() {
    tone(330, 0, 0.3);
  },
  /** Error al identificar. */
  error() {
    tone(220, 0, 0.18);
    tone(180, 0.2, 0.25);
  },
};
