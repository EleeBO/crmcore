import { h } from "preact";
import type { TranscriptMessage as TMsg } from "./types";

const SPEAKER_LABELS: Record<"manager" | "client", string> = {
  manager: "Вы",
  client: "Клиент",
};

interface Props {
  message: TMsg;
}

export function TranscriptMessage({ message }: Props): h.JSX.Element {
  const isManager = message.speaker === "manager";

  return (
    <div class={`lc-msg ${message.isInterim ? "lc-msg--interim" : ""}`}>
      <div class="lc-msg-meta">
        <span class={`lc-msg-speaker ${isManager ? "lc-msg-speaker--mgr" : "lc-msg-speaker--cli"}`}>
          {SPEAKER_LABELS[message.speaker] ?? message.speaker}
        </span>
        <span class="lc-msg-time">{message.timestamp}</span>
      </div>
      <div class="lc-msg-body">
        <div class={`lc-msg-bar ${isManager ? "lc-msg-bar--mgr" : "lc-msg-bar--cli"}`} />
        <div class="lc-msg-text">{message.text}</div>
      </div>
    </div>
  );
}
