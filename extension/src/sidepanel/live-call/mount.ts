import { render, h } from "preact";
import { LiveCallPanel } from "./LiveCallPanel";
import { RecordingBar } from "./RecordingBar";
import type { ContextTab } from "./types";
import "./live-call.css";

let mountedContainer: HTMLElement | null = null;
let phase4Container: HTMLElement | null = null;

export interface LiveCallCallbacks {
  onStopRecording: () => void;
  onTabChange: (tab: ContextTab) => void;
  onBriefingTabActive: (active: boolean) => void;
}

export function mountLiveCall(
  container: HTMLElement,
  callbacks: LiveCallCallbacks,
): void {
  // Guard against double-mount (e.g., WS reconnect mid-call)
  if (mountedContainer) {
    render(null, mountedContainer);
    mountedContainer = null;
  }
  mountedContainer = container;
  render(h(LiveCallPanel, { callbacks }), container);
}

export function unmountLiveCall(): void {
  if (mountedContainer) {
    render(null, mountedContainer);
    mountedContainer = null;
  }
}

/** Mount a "done" RecordingBar (grey pill) in Phase 4. */
export function mountRecBarDone(container: HTMLElement): void {
  unmountRecBarDone();
  phase4Container = container;
  render(h(RecordingBar, { mode: "done" }), container);
}

export function unmountRecBarDone(): void {
  if (phase4Container) {
    render(null, phase4Container);
    phase4Container = null;
  }
}
