import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import CardDetail from "../components/CardDetail";
import type { Card, Facets } from "../types";

const FACET_LABELS: Record<keyof Facets, string> = {
  set_code: "Set",
  rarity: "Rareza",
  card_type: "Tipo",
  color: "Color",
};

export default function Catalog() {
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<Partial<Record<keyof Facets, string>>>({});
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Card | null>(null);

  const params = new URLSearchParams({ page: String(page) });
  if (search) params.set("search", search);
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);

  const facets = useQuery({ queryKey: ["facets"], queryFn: api.facets });
  const cards = useQuery({
    queryKey: ["cards", params.toString()],
    queryFn: () => api.listCards(params),
    placeholderData: keepPreviousData,
  });

  const update = (key: keyof Facets, value: string) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  };

  return (
    <div className="catalog">
      <div className="filters">
        <input
          type="search"
          placeholder="Nombre, número o texto…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
        {facets.data &&
          (Object.keys(FACET_LABELS) as (keyof Facets)[]).map((key) => (
            <select key={key} value={filters[key] ?? ""} onChange={(e) => update(key, e.target.value)}>
              <option value="">{FACET_LABELS[key]}: todos</option>
              {facets.data[key].map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          ))}
      </div>

      {cards.isError && <p className="error">{cards.error.message}</p>}
      {cards.data && (
        <>
          <p className="muted">{cards.data.count} cartas</p>
          <div className="grid">
            {cards.data.results.map((card) => (
              <button key={card.id} className="tile" onClick={() => setSelected(card)}>
                {card.image_url ? <img src={card.image_url} alt={card.name} loading="lazy" /> : null}
                <span>
                  {card.card_number} · {card.name}
                </span>
              </button>
            ))}
          </div>
          <div className="pager">
            <button disabled={!cards.data.previous} onClick={() => setPage((p) => p - 1)}>
              ← Anterior
            </button>
            <span>Página {page}</span>
            <button disabled={!cards.data.next} onClick={() => setPage((p) => p + 1)}>
              Siguiente →
            </button>
          </div>
        </>
      )}

      {selected && (
        <div className="modal" onClick={() => setSelected(null)}>
          <div onClick={(e) => e.stopPropagation()}>
            <CardDetail card={selected} />
          </div>
        </div>
      )}
    </div>
  );
}
