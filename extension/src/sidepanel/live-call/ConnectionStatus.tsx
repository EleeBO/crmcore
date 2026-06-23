import { h } from "preact";
import { wsConnectedSignal, sttActiveSignal } from "./store";

export function ConnectionStatus(): h.JSX.Element {
  const ws = wsConnectedSignal.value;
  const stt = sttActiveSignal.value;

  return (
    <div class="lc-conn">
      <span class={`lc-conn-dot ${ws ? "lc-conn-dot--on" : "lc-conn-dot--off"}`} />
      <span class={ws ? "" : "lc-conn-label--off"}>WS</span>
      <span class={`lc-conn-dot ${stt ? "lc-conn-dot--on" : "lc-conn-dot--off"}`} />
      <span class={stt ? "" : "lc-conn-label--off"}>STT</span>
    </div>
  );
}
