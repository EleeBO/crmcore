import { h } from "preact";
import { recordingSignal } from "./store";

interface Props {
  onStop?: () => void;
  mode?: "recording" | "done";
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** Raw RMS amplitude ~0.02 needs scaling to 0-1 range (matches DOM VU meters). */
const MIC_SCALE = 400;

function MicBars(): h.JSX.Element {
  const raw = recordingSignal.value.micLevel;
  const level = Math.min(1.0, raw * MIC_SCALE);
  const baseHeights = [0.4, 0.7, 1.0, 0.7, 0.4];
  return (
    <div class="lc-mic-bars">
      {baseHeights.map((scale, i) => {
        const h = Math.max(2, Math.round(level * scale * 16));
        return (
          <div
            key={i}
            class="lc-mic-bar"
            style={{ height: `${h}px` }}
          />
        );
      })}
    </div>
  );
}

export function RecordingBar({ onStop, mode = "recording" }: Props): h.JSX.Element {
  if (mode === "done") {
    return (
      <div class="lc-rec-bar lc-rec-bar--done">
        <span class="lc-rec-pill-done">
          <span class="lc-rec-dot lc-rec-dot--done" />
          REC
        </span>
      </div>
    );
  }

  const state = recordingSignal.value;

  return (
    <div class="lc-rec-bar">
      <button class="lc-rec-stop" onClick={onStop}>
        <span class="lc-rec-dot" />
        СТОП
      </button>
      <MicBars />
      <span class="lc-rec-timer">{formatTime(state.elapsedSeconds)}</span>
    </div>
  );
}
