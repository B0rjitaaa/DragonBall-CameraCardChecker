import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import type { Candidate } from "../types";

interface Option {
  id: number;
  card_number: string;
  name: string;
  image_url: string;
  hint?: string;
}

function fromCandidate(c: Candidate): Option {
  return {
    id: c.card_id,
    card_number: c.card_number,
    name: c.name,
    image_url: c.image_url,
    hint: `${Math.round(c.score * 100)}%`,
  };
}

/** Elige la carta correcta: entre los candidatos del escaneo o buscándola. */
export default function CardPicker({
  candidates,
  onPick,
  busy,
}: {
  candidates: Candidate[];
  onPick: (cardId: number) => void;
  busy: boolean;
}) {
  const [search, setSearch] = useState("");
  const term = search.trim();
  const results = useQuery({
    queryKey: ["cards", "picker", term],
    queryFn: () => api.listCards(new URLSearchParams({ search: term })),
    enabled: term.length >= 2,
  });

  const options: Option[] = term.length >= 2 ? (results.data?.results ?? []) : candidates.map(fromCandidate);

  return (
    <div className="picker">
      <input
        type="search"
        placeholder="Buscar por nombre o número (p. ej. BT25-120)…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {term.length >= 2 && results.data && (
        <p className="muted">{results.data.count} resultados{results.data.count > 30 && " (se muestran 30)"}</p>
      )}
      <div className="picker-grid">
        {options.map((o) => (
          <button key={o.id} className="tile" disabled={busy} onClick={() => onPick(o.id)} title="Es esta">
            {o.image_url && <img src={o.image_url} alt={o.name} loading="lazy" />}
            <span>
              {o.card_number} · {o.name}
              {o.hint && <span className="muted"> · {o.hint}</span>}
            </span>
          </button>
        ))}
      </div>
      <p className="muted small">
        Si tu impresión no aparece (promos, premios…), elige la misma carta en otra impresión: tu foto se guarda y la
        próxima vez la reconocerá.
      </p>
    </div>
  );
}
