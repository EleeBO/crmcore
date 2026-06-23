import { h } from "preact";
import { transcriptSignal, recordingSignal } from "./store";
import { TranscriptMessage } from "./TranscriptMessage";
import { useAutoScroll } from "./hooks/useAutoScroll";
import type { TranscriptItem } from "./types";

export function TranscriptFeed(): h.JSX.Element {
  const items = transcriptSignal.value;
  const isRecording = recordingSignal.value.isRecording;
  const lastText = items.length > 0 ? items[items.length - 1].text : "";
  const { containerRef, isAtBottom, scrollToBottom } = useAutoScroll([items.length, lastText]);

  return (
    <div class="lc-transcript">
      <div class="lc-transcript-header">
        <span class="lc-transcript-title">Транскрипт</span>
        {isRecording && (
          <span class="lc-live-badge">
            <span class="lc-live-dot" />
            LIVE
          </span>
        )}
      </div>
      <div class="lc-transcript-list" ref={containerRef}>
        {items.map((item: TranscriptItem) => (
          <TranscriptMessage key={item.id} message={item} />
        ))}
      </div>
      {!isAtBottom && (
        <button class="lc-jump-pill" onClick={scrollToBottom}>
          К последнему ↓
        </button>
      )}
    </div>
  );
}
