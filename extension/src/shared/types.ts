/** @deprecated Use WsHintEndV2 from messages.ts instead. Kept for service worker compat. */
export interface HintPayload {
  hint: string;
  source: string;
  sentiment: "positive" | "neutral" | "negative";
  color: "green" | "blue" | "red";
  coaching?: string;
  relevance?: "on_topic" | "off_topic";
}

/** RAG search result. */
export interface SearchResult {
  text: string;
  sourceFile: string;
  pageNumber: number;
  score: number;
}

/** Binary frame header fields (after decode). */
export interface AudioFrame {
  seq: number;
  channel: 0; // audio PCM16
  pcm16: ArrayBuffer;
}

export interface ControlFrame {
  seq: number;
  channel: 1; // control JSON
  payload: Record<string, unknown>;
}
