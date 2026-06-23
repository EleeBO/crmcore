import { describe, it, expect, beforeEach } from "vitest";
import { h } from "preact";
import { render } from "@testing-library/preact";
import { hintSignal } from "./store";
import { AIHintCard } from "./AIHintCard";
import type { AIHint } from "./types";

function makeHint(overrides: Partial<AIHint> = {}): AIHint {
  return {
    id: "test-1",
    hintType: "coaching",
    headline: "Test headline",
    detail: "Test detail",
    coaching: "Test coaching",
    source: "test",
    timestamp: Date.now(),
    ...overrides,
  };
}

describe("AIHintCard", () => {
  beforeEach(() => {
    hintSignal.value = null;
  });

  it("should render null state with placeholder text and lc-hint-null class", () => {
    const { container } = render(h(AIHintCard, {}));
    const card = container.querySelector(".lc-hint-null");
    expect(card).toBeTruthy();
    expect(container.textContent).toContain("Слушаю разговор...");
    expect(container.textContent).toContain("Подсказки появятся автоматически");
  });

  it("should render coaching state with ПОДСКАЗКА label, headline, detail, and coaching footnote", () => {
    hintSignal.value = makeHint({
      hintType: "coaching",
      headline: "Coaching headline",
      detail: "Coaching detail",
      coaching: "Coaching footnote",
    });
    const { container } = render(h(AIHintCard, {}));

    const label = container.querySelector(".lc-hint-label");
    expect(label).toBeTruthy();
    expect(label?.textContent).toBe("ПОДСКАЗКА");

    const headline = container.querySelector(".lc-hint-headline");
    expect(headline?.textContent).toBe("Coaching headline");

    const detail = container.querySelector(".lc-hint-detail");
    expect(detail?.textContent).toBe("Coaching detail");

    const coaching = container.querySelector(".lc-hint-coaching");
    expect(coaching).toBeTruthy();
    expect(coaching?.textContent).toBe("Coaching footnote");
  });

  it("should render success state with check icon, headline, detail in success row", () => {
    hintSignal.value = makeHint({
      hintType: "success",
      headline: "Success headline",
      detail: "Success detail",
    });
    const { container } = render(h(AIHintCard, {}));

    const successRow = container.querySelector(".lc-hint-success-row");
    expect(successRow).toBeTruthy();

    const checkIcon = container.querySelector(".lc-hint-check-icon");
    expect(checkIcon).toBeTruthy();

    const headline = container.querySelector(".lc-hint-headline");
    expect(headline?.textContent).toBe("Success headline");

    const detail = container.querySelector(".lc-hint-detail");
    expect(detail?.textContent).toBe("Success detail");
  });

  it("should render warning state with ВНИМАНИЕ label, headline, and detail", () => {
    hintSignal.value = makeHint({
      hintType: "warning",
      headline: "Warning headline",
      detail: "Warning detail",
      coaching: "",
    });
    const { container } = render(h(AIHintCard, {}));

    const label = container.querySelector(".lc-hint-label");
    expect(label).toBeTruthy();
    expect(label?.textContent).toBe("ВНИМАНИЕ");

    const headline = container.querySelector(".lc-hint-headline");
    expect(headline?.textContent).toBe("Warning headline");

    const detail = container.querySelector(".lc-hint-detail");
    expect(detail?.textContent).toBe("Warning detail");
  });

  it("should not render coaching element when coaching field is empty string", () => {
    hintSignal.value = makeHint({
      hintType: "coaching",
      headline: "Coaching headline",
      detail: "Coaching detail",
      coaching: "",
    });
    const { container } = render(h(AIHintCard, {}));

    const coaching = container.querySelector(".lc-hint-coaching");
    expect(coaching).toBeNull();
  });

  it("should not render detail element when detail field is empty string for success state", () => {
    hintSignal.value = makeHint({
      hintType: "success",
      headline: "Success headline",
      detail: "",
    });
    const { container } = render(h(AIHintCard, {}));

    const successRow = container.querySelector(".lc-hint-success-row");
    expect(successRow).toBeTruthy();

    const detail = container.querySelector(".lc-hint-detail");
    expect(detail).toBeNull();

    const headline = container.querySelector(".lc-hint-headline");
    expect(headline?.textContent).toBe("Success headline");
  });
});
