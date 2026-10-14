import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../api";
import ScanResult from "../components/ScanResult";

const PREVIEW_INTERVAL_MS = 700;

function CameraPreview() {
  const [src, setSrc] = useState(api.previewUrl);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const timer = window.setInterval(() => setSrc(api.previewUrl()), PREVIEW_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, []);

  if (failed) {
    return (
      <div className="preview placeholder">
        Cámara no disponible. Puedes subir una foto.
        <button onClick={() => setFailed(false)}>Reintentar</button>
      </div>
    );
  }
  return <img className="preview" src={src} alt="Vista previa" onError={() => setFailed(true)} />;
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
