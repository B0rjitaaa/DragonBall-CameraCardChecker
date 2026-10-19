import { useMutation, useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { preparePhoto } from "../lib/photo";
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
          Cámara no disponible (¿webcam desconectada?). Reintentando… Mientras tanto puedes subir una foto.
        </div>
      )}
    </div>
  );
}

// Móvil o tableta: pantalla táctil como puntero principal.
const isTouchDevice = window.matchMedia("(pointer: coarse)").matches;

function PhotoButton({
  label,
  useCamera,
  primary,
  disabled,
  onPhoto,
}: {
  label: string;
  useCamera: boolean;
  primary?: boolean;
  disabled: boolean;
  onPhoto: (file: File) => void;
}) {
  return (
    <label className={`button${primary ? "" : " secondary"}${disabled ? " disabled" : ""}`}>
      {label}
      <input
        type="file"
        accept="image/*"
        // capture abre directamente la cámara trasera en el móvil; en el
        // ordenador se ignora y funciona como una subida normal.
        capture={useCamera ? "environment" : undefined}
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
  const [scanId, setScanId] = useState<number | null>(null);
  const [phase, setPhase] = useState<"preparing" | "uploading" | null>(null);

  const create = useMutation({
    mutationFn: async (file?: File) => {
      if (!file) return api.createScan();
      setPhase("preparing");
      const photo = await preparePhoto(file);
      setPhase("uploading");
      return api.createScan(photo);
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
  const uploadPhoto = (file: File) => create.mutate(file);
  const captureWebcam = (
    <button className={isTouchDevice ? "secondary" : ""} onClick={() => create.mutate(undefined)} disabled={busy}>
      {isTouchDevice ? "Capturar con la webcam" : "Capturar e identificar"}
    </button>
  );

  return (
    <div className="scanner">
      <section>
        {isTouchDevice ? (
          <>
            <div className="actions">
              <PhotoButton label="📷 Hacer foto" useCamera primary disabled={busy} onPhoto={uploadPhoto} />
              <PhotoButton label="Elegir de la galería" useCamera={false} disabled={busy} onPhoto={uploadPhoto} />
            </div>
            {/* Plegada por defecto: solo se piden frames a la webcam si se abre. */}
            <WebcamSection>{captureWebcam}</WebcamSection>
          </>
        ) : (
          <>
            <CameraPreview />
            <div className="actions">
              {captureWebcam}
              <PhotoButton label="Subir foto" useCamera={false} disabled={busy} onPhoto={uploadPhoto} />
            </div>
          </>
        )}
        {phase === "preparing" && <p className="muted">Preparando la foto…</p>}
        {phase === "uploading" && <p className="muted">Subiendo la foto…</p>}
        {create.isError && <p className="error">{create.error.message}</p>}
      </section>
      <section>
        {scan.data ? (
          <ScanResult key={scan.data.id} scan={scan.data} />
        ) : (
          <p className="muted">
            {isTouchDevice
              ? "Pulsa «Hacer foto» y encuadra la carta entera, mejor sobre un fondo liso y oscuro."
              : "Coloca una carta bajo la cámara y pulsa capturar."}
          </p>
        )}
      </section>
    </div>
  );
}

function WebcamSection({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="webcam-section" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Usar la webcam del escáner</summary>
      {open && (
        <>
          <CameraPreview />
          <div className="actions">{children}</div>
        </>
      )}
    </details>
  );
}
