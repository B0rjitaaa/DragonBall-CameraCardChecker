export interface Card {
  id: number;
  bandai_id: number;
  card_number: string;
  name: string;
  set_code: string;
  set_name: string;
  rarity: string;
  card_type: string;
  color: string;
  cost: string;
  power: string;
  text: string;
  image_url: string;
  back_name: string;
  back_text: string;
  image_back_url: string;
  attributes: Record<string, unknown>;
}

export type CardSummary = Pick<
  Card,
  "id" | "card_number" | "name" | "set_code" | "rarity" | "color" | "image_url"
>;

export interface Candidate {
  card_id: number;
  card_number: string;
  name: string;
  image_url: string;
  distance: number;
  orb_matches: number | null;
  score: number;
}

export type ScanStatus = "pending" | "processing" | "done" | "failed";

export interface Scan {
  id: number;
  source: "upload" | "camera";
  status: ScanStatus;
  image: string | null;
  cropped_image: string | null;
  card_detected: boolean;
  matched_card: Card | null;
  confidence: number | null;
  needs_review: boolean;
  confirmed: boolean;
  session: number | null;
  added_to_collection: boolean;
  dismissed: boolean;
  after_empty: boolean;
  repeat_suspect: boolean;
  method: string;
  candidates: Candidate[];
  error: string;
  duration_ms: number | null;
  created_at: string;
  finished_at: string | null;
}

export interface CollectionEntry {
  id: number;
  card: CardSummary;
  quantity: number;
  condition: string;
  notes: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type Facets = Record<"set_code" | "rarity" | "card_type" | "color", string[]>;

export interface SessionScan {
  id: number;
  status: ScanStatus;
  cropped_image: string | null;
  card_detected: boolean;
  card_id: number | null;
  card_number: string | null;
  card_name: string | null;
  confidence: number | null;
  needs_review: boolean;
  confirmed: boolean;
  added_to_collection: boolean;
  copies: number;
  dismissed: boolean;
  repeat_suspect: boolean;
  error: string;
  duration_ms: number | null;
  created_at: string;
}

export interface ScanSession {
  id: number;
  started_at: string;
  ended_at: string | null;
  condition: string;
  auto_add_min_confidence: number;
  stats: { total: number; added: number; copies: number; review: number; pending: number; failed: number; undone: number };
  scans: SessionScan[];
}
