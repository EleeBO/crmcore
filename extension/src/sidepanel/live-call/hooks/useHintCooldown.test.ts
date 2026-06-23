import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { h } from "preact";
import { act, render } from "@testing-library/preact";
import { signal, type Signal } from "@preact/signals";
import type { AIHint } from "../types";
import { useHintCooldown } from "./useHintCooldown";

function makeHint(overrides: Partial<AIHint> = {}): AIHint {
  return {
    id: "h-" + Math.random().toString(36).slice(2, 6),
    hintType: "coaching",
    headline: "Test",
    detail: "",
    coaching: "",
    source: "",
    timestamp: Date.now(),
    ...overrides,
  };
}

// Wrapper component to test the hook
function HookTester({ src }: { src: Signal<AIHint | null> }) {
  const hint = useHintCooldown(src);
  return h("div", { "data-testid": "result" }, hint ? hint.headline : "null");
}

describe("useHintCooldown", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("should show null initially when signal is null", () => {
    const src = signal<AIHint | null>(null);
    const { getByTestId } = render(h(HookTester, { src }));
    expect(getByTestId("result").textContent).toBe("null");
  });

  it("should show first hint immediately when signal is set", async () => {
    const src = signal<AIHint | null>(null);
    const { getByTestId } = render(h(HookTester, { src }));

    const hint = makeHint({ headline: "First hint" });
    await act(() => {
      src.value = hint;
    });

    expect(getByTestId("result").textContent).toBe("First hint");
  });

  it("should block rapid update within cooldown period (< 8s)", async () => {
    const src = signal<AIHint | null>(null);
    const { getByTestId } = render(h(HookTester, { src }));

    const first = makeHint({ headline: "First hint" });
    await act(() => {
      src.value = first;
    });

    // Advance only 3 seconds (less than 8s cooldown)
    await act(() => {
      vi.advanceTimersByTime(3_000);
    });

    const second = makeHint({ headline: "Second hint" });
    await act(() => {
      src.value = second;
    });

    // Still showing first hint because cooldown hasn't expired
    expect(getByTestId("result").textContent).toBe("First hint");
  });

  it("should show new hint after cooldown of 8s expires", async () => {
    const src = signal<AIHint | null>(null);
    const { getByTestId } = render(h(HookTester, { src }));

    const first = makeHint({ headline: "First hint" });
    await act(() => {
      src.value = first;
    });

    // Advance past the full 8s cooldown
    await act(() => {
      vi.advanceTimersByTime(8_000);
    });

    const second = makeHint({ headline: "Second hint" });
    await act(() => {
      src.value = second;
    });

    expect(getByTestId("result").textContent).toBe("Second hint");
  });

  it("should auto-dismiss success hint after 4s and revert to last coaching hint", async () => {
    const src = signal<AIHint | null>(null);
    const { getByTestId } = render(h(HookTester, { src }));

    // Set an initial coaching hint
    const coaching = makeHint({ headline: "Coaching hint", hintType: "coaching" });
    await act(() => {
      src.value = coaching;
    });
    expect(getByTestId("result").textContent).toBe("Coaching hint");

    // Advance past cooldown so we can show the success hint
    await act(() => {
      vi.advanceTimersByTime(8_000);
    });

    // Set success hint
    const success = makeHint({ headline: "Success hint", hintType: "success" });
    await act(() => {
      src.value = success;
    });
    expect(getByTestId("result").textContent).toBe("Success hint");

    // Advance 4s — success hint should auto-dismiss and revert to coaching
    await act(() => {
      vi.advanceTimersByTime(4_000);
    });

    expect(getByTestId("result").textContent).toBe("Coaching hint");
  });
});
