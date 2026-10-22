import type { BinderSpot, Card, FrameRegion, CollectionEntry, Facets, Location, Page, Scan, ScanSession, SessionMode } from "./types";

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
  /** `binder`: página y casilla (1-9) en una sesión de archivador. */
  /** `region`: zona del marco (fracciones 0-1) que el servidor recorta de la webcam. */
  createScan(image?: File, session?: number, afterEmpty = true, binder?: BinderSpot, region?: FrameRegion | null): Promise<Scan> {
    const spot = {
      ...(binder ? { binder_page: binder.page, binder_slot: binder.slot } : {}),
      ...(region && !image ? { region } : {}),
    };
    if (!image) {
      return request("/api/scans/", json("POST", session ? { session, after_empty: afterEmpty, ...spot } : {}));
    }
    const form = new FormData();
    form.append("image", image);
    if (session) {
      form.append("session", String(session));
      form.append("after_empty", afterEmpty ? "true" : "false");
      for (const [k, v] of Object.entries(spot)) form.append(k, String(v)); // region solo va sin imagen
    }
    return request("/api/scans/", { method: "POST", body: form });
  },
  undoScan: (id: number) => request<Scan>(`/api/scans/${id}/undo/`, json("POST", {})),

  createSession: (location?: number | null, mode: SessionMode = "burst") =>
    request<ScanSession>("/api/sessions/", json("POST", { mode, ...(location ? { location } : {}) })),
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
