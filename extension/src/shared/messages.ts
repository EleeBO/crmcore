import type {
  WsEvaluationStarted,
  WsEvaluationResult,
  WsEvaluationError,
  WsFollowUpReady,
  CallEvaluationResult,
  FollowUpEmail,
  CrmNote,
} from "./evaluation-types";

// ── WebSocket message types (backend → extension) ─────────────────────────

// NEW v2 types
export interface WsHintEndV2 {
  type: "hint_end";
  v: 2;
  hint_type: "coaching" | "success" | "warning";
  headline: string;
  detail: string;
  coaching: string;
  source: string;
}

export interface WsTalkRatio {
  type: "talk_ratio";
  managerPercent: number;
  clientPercent: number;
  waveform: Array<{ speaker: "manager" | "client"; amplitude: number }>;
}

export interface WsTranscript {
  type: "transcript";
  speaker: "rep" | "client";
  text: string;
  is_final: boolean;
  utterance_id?: string;
}

export interface WsError {
  type: "error";
  code: string;
  message: string;
}

export type WsMessage =
  | WsHintEndV2
  | WsTalkRatio
  | WsTranscript
  | WsError
  | WsEvaluationStarted
  | WsEvaluationResult
  | WsEvaluationError
  | WsFollowUpReady;

// ── Extension internal messages (Chrome runtime / ports) ──────────────────

export type ExtMessage =
  | { type: "PREPARE_CAPTURE"; sessionId: string; kbId: string; tabId: number }
  | { type: "START_SESSION"; sessionId: string; kbId: string; tabId: number; streamId: string; deviceId?: string; sttProvider?: string }
  | { type: "STOP_SESSION"; sessionId: string }
  | { type: "TRANSCRIPT"; transcript: WsTranscript }
  | { type: "AUDIO_LEVEL"; mic: number; tab: number }
  | { type: "GET_SESSION_STATE" }
  | { type: "SESSION_STATE"; capturing: boolean; sessionId: string; kbId: string; wsConnected: boolean }
  | { type: "SESSION_ABORTED"; reason: string }
  | { type: "WS_RECONNECTED" }
  | { type: "WS_STATUS"; connected: boolean }
  | { type: "CAPTURE_STARTED" }
  | { type: "CAPTURE_FAILED"; error: string }
  | { type: "EVALUATION_STARTED"; sessionId: string }
  | { type: "EVALUATION_RESULT"; sessionId: string; evalToken: string; evaluation: CallEvaluationResult }
  | { type: "EVALUATION_ERROR"; sessionId: string; code: string; message: string }
  | { type: "FOLLOW_UP_READY"; sessionId: string; followUpEmail: FollowUpEmail; crmNote: CrmNote };
