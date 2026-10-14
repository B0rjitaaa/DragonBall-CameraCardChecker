import type { Card, CollectionEntry, Facets, Page, Scan } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* respuesta sin JSON */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export const api = {
  createScan(image?: File): Promise<Scan> {
    if (!image) return request("/api/scans/", json("POST", {}));
    const form = new FormData();
    form.append("image", image);
    return request("/api/scans/", { method: "POST", body: form });
  },
  getScan: (id: number) => request<Scan>(`/api/scans/${id}/`),
  confirmScan: (id: number, cardId: number) =>
    request<Scan>(`/api/scans/${id}/confirm/`, json("POST", { card_id: cardId })),
  listScans: (page = 1) => request<Page<Scan>>(`/api/scans/?page=${page}`),

  listCards: (params: URLSearchParams) => request<Page<Card>>(`/api/cards/?${params}`),
  facets: () => request<Facets>("/api/cards/facets/"),

  listCollection: (page = 1) => request<Page<CollectionEntry>>(`/api/collection/?page=${page}`),
  addToCollection: (cardId: number, quantity = 1) =>
    request<CollectionEntry>("/api/collection/", json("POST", { card_id: cardId, quantity })),
  updateCollection: (id: number, quantity: number) =>
    request<CollectionEntry>(`/api/collection/${id}/`, json("PATCH", { quantity })),
  async removeFromCollection(id: number): Promise<void> {
    const response = await fetch(`/api/collection/${id}/`, { method: "DELETE" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  },

  previewUrl: () => `/api/camera/preview/?t=${Date.now()}`,
};
