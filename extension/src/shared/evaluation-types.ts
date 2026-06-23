/** TypeScript types for call evaluation (FEAT-004). */

export interface CriterionResultWire {
  criterion_id: string;
  criterion_name: string;
  reasoning: string;
  score: number;
  comment: string;
  recommendations: string[];
}

export interface FollowUpEmail {
  subject: string;
  body: string;
}

export interface CrmNote {
  title: string;
  body: string;
}

export interface CallEvaluationResult {
  call_summary: string;
  criteria_results: CriterionResultWire[];
  overall_score: number;
  verdict: "excellent" | "good" | "satisfactory" | "needs_improvement";
  strengths: string[];
  growth_areas: string[];
  action_plan: string[];
  follow_up_email?: FollowUpEmail;
  crm_note?: CrmNote;
}

export interface WsEvaluationStarted {
  type: "evaluation_started";
  session_id: string;
  eval_token: string;
}

export interface CallAnalyticsWire {
  total_duration_s: number;
  rep_talk_ratio: number;
  rep_talk_time_s: number;
  client_talk_time_s: number;
  rep_speech_rate_wpm: number;
  client_speech_rate_wpm: number;
  interruptions_by_rep: number;
  interruptions_by_client: number;
  avg_rep_pause_before_response_s: number;
  rep_word_count: number;
  client_word_count: number;
}

export interface DiarizedUtterance {
  speaker: string;
  text: string;
  start_ms?: number;
  end_ms?: number;
}

export interface WsEvaluationResult {
  type: "evaluation_result";
  session_id: string;
  eval_token: string;
  evaluation: CallEvaluationResult;
  analytics?: CallAnalyticsWire;
  transcript?: DiarizedUtterance[];
}

export interface WsEvaluationError {
  type: "evaluation_error";
  session_id: string;
  code: string;
  message: string;
}

export interface WsFollowUpReady {
  type: "follow_up_ready";
  session_id: string;
  follow_up_email: FollowUpEmail;
  crm_note: CrmNote;
}

/** Verdict labels in Russian. */
export const VERDICT_LABELS: Record<string, string> = {
  excellent: "Отлично",
  good: "Хорошо",
  satisfactory: "Удовлетворительно",
  needs_improvement: "Требует внимания",
};

/** Verdict colors. */
export const VERDICT_COLORS: Record<string, string> = {
  excellent: "#22c55e",
  good: "#3b82f6",
  satisfactory: "#f59e0b",
  needs_improvement: "#ef4444",
};
