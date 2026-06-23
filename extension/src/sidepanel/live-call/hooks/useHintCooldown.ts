import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import type { Signal } from "@preact/signals";
import type { AIHint } from "../types";

const COOLDOWN_MS = 8_000;
const SUCCESS_DISMISS_MS = 4_000;

export function useHintCooldown(rawHint: Signal<AIHint | null>): AIHint | null {
  const displayed = useSignal<AIHint | null>(null);
  const lastSwapAt = useSignal<number>(0);
  const lastCoachingHint = useSignal<AIHint | null>(null);

  // Subscribe to rawHint changes (runs ONLY when rawHint changes, not on every render)
  useEffect(() => {
    let cooldownTimer: ReturnType<typeof setTimeout> | undefined;

    const unsubscribe = rawHint.subscribe((hint: AIHint | null) => {
      if (!hint) {
        displayed.value = null;
        return;
      }

      // Track last coaching hint for success-dismiss revert
      if (hint.hintType === "coaching") {
        lastCoachingHint.value = hint;
      }

      const now = Date.now();
      const elapsed = now - lastSwapAt.value;

      if (elapsed >= COOLDOWN_MS || displayed.value === null) {
        displayed.value = hint;
        lastSwapAt.value = now;
        if (cooldownTimer) clearTimeout(cooldownTimer);
      } else {
        // Queue: show after remaining cooldown
        if (cooldownTimer) clearTimeout(cooldownTimer);
        const remaining = COOLDOWN_MS - elapsed;
        cooldownTimer = setTimeout(() => {
          displayed.value = hint;
          lastSwapAt.value = Date.now();
        }, remaining);
      }
    });

    return () => {
      unsubscribe();
      if (cooldownTimer) clearTimeout(cooldownTimer);
    };
  }, []); // empty deps: subscribe once

  // Auto-dismiss success after 4s → revert to last coaching hint
  useEffect(() => {
    const hint = displayed.value;
    if (hint?.hintType !== "success") return;

    const timer = setTimeout(() => {
      displayed.value = lastCoachingHint.value; // revert to last coaching, not null
    }, SUCCESS_DISMISS_MS);

    return () => clearTimeout(timer);
  }, [displayed.value]); // re-run only when displayed hint changes

  return displayed.value;
}
