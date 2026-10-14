import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import type { Card } from "../types";

// El texto de Bandai usa <br> como salto de línea.
const stripHtml = (text: string) => text.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, "");

export default function CardDetail({ card }: { card: Card }) {
  const queryClient = useQueryClient();
  const add = useMutation({
    mutationFn: () => api.addToCollection(card.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["collection"] }),
  });

  const stats: [string, string][] = [
    ["Número", card.card_number],
    ["Set", [card.set_code, card.set_name].filter(Boolean).join(" · ")],
    ["Rareza", card.rarity],
    ["Tipo", card.card_type],
    ["Color", card.color],
    ["Coste", card.cost],
    ["Poder", card.power],
  ];

  return (
    <article className="card-detail">
      {card.image_url && <img src={card.image_url} alt={card.name} loading="lazy" />}
      <div>
        <h2>{card.name}</h2>
        <dl>
          {stats
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>
        {card.text && <p className="card-text">{stripHtml(card.text)}</p>}
        {card.back_name && (
          <div className="card-back">
            <h3>Reverso: {card.back_name}</h3>
            {card.back_text && <p className="card-text">{stripHtml(card.back_text)}</p>}
            {card.image_back_url && <img src={card.image_back_url} alt={card.back_name} loading="lazy" />}
          </div>
        )}
        <button onClick={() => add.mutate()} disabled={add.isPending}>
          {add.isSuccess ? "Añadida ✓ (añadir otra)" : "Añadir a la colección"}
        </button>
        {add.isError && <p className="error">{add.error.message}</p>}
      </div>
    </article>
  );
}
