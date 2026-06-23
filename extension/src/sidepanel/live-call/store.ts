import { signal } from "@preact/signals";
import type { AIHint, TalkRatio, TranscriptItem, ContextTab, RecordingState } from "./types";
import type { BriefData } from "../brief/types";

export const transcriptSignal = signal<TranscriptItem[]>([]);
export const hintSignal = signal<AIHint | null>(null);
export const talkRatioSignal = signal<TalkRatio>({
  managerPercent: 0, clientPercent: 0, waveform: [],
});
export const recordingSignal = signal<RecordingState>({
  isRecording: false, elapsedSeconds: 0, micLevel: 0,
});
export const activeTabSignal = signal<ContextTab>("hints");
export const wsConnectedSignal = signal<boolean>(false);
export const sttActiveSignal = signal<boolean>(true);
export const briefDataSignal = signal<BriefData | null>(null);
