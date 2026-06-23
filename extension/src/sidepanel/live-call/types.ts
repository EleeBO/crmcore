/** Mirrors backend HintResponseV2 SGR schema. */

export type HintType = "coaching" | "success" | "warning";

export interface AIHint {
  id: string;
  hintType: HintType;
  headline: string;
  detail: string;
  coaching: string;
  source: string;
  timestamp: number;
}

export interface WaveSegment {
  speaker: "manager" | "client";
  amplitude: number;
}

export interface TalkRatio {
  managerPercent: number;
  clientPercent: number;
  waveform: WaveSegment[];
}

export interface RecordingState {
  isRecording: boolean;
  elapsedSeconds: number;
  micLevel: number;
}

export type ContextTab = "hints" | "objections" | "briefing" | "strategy";

// ── Transcript ──

export interface TranscriptMessage {
  type: "message";
  id: string;
  speaker: "manager" | "client";
  text: string;
  timestamp: string;
  isInterim?: boolean;
}

export type TranscriptItem = TranscriptMessage;
// NOTE: TranscriptEvent is out of scope for MVP.
