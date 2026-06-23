import { h } from "preact";
import { activeTabSignal, briefDataSignal } from "./store";
import { AIHintCard } from "./AIHintCard";
import type { ContextTab } from "./types";
import type { LiveCallCallbacks } from "./mount";
import type { BriefObjection, BriefFocusPoint } from "../brief/types";

const TABS: { id: ContextTab; label: string }[] = [
  { id: "hints", label: "Подсказки" },
  { id: "objections", label: "Возражения" },
  { id: "briefing", label: "Брифинг" },
  { id: "strategy", label: "Стратегия" },
];

interface Props {
  callbacks: LiveCallCallbacks;
}

export function ContextTabs({ callbacks }: Props): h.JSX.Element {
  const active = activeTabSignal.value;

  const handleClick = (tab: ContextTab) => {
    activeTabSignal.value = tab;
    callbacks.onTabChange(tab);
    callbacks.onBriefingTabActive(tab === "briefing");
  };

  return (
    <div class="lc-tabs-container">
      <div class="lc-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            class={`lc-tab ${active === tab.id ? "lc-tab--active" : ""}`}
            onClick={() => handleClick(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {active === "hints" && <AIHintCard />}

      {active === "objections" && (
        <div class="lc-tab-content">
          {(briefDataSignal.value?.objections?.length ?? 0) > 0
            ? briefDataSignal.value!.objections.map((obj: BriefObjection, i: number) => (
                <div key={i} class="lc-objection">
                  <div class="lc-objection-q">{obj.question}</div>
                  <div class="lc-objection-a">{obj.answer}</div>
                </div>
              ))
            : <div class="lc-tab-empty">Нет данных о возражениях</div>
          }
        </div>
      )}

      {active === "strategy" && (
        <div class="lc-tab-content">
          {(briefDataSignal.value?.focusPoints?.length ?? 0) > 0
            ? briefDataSignal.value!.focusPoints.slice(0, 3).map((fp: BriefFocusPoint, i: number) => (
                <div key={i} class="lc-focus-point">
                  <div class="lc-focus-point-title">{fp.headline}</div>
                  {fp.detail && <div class="lc-focus-point-text">{fp.detail}</div>}
                </div>
              ))
            : <div class="lc-tab-empty">Нет данных о стратегии</div>
          }
        </div>
      )}
    </div>
  );
}
