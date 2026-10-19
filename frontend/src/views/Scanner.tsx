import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { frameFromVideo, preparePhoto } from "../lib/photo";
import DeviceCamera, { deviceCameraSupported, type Facing } from "../components/DeviceCamera";
import ScanResult from "../components/ScanResult";

const PREVIEW_INTERVAL_MS = 500;
const RETRY_INTERVAL_MS = 5000;
// Pestaña en segundo plano: no hace falta refrescar la vista previa.
const HIDDEN_INTERVAL_MS = 10000;

function CameraPreview() {
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
          Webcam del escáner no disponible (¿desconectada?). Reintentando… Prueba con la cámara de este dispositivo o sube una foto.
        </div>
      )}
    </div>
  );
}

type Source = "device" | "server";

const SOURCE_KEY = "scanner.source";

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

export default function Scanner() {
  const [source, setSource] = useState<Source>(initialSource);
  const [facing, setFacing] = useState<Facing>("environment");
  const [scanId, setScanId] = useState<number | null>(null);
  const [phase, setPhase] = useState<"preparing" | "uploading" | null>(null);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const chooseSource = (next: Source) => {
    setSource(next);
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
    onSuccess: (scan) => setScanId(scan.id),
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

  const busy = create.isPending;
  const capture = async () => {
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
          {source === "device" ? <DeviceCamera videoRef={videoRef} facing={facing} /> : <CameraPreview />}
          {/* Guía con la proporción de una carta (63 × 88 mm) para encuadrarla. */}
          <div className="card-guide" aria-hidden="true" />
        </div>

        <div className="actions">
          <button
            onClick={() => {
              setCaptureError(null);
              void capture();
            }}
            disabled={busy}
          >
            Capturar e identificar
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
          <UploadButton disabled={busy} onPhoto={(file) => create.mutate({ file })} />
        </div>
        {phase === "preparing" && <p className="muted">Preparando la foto…</p>}
        {phase === "uploading" && <p className="muted">Enviando la imagen…</p>}
        {captureError && <p className="error">{captureError}</p>}
        {create.isError && <p className="error">{create.error.message}</p>}
      </section>
      <section>
        {scan.data ? (
          <ScanResult key={scan.data.id} scan={scan.data} />
        ) : (
          <p className="muted">Coloca la carta dentro del marco y pulsa «Capturar e identificar».</p>
        )}
      </section>
    </div>
  );
}
