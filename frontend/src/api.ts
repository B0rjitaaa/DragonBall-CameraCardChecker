import type { Card, CollectionEntry, Facets, Location, Page, Scan, ScanSession } from "./types";

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
  createScan(image?: File, session?: number, afterEmpty = true): Promise<Scan> {
    if (!image) {
      return request("/api/scans/", json("POST", session ? { session, after_empty: afterEmpty } : {}));
    }
    const form = new FormData();
    form.append("image", image);
    if (session) {
      form.append("session", String(session));
      form.append("after_empty", afterEmpty ? "true" : "false");
    }
    return request("/api/scans/", { method: "POST", body: form });
  },
  undoScan: (id: number) => request<Scan>(`/api/scans/${id}/undo/`, json("POST", {})),

  createSession: (location?: number | null) =>
    request<ScanSession>("/api/sessions/", json("POST", location ? { location } : {})),
  listLocations: () => request<Location[]>("/api/locations/"),
  getSession: (id: number) => request<ScanSession>(`/api/sessions/${id}/`),
  endSession: (id: number) => request<ScanSession>(`/api/sessions/${id}/end/`, json("POST", {})),
  getScan: (id: number) => request<Scan>(`/api/scans/${id}/`),
  confirmScan: (id: number, cardId: number, copies?: number) =>
    request<Scan>(`/api/scans/${id}/confirm/`, json("POST", copies ? { card_id: cardId, copies } : { card_id: cardId })),
  setScanCopies: (id: number, copies: number) =>
    request<Scan>(`/api/scans/${id}/copies/`, json("POST", { copies })),
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
