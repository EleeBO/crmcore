import { h } from "preact";
import { talkRatioSignal } from "./store";
import type { WaveSegment } from "./types";

function getTextHint(managerPct: number, clientPct: number): { text: string; color: string } {
  if (managerPct === 0 && clientPct === 0) return { text: "Начните разговор", color: "#9ca3af" };
  if (managerPct > 65) return { text: "Дайте клиенту больше говорить", color: "#854F0B" };
  if (managerPct < 35) return { text: "Перехватите инициативу", color: "#854F0B" };
  return { text: "Отличный баланс", color: "#3B6D11" };
}

export function TalkRatioBar(): h.JSX.Element {
  const ratio = talkRatioSignal.value;
  const isEmpty = ratio.managerPercent === 0 && ratio.clientPercent === 0;
  const hint = getTextHint(ratio.managerPercent, ratio.clientPercent);

  return (
    <div class="lc-ratio">
      <div class="lc-ratio-labels">
        <span class="lc-ratio-label">Вы <strong>{ratio.managerPercent}%</strong></span>
        <span class="lc-ratio-label"><strong>{ratio.clientPercent}%</strong> Клиент</span>
      </div>
      <div class="lc-ratio-track">
        <div
          class="lc-ratio-fill"
          style={{
            width: isEmpty ? "50%" : `${ratio.managerPercent}%`,
            background: isEmpty ? "#d1d5db" : undefined,
          }}
        />
      </div>
      {ratio.waveform.length > 0 && (
        <div class="lc-waveform">
          {ratio.waveform.map((seg: WaveSegment, i: number) => (
            <div
              key={i}
              class={`lc-wave-bar lc-wave-${seg.speaker}`}
              style={{ height: `${3 + seg.amplitude * 13}px` }}
            />
          ))}
        </div>
      )}
      <div class="lc-ratio-hint" style={{ color: hint.color }}>{hint.text}</div>
    </div>
  );
}
