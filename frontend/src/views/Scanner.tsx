import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type RefObject, useEffect, useRef, useState } from "react";

import { api } from "../api";
import BinderBar from "../components/BinderBar";
import BurstPanel from "../components/BurstPanel";
import DeviceCamera, { deviceCameraSupported, type Facing } from "../components/DeviceCamera";
import ScanResult from "../components/ScanResult";
import { ChangeDetector, type DetectorState } from "../lib/changeDetector";
import { frameFromVideo, guideFraction, guideRegion, preparePhoto } from "../lib/photo";
import { unlockAudio } from "../lib/sounds";

const PREVIEW_INTERVAL_MS = 500;
const RETRY_INTERVAL_MS = 5000;
// Pestaña en segundo plano: no hace falta refrescar la vista previa.
const HIDDEN_INTERVAL_MS = 10000;
// Cada cuánto el modo ráfaga mira si ha cambiado la carta.
const DETECT_INTERVAL_MS = 150;

function CameraPreview({ imgRef }: { imgRef: RefObject<HTMLImageElement> }) {
  const [src, setSrc] = useState(api.previewUrl);
  const [failed, setFailed] = useState(false);
  const timer = useRef<number>();

  useEffect(() => () => window.clearTimeout(timer.current), []);

  // Un solo frame en vuelo: el siguiente se pide cuando el anterior termina.
  // Con setInterval, si el backend tardaba, las peticiones se acumulaban.
  const scheduleNext = (delay: number) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(
      () => setSrc(api.previewUrl()),
      document.hidden ? HIDDEN_INTERVAL_MS : delay,
    );
  };

  return (
    <div className="preview-wrap">
      <img
        ref={imgRef}
        className="preview"
        src={src}
        alt="Vista previa"
        hidden={failed}
        onLoad={() => {
          setFailed(false);
          scheduleNext(PREVIEW_INTERVAL_MS);
        }}
        onError={() => {
          setFailed(true);
          scheduleNext(RETRY_INTERVAL_MS);
        }}
      />
      {failed && (
        <div className="preview placeholder">
          Webcam del escáner no disponible (¿desconectada?). Reintentando… Prueba con la cámara de este dispositivo o
          sube una foto.
        </div>
      )}
    </div>
  );
}

type Source = "device" | "server";

const SOURCE_KEY = "scanner.source";
const LOCATION_KEY = "scanner.burstLocation";

// Por defecto: la cámara del propio dispositivo en móviles/tabletas (si el
// navegador la permite) y la webcam del escáner en el ordenador. Se recuerda
// la última elección.
function initialSource(): Source {
  try {
    const saved = localStorage.getItem(SOURCE_KEY);
    if (saved === "device" || saved === "server") return saved;
  } catch {
    /* localStorage no disponible */
  }
  const touch = window.matchMedia("(pointer: coarse)").matches;
  return touch && deviceCameraSupported() ? "device" : "server";
}

function UploadButton({ disabled, onPhoto }: { disabled: boolean; onPhoto: (file: File) => void }) {
  return (
    <label className={`button secondary${disabled ? " disabled" : ""}`}>
      Subir foto
      <input
        type="file"
        accept="image/*"
        hidden
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onPhoto(file);
          e.target.value = "";
        }}
      />
    </label>
  );
}

const DETECTOR_LABELS: Record<DetectorState, string> = {
  learning: "Aprendiendo el fondo: deja la zona vacía…",
  idle: "Esperando carta…",
  moving: "Movimiento: deja la carta quieta",
  settling: "Carta quieta…",
};

export default function Scanner() {
  const queryClient = useQueryClient();
  const [source, setSource] = useState<Source>(initialSource);
  const [facing, setFacing] = useState<Facing>("environment");
  const [scanId, setScanId] = useState<number | null>(null);
  const [phase, setPhase] = useState<"preparing" | "uploading" | null>(null);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const previewRef = useRef<HTMLImageElement>(null);
  const guideRef = useRef<HTMLDivElement>(null);

  // Modo ráfaga: sesión activa (o la última, para seguir viendo su resumen).
  const [burstId, setBurstId] = useState<number | null>(null);
  // Ubicación a la que van las cartas del modo ráfaga (null = "Sin ubicar").
  const locations = useQuery({ queryKey: ["locations"], queryFn: api.listLocations });
  const [burstLocation, setBurstLocation] = useState<number | null>(() => {
    try {
      return Number(localStorage.getItem(LOCATION_KEY)) || null;
    } catch {
      return null;
    }
  });
  const chooseLocation = (id: number | null) => {
    setBurstLocation(id);
    try {
      localStorage.setItem(LOCATION_KEY, id ? String(id) : "");
    } catch {
      /* sin persistencia */
    }
  };
  // Si la ubicación guardada ya no existe (se borró), vuelve a "Sin ubicar".
  const validLocation =
    burstLocation != null && locations.data?.some((l) => l.id === burstLocation && !l.is_default)
      ? burstLocation
      : null;
  const [burstActive, setBurstActive] = useState(false);
  // Sesión de archivador: página, casilla a capturar (null = página terminada) y huecos.
  const [binderActive, setBinderActive] = useState(false);
  const [binderPage, setBinderPage] = useState(1);
  const [binderSlot, setBinderSlot] = useState<number | null>(1);
  const [binderSkipped, setBinderSkipped] = useState<Set<number>>(() => new Set());
  const [detectorState, setDetectorState] = useState<DetectorState>("idle");
  const [sending, setSending] = useState(false);
  const detector = useRef<ChangeDetector | null>(null);
  const inFlight = useRef(false);
  const pendingFire = useRef<boolean | null>(null); // after_empty del disparo pendiente

  const chooseSource = (next: Source) => {
    setSource(next);
    detector.current?.reset();
    try {
      localStorage.setItem(SOURCE_KEY, next);
    } catch {
      /* sin persistencia */
    }
  };

  // file: foto subida (se prepara: reducción, orientación, JPEG).
  // frame: fotograma de la cámara del dispositivo (ya viene preparado).
  // ninguno: captura de la webcam del escáner en el servidor.
  const create = useMutation({
    mutationFn: async (input: { file?: File; frame?: File }) => {
      if (input.frame) {
        setPhase("uploading");
        return api.createScan(input.frame);
      }
      if (input.file) {
        setPhase("preparing");
        const photo = await preparePhoto(input.file);
        setPhase("uploading");
        return api.createScan(photo);
      }
      return api.createScan();
    },
    onSuccess: (scan) => {
      setScanId(scan.id);
      // Fuera del modo ráfaga: el resumen de la última sesión taparía el resultado.
      setBurstId(null);
    },
    onSettled: () => setPhase(null),
  });

  const scan = useQuery({
    queryKey: ["scan", scanId],
    queryFn: () => api.getScan(scanId!),
    enabled: scanId != null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "done" || status === "failed" ? false : 500;
    },
  });

  /** Envía el fotograma actual a la sesión de modo ráfaga (sin esperar a identificar). */
  const sendToSession = async (session: number, afterEmpty = true) => {
    if (inFlight.current) {
      pendingFire.current = afterEmpty; // se cambió de carta mientras se enviaba la anterior
      return;
    }
    inFlight.current = true;
    setSending(true);
    try {
      const thumb = detector.current?.snapshot() ?? null;
      let created;
      if (source === "device") {
        if (!videoRef.current) throw new Error("La cámara no está activa");
        created = await api.createScan(await frameFromVideo(videoRef.current), session, afterEmpty);
      } else {
        created = await api.createScan(undefined, session, afterEmpty);
      }
      setCaptureError(null);
      void queryClient.invalidateQueries({ queryKey: ["session", session] });
      if (thumb) void learnFromEmpty(created.id, thumb);
    } catch (err) {
      setCaptureError(err instanceof Error ? err.message : String(err));
    } finally {
      inFlight.current = false;
      setSending(false);
      if (pendingFire.current !== null) {
        const next = pendingFire.current;
        pendingFire.current = null;
        void sendToSession(session, next);
      }
    }
  };

  /** Si el servidor dice que esa captura no tenía carta, corrige el fondo del detector. */
  const learnFromEmpty = async (id: number, thumb: Float32Array) => {
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 300));
      const s = await api.getScan(id).catch(() => null);
      if (!s || s.status === "pending" || s.status === "processing") continue;
      if (s.status === "done" && !s.card_detected && (s.confidence ?? 0) < 0.55) {
        detector.current?.adoptBackground(thumb);
      }
      return;
    }
  };

  // Bucle del detector mientras la sesión está activa.
  useEffect(() => {
    if (!burstActive || burstId == null) return;
    detector.current ??= new ChangeDetector();
    const timer = window.setInterval(() => {
      const d = detector.current;
      const src = source === "device" ? videoRef.current : previewRef.current;
      if (!d || !src) return;
      const fire = d.feed(src, performance.now());
      setDetectorState(d.state);
      if (fire) void sendToSession(burstId, d.lastFireAfterEmpty);
    }, DETECT_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [burstActive, burstId, source]); // sendToSession solo depende de source y burstId

  const startBurst = async () => {
    unlockAudio(); // iOS: el sonido solo se activa tras un toque
    setCaptureError(null);
    try {
      const session = await api.createSession(validLocation);
      detector.current = new ChangeDetector(); // el primer fotograma será el fondo vacío
      setBurstId(session.id);
      setBurstActive(true);
    } catch (err) {
      setCaptureError(err instanceof Error ? err.message : String(err));
    }
  };

  const stopBurst = async () => {
    setBurstActive(false);
    if (burstId != null) {
      await api.endSession(burstId).catch(() => undefined);
      void queryClient.invalidateQueries({ queryKey: ["session", burstId] });
    }
  };

  const startBinder = async () => {
    unlockAudio();
    setCaptureError(null);
    try {
      const session = await api.createSession(validLocation, "binder");
      setBurstId(session.id);
      setBinderActive(true);
      setBinderSlot(1);
      setBinderSkipped(new Set());
    } catch (err) {
      setCaptureError(err instanceof Error ? err.message : String(err));
    }
  };

  const stopBinder = async () => {
    setBinderActive(false);
    if (burstId != null) {
      await api.endSession(burstId).catch(() => undefined);
      void queryClient.invalidateQueries({ queryKey: ["session", burstId] });
    }
  };

  const nextSlot = (from: number) => (from >= 9 ? null : from + 1);

  /** Captura la casilla actual del archivador y pasa a la siguiente (sin esperar a identificar). */
  const captureBinder = async () => {
    if (burstId == null || binderSlot == null || sending) return;
    const spot = { page: binderPage, slot: binderSlot };
    setSending(true);
    setCaptureError(null);
    try {
      if (source === "device") {
        if (!videoRef.current) throw new Error("La cámara no está activa");
        // Solo lo que está dentro del marco: las cartas vecinas del archivador no cuentan.
        const region = guideRef.current ? guideRegion(videoRef.current, guideRef.current) : null;
        await api.createScan(await frameFromVideo(videoRef.current, region), burstId, true, spot);
      } else {
        // Webcam del escáner: el servidor captura y recorta esta misma zona.
        const region = guideRef.current && previewRef.current ? guideFraction(previewRef.current, guideRef.current) : null;
        await api.createScan(undefined, burstId, true, spot, region);
      }
      setBinderSkipped((s) => {
        const next = new Set(s);
        next.delete(spot.slot);
        return next;
      });
      setBinderSlot(nextSlot(spot.slot));
      void queryClient.invalidateQueries({ queryKey: ["session", burstId] });
    } catch (err) {
      setCaptureError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  };

  const busy = create.isPending;
  const captureManual = async () => {
    setCaptureError(null);
    if (binderActive) {
      void captureBinder();
      return;
    }
    if (burstActive && burstId != null) {
      void sendToSession(burstId); // en sesión, la captura manual entra en la sesión
      return;
    }
    if (source === "server") {
      create.mutate({});
      return;
    }
    try {
      if (!videoRef.current) throw new Error("La cámara no está activa");
      create.mutate({ frame: await frameFromVideo(videoRef.current) });
    } catch (err) {
      create.reset();
      setCaptureError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="scanner">
      <section>
        <div className="source-switch" role="tablist" aria-label="Fuente de la cámara">
          <button
            role="tab"
            aria-selected={source === "device"}
            className={source === "device" ? "active" : ""}
            onClick={() => chooseSource("device")}
          >
            Cámara de este dispositivo
          </button>
          <button
            role="tab"
            aria-selected={source === "server"}
            className={source === "server" ? "active" : ""}
            onClick={() => chooseSource("server")}
          >
            Webcam del escáner
          </button>
        </div>

        <div className="camera-frame">
          {source === "device" ? (
            <DeviceCamera videoRef={videoRef} facing={facing} />
          ) : (
            <CameraPreview imgRef={previewRef} />
          )}
          {/* Guía con la proporción de una carta (63 × 88 mm) para encuadrarla. */}
          <div ref={guideRef} className="card-guide" aria-hidden="true" />
          {burstActive && (
            <div className={`burst-status ${sending ? "sending" : detectorState}`}>
              {sending ? "Enviando…" : DETECTOR_LABELS[detectorState]}
            </div>
          )}
        </div>

        {binderActive && burstId != null ? (
          <BinderBar
            sessionId={burstId}
            page={binderPage}
            slot={binderSlot}
            skipped={binderSkipped}
            sending={sending}
            onSelect={setBinderSlot}
            onCapture={() => void captureBinder()}
            onSkip={() => {
              if (binderSlot == null) return;
              setBinderSkipped((s) => new Set(s).add(binderSlot));
              setBinderSlot(nextSlot(binderSlot));
            }}
            onPage={(page) => {
              setBinderPage(Math.max(1, page));
              setBinderSlot(1);
              setBinderSkipped(new Set());
            }}
            onStop={() => void stopBinder()}
          />
        ) : (
        <div className="actions">
          {burstActive ? (
            <button className="stop" onClick={() => void stopBurst()}>
              ■ Terminar sesión
            </button>
          ) : (
            <>
              <button onClick={() => void startBurst()}>▶ Modo ráfaga</button>
              <button onClick={() => void startBinder()} title="Carta a carta por las casillas de cada página">
                ▦ Modo archivador
              </button>
              <label className="burst-location">
                <span>Guardar en</span>
                <select
                  value={validLocation ?? ""}
                  onChange={(e) => chooseLocation(e.target.value ? Number(e.target.value) : null)}
                >
                  {(locations.data ?? [{ id: 0, name: "Sin ubicar", is_default: true }]).map((l) =>
                    l.is_default ? (
                      <option key={l.id} value="">
                        {l.name}
                      </option>
                    ) : (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ),
                  )}
                </select>
              </label>
            </>
          )}
          <button className="secondary" onClick={() => void captureManual()} disabled={busy}>
            {burstActive ? "Capturar ahora" : "Capturar e identificar"}
          </button>
          {source === "device" && (
            <button
              className="secondary"
              onClick={() => setFacing((f) => (f === "environment" ? "user" : "environment"))}
              disabled={busy}
            >
              Cambiar cámara
            </button>
          )}
          {!burstActive && <UploadButton disabled={busy} onPhoto={(file) => create.mutate({ file })} />}
        </div>
        )}
        {burstActive && (
          <p className="muted small">
            Empieza con la zona vacía (el fondo se aprende en 1 s) y ve poniendo las cartas de una en una dentro del
            marco. Cada carta nueva se identifica sola cuando la dejas quieta.
          </p>
        )}
        {phase === "preparing" && <p className="muted">Preparando la foto…</p>}
        {phase === "uploading" && <p className="muted">Enviando la imagen…</p>}
        {captureError && <p className="error">{captureError}</p>}
        {create.isError && <p className="error">{create.error.message}</p>}
      </section>
      <section>
        {burstId != null ? (
          <>
            {!burstActive && !binderActive && (
              <p className="muted small">
                Sesión terminada. <button className="link" onClick={() => setBurstId(null)}>Cerrar resumen</button>
              </p>
            )}
            <BurstPanel sessionId={burstId} active={burstActive || binderActive} />
          </>
        ) : scan.data ? (
          <ScanResult key={scan.data.id} scan={scan.data} />
        ) : (
          <p className="muted">
            Coloca la carta dentro del marco y pulsa «Capturar e identificar», o usa el modo ráfaga para ir cambiando
            cartas sin tocar la pantalla.
          </p>
        )}
      </section>
    </div>
  );
}
