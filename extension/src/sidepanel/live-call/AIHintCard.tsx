import { h } from "preact";
import { hintSignal } from "./store";
import { useHintCooldown } from "./hooks/useHintCooldown";
import type { HintType } from "./types";

const TYPE_CONFIG: Record<HintType, { bg: string; border: string; label: string; labelColor: string; headlineColor: string; detailColor: string }> = {
  coaching: { bg: "#FFF8F0", border: "#EF9F27", label: "ПОДСКАЗКА", labelColor: "#854F0B", headlineColor: "#633806", detailColor: "#854F0B" },
  success:  { bg: "#EAF3DE", border: "#639922", label: "",          labelColor: "",        headlineColor: "#27500A", detailColor: "#3B6D11" },
  warning:  { bg: "#FEF5F5", border: "#E24B4A", label: "ВНИМАНИЕ",  labelColor: "#791F1F", headlineColor: "#501313", detailColor: "#791F1F" },
};

function renderCheckIcon(): h.JSX.Element {
  return (
    <div class="lc-hint-check-icon">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M3 7L6 10L11 4" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
  );
}

export function AIHintCard(): h.JSX.Element {
  const hint = useHintCooldown(hintSignal);

  if (!hint) {
    return (
      <div class="lc-hint-card lc-hint-null">
        <div class="lc-hint-null-text">Слушаю разговор...</div>
        <div class="lc-hint-null-sub">Подсказки появятся автоматически</div>
      </div>
    );
  }

  const cfg = TYPE_CONFIG[hint.hintType];

  return (
    <div
      class="lc-hint-card"
      style={{ background: cfg.bg, borderLeft: `3px solid ${cfg.border}` }}
    >
      {hint.hintType === "success" ? (
        <div class="lc-hint-success-row">
          {renderCheckIcon()}
          <div>
            <div class="lc-hint-headline" style={{ color: cfg.headlineColor }}>{hint.headline}</div>
            {hint.detail && <div class="lc-hint-detail" style={{ color: cfg.detailColor }}>{hint.detail}</div>}
          </div>
        </div>
      ) : (
        <>
          {cfg.label && (
            <div class="lc-hint-label" style={{ color: cfg.labelColor }}>{cfg.label}</div>
          )}
          <div class="lc-hint-headline" style={{ color: cfg.headlineColor }}>{hint.headline}</div>
          {hint.detail && <div class="lc-hint-detail" style={{ color: cfg.detailColor }}>{hint.detail}</div>}
          {hint.coaching && (
            <div class="lc-hint-coaching">{hint.coaching}</div>
          )}
        </>
      )}
    </div>
  );
}
