import { h } from "preact";
import type { LiveCallCallbacks } from "./mount";
import { RecordingBar } from "./RecordingBar";
import { ConnectionStatus } from "./ConnectionStatus";
import { TalkRatioBar } from "./TalkRatioBar";
import { ContextTabs } from "./ContextTabs";
import { TranscriptFeed } from "./TranscriptFeed";

interface LiveCallPanelProps {
  callbacks: LiveCallCallbacks;
}

export function LiveCallPanel({
  callbacks,
}: LiveCallPanelProps): h.JSX.Element {
  return (
    <div class="lc-panel">
      <RecordingBar onStop={callbacks.onStopRecording} />
      <ConnectionStatus />
      <ContextTabs callbacks={callbacks} />
      <TalkRatioBar />
      <TranscriptFeed />
    </div>
  );
}
