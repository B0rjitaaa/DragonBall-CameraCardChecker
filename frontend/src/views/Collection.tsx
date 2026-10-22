import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";

export default function Collection() {
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();
  const entries = useQuery({
    queryKey: ["collection", page],
    queryFn: () => api.listCollection(page),
    placeholderData: keepPreviousData,
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["collection"] });

  const setQuantity = useMutation({
    mutationFn: async ({ id, quantity }: { id: number; quantity: number }) => {
      if (quantity > 0) await api.updateCollection(id, quantity);
      else await api.removeFromCollection(id);
    },
    onSuccess: invalidate,
  });

  if (entries.isError) return <p className="error">{entries.error.message}</p>;
  if (!entries.data) return <p className="muted">Cargando…</p>;
  if (entries.data.count === 0) {
    return <p className="muted">La colección está vacía. Escanea una carta y añádela.</p>;
  }

  return (
    <div>
      <table className="table">
        <thead>
          <tr>
            <th />
            <th>Número</th>
            <th>Nombre</th>
            <th>Ubicación</th>
            <th>Cantidad</th>
          </tr>
        </thead>
        <tbody>
          {entries.data.results.map((entry) => (
            <tr key={entry.id}>
              <td>{entry.card.image_url && <img className="thumb" src={entry.card.image_url} alt="" />}</td>
              <td>{entry.card.card_number}</td>
              <td>{entry.card.name}</td>
              <td>{entry.location_name}</td>
              <td className="qty">
                <button
                  onClick={() => setQuantity.mutate({ id: entry.id, quantity: entry.quantity - 1 })}
                >
                  −
                </button>
                {entry.quantity}
                <button
                  onClick={() => setQuantity.mutate({ id: entry.id, quantity: entry.quantity + 1 })}
                >
                  +
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="pager">
        <button disabled={!entries.data.previous} onClick={() => setPage((p) => p - 1)}>
          ← Anterior
        </button>
        <span>Página {page}</span>
        <button disabled={!entries.data.next} onClick={() => setPage((p) => p + 1)}>
          Siguiente →
        </button>
      </div>
    </div>
  );
}
