import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
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

export default function Scanner() {
  const [scanId, setScanId] = useState<number | null>(null);

  const create = useMutation({
    mutationFn: (file?: File) => api.createScan(file),
    onSuccess: (scan) => setScanId(scan.id),
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

  return (
    <div className="scanner">
      <section>
        <CameraPreview />
        <div className="actions">
          <button onClick={() => create.mutate(undefined)} disabled={create.isPending}>
            Capturar e identificar
          </button>
          <label className="button secondary">
            Subir foto
            <input
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) create.mutate(file);
                e.target.value = "";
              }}
            />
          </label>
        </div>
        {create.isError && <p className="error">{create.error.message}</p>}
      </section>
      <section>
        {scan.data ? (
          <ScanResult key={scan.data.id} scan={scan.data} />
        ) : (
          <p className="muted">Coloca una carta bajo la cámara y pulsa capturar.</p>
        )}
      </section>
    </div>
  );
}
