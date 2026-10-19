import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { sounds } from "../lib/sounds";
import type { SessionScan } from "../types";
import ScanResult from "./ScanResult";

const percent = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

function rowState(s: SessionScan): { label: string; tone: "ok" | "warn" | "muted" | "error" } {
  if (s.status === "pending" || s.status === "processing") return { label: "Identificando…", tone: "muted" };
  if (s.status === "failed") return { label: "Error", tone: "error" };
  if (s.dismissed) return { label: "Deshecha", tone: "muted" };
  if (s.added_to_collection) return { label: "Añadida", tone: "ok" };
  if (s.repeat_suspect) return { label: "¿Otra copia?", tone: "warn" };
  return { label: "Por revisar", tone: "warn" };
}

const MAX_COPIES = 99;
const clampCopies = (n: number) => Math.min(MAX_COPIES, Math.max(1, Math.round(n) || 1));

/** − [n] +: se puede escribir el número o usar los botones. */
function CopiesInput({
  value,
  onChange,
  disabled,
}: {
  value: number;
  onChange: (n: number) => void;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState(String(value));
  const [editing, setEditing] = useState(false);
  useEffect(() => {
    if (!editing) setDraft(String(value));
  }, [value, editing]);

  const commit = (n: number) => {
    const next = clampCopies(n);
    setDraft(String(next));
    if (next !== value) onChange(next);
  };

  return (
    <span className="copies-input">
      <button
        type="button"
        className="secondary"
        aria-label="Una copia menos"
        disabled={disabled || value <= 1}
        onClick={() => commit(value - 1)}
      >
        −
      </button>
      <input
        type="number"
        inputMode="numeric"
        min={1}
        max={MAX_COPIES}
        aria-label="Copias"
        value={draft}
        disabled={disabled}
        onFocus={(e) => {
          setEditing(true);
          e.target.select();
        }}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          setEditing(false);
          commit(Number(draft));
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
        }}
      />
      <button
        type="button"
        className="secondary"
        aria-label="Una copia más"
        disabled={disabled || value >= MAX_COPIES}
        onClick={() => commit(value + 1)}
      >
        +
      </button>
    </span>
  );
}

function ReviewModal({ scanId, onClose }: { scanId: number; onClose: () => void }) {
  const scan = useQuery({ queryKey: ["scan", scanId], queryFn: () => api.getScan(scanId) });
  return (
    <div className="modal" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}>
        {scan.data ? <ScanResult key={scanId} scan={scan.data} /> : <p className="muted">Cargando…</p>}
        <button className="secondary" onClick={onClose}>
          Cerrar
        </button>
      </div>
    </div>
  );
}

/** Panel de una sesión de modo ráfaga: contadores, lista de cartas y acciones. */
export default function BurstPanel({ sessionId, active }: { sessionId: number; active: boolean }) {
  const queryClient = useQueryClient();
  const [reviewing, setReviewing] = useState<number | null>(null);
  // Copias elegidas en las filas "¿Otra copia?" antes de añadirlas.
  const [pendingCopies, setPendingCopies] = useState<Record<number, number>>({});
  const announced = useRef<Set<number> | null>(null);

  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.getSession(sessionId),
    refetchInterval: active ? 1000 : false,
  });

  const addCopy = useMutation({
    mutationFn: (s: SessionScan) => api.confirmScan(s.id, s.card_id!, pendingCopies[s.id] ?? 1),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      void queryClient.invalidateQueries({ queryKey: ["collection"] });
    },
  });

  const setCopies = useMutation({
    mutationFn: ({ id, copies }: { id: number; copies: number }) => api.setScanCopies(id, copies),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      void queryClient.invalidateQueries({ queryKey: ["collection"] });
    },
  });

  const undo = useMutation({
    mutationFn: (id: number) => api.undoScan(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      void queryClient.invalidateQueries({ queryKey: ["collection"] });
    },
  });

  // Sonido al terminar cada identificación (solo las nuevas desde que se abrió el panel).
  useEffect(() => {
    const scans = session.data?.scans;
    if (!scans) return;
    const finished = scans.filter((s) => s.status === "done" || s.status === "failed");
    if (announced.current === null) {
      announced.current = new Set(finished.map((s) => s.id));
      return;
    }
    for (const s of finished) {
      if (announced.current.has(s.id)) continue;
      announced.current.add(s.id);
      if (!active) continue;
      if (s.status === "failed") sounds.error();
      else if (s.added_to_collection) sounds.added();
      else sounds.review();
    }
  }, [session.data, active]);

  if (!session.data) return <p className="muted">Cargando la sesión…</p>;
  const { stats, scans, auto_add_min_confidence } = session.data;

  return (
    <section className="burst-panel">
      <div className="burst-stats">
        <div>
          <strong>{stats.added}</strong>
          <span>{stats.copies > stats.added ? `añadidas · ${stats.copies} copias` : "añadidas"}</span>
        </div>
        <div className={stats.review ? "warn" : ""}>
          <strong>{stats.review}</strong>
          <span>por revisar</span>
        </div>
        <div>
          <strong>{stats.undone}</strong>
          <span>deshechas</span>
        </div>
      </div>
      <p className="muted small">
        Se añaden solas a la colección a partir del {percent(auto_add_min_confidence)} (1 copia, Near Mint; con − / +
        cambias cuántas). Por debajo quedan "por revisar". Si la misma carta sale dos veces seguidas sin retirarla, se
        pregunta "¿Otra copia?" y eliges cuántas añadir.
      </p>

      {scans.length === 0 ? (
        <p className="muted">Aún no hay cartas en esta sesión.</p>
      ) : (
        <ul className="burst-list">
          {scans.map((s) => {
            const state = rowState(s);
            const done = s.status === "done" && !s.dismissed;
            return (
              <li key={s.id} className={s.dismissed ? "dismissed" : ""}>
                {s.cropped_image ? <img className="thumb" src={s.cropped_image} alt="" /> : <span className="thumb" />}
                <div className="burst-card">
                  <span>{s.card_number ? `${s.card_number} · ${s.card_name}` : s.error || "—"}</span>
                  <span className="muted small">
                    {percent(s.confidence)}
                    {s.confirmed && " · confirmada"}
                  </span>
                </div>
                <span className={`badge ${state.tone}`}>{state.label}</span>
                <div className="burst-actions">
                  {done && !s.added_to_collection && s.repeat_suspect && s.card_id != null && (
                    <>
                      <CopiesInput
                        value={pendingCopies[s.id] ?? 1}
                        disabled={addCopy.isPending}
                        onChange={(n) => setPendingCopies((p) => ({ ...p, [s.id]: n }))}
                      />
                      <button disabled={addCopy.isPending} onClick={() => addCopy.mutate(s)}>
                        {(pendingCopies[s.id] ?? 1) > 1 ? `Añadir ${pendingCopies[s.id]} copias` : "Añadir copia"}
                      </button>
                    </>
                  )}
                  {done && s.added_to_collection && (
                    <CopiesInput
                      value={s.copies}
                      disabled={setCopies.isPending}
                      onChange={(copies) => setCopies.mutate({ id: s.id, copies })}
                    />
                  )}
                  {done && !s.added_to_collection && !s.repeat_suspect && (
                    <button className="secondary" onClick={() => setReviewing(s.id)}>
                      Revisar
                    </button>
                  )}
                  {done && s.added_to_collection && (
                    <button className="secondary" onClick={() => setReviewing(s.id)} title="Corregir la carta">
                      Corregir
                    </button>
                  )}
                  {done && (
                    <button className="secondary" disabled={undo.isPending} onClick={() => undo.mutate(s.id)}>
                      {s.added_to_collection ? "Deshacer" : "Descartar"}
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {reviewing != null && (
        <ReviewModal
          scanId={reviewing}
          onClose={() => {
            setReviewing(null);
            void queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
          }}
        />
      )}
    </section>
  );
}
