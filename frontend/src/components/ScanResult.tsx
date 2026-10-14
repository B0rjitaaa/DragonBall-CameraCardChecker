import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import type { Scan } from "../types";
import CardDetail from "./CardDetail";
import CardPicker from "./CardPicker";

function percent(value: number | null) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

export default function ScanResult({ scan }: { scan: Scan }) {
  const queryClient = useQueryClient();
  const [correcting, setCorrecting] = useState(false);
  const confirm = useMutation({
    mutationFn: (cardId: number) => api.confirmScan(scan.id, cardId),
    onSuccess: (updated) => {
      queryClient.setQueryData(["scan", scan.id], updated);
      queryClient.invalidateQueries({ queryKey: ["scans"] });
      setCorrecting(false);
    },
  });

  if (scan.status === "pending" || scan.status === "processing") {
    return <p className="muted">Identificando… ({scan.status})</p>;
  }
  if (scan.status === "failed") {
    return <p className="error">Error: {scan.error}</p>;
  }

  const unsure = scan.needs_review && !scan.confirmed;
  const picking = unsure || correcting;
  const current = confirm.data ?? scan;

  return (
    <section className="scan-result">
      <div className="scan-meta">
        {current.confirmed ? (
          <span className="badge ok">Confirmada ✓</span>
        ) : (
          <span className={unsure ? "badge warn" : "badge ok"}>
            {unsure ? "No estoy seguro" : "Identificada"} · {percent(scan.confidence)}
          </span>
        )}
        <span className="muted">
          {scan.method} · {scan.duration_ms} ms
          {!scan.card_detected && " · bordes de la carta no detectados"}
        </span>
      </div>

      <div className="scan-body">
        {scan.cropped_image && (
          <figure className="crop">
            <img src={scan.cropped_image} alt="Recorte" />
            <figcaption>Tu foto</figcaption>
          </figure>
        )}
        <div className="scan-main">
          {picking ? (
            <>
              <h3>{unsure ? "¿Cuál de estas es?" : "Elige la carta correcta"}</h3>
              <CardPicker candidates={scan.candidates} onPick={(id) => confirm.mutate(id)} busy={confirm.isPending} />
              {correcting && (
                <button className="link" onClick={() => setCorrecting(false)}>
                  Cancelar
                </button>
              )}
            </>
          ) : current.matched_card ? (
            <>
              <CardDetail card={current.matched_card} />
              {!current.confirmed && (
                <button className="link" onClick={() => setCorrecting(true)}>
                  ¿No es esta carta? Corregir
                </button>
              )}
            </>
          ) : (
            <p className="muted">Sin coincidencias: ¿hay fingerprints calculados?</p>
          )}
          {confirm.isError && <p className="error">{confirm.error.message}</p>}
        </div>
      </div>
    </section>
  );
}
